"""Tests for NotebookLM / JSON batch import CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.config import EXAMS_DIR
from backend.database import get_connection
from scripts import import_questions
from scripts.validate_data import validate_exam_dir


def test_extract_json_payload_variants():
    # Raw JSON array
    u1, q1 = import_questions.extract_json_payload('[{"stem": "Q1"}]')
    assert u1 is None and len(q1) == 1

    # Fenced Markdown JSON embedded in LLM prose
    md = (
        "Here are the extracted questions:\n\n"
        "```json\n"
        '[{"stem": "From Markdown", "options": {"A": "1", "B": "2"}, "answer": "A"}]\n'
        "```\n\nHope this helps!"
    )
    u2, q2 = import_questions.extract_json_payload(md)
    assert u2 is None and q2[0]["stem"] == "From Markdown"

    # Bundle object with unit metadata
    bundle = json.dumps(
        {
            "unit": {"unitCode": "NEW_Unit", "unitTitle": "新單元"},
            "questions": [{"stem": "Q2"}],
        }
    )
    u3, q3 = import_questions.extract_json_payload(bundle)
    assert u3["unitCode"] == "NEW_Unit" and len(q3) == 1


def test_import_dry_run_append_dedup_update_and_new_unit(tmp_path: Path):
    exams_copy = tmp_path / "exams"
    shutil.copytree(EXAMS_DIR, exams_copy)
    db_path = tmp_path / "import_test.db"

    incoming = [
        {
            "year": "114 學年度",
            "yearGroup": "114",
            "stem": "批次匯入測試新題目一？",
            "options": {"A": "選項一", "B": "選項二", "C": "選項三", "D": "選項四"},
            "answer": "C",
            "explanations": ["核心考點：測試自動補齊預設欄位。"],
        }
    ]

    # Dry-run leaves files untouched
    dry = import_questions.import_questions_into_exam(
        exams_copy,
        db_path,
        "cmu-int2-msk",
        incoming,
        unit_code="1014_Physio1",
        dry_run=True,
    )
    assert dry["dryRun"] is True and dry["added"] == 1
    assert not db_path.exists()

    # Actual append + SQLite sync
    real = import_questions.import_questions_into_exam(
        exams_copy,
        db_path,
        "cmu-int2-msk",
        incoming,
        unit_code="1014_Physio1",
    )
    assert real["added"] == 1
    assert real["unitTotal"] == 27

    # Re-importing identical stem skips duplicate
    dup = import_questions.import_questions_into_exam(
        exams_copy,
        db_path,
        "cmu-int2-msk",
        incoming,
        unit_code="1014_Physio1",
    )
    assert dup["added"] == 0 and dup["skipped"] == 1

    # Updating an existing question by explicit ID
    upd = import_questions.import_questions_into_exam(
        exams_copy,
        db_path,
        "cmu-int2-msk",
        [
            {
                "id": "1014_Physio1-27",
                "year": "114 學年度",
                "yearGroup": "114",
                "stem": "批次匯入測試新題目一（已更新勘誤）？",
                "options": {"A": "選項一", "B": "選項二", "C": "選項三", "D": "選項四"},
                "answer": "C",
                "acceptedAnswers": ["C", "D"],
                "answerDisplay": "(C/D)（申覆並列）",
                "explanations": ["更新後詳解"],
            }
        ],
        unit_code="1014_Physio1",
        update_existing=True,
    )
    assert upd["updated"] == 1

    # Create a brand new unit cleanly updating exam.json
    new_unit = import_questions.import_questions_into_exam(
        exams_copy,
        db_path,
        "cmu-int2-msk",
        [
            {
                "year": "114 學年度",
                "yearGroup": "114",
                "stem": "全新單元測試題？",
                "options": {"A": "甲", "B": "乙"},
                "answer": "A",
                "explanations": ["全新單元解析"],
            }
        ],
        unit_code="1120_NewUnit",
        unit_meta={
            "unitTitle": "11/20 新補充共筆",
            "shortLabel": "11/20 新補充",
            "session": "B",
            "subject": "Surg",
            "subjectTitle": "外科學概論 (一)",
            "prof": "測試教授",
            "examRange": "B卷補充",
            "unitUrl": "https://notebook.google.com/notebook/01b3322a-9c0a-498f-91ce-4c29f24657f5",
        },
    )
    assert new_unit["newUnit"] is True and new_unit["added"] == 1
    assert validate_exam_dir(exams_copy / "cmu-int2-msk")[0] == []

    conn = get_connection(db_path)
    try:
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM questions WHERE exam_slug = 'cmu-int2-msk'"
        ).fetchone()["c"]
        assert cnt == 569
    finally:
        conn.close()


def test_from_notebooklm_cli_with_mocked_query(tmp_path: Path, monkeypatch):
    exams_copy = tmp_path / "exams"
    shutil.copytree(EXAMS_DIR, exams_copy)
    db_path = tmp_path / "nlm_test.db"

    monkeypatch.setattr(import_questions, "EXAMS_DIR", exams_copy)
    monkeypatch.setattr(import_questions, "DB_PATH", db_path)

    fake_response = (
        "根據來源整理如下：\n```json\n"
        + json.dumps(
            [
                {
                    "year": "114 學年度",
                    "yearGroup": "114",
                    "stem": "NotebookLM 模擬匯入題？",
                    "options": {"A": "是", "B": "否"},
                    "answer": "A",
                    "explanations": ["來自 NotebookLM 整理詳解"],
                }
            ],
            ensure_ascii=False,
        )
        + "\n```"
    )
    monkeypatch.setattr(
        import_questions,
        "run_nlm_query",
        lambda *args, **kwargs: fake_response,
    )

    raw_dump = tmp_path / "nlm_raw.txt"
    exit_code = import_questions.main(
        [
            "from-notebooklm",
            "--exam",
            "cmu-int2-msk",
            "--unit",
            "1118_ClinEval",
            "--prompt",
            "整理新增考古題",
            "--save-raw",
            str(raw_dump),
        ]
    )
    assert exit_code == 0
    assert raw_dump.is_file()
    assert validate_exam_dir(exams_copy / "cmu-int2-msk")[0] == []
