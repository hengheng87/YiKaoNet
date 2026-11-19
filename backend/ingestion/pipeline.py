"""Exam scaffolding, staging draft bundles, and validated atomic JSON/SQLite commits."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from backend.database import get_connection, init_db
from backend.ingestion.extractors import import_image_asset
from backend.ingestion.parser import find_cross_unit_duplicates, normalize_stem
from backend.sync_data import sync_single_exam
from scripts.validate_data import validate_exam_dir

SLUG_RE = re.compile(r"^[a-z0-9-]+$")

DEFAULT_SESSIONS = [
    {"code": "A", "label": "第一節 A 卷", "emoji": "📘", "description": "基礎整合科目"},
    {"code": "B", "label": "第二節 B 卷", "emoji": "📗", "description": "進階整合科目"},
]
DEFAULT_SUBJECTS = [
    {"code": "General", "label": "綜合學科", "emoji": "📚", "session": "A", "profs": ""},
]
DEFAULT_YEAR_GROUPS = [
    {"code": "114", "label": "114 學年度 (M66)"},
    {"code": "113", "label": "113 學年度 (M65)"},
    {"code": "112", "label": "112 學年度 (M64)"},
    {"code": "111/110", "label": "111 / 110 學年度"},
]


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def init_exam(
    exams_dir: Path,
    *,
    slug: str,
    title: str,
    badge: str = "",
    subtitle: str = "",
    source_name: str = "",
    source_url: str = "",
    notebook_id: str | None = None,
    sessions: list[dict] | None = None,
    subjects: list[dict] | None = None,
    year_groups: list[dict] | None = None,
) -> Path:
    clean_slug = slug.strip()
    if not SLUG_RE.fullmatch(clean_slug):
        raise ValueError(f"考科 slug 僅允許小寫英數字與連字號 (-)：{slug}")

    exam_dir = exams_dir / clean_slug
    manifest_path = exam_dir / "exam.json"
    if manifest_path.exists():
        raise FileExistsError(f"考科已存在：{manifest_path}")

    (exam_dir / "units").mkdir(parents=True, exist_ok=True)
    (exam_dir / "images").mkdir(parents=True, exist_ok=True)

    source_obj: dict = {
        "name": source_name.strip() or title.strip(),
        "url": source_url.strip() or "https://notebook.google.com/",
    }
    if notebook_id and notebook_id.strip():
        source_obj["notebookId"] = notebook_id.strip()

    manifest = {
        "slug": clean_slug,
        "version": "2.0.0",
        "badge": badge.strip() or clean_slug.upper(),
        "title": title.strip(),
        "subtitle": subtitle.strip() or f"{title.strip()} 互動考古題庫",
        "source": source_obj,
        "sessions": sessions or DEFAULT_SESSIONS,
        "subjects": subjects or DEFAULT_SUBJECTS,
        "yearGroups": year_groups or DEFAULT_YEAR_GROUPS,
        "units": [],
    }
    _atomic_write_json(manifest_path, manifest)
    return exam_dir


def prepare_staging_bundle(
    exams_dir: Path,
    staging_dir: Path,
    *,
    exam_slug: str,
    unit_code: str,
    source_name: str,
    raw_text: str,
    parsed_questions: list[dict],
    extracted_images: list[dict] | None = None,
    out_path: Path | None = None,
) -> dict:
    manifest_path = exams_dir / exam_slug / "exam.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"找不到考科設定檔：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    year_codes = [y["code"] for y in manifest.get("yearGroups", [])]

    ai_prompt = (
        f"請將來源「{source_name}」的共筆／考題內容整理為 JSON 陣列（置於 ```json ... ``` 區塊），"
        f"準備匯入考科 {exam_slug} 的單元 {unit_code}。\n"
        f"每題物件需包含欄位：year、yearGroup (僅限 {year_codes})、stem、options (如 {{\"A\":\"...\"}})、"
        "answer、acceptedAnswers、answerDisplay、hasErrata、explanations (詳解字串陣列)。"
    )

    target_json = out_path or (staging_dir / f"{exam_slug}_{unit_code}_draft.json")
    target_json.parent.mkdir(parents=True, exist_ok=True)

    raw_text_sidecar: str | None = None
    if len(raw_text) > 4000:
        sidecar_path = target_json.with_suffix(".raw.txt")
        sidecar_path.write_text(raw_text, encoding="utf-8")
        raw_text_sidecar = str(sidecar_path)

    bundle = {
        "examSlug": exam_slug,
        "unitCode": unit_code,
        "sourceName": source_name,
        "aiPrompt": ai_prompt,
        "extractedImages": extracted_images or [],
        "rawTextSidecar": raw_text_sidecar,
        "rawTextPreview": raw_text[:2000],
        "parsedCount": len(parsed_questions),
        "questions": parsed_questions,
    }
    _atomic_write_json(target_json, bundle)
    return {"stagingFile": str(target_json), **bundle}


def _normalize_question(
    raw_q: dict,
    *,
    exam_dir: Path,
    unit_code: str,
    next_q_num: int,
    next_global_idx: int,
    valid_year_groups: set[str],
    existing_ids: set[str],
    unit_prof: str,
    dry_run: bool,
) -> tuple[dict, bool, bool]:
    stem = str(raw_q.get("stem", "")).strip()
    if not stem:
        raise ValueError("題目缺少非空 'stem' 欄位")

    raw_opts = raw_q.get("options")
    if not isinstance(raw_opts, dict) or len(raw_opts) < 2:
        raise ValueError(f"題目 '{stem[:20]}' 選項數量不足 2 個")
    options = {
        str(k).strip().upper(): str(v).strip()
        for k, v in raw_opts.items()
        if str(k).strip() and str(v).strip()
    }
    if len(options) < 2:
        raise ValueError(f"題目 '{stem[:20]}' 有效非空選項不足 2 個")

    answer = str(raw_q.get("answer", "")).strip().upper()
    if answer not in options:
        raise ValueError(f"題目 '{stem[:20]}' 的 answer '{answer}' 不在選項中")

    raw_accepted = raw_q.get("acceptedAnswers")
    if isinstance(raw_accepted, list) and raw_accepted:
        accepted = []
        for a in raw_accepted:
            code = str(a).strip().upper()
            if code not in options:
                raise ValueError(f"題目 '{stem[:20]}' 的 acceptedAnswers '{code}' 不在選項中")
            if code not in accepted:
                accepted.append(code)
    else:
        accepted = [answer]

    raw_expl = raw_q.get("explanations")
    if not isinstance(raw_expl, list) or not [
        str(e).strip() for e in raw_expl if str(e).strip()
    ]:
        raise ValueError(f"題目 '{stem[:20]}' 缺少非空 'explanations' 陣列")
    explanations = [str(e).strip() for e in raw_expl if str(e).strip()]

    year_group = str(raw_q.get("yearGroup", "")).strip()
    if year_group not in valid_year_groups:
        raise ValueError(
            f"題目 '{stem[:20]}' 的 yearGroup '{year_group}' 不在 {sorted(valid_year_groups)} 中"
        )
    year = str(raw_q.get("year", "")).strip() or f"{year_group} 學年度"

    q_num = int(raw_q["qNum"]) if raw_q.get("qNum") else next_q_num
    orig_q = str(raw_q.get("origQ", "")).strip() or f"Q{q_num}"

    explicit_id = str(raw_q.get("id", "")).strip()
    if explicit_id:
        qid = explicit_id
        had_explicit_id = True
    else:
        qid = f"{unit_code}-{q_num}"
        suffix = 2
        while qid in existing_ids:
            qid = f"{unit_code}-{q_num}_{suffix}"
            suffix += 1
        had_explicit_id = False

    has_errata = (
        bool(raw_q["hasErrata"]) if "hasErrata" in raw_q else len(accepted) > 1
    )
    answer_display = str(raw_q.get("answerDisplay", "")).strip() or f"({answer})"

    raw_img = raw_q.get("image")
    resolved_img: str | None = None
    imported_img = False
    if raw_img and str(raw_img).strip():
        resolved_img = import_image_asset(
            exam_dir, str(raw_img).strip(), dry_run=dry_run
        )
        imported_img = not str(raw_img).strip().startswith("images/")

    normalized = {
        "id": qid,
        "globalIndex": int(raw_q["globalIndex"])
        if raw_q.get("globalIndex")
        else next_global_idx,
        "qNum": q_num,
        "origQ": orig_q,
        "year": year,
        "yearGroup": year_group,
        "hasErrata": has_errata,
        "isCrossDup": bool(raw_q.get("isCrossDup", False)),
        "stem": stem,
        "image": resolved_img,
        "options": options,
        "answer": answer,
        "acceptedAnswers": accepted,
        "answerDisplay": answer_display,
        "explanations": explanations,
    }
    if raw_q.get("prof") and str(raw_q["prof"]).strip() != unit_prof:
        normalized["prof"] = str(raw_q["prof"]).strip()

    return normalized, had_explicit_id, imported_img


def commit_questions_import(
    exams_dir: Path,
    db_path: Path,
    exam_slug: str,
    raw_questions: list[dict],
    *,
    unit_code: str | None = None,
    unit_meta: dict | None = None,
    dry_run: bool = False,
    update_existing: bool = False,
    auto_mark_cross_dup: bool = False,
    sync_db: bool = True,
) -> dict:
    exam_dir = (exams_dir / exam_slug).resolve()
    manifest_path = exam_dir / "exam.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"找不到考科設定檔：{manifest_path}")

    exam_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_unit_code = (unit_code or (unit_meta or {}).get("unitCode") or "").strip()
    if not target_unit_code:
        raise ValueError("必須透過 --unit 或 JSON 內的 unit.unitCode 指定目標單元代碼")

    valid_sessions = {s["code"] for s in exam_manifest.get("sessions", [])}
    valid_subjects = {s["code"] for s in exam_manifest.get("subjects", [])}
    valid_year_groups = {y["code"] for y in exam_manifest.get("yearGroups", [])}

    existing_ids: set[str] = set()
    max_global_idx = 0
    for u_entry in exam_manifest.get("units", []):
        u_path = (exam_dir / u_entry["file"]).resolve()
        if u_path.is_file():
            u_json = json.loads(u_path.read_text(encoding="utf-8"))
            for q in u_json.get("questions", []):
                existing_ids.add(q["id"])
                max_global_idx = max(max_global_idx, int(q["globalIndex"]))

    unit_entry = next(
        (u for u in exam_manifest.get("units", []) if u["unitCode"] == target_unit_code),
        None,
    )
    is_new_unit = unit_entry is None

    if is_new_unit:
        if not unit_meta:
            raise ValueError(
                f"單元 '{target_unit_code}' 尚未存在，請提供新單元 metadata（unitTitle, session, subject, subjectTitle, prof, examRange, unitUrl）"
            )
        required_unit_fields = (
            "unitTitle",
            "session",
            "subject",
            "subjectTitle",
            "prof",
            "examRange",
            "unitUrl",
        )
        missing_meta = [
            f for f in required_unit_fields if not str(unit_meta.get(f, "")).strip()
        ]
        if missing_meta:
            raise ValueError(f"建立新單元 '{target_unit_code}' 缺少欄位：{missing_meta}")
        if unit_meta["session"] not in valid_sessions:
            raise ValueError(f"無效 session: {unit_meta['session']}")
        if unit_meta["subject"] not in valid_subjects:
            raise ValueError(f"無效 subject: {unit_meta['subject']}")

        unit_rel_file = f"units/{target_unit_code}.json"
        unit_path = exam_dir / unit_rel_file
        unit_data = {
            "unitCode": target_unit_code,
            "unitTitle": unit_meta["unitTitle"].strip(),
            "session": unit_meta["session"].strip(),
            "subject": unit_meta["subject"].strip(),
            "subjectTitle": unit_meta["subjectTitle"].strip(),
            "prof": unit_meta["prof"].strip(),
            "examRange": unit_meta["examRange"].strip(),
            "unitUrl": unit_meta["unitUrl"].strip(),
            "questions": [],
        }
        exam_manifest["units"].append(
            {
                "unitCode": target_unit_code,
                "shortLabel": str(
                    unit_meta.get("shortLabel") or unit_data["unitTitle"]
                ).strip(),
                "file": unit_rel_file,
                "highlight": bool(unit_meta.get("highlight", False)),
                "isOutOfScope": bool(unit_meta.get("isOutOfScope", False)),
                "exemptFromCrossDupFilter": bool(
                    unit_meta.get("exemptFromCrossDupFilter", False)
                ),
            }
        )
    else:
        unit_path = (exam_dir / unit_entry["file"]).resolve()
        unit_data = json.loads(unit_path.read_text(encoding="utf-8"))

    cross_dup_hits: dict[int, dict] = {}
    if auto_mark_cross_dup and raw_questions:
        cross_dup_hits = find_cross_unit_duplicates(
            exam_dir, raw_questions, target_unit_code
        )

    unit_questions: list[dict] = list(unit_data.get("questions", []))
    unit_by_id = {q["id"]: idx for idx, q in enumerate(unit_questions)}
    unit_stems = {normalize_stem(q["stem"]) for q in unit_questions}
    next_q_num = max((int(q["qNum"]) for q in unit_questions), default=0) + 1
    next_global_idx = max_global_idx + 1

    added = 0
    updated = 0
    skipped = 0
    cross_dup_marked = 0
    images_imported = 0

    for idx, raw_q in enumerate(raw_questions):
        candidate, had_explicit_id, imported_img = _normalize_question(
            raw_q,
            exam_dir=exam_dir,
            unit_code=target_unit_code,
            next_q_num=next_q_num,
            next_global_idx=next_global_idx,
            valid_year_groups=valid_year_groups,
            existing_ids=existing_ids,
            unit_prof=unit_data["prof"],
            dry_run=dry_run,
        )
        if imported_img:
            images_imported += 1
        if idx in cross_dup_hits and not candidate["isCrossDup"]:
            candidate["isCrossDup"] = True
            cross_dup_marked += 1

        if had_explicit_id and candidate["id"] in unit_by_id:
            if update_existing:
                pos = unit_by_id[candidate["id"]]
                existing_q = unit_questions[pos]
                candidate["globalIndex"] = existing_q["globalIndex"]
                unit_questions[pos] = candidate
                unit_stems.add(normalize_stem(candidate["stem"]))
                updated += 1
            else:
                skipped += 1
            continue

        norm_stem = normalize_stem(candidate["stem"])
        if candidate["id"] in existing_ids or norm_stem in unit_stems:
            skipped += 1
            continue

        unit_questions.append(candidate)
        unit_by_id[candidate["id"]] = len(unit_questions) - 1
        unit_stems.add(norm_stem)
        existing_ids.add(candidate["id"])
        next_q_num = max(next_q_num, candidate["qNum"] + 1)
        next_global_idx = max(next_global_idx, candidate["globalIndex"] + 1)
        added += 1

    if not unit_questions:
        raise ValueError("匯入後目標單元沒有任何題目")

    unit_data["questions"] = unit_questions

    if not dry_run:
        _atomic_write_json(unit_path, unit_data)
        if is_new_unit:
            _atomic_write_json(manifest_path, exam_manifest)
        errors, _ = validate_exam_dir(exam_dir)
        if errors:
            raise RuntimeError("匯入後資料驗證失敗：\n" + "\n".join(errors))
        if sync_db:
            conn = get_connection(db_path)
            try:
                init_db(conn)
                sync_single_exam(conn, exam_dir, force=True)
            finally:
                conn.close()

    return {
        "examSlug": exam_slug,
        "unitCode": target_unit_code,
        "newUnit": is_new_unit,
        "dryRun": dry_run,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "crossDupMarked": cross_dup_marked,
        "imagesImported": images_imported,
        "unitTotal": len(unit_questions),
    }
