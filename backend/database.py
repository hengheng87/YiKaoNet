"""SQLite connection management and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import Request

from backend.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS exams (
    slug TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    badge TEXT NOT NULL,
    title TEXT NOT NULL,
    subtitle TEXT NOT NULL,
    source_json TEXT NOT NULL,
    sessions_json TEXT NOT NULL,
    subjects_json TEXT NOT NULL,
    year_groups_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS units (
    exam_slug TEXT NOT NULL,
    unit_code TEXT NOT NULL,
    unit_title TEXT NOT NULL,
    short_label TEXT NOT NULL,
    session TEXT NOT NULL,
    subject TEXT NOT NULL,
    subject_title TEXT NOT NULL,
    prof TEXT NOT NULL,
    exam_range TEXT NOT NULL,
    unit_url TEXT NOT NULL,
    highlight INTEGER NOT NULL DEFAULT 0,
    is_out_of_scope INTEGER NOT NULL DEFAULT 0,
    exempt_cross_dup INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (exam_slug, unit_code),
    FOREIGN KEY (exam_slug) REFERENCES exams(slug) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS questions (
    exam_slug TEXT NOT NULL,
    id TEXT NOT NULL,
    global_index INTEGER NOT NULL,
    unit_code TEXT NOT NULL,
    unit_title TEXT NOT NULL,
    session TEXT NOT NULL,
    subject TEXT NOT NULL,
    subject_title TEXT NOT NULL,
    prof TEXT NOT NULL,
    exam_range TEXT NOT NULL,
    unit_url TEXT NOT NULL,
    q_num INTEGER NOT NULL,
    orig_q TEXT NOT NULL,
    year TEXT NOT NULL,
    year_group TEXT NOT NULL,
    has_errata INTEGER NOT NULL DEFAULT 0,
    is_cross_dup INTEGER NOT NULL DEFAULT 0,
    stem TEXT NOT NULL,
    image_path TEXT,
    options_json TEXT NOT NULL,
    answer TEXT NOT NULL,
    accepted_answers_json TEXT NOT NULL,
    answer_display TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    search_text TEXT NOT NULL,
    PRIMARY KEY (exam_slug, id),
    FOREIGN KEY (exam_slug) REFERENCES exams(slug) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_questions_exam_global
    ON questions(exam_slug, global_index);
CREATE INDEX IF NOT EXISTS idx_questions_exam_unit
    ON questions(exam_slug, unit_code);
CREATE INDEX IF NOT EXISTS idx_questions_exam_subject
    ON questions(exam_slug, subject);
CREATE INDEX IF NOT EXISTS idx_questions_exam_session
    ON questions(exam_slug, session);
CREATE INDEX IF NOT EXISTS idx_questions_exam_year
    ON questions(exam_slug, year_group);

CREATE TABLE IF NOT EXISTS user_progress (
    sync_code TEXT NOT NULL,
    exam_slug TEXT NOT NULL,
    answers_json TEXT NOT NULL DEFAULT '{}',
    answer_timestamps_json TEXT NOT NULL DEFAULT '{}',
    starred_json TEXT NOT NULL DEFAULT '{}',
    starred_timestamps_json TEXT NOT NULL DEFAULT '{}',
    last_answered_qid TEXT,
    last_viewed_qid TEXT,
    active_filters_json TEXT NOT NULL DEFAULT '{}',
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (sync_code, exam_slug)
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db
