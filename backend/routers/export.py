"""Notion toggle markdown and standalone offline HTML export endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from backend.config import BLOCKS_CATALOG_PATH, EXAMS_DIR, FRONTEND_DIR
from backend.database import get_db
from backend.offline_builder import build_offline_html
from backend.queries import ensure_exam_exists, query_exam_questions, row_to_question
from backend.schemas import NotionExportRequest, NotionExportResponse, QuestionOut

router = APIRouter(prefix="/api/exams/{slug}/export", tags=["export"])


def render_notion_markdown(exam_title: str, questions: list[QuestionOut]) -> str:
    header = (
        f"# {exam_title}（共 {len(questions)} 題）\n"
        "> 💡 **使用說明**：直接貼入 Notion 後，每道題目下方皆有可展開的 "
        "**「點擊查看正解與逐項詳解」** 摺疊區塊 (Toggle)！\n\n"
    )
    blocks: list[str] = []
    for q in questions:
        err_tag = " ⚠️【申覆／爭議題】" if q.hasErrata else ""
        opt_lines = [f"- ({k}) {v}" for k, v in q.options.items()]
        stem_flat = q.stem.replace("\n", " ")
        lines = [
            f"### [#{q.globalIndex}｜{q.unitTitle} Q{q.qNum}] 〈{q.year}〉 {stem_flat}{err_tag}",
            *opt_lines,
            f"<details><summary>💡 <strong>點擊展開【標準答案：({q.answer})】與核心機制詳解</strong></summary>",
            "",
            f"- **【標準答案】**：{q.answerDisplay}（來源：[{q.unitTitle}（{q.prof}）共筆]({q.unitUrl})）",
        ]
        for exp in q.explanations:
            lines.append(f"- {exp}")
        lines.append("</details>\n")
        blocks.append("\n".join(lines))
    return header + "\n".join(blocks)


@router.post("/notion", response_model=NotionExportResponse)
def export_notion(
    slug: str,
    req: NotionExportRequest,
    db: sqlite3.Connection = Depends(get_db),
) -> NotionExportResponse:
    exam_row = ensure_exam_exists(db, slug)

    questions: list[QuestionOut]
    if req.questionIds is not None:
        if not req.questionIds:
            questions = []
        else:
            placeholders = ",".join("?" for _ in req.questionIds)
            rows = db.execute(
                f"SELECT * FROM questions WHERE exam_slug = ? AND id IN ({placeholders}) ORDER BY global_index ASC",
                [slug, *req.questionIds],
            ).fetchall()
            questions = [row_to_question(r, slug) for r in rows]
    else:
        scope = req.scope or "ALL"
        if scope == "UNIQUE":
            _, questions = query_exam_questions(db, slug, hide_cross_dup=True)
        elif scope == "ERRATA":
            _, questions = query_exam_questions(db, slug, has_errata=True)
        else:
            _, questions = query_exam_questions(db, slug, unit=scope)

    markdown = render_notion_markdown(exam_row["title"], questions)
    return NotionExportResponse(count=len(questions), markdown=markdown)


@router.get("/offline-html")
def export_offline_html(
    slug: str,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> Response:
    exams_dir = getattr(request.app.state, "exams_dir", EXAMS_DIR)
    frontend_dir = getattr(request.app.state, "frontend_dir", FRONTEND_DIR)
    blocks_catalog_path = getattr(
        request.app.state, "blocks_catalog_path", BLOCKS_CATALOG_PATH
    )
    html = build_offline_html(
        db,
        exams_dir,
        frontend_dir,
        exam_slugs=[slug],
        blocks_catalog_path=blocks_catalog_path,
    )
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="yikao-{slug}-offline.html"'
        },
    )
