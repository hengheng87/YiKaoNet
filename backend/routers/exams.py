"""Exam metadata, statistics, image serving, and reload endpoints."""

from __future__ import annotations

import json
import mimetypes
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.blocks import build_blocks_catalog
from backend.config import BLOCKS_CATALOG_PATH, EXAMS_DIR
from backend.database import get_db
from backend.queries import compute_exam_counts, ensure_exam_exists
from backend.schemas import (
    BlockMeta,
    BlocksCatalogResponse,
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


def _get_blocks_catalog_path(request: Request) -> Path:
    return getattr(request.app.state, "blocks_catalog_path", BLOCKS_CATALOG_PATH)


def _parse_block_meta(row: sqlite3.Row) -> BlockMeta | None:
    if "block_json" not in row.keys():
        return None
    raw = json.loads(row["block_json"] or "{}")
    if not raw or not isinstance(raw, dict):
        return None
    return BlockMeta(**raw)


@router.get("/health")
def health_check(db: sqlite3.Connection = Depends(get_db)) -> dict:
    exams_cnt = int(db.execute("SELECT COUNT(*) AS c FROM exams").fetchone()["c"])
    q_cnt = int(db.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"])
    return {"status": "ok", "exams": exams_cnt, "questions": q_cnt}


@router.get("/blocks", response_model=BlocksCatalogResponse)
def get_blocks_catalog(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> BlocksCatalogResponse:
    catalog_path = _get_blocks_catalog_path(request)
    return build_blocks_catalog(db, catalog_path=catalog_path)


@router.get("/exams", response_model=list[ExamSummary])
def list_exams(db: sqlite3.Connection = Depends(get_db)) -> list[ExamSummary]:
    rows = db.execute("SELECT * FROM exams ORDER BY slug ASC").fetchall()
    result: list[ExamSummary] = []
    for row in rows:
        counts = compute_exam_counts(db, row["slug"])
        result.append(
            ExamSummary(
                slug=row["slug"],
                version=row["version"],
                badge=row["badge"],
                title=row["title"],
                subtitle=row["subtitle"],
                source=SourceInfo(**json.loads(row["source_json"])),
                block=_parse_block_meta(row),
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
    counts = compute_exam_counts(db, slug)

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
        block=_parse_block_meta(row),
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
