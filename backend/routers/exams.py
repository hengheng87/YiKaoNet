"""Exam metadata, statistics, image serving, and reload endpoints."""

from __future__ import annotations

import json
import mimetypes
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.config import EXAMS_DIR
from backend.database import get_db
from backend.queries import ensure_exam_exists
from backend.schemas import (
    ExamDetail,
    ExamSummary,
    SessionInfo,
    SourceInfo,
    SubjectInfo,
    UnitSummary,
    YearGroupInfo,
)
from backend.sync_data import sync_all_exams

router = APIRouter(prefix="/api", tags=["exams"])


def _get_exams_dir(request: Request) -> Path:
    return getattr(request.app.state, "exams_dir", EXAMS_DIR)


def _compute_exam_counts(conn: sqlite3.Connection, slug: str) -> dict:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN is_cross_dup = 0 THEN 1 ELSE 0 END), 0) AS unique_cnt,
            COALESCE(SUM(CASE WHEN has_errata = 1 THEN 1 ELSE 0 END), 0) AS errata_cnt
        FROM questions
        WHERE exam_slug = ?
        """,
        (slug,),
    ).fetchone()

    out_of_scope_row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM questions q
        JOIN units u ON u.exam_slug = q.exam_slug AND u.unit_code = q.unit_code
        WHERE q.exam_slug = ? AND u.is_out_of_scope = 1
        """,
        (slug,),
    ).fetchone()

    unit_count_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM units WHERE exam_slug = ?",
        (slug,),
    ).fetchone()

    return {
        "total": int(row["total"]),
        "unique": int(row["unique_cnt"]),
        "errata": int(row["errata_cnt"]),
        "out_of_scope": int(out_of_scope_row["cnt"]),
        "unit_count": int(unit_count_row["cnt"]),
    }


@router.get("/health")
def health_check(db: sqlite3.Connection = Depends(get_db)) -> dict:
    exams_cnt = int(db.execute("SELECT COUNT(*) AS c FROM exams").fetchone()["c"])
    q_cnt = int(db.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"])
    return {"status": "ok", "exams": exams_cnt, "questions": q_cnt}


@router.get("/exams", response_model=list[ExamSummary])
def list_exams(db: sqlite3.Connection = Depends(get_db)) -> list[ExamSummary]:
    rows = db.execute("SELECT * FROM exams ORDER BY slug ASC").fetchall()
    result: list[ExamSummary] = []
    for row in rows:
        counts = _compute_exam_counts(db, row["slug"])
        result.append(
            ExamSummary(
                slug=row["slug"],
                version=row["version"],
                badge=row["badge"],
                title=row["title"],
                subtitle=row["subtitle"],
                source=SourceInfo(**json.loads(row["source_json"])),
                totalQuestions=counts["total"],
                uniqueQuestions=counts["unique"],
                errataCount=counts["errata"],
                outOfScopeCount=counts["out_of_scope"],
                unitCount=counts["unit_count"],
            )
        )
    return result


@router.get("/exams/{slug}", response_model=ExamDetail)
def get_exam_detail(slug: str, db: sqlite3.Connection = Depends(get_db)) -> ExamDetail:
    row = ensure_exam_exists(db, slug)
    counts = _compute_exam_counts(db, slug)

    ses_counts = {
        r["session"]: int(r["cnt"])
        for r in db.execute(
            "SELECT session, COUNT(*) AS cnt FROM questions WHERE exam_slug = ? GROUP BY session",
            (slug,),
        ).fetchall()
    }
    subj_counts = {
        r["subject"]: int(r["cnt"])
        for r in db.execute(
            "SELECT subject, COUNT(*) AS cnt FROM questions WHERE exam_slug = ? GROUP BY subject",
            (slug,),
        ).fetchall()
    }
    year_counts = {
        r["year_group"]: int(r["cnt"])
        for r in db.execute(
            "SELECT year_group, COUNT(*) AS cnt FROM questions WHERE exam_slug = ? GROUP BY year_group",
            (slug,),
        ).fetchall()
    }
    unit_counts = {
        r["unit_code"]: int(r["cnt"])
        for r in db.execute(
            "SELECT unit_code, COUNT(*) AS cnt FROM questions WHERE exam_slug = ? GROUP BY unit_code",
            (slug,),
        ).fetchall()
    }

    sessions = [
        SessionInfo(**item, questionCount=ses_counts.get(item["code"], 0))
        for item in json.loads(row["sessions_json"])
    ]
    subjects = [
        SubjectInfo(**item, questionCount=subj_counts.get(item["code"], 0))
        for item in json.loads(row["subjects_json"])
    ]
    year_groups = [
        YearGroupInfo(**item, questionCount=year_counts.get(item["code"], 0))
        for item in json.loads(row["year_groups_json"])
    ]

    unit_rows = db.execute(
        "SELECT * FROM units WHERE exam_slug = ? ORDER BY sort_order ASC",
        (slug,),
    ).fetchall()
    units = [
        UnitSummary(
            unitCode=u["unit_code"],
            unitTitle=u["unit_title"],
            shortLabel=u["short_label"],
            session=u["session"],
            subject=u["subject"],
            subjectTitle=u["subject_title"],
            prof=u["prof"],
            examRange=u["exam_range"],
            unitUrl=u["unit_url"],
            highlight=bool(u["highlight"]),
            isOutOfScope=bool(u["is_out_of_scope"]),
            exemptFromCrossDupFilter=bool(u["exempt_cross_dup"]),
            questionCount=unit_counts.get(u["unit_code"], 0),
        )
        for u in unit_rows
    ]

    return ExamDetail(
        slug=row["slug"],
        version=row["version"],
        badge=row["badge"],
        title=row["title"],
        subtitle=row["subtitle"],
        source=SourceInfo(**json.loads(row["source_json"])),
        totalQuestions=counts["total"],
        uniqueQuestions=counts["unique"],
        errataCount=counts["errata"],
        outOfScopeCount=counts["out_of_scope"],
        unitCount=counts["unit_count"],
        sessions=sessions,
        subjects=subjects,
        yearGroups=year_groups,
        units=units,
    )


@router.get("/exams/{slug}/images/{filename}")
def get_exam_image(slug: str, filename: str, request: Request) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename or ".." in slug:
        raise HTTPException(status_code=400, detail="Invalid file path")

    exams_dir = _get_exams_dir(request)
    images_dir = (exams_dir / slug / "images").resolve()
    target = (images_dir / filename).resolve()

    if not target.is_relative_to(images_dir) or not target.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(
        target,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/exams/reload")
def reload_exams(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    exams_dir = _get_exams_dir(request)
    summary = sync_all_exams(db, exams_dir=exams_dir, force=True)
    return {"status": "reloaded", **summary}
