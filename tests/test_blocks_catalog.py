"""Tests for Block catalog aggregation, auto-unlocking, legacy SQLite migration, and API."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.blocks import build_blocks_catalog
from backend.config import BLOCKS_CATALOG_PATH, EXAMS_DIR, FRONTEND_DIR
from backend.database import init_db
from backend.ingestion import commit_questions_import, init_exam
from backend.main import create_app
from backend.sync_data import sync_all_exams
from scripts.validate_data import validate_blocks_catalog


def test_blocks_catalog_api_and_exam_block_metadata(client):
    res = client.get("/api/blocks")
    assert res.status_code == 200
    body = res.json()

    assert body["readyBlocks"] == 1
    assert body["plannedBlocks"] == 3
    assert body["totalBlocks"] == 4
    assert body["totalQuestions"] == 547
    assert body["totalUnits"] == 22

    assert len(body["terms"]) == 1
    term = body["terms"][0]
    assert term["code"] == "y3-s1"
    assert term["shortLabel"] == "大三上"
    assert term["readyCount"] == 1
    assert term["totalCount"] == 4

    slugs = [b["slug"] for b in term["blocks"]]
    assert slugs == [
        "cmu-int1-foundations",
        "cmu-int2-msk",
        "cmu-int3-hema-imm",
        "cmu-int4-neuro",
    ]
    by_slug = {b["slug"]: b for b in term["blocks"]}
    assert by_slug["cmu-int1-foundations"]["status"] == "planned"
    assert by_slug["cmu-int2-msk"]["status"] == "ready"
    assert by_slug["cmu-int2-msk"]["totalQuestions"] == 547
    assert by_slug["cmu-int2-msk"]["unitCount"] == 22
    assert len(by_slug["cmu-int2-msk"]["subjects"]) == 6

    exams_list = client.get("/api/exams").json()
    assert exams_list[0]["block"]["term"] == "y3-s1"
    assert exams_list[0]["block"]["name"] == "骨骼肌肉系統"

    detail = client.get("/api/exams/cmu-int2-msk").json()
    assert detail["block"]["examLabel"] == "第二次整合考"


def test_auto_unlock_planned_block_and_dynamic_new_term(tmp_path: Path):
    exams_dir = tmp_path / "exams"
    shutil.copytree(EXAMS_DIR, exams_dir)
    catalog_path = tmp_path / "blocks.json"
    shutil.copy2(BLOCKS_CATALOG_PATH, catalog_path)
    db_path = tmp_path / "blocks_unlock.db"

    # 1) Create and populate previously planned block cmu-int1-foundations
    init_exam(
        exams_dir,
        slug="cmu-int1-foundations",
        title="三上第一次整合考：基礎醫學概論",
        block={
            "term": "y3-s1",
            "examLabel": "第一次整合考",
            "name": "基礎醫學概論",
            "icon": "🧬",
            "accent": "blue",
            "order": 1,
        },
    )
    commit_questions_import(
        exams_dir,
        db_path,
        "cmu-int1-foundations",
        [
            {
                "year": "114 學年度",
                "yearGroup": "114",
                "stem": "細胞凋亡最典型之生化特徵為何？",
                "options": {"A": "DNA 梯狀片段化", "B": "細胞腫脹破裂"},
                "answer": "A",
                "explanations": ["Caspase 活化切割核小體間 DNA。"],
            }
        ],
        unit_code="0915_CellPath",
        unit_meta={
            "unitTitle": "09/15 細胞病理",
            "shortLabel": "09/15 細胞病理",
            "session": "A",
            "subject": "General",
            "subjectTitle": "綜合學科",
            "prof": "測試教授",
            "examRange": "A卷 Q1",
            "unitUrl": "https://notebook.google.com/",
        },
    )

    # 2) Add an unlisted exam in a brand-new semester term y3-s2
    init_exam(
        exams_dir,
        slug="cmu-int5-cardio",
        title="三下第一次整合考：心血管系統",
        block={
            "term": "y3-s2",
            "termLabel": "大三下學期整合考",
            "termShortLabel": "大三下",
            "examLabel": "第一次整合考",
            "name": "心血管系統",
            "englishName": "Cardiovascular System",
            "icon": "🫀",
            "accent": "rose",
            "order": 1,
            "description": "心電生理、心衰竭病理與心血管用藥。",
        },
    )
    commit_questions_import(
        exams_dir,
        db_path,
        "cmu-int5-cardio",
        [
            {
                "year": "114 學年度",
                "yearGroup": "114",
                "stem": "房室結傳導速度最慢的生理意義為何？",
                "options": {"A": "利於心室充血", "B": "增加心搏速率"},
                "answer": "A",
                "explanations": ["AV delay 確保心房收縮先完成心室充填。"],
            }
        ],
        unit_code="0301_CVPhysio",
        unit_meta={
            "unitTitle": "03/01 心臟電生理",
            "shortLabel": "03/01 心電生理",
            "session": "A",
            "subject": "General",
            "subjectTitle": "綜合學科",
            "prof": "測試教授",
            "examRange": "A卷 Q1",
            "unitUrl": "https://notebook.google.com/",
        },
    )

    app = create_app(
        db_path=db_path,
        exams_dir=exams_dir,
        frontend_dir=FRONTEND_DIR,
        blocks_catalog_path=catalog_path,
    )
    with TestClient(app) as tc:
        res = tc.get("/api/blocks")
        assert res.status_code == 200
        data = res.json()

        assert data["readyBlocks"] == 3
        assert data["plannedBlocks"] == 2
        assert data["totalBlocks"] == 5
        assert data["totalQuestions"] == 549
        assert [t["code"] for t in data["terms"]] == ["y3-s1", "y3-s2"]

        y3s1_blocks = {b["slug"]: b for b in data["terms"][0]["blocks"]}
        assert y3s1_blocks["cmu-int1-foundations"]["status"] == "ready"
        assert y3s1_blocks["cmu-int1-foundations"]["totalQuestions"] == 1

        y3s2_blocks = {b["slug"]: b for b in data["terms"][1]["blocks"]}
        assert y3s2_blocks["cmu-int5-cardio"]["status"] == "ready"
        assert y3s2_blocks["cmu-int5-cardio"]["icon"] == "🫀"


def test_legacy_sqlite_migration_adds_block_json_column(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE exams (
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
        INSERT INTO exams VALUES (
            'cmu-int2-msk', '2.0.0', 'B', 'Old Title', 'Old Sub',
            '{"name":"KB","url":"https://example.com"}',
            '[]', '[]', '[]', 'stale-hash', 100
        );
        """
    )
    conn.commit()

    try:
        init_db(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(exams)").fetchall()}
        assert "block_json" in cols

        sync_all_exams(conn, exams_dir=EXAMS_DIR)
        catalog = build_blocks_catalog(conn, catalog_path=BLOCKS_CATALOG_PATH)
        assert catalog.readyBlocks == 1
        assert catalog.totalQuestions == 547
    finally:
        conn.close()


def test_validate_blocks_catalog_checks(tmp_path: Path):
    assert validate_blocks_catalog(BLOCKS_CATALOG_PATH) == []

    bad_catalog = tmp_path / "blocks.json"
    bad_catalog.write_text(
        '{"version":"1","title":"T","subtitle":"S","terms":[{"code":"t1","label":"L","shortLabel":"S","order":1}],"blocks":[{"slug":"b1","term":"missing-term","name":"N","order":1}]}',
        encoding="utf-8",
    )
    errs = validate_blocks_catalog(bad_catalog)
    assert any("missing-term" in e for e in errs)
