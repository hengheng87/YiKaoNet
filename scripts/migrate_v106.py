"""Lossless migration script from monolithic 易考網1.0.6.html into modular exam/unit JSON + JPEG assets."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_HTML = BASE_DIR / "易考網1.0.6.html"
EXAM_SLUG = "cmu-int2-msk"
EXAM_DIR = BASE_DIR / "data" / "exams" / EXAM_SLUG
UNITS_DIR = EXAM_DIR / "units"
IMAGES_DIR = EXAM_DIR / "images"

UNIT_SHORT_LABELS: dict[str, dict] = {
    "1014_Physio1": {"shortLabel": "10/14 肌生理I"},
    "1016_Physio2": {"shortLabel": "10/16 肌生理II"},
    "1023_ANS": {"shortLabel": "10/23 生理ANS"},
    "1028_Synapse": {"shortLabel": "10/28 突觸傳遞"},
    "1007_Neo1": {"shortLabel": "10/07 腫瘤I"},
    "1014_Neo2": {"shortLabel": "10/14 腫瘤II"},
    "1015_Neo3": {"shortLabel": "10/15 腫瘤III"},
    "Robbins_Ch7_Neo": {
        "shortLabel": "📘 大R題庫：Ch.7 腫瘤學",
        "highlight": True,
        "exemptFromCrossDupFilter": True,
    },
    "1021_BonePath": {"shortLabel": "10/21 骨關節病理"},
    "Patho_SoftTissue": {
        "shortLabel": "補充：軟組織腫瘤病理",
        "isOutOfScope": True,
    },
    "0930_BoneHisto": {"shortLabel": "09/30 軟骨與骨"},
    "1007_MuscleHisto": {"shortLabel": "10/07 肌肉組織"},
    "1022_Pharm1": {"shortLabel": "10/22 藥理ANS"},
    "1029_Pharm2": {"shortLabel": "10/29 擬膽鹼藥"},
    "1030_Pharm3": {"shortLabel": "10/30 抗膽鹼肌鬆"},
    "1104_Pharm4": {"shortLabel": "11/04 腎上腺素藥"},
    "1104_SurgDigi": {"shortLabel": "11/04 數位骨科"},
    "1106_SurgRad": {"shortLabel": "11/06 骨科放射"},
    "1106_SurgTrauma": {"shortLabel": "11/06 骨科創傷"},
    "Surg_BoneTumor": {
        "shortLabel": "補充：骨腫瘤外科",
        "isOutOfScope": True,
    },
    "1104_ClinRad": {"shortLabel": "11/04 臨診影像"},
    "1118_ClinEval": {"shortLabel": "11/18 臨診理學"},
}

UNIT_DEFAULT_FIELDS = [
    "unitTitle",
    "session",
    "subject",
    "subjectTitle",
    "prof",
    "examRange",
    "unitUrl",
]


def extract_questions_from_html(html_path: Path) -> list[dict]:
    raw = html_path.read_text(encoding="utf-8")
    match = re.search(
        r"const QUESTIONS\s*=\s*(\[.*?\]);\s*\n\s*// Application State",
        raw,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Could not locate QUESTIONS array in {html_path}")
    return json.loads(match.group(1))


def build_exam_manifest(unit_order: list[str]) -> dict:
    units = []
    for unit_code in unit_order:
        meta = UNIT_SHORT_LABELS.get(unit_code, {"shortLabel": unit_code})
        units.append(
            {
                "unitCode": unit_code,
                "shortLabel": meta["shortLabel"],
                "file": f"units/{unit_code}.json",
                "highlight": bool(meta.get("highlight", False)),
                "isOutOfScope": bool(meta.get("isOutOfScope", False)),
                "exemptFromCrossDupFilter": bool(
                    meta.get("exemptFromCrossDupFilter", False)
                ),
            }
        )

    return {
        "slug": EXAM_SLUG,
        "version": "2.0.0",
        "badge": "CMU Musculoskeletal System",
        "title": "三上第二次整合考：骨骼肌肉系統全收錄互動題庫",
        "subtitle": (
            "整合「大三整合2 知識庫」18 份 M67×CM59 共筆考古題、M65 試題合輯與歷屆申覆勘誤解析"
            "（第一節 A 卷 80 題配分 ｜ 第二節 B 卷 76 題配分）"
        ),
        "source": {
            "name": "大三整合2 知識庫",
            "url": "https://notebook.google.com/notebook/01b3322a-9c0a-498f-91ce-4c29f24657f5",
            "notebookId": "01b3322a-9c0a-498f-91ce-4c29f24657f5",
        },
        "sessions": [
            {
                "code": "A",
                "label": "第一節 A 卷",
                "emoji": "📘",
                "description": "生理＋病理＋組織",
            },
            {
                "code": "B",
                "label": "第二節 B 卷",
                "emoji": "📗",
                "description": "藥理＋外科＋臨診",
            },
        ],
        "subjects": [
            {
                "code": "Physio",
                "label": "生理學",
                "emoji": "⚡",
                "session": "A",
                "profs": "林靜茹 教授",
            },
            {
                "code": "Patho",
                "label": "病理學",
                "emoji": "🔬",
                "session": "A",
                "profs": "王約翰、張凱博 教授",
            },
            {
                "code": "Histo",
                "label": "組織學",
                "emoji": "🧬",
                "session": "A",
                "profs": "吳政訓、林成翰 教授",
            },
            {
                "code": "Pharm",
                "label": "藥理學",
                "emoji": "💊",
                "session": "B",
                "profs": "賴弘岳 教授",
            },
            {
                "code": "Surg",
                "label": "外科學概論",
                "emoji": "🦴",
                "session": "B",
                "profs": "蔡俊灝、洪誌鴻、邱詠証",
            },
            {
                "code": "ClinDiag",
                "label": "臨床診斷學",
                "emoji": "🩺",
                "session": "B",
                "profs": "陳潓誼、郭書瑞",
            },
        ],
        "yearGroups": [
            {"code": "114", "label": "114 學年度 (M66)"},
            {"code": "113", "label": "113 學年度 (M65)"},
            {"code": "112", "label": "112 學年度 (M64)"},
            {"code": "111/110", "label": "111 / 110 學年度"},
            {"code": "Robbins", "label": "📘 大R題庫 Ch.7 擴充原題"},
        ],
        "units": units,
    }


def extract_image(raw_image: str | None, qid: str, seen_hashes: dict[str, str]) -> str | None:
    if not raw_image:
        return None
    if not raw_image.startswith("data:image/"):
        raise ValueError(f"Unexpected image format for {qid}: {raw_image[:40]}")

    header, b64_payload = raw_image.split(",", 1)
    ext = "jpg" if "jpeg" in header or "jpg" in header else "png"
    img_bytes = base64.b64decode(b64_payload)
    if ext == "jpg" and not img_bytes.startswith(b"\xff\xd8\xff"):
        raise ValueError(f"Invalid JPEG magic bytes for {qid}")

    digest = hashlib.sha256(img_bytes).hexdigest()
    if digest in seen_hashes:
        return seen_hashes[digest]

    rel_path = f"images/{qid}.{ext}"
    out_file = EXAM_DIR / rel_path
    out_file.write_bytes(img_bytes)
    seen_hashes[digest] = rel_path
    return rel_path


def migrate() -> None:
    questions = extract_questions_from_html(SOURCE_HTML)
    UNITS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict]] = defaultdict(list)
    unit_order: list[str] = []
    for q in sorted(questions, key=lambda item: item["globalIndex"]):
        uc = q["unitCode"]
        if uc not in grouped:
            unit_order.append(uc)
        grouped[uc].append(q)

    seen_hashes: dict[str, str] = {}

    for unit_code in unit_order:
        items = grouped[unit_code]
        defaults: dict[str, str] = {"unitCode": unit_code}
        for field in UNIT_DEFAULT_FIELDS:
            most_common = Counter(item[field] for item in items).most_common(1)[0][0]
            defaults[field] = most_common

        unit_questions = []
        for item in items:
            rel_img = extract_image(item.get("image"), item["id"], seen_hashes)
            q_obj: dict = {
                "id": item["id"],
                "globalIndex": item["globalIndex"],
                "qNum": item["qNum"],
                "origQ": item["origQ"],
                "year": item["year"],
                "yearGroup": item["yearGroup"],
                "hasErrata": bool(item["hasErrata"]),
                "isCrossDup": bool(item["isCrossDup"]),
                "stem": item["stem"],
                "image": rel_img,
                "options": item["options"],
                "answer": item["answer"],
                "acceptedAnswers": item["acceptedAnswers"],
                "answerDisplay": item["answerDisplay"],
                "explanations": item["explanations"],
            }
            for field in UNIT_DEFAULT_FIELDS:
                if item[field] != defaults[field]:
                    q_obj[field] = item[field]
            unit_questions.append(q_obj)

        unit_payload = {**defaults, "questions": unit_questions}
        unit_file = UNITS_DIR / f"{unit_code}.json"
        unit_file.write_text(
            json.dumps(unit_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    exam_manifest = build_exam_manifest(unit_order)
    (EXAM_DIR / "exam.json").write_text(
        json.dumps(exam_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    verify_round_trip(questions, exam_manifest)
    print(
        f"Migrated {len(questions)} questions across {len(unit_order)} units "
        f"and {len(seen_hashes)} deduplicated JPEG images into {EXAM_DIR}"
    )


def verify_round_trip(source_questions: list[dict], exam_manifest: dict) -> None:
    reconstructed: list[dict] = []
    for unit_meta in exam_manifest["units"]:
        unit_path = EXAM_DIR / unit_meta["file"]
        unit_data = json.loads(unit_path.read_text(encoding="utf-8"))
        for q in unit_data["questions"]:
            merged = {
                "id": q["id"],
                "globalIndex": q["globalIndex"],
                "unitCode": unit_data["unitCode"],
                "unitTitle": q.get("unitTitle", unit_data["unitTitle"]),
                "session": q.get("session", unit_data["session"]),
                "subject": q.get("subject", unit_data["subject"]),
                "subjectTitle": q.get("subjectTitle", unit_data["subjectTitle"]),
                "prof": q.get("prof", unit_data["prof"]),
                "examRange": q.get("examRange", unit_data["examRange"]),
                "unitUrl": q.get("unitUrl", unit_data["unitUrl"]),
                "qNum": q["qNum"],
                "origQ": q["origQ"],
                "year": q["year"],
                "yearGroup": q["yearGroup"],
                "hasErrata": q["hasErrata"],
                "stem": q["stem"],
                "image": q["image"],
                "options": q["options"],
                "answer": q["answer"],
                "acceptedAnswers": q["acceptedAnswers"],
                "answerDisplay": q["answerDisplay"],
                "explanations": q["explanations"],
                "isCrossDup": q["isCrossDup"],
            }
            reconstructed.append(merged)

    assert len(reconstructed) == len(source_questions), "Question count mismatch"
    src_by_id = {q["id"]: q for q in source_questions}
    compare_fields = [
        "id",
        "globalIndex",
        "unitCode",
        "unitTitle",
        "session",
        "subject",
        "subjectTitle",
        "prof",
        "examRange",
        "unitUrl",
        "qNum",
        "origQ",
        "year",
        "yearGroup",
        "hasErrata",
        "stem",
        "options",
        "answer",
        "acceptedAnswers",
        "answerDisplay",
        "explanations",
        "isCrossDup",
    ]
    for rec in reconstructed:
        src = src_by_id[rec["id"]]
        for f in compare_fields:
            assert rec[f] == src[f], f"Field mismatch on {rec['id']}.{f}"
        if src.get("image"):
            img_path = EXAM_DIR / rec["image"]
            assert img_path.is_file(), f"Missing image {img_path}"
            raw_b64 = src["image"].split(",", 1)[1]
            assert img_path.read_bytes() == base64.b64decode(raw_b64), (
                f"Image byte mismatch on {rec['id']}"
            )
        else:
            assert rec["image"] is None


if __name__ == "__main__":
    migrate()
