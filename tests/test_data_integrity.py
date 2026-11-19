"""Data integrity and lossless migration tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.migrate_v106 import (
    EXAM_DIR,
    SOURCE_HTML,
    extract_questions_from_html,
    verify_round_trip,
)
from scripts.validate_data import validate_all, validate_exam_dir


def test_validate_all_passes():
    assert validate_all() == 0


def test_cmu_int2_msk_counts_and_assets():
    errors, stats = validate_exam_dir(EXAM_DIR)
    assert errors == []
    assert stats == {"slug": "cmu-int2-msk", "units": 22, "questions": 547}

    exam = json.loads((EXAM_DIR / "exam.json").read_text(encoding="utf-8"))
    all_questions: list[dict] = []
    bone_path_profs: set[str] = set()

    for unit_meta in exam["units"]:
        unit = json.loads((EXAM_DIR / unit_meta["file"]).read_text(encoding="utf-8"))
        for q in unit["questions"]:
            eff_prof = q.get("prof", unit["prof"])
            if unit["unitCode"] == "1021_BonePath":
                bone_path_profs.add(eff_prof)
            all_questions.append(
                {
                    **q,
                    "session": q.get("session", unit["session"]),
                    "subject": q.get("subject", unit["subject"]),
                }
            )

    assert len(all_questions) == 547
    assert sum(1 for q in all_questions if q["session"] == "A") == 339
    assert sum(1 for q in all_questions if q["session"] == "B") == 208
    assert sum(1 for q in all_questions if q["isCrossDup"]) == 90
    assert sum(1 for q in all_questions if not q["isCrossDup"]) == 457
    assert sum(1 for q in all_questions if q["hasErrata"]) == 12

    assert bone_path_profs == {
        "張凱博 醫師（含歷屆骨關節題庫）",
        "張凱博 醫師（M65 舊彙編補充）",
    }

    img_questions = [q for q in all_questions if q["image"] is not None]
    assert len(img_questions) == 12
    for q in img_questions:
        img_file: Path = EXAM_DIR / q["image"]
        assert img_file.is_file()
        assert img_file.read_bytes().startswith(b"\xff\xd8\xff")


def test_lossless_match_against_v106_html_if_present():
    if not SOURCE_HTML.is_file():
        return
    src_questions = extract_questions_from_html(SOURCE_HTML)
    exam_manifest = json.loads((EXAM_DIR / "exam.json").read_text(encoding="utf-8"))
    verify_round_trip(src_questions, exam_manifest)
