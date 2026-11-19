"""Question listing, filtering, search, and detail endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_db
from backend.queries import ensure_exam_exists, query_exam_questions, row_to_question
from backend.schemas import QuestionListResponse, QuestionOut

router = APIRouter(prefix="/api/exams/{slug}/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    slug: str,
    unit: str | None = Query(default=None),
    year: str | None = Query(default=None),
    search: str | None = Query(default=None),
    hide_cross_dup: bool = Query(default=False),
    has_errata: bool | None = Query(default=None),
    random_count: int | None = Query(default=None, ge=1, le=500),
    limit: int | None = Query(default=None, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
) -> QuestionListResponse:
    total, questions = query_exam_questions(
        db,
        slug,
        unit=unit,
        year=year,
        search=search,
        hide_cross_dup=hide_cross_dup,
        has_errata=has_errata,
        random_count=random_count,
        limit=limit,
        offset=offset,
    )
    return QuestionListResponse(
        examSlug=slug,
        total=total,
        filtered=len(questions),
        questions=questions,
    )


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(
    slug: str,
    question_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> QuestionOut:
    ensure_exam_exists(db, slug)
    row = db.execute(
        "SELECT * FROM questions WHERE exam_slug = ? AND id = ?",
        (slug, question_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"找不到題目：{question_id}")
    return row_to_question(row, slug)
