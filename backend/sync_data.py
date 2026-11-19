"""Sync modular exam and unit JSON files into SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from backend.config import EXAMS_DIR


def compute_exam_hash(exam_dir: Path, exam_manifest: dict) -> str:
    hasher = hashlib.sha256()
    manifest_path = exam_dir / "exam.json"
    hasher.update(manifest_path.read_bytes())
    for unit_meta in exam_manifest.get("units", []):
        unit_file = (exam_dir / unit_meta["file"]).resolve()
        if unit_file.is_file():
            hasher.update(unit_meta["file"].encode("utf-8"))
            hasher.update(unit_file.read_bytes())
    return hasher.hexdigest()


def build_search_text(
    stem: str,
    options: dict[str, str],
    unit_title: str,
    prof: str,
    year: str,
    explanations: list[str],
) -> str:
    parts = [
        stem,
        *options.values(),
        unit_title,
        prof,
        year,
        *explanations,
    ]
    return " ".join(p for p in parts if p).lower()


def sync_single_exam(
    conn: sqlite3.Connection,
    exam_dir: Path,
    force: bool = False,
) -> tuple[bool, int, int]:
    manifest_path = exam_dir / "exam.json"
    if not manifest_path.is_file():
        return False, 0, 0

    exam = json.loads(manifest_path.read_text(encoding="utf-8"))
    slug = exam["slug"]
    content_hash = compute_exam_hash(exam_dir, exam)

    if not force:
        row = conn.execute(
            "SELECT content_hash FROM exams WHERE slug = ?", (slug,)
        ).fetchone()
        if row and row["content_hash"] == content_hash:
            counts = conn.execute(
                "SELECT COUNT(*) AS q_cnt FROM questions WHERE exam_slug = ?",
                (slug,),
            ).fetchone()
            return False, len(exam["units"]), int(counts["q_cnt"])

    now_ms = int(time.time() * 1000)
    unit_rows: list[tuple] = []
    question_rows: list[tuple] = []

    for sort_idx, unit_meta in enumerate(exam["units"]):
        unit_path = (exam_dir / unit_meta["file"]).resolve()
        if not unit_path.is_relative_to(exam_dir.resolve()):
            raise ValueError(f"Unsafe unit file path: {unit_meta['file']}")
        unit = json.loads(unit_path.read_text(encoding="utf-8"))

        unit_code = unit["unitCode"]
        unit_rows.append(
            (
                slug,
                unit_code,
                unit["unitTitle"],
                unit_meta.get("shortLabel", unit["unitTitle"]),
                unit["session"],
                unit["subject"],
                unit["subjectTitle"],
                unit["prof"],
                unit["examRange"],
                unit["unitUrl"],
                int(bool(unit_meta.get("highlight", False))),
                int(bool(unit_meta.get("isOutOfScope", False))),
                int(bool(unit_meta.get("exemptFromCrossDupFilter", False))),
                sort_idx,
            )
        )

        for q in unit["questions"]:
            eff_unit_title = q.get("unitTitle", unit["unitTitle"])
            eff_session = q.get("session", unit["session"])
            eff_subject = q.get("subject", unit["subject"])
            eff_subject_title = q.get("subjectTitle", unit["subjectTitle"])
            eff_prof = q.get("prof", unit["prof"])
            eff_exam_range = q.get("examRange", unit["examRange"])
            eff_unit_url = q.get("unitUrl", unit["unitUrl"])
            options = q["options"]
            explanations = q["explanations"]

            search_text = build_search_text(
                q["stem"],
                options,
                eff_unit_title,
                eff_prof,
                q["year"],
                explanations,
            )

            question_rows.append(
                (
                    slug,
                    q["id"],
                    int(q["globalIndex"]),
                    unit_code,
                    eff_unit_title,
                    eff_session,
                    eff_subject,
                    eff_subject_title,
                    eff_prof,
                    eff_exam_range,
                    eff_unit_url,
                    int(q["qNum"]),
                    q["origQ"],
                    q["year"],
                    q["yearGroup"],
                    int(bool(q["hasErrata"])),
                    int(bool(q["isCrossDup"])),
                    q["stem"],
                    q.get("image"),
                    json.dumps(options, ensure_ascii=False),
                    q["answer"],
                    json.dumps(q["acceptedAnswers"], ensure_ascii=False),
                    q["answerDisplay"],
                    json.dumps(explanations, ensure_ascii=False),
                    search_text,
                )
            )

    with conn:
        conn.execute("DELETE FROM questions WHERE exam_slug = ?", (slug,))
        conn.execute("DELETE FROM units WHERE exam_slug = ?", (slug,))
        conn.execute(
            """
            INSERT INTO exams (
                slug, version, badge, title, subtitle,
                source_json, block_json, sessions_json, subjects_json, year_groups_json,
                content_hash, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                version = excluded.version,
                badge = excluded.badge,
                title = excluded.title,
                subtitle = excluded.subtitle,
                source_json = excluded.source_json,
                block_json = excluded.block_json,
                sessions_json = excluded.sessions_json,
                subjects_json = excluded.subjects_json,
                year_groups_json = excluded.year_groups_json,
                content_hash = excluded.content_hash,
                updated_at = excluded.updated_at
            """,
            (
                slug,
                exam["version"],
                exam["badge"],
                exam["title"],
                exam["subtitle"],
                json.dumps(exam["source"], ensure_ascii=False),
                json.dumps(exam.get("block") or {}, ensure_ascii=False),
                json.dumps(exam["sessions"], ensure_ascii=False),
                json.dumps(exam["subjects"], ensure_ascii=False),
                json.dumps(exam["yearGroups"], ensure_ascii=False),
                content_hash,
                now_ms,
            ),
        )
        conn.executemany(
            """
            INSERT INTO units (
                exam_slug, unit_code, unit_title, short_label, session,
                subject, subject_title, prof, exam_range, unit_url,
                highlight, is_out_of_scope, exempt_cross_dup, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            unit_rows,
        )
        conn.executemany(
            """
            INSERT INTO questions (
                exam_slug, id, global_index, unit_code, unit_title, session,
                subject, subject_title, prof, exam_range, unit_url, q_num,
                orig_q, year, year_group, has_errata, is_cross_dup, stem,
                image_path, options_json, answer, accepted_answers_json,
                answer_display, explanations_json, search_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            question_rows,
        )

    return True, len(unit_rows), len(question_rows)


def sync_all_exams(
    conn: sqlite3.Connection,
    exams_dir: Path = EXAMS_DIR,
    force: bool = False,
) -> dict:
    if not exams_dir.is_dir():
        return {"exams": 0, "updated": 0, "units": 0, "questions": 0}

    present_slugs: list[str] = []
    updated_count = 0
    total_units = 0
    total_questions = 0

    for exam_dir in sorted(p for p in exams_dir.iterdir() if p.is_dir()):
        manifest_path = exam_dir / "exam.json"
        if not manifest_path.is_file():
            continue
        changed, u_cnt, q_cnt = sync_single_exam(conn, exam_dir, force=force)
        exam_slug = json.loads(manifest_path.read_text(encoding="utf-8"))["slug"]
        present_slugs.append(exam_slug)
        if changed:
            updated_count += 1
        total_units += u_cnt
        total_questions += q_cnt

    with conn:
        if present_slugs:
            placeholders = ",".join("?" for _ in present_slugs)
            conn.execute(
                f"DELETE FROM exams WHERE slug NOT IN ({placeholders})",
                present_slugs,
            )
        else:
            conn.execute("DELETE FROM exams")

    return {
        "exams": len(present_slugs),
        "updated": updated_count,
        "units": total_units,
        "questions": total_questions,
    }
