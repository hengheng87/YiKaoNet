"""Cloud progress sync and backup endpoints."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, Query

from backend.database import get_db
from backend.queries import ensure_exam_exists
from backend.schemas import (
    ProgressMergeRequest,
    ProgressPayload,
    ProgressResponse,
    normalize_sync_code,
)

router = APIRouter(prefix="/api/progress", tags=["progress"])

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _row_to_progress(
    row: sqlite3.Row | None,
    sync_code: str,
    exam_slug: str,
) -> ProgressResponse:
    if not row:
        return ProgressResponse(
            exists=False,
            syncCode=sync_code,
            examSlug=exam_slug,
        )
    return ProgressResponse(
        exists=True,
        syncCode=sync_code,
        examSlug=exam_slug,
        answers=json.loads(row["answers_json"]),
        answerTimestamps=json.loads(row["answer_timestamps_json"]),
        starred=json.loads(row["starred_json"]),
        starredTimestamps=json.loads(row["starred_timestamps_json"]),
        lastAnsweredQid=row["last_answered_qid"],
        lastViewedQid=row["last_viewed_qid"],
        activeFilters=json.loads(row["active_filters_json"]),
        updatedAt=int(row["updated_at"]),
    )


def _save_progress(
    conn: sqlite3.Connection,
    sync_code: str,
    exam_slug: str,
    payload: ProgressPayload,
) -> ProgressResponse:
    now_ms = payload.updatedAt or int(time.time() * 1000)
    with conn:
        conn.execute(
            """
            INSERT INTO user_progress (
                sync_code, exam_slug, answers_json, answer_timestamps_json,
                starred_json, starred_timestamps_json, last_answered_qid,
                last_viewed_qid, active_filters_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sync_code, exam_slug) DO UPDATE SET
                answers_json = excluded.answers_json,
                answer_timestamps_json = excluded.answer_timestamps_json,
                starred_json = excluded.starred_json,
                starred_timestamps_json = excluded.starred_timestamps_json,
                last_answered_qid = excluded.last_answered_qid,
                last_viewed_qid = excluded.last_viewed_qid,
                active_filters_json = excluded.active_filters_json,
                updated_at = excluded.updated_at
            """,
            (
                sync_code,
                exam_slug,
                json.dumps(payload.answers, ensure_ascii=False),
                json.dumps(payload.answerTimestamps, ensure_ascii=False),
                json.dumps(payload.starred, ensure_ascii=False),
                json.dumps(payload.starredTimestamps, ensure_ascii=False),
                payload.lastAnsweredQid,
                payload.lastViewedQid,
                json.dumps(payload.activeFilters, ensure_ascii=False),
                now_ms,
            ),
        )
    row = conn.execute(
        "SELECT * FROM user_progress WHERE sync_code = ? AND exam_slug = ?",
        (sync_code, exam_slug),
    ).fetchone()
    return _row_to_progress(row, sync_code, exam_slug)


def merge_progress_states(
    server: ProgressPayload,
    client: ProgressPayload,
) -> ProgressPayload:
    merged_answers: dict[str, str] = {}
    merged_ans_ts: dict[str, int] = {}
    for qid in set(server.answers) | set(client.answers):
        in_server = qid in server.answers
        in_client = qid in client.answers
        s_ts = server.answerTimestamps.get(qid, 0)
        c_ts = client.answerTimestamps.get(qid, 0)
        if in_client and (not in_server or c_ts >= s_ts):
            merged_answers[qid] = client.answers[qid]
            merged_ans_ts[qid] = c_ts
        else:
            merged_answers[qid] = server.answers[qid]
            merged_ans_ts[qid] = s_ts

    merged_starred: dict[str, bool] = {}
    merged_star_ts: dict[str, int] = {}
    for qid in set(server.starred) | set(client.starred):
        in_server = qid in server.starred
        in_client = qid in client.starred
        s_ts = server.starredTimestamps.get(qid, 0)
        c_ts = client.starredTimestamps.get(qid, 0)
        if in_client and (not in_server or c_ts >= s_ts):
            merged_starred[qid] = bool(client.starred[qid])
            merged_star_ts[qid] = c_ts
        else:
            merged_starred[qid] = bool(server.starred[qid])
            merged_star_ts[qid] = s_ts

    prefer_client = client.updatedAt >= server.updatedAt
    last_answered = (
        client.lastAnsweredQid or server.lastAnsweredQid
        if prefer_client
        else server.lastAnsweredQid or client.lastAnsweredQid
    )
    last_viewed = (
        client.lastViewedQid or server.lastViewedQid
        if prefer_client
        else server.lastViewedQid or client.lastViewedQid
    )
    active_filters = client.activeFilters if prefer_client else server.activeFilters
    merged_updated = max(server.updatedAt, client.updatedAt, int(time.time() * 1000))

    return ProgressPayload(
        answers=merged_answers,
        answerTimestamps=merged_ans_ts,
        starred=merged_starred,
        starredTimestamps=merged_star_ts,
        lastAnsweredQid=last_answered,
        lastViewedQid=last_viewed,
        activeFilters=active_filters,
        updatedAt=merged_updated,
    )


@router.post("/generate-code")
def generate_sync_code() -> dict[str, str]:
    part1 = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    part2 = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    return {"syncCode": f"YK-{part1}-{part2}"}


@router.get("/{sync_code}/{exam_slug}", response_model=ProgressResponse)
def get_progress(
    sync_code: str,
    exam_slug: str,
    db: sqlite3.Connection = Depends(get_db),
) -> ProgressResponse:
    ensure_exam_exists(db, exam_slug)
    code = normalize_sync_code(sync_code)
    row = db.execute(
        "SELECT * FROM user_progress WHERE sync_code = ? AND exam_slug = ?",
        (code, exam_slug),
    ).fetchone()
    return _row_to_progress(row, code, exam_slug)


@router.put("/{sync_code}/{exam_slug}", response_model=ProgressResponse)
def put_progress(
    sync_code: str,
    exam_slug: str,
    payload: ProgressPayload,
    db: sqlite3.Connection = Depends(get_db),
) -> ProgressResponse:
    ensure_exam_exists(db, exam_slug)
    code = normalize_sync_code(sync_code)
    return _save_progress(db, code, exam_slug, payload)


@router.post("/{sync_code}/{exam_slug}/merge", response_model=ProgressResponse)
def merge_progress(
    sync_code: str,
    exam_slug: str,
    payload: ProgressMergeRequest,
    db: sqlite3.Connection = Depends(get_db),
) -> ProgressResponse:
    ensure_exam_exists(db, exam_slug)
    code = normalize_sync_code(sync_code)
    row = db.execute(
        "SELECT * FROM user_progress WHERE sync_code = ? AND exam_slug = ?",
        (code, exam_slug),
    ).fetchone()
    if not row:
        return _save_progress(db, code, exam_slug, payload)

    server_state = ProgressPayload(
        answers=json.loads(row["answers_json"]),
        answerTimestamps=json.loads(row["answer_timestamps_json"]),
        starred=json.loads(row["starred_json"]),
        starredTimestamps=json.loads(row["starred_timestamps_json"]),
        lastAnsweredQid=row["last_answered_qid"],
        lastViewedQid=row["last_viewed_qid"],
        activeFilters=json.loads(row["active_filters_json"]),
        updatedAt=int(row["updated_at"]),
    )
    merged = merge_progress_states(server_state, payload)
    return _save_progress(db, code, exam_slug, merged)


@router.delete("/{sync_code}/{exam_slug}")
def delete_progress(
    sync_code: str,
    exam_slug: str,
    keep_starred: bool = Query(default=True),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    ensure_exam_exists(db, exam_slug)
    code = normalize_sync_code(sync_code)
    row = db.execute(
        "SELECT * FROM user_progress WHERE sync_code = ? AND exam_slug = ?",
        (code, exam_slug),
    ).fetchone()

    if not row:
        return {"status": "ok", "syncCode": code, "examSlug": exam_slug, "cleared": False}

    with db:
        if keep_starred:
            now_ms = int(time.time() * 1000)
            db.execute(
                """
                UPDATE user_progress
                SET answers_json = '{}',
                    answer_timestamps_json = '{}',
                    last_answered_qid = NULL,
                    last_viewed_qid = NULL,
                    updated_at = ?
                WHERE sync_code = ? AND exam_slug = ?
                """,
                (now_ms, code, exam_slug),
            )
        else:
            db.execute(
                "DELETE FROM user_progress WHERE sync_code = ? AND exam_slug = ?",
                (code, exam_slug),
            )

    return {"status": "ok", "syncCode": code, "examSlug": exam_slug, "cleared": True}
