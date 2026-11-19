"""Shared SQLite query and row-mapping helpers for exams and questions."""

from __future__ import annotations

import json
import random
import sqlite3

from fastapi import HTTPException

from backend.schemas import QuestionOut


def ensure_exam_exists(conn: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM exams WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"找不到題庫：{slug}")
    return row


def row_to_question(row: sqlite3.Row, slug: str) -> QuestionOut:
    img_rel = row["image_path"]
    image_url: str | None = None
    if img_rel:
        filename = img_rel.split("/")[-1]
        image_url = f"/api/exams/{slug}/images/{filename}"

    return QuestionOut(
        id=row["id"],
        globalIndex=row["global_index"],
        unitCode=row["unit_code"],
        unitTitle=row["unit_title"],
        session=row["session"],
        subject=row["subject"],
        subjectTitle=row["subject_title"],
        prof=row["prof"],
        examRange=row["exam_range"],
        unitUrl=row["unit_url"],
        qNum=row["q_num"],
        origQ=row["orig_q"],
        year=row["year"],
        yearGroup=row["year_group"],
        hasErrata=bool(row["has_errata"]),
        isCrossDup=bool(row["is_cross_dup"]),
        stem=row["stem"],
        image=image_url,
        options=json.loads(row["options_json"]),
        answer=row["answer"],
        acceptedAnswers=json.loads(row["accepted_answers_json"]),
        answerDisplay=row["answer_display"],
        explanations=json.loads(row["explanations_json"]),
    )


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def query_exam_questions(
    conn: sqlite3.Connection,
    slug: str,
    *,
    unit: str | None = None,
    year: str | None = None,
    search: str | None = None,
    hide_cross_dup: bool = False,
    has_errata: bool | None = None,
    random_count: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[int, list[QuestionOut]]:
    ensure_exam_exists(conn, slug)

    total_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM questions WHERE exam_slug = ?",
        (slug,),
    ).fetchone()
    total = int(total_row["cnt"])

    clauses = ["exam_slug = ?"]
    params: list[object] = [slug]

    if unit and unit != "ALL":
        if unit.startswith("SESSION_"):
            clauses.append("session = ?")
            params.append(unit[len("SESSION_") :])
        elif unit.startswith("SUBJ_"):
            clauses.append("subject = ?")
            params.append(unit[len("SUBJ_") :])
        elif unit == "OUT_OF_SCOPE":
            clauses.append(
                "unit_code IN (SELECT unit_code FROM units WHERE exam_slug = ? AND is_out_of_scope = 1)"
            )
            params.append(slug)
        else:
            clauses.append("unit_code = ?")
            params.append(unit)

    if year and year != "ALL":
        clauses.append("year_group = ?")
        params.append(year)

    if has_errata is True:
        clauses.append("has_errata = 1")
    elif has_errata is False:
        clauses.append("has_errata = 0")

    if hide_cross_dup:
        is_exempt = False
        if unit and unit not in ("ALL", "OUT_OF_SCOPE") and not unit.startswith(
            ("SESSION_", "SUBJ_")
        ):
            exempt_row = conn.execute(
                "SELECT exempt_cross_dup FROM units WHERE exam_slug = ? AND unit_code = ?",
                (slug, unit),
            ).fetchone()
            is_exempt = bool(exempt_row and exempt_row["exempt_cross_dup"])
        if not is_exempt:
            clauses.append("is_cross_dup = 0")

    if search and search.strip():
        escaped = _escape_like(search.strip().lower())
        clauses.append("search_text LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")

    where_sql = " AND ".join(clauses)
    rows = conn.execute(
        f"SELECT * FROM questions WHERE {where_sql} ORDER BY global_index ASC",
        params,
    ).fetchall()

    if random_count is not None and random_count > 0:
        pool = [r for r in rows if not r["is_cross_dup"]]
        sample_size = min(random_count, len(pool))
        sampled = random.sample(pool, sample_size)
        return total, [row_to_question(r, slug) for r in sampled]

    if limit is not None and limit >= 0:
        rows = rows[offset : offset + limit]
    elif offset > 0:
        rows = rows[offset:]

    return total, [row_to_question(r, slug) for r in rows]
