"""Data integrity and lossless migration tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from scripts.migrate_v106 import (
    EXAM_DIR,
    SOURCE_HTML,
    extract_questions_from_html,
)
from scripts.validate_data import validate_all, validate_exam_dir


def test_validate_all_passes():
    assert validate_all() == 0


def test_cmu_int2_msk_counts_and_assets():
    errors, stats = validate_exam_dir(EXAM_DIR)
    assert errors == []
    assert stats == {"slug": "cmu-int2-msk", "units": 22, "questions": 567}

    exam = json.loads((EXAM_DIR / "exam.json").read_text(encoding="utf-8"))
    all_questions: list[dict] = []
    bone_path_profs: set[str] = set()
    clin_eval_qs: list[dict] = []

    for unit_meta in exam["units"]:
        unit = json.loads((EXAM_DIR / unit_meta["file"]).read_text(encoding="utf-8"))
        if unit["unitCode"] == "1118_ClinEval":
            clin_eval_qs = unit["questions"]
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

    assert len(all_questions) == 567
    assert sum(1 for q in all_questions if q["session"] == "A") == 339
    assert sum(1 for q in all_questions if q["session"] == "B") == 228
    assert sum(1 for q in all_questions if q["isCrossDup"]) == 90
    assert sum(1 for q in all_questions if not q["isCrossDup"]) == 477
    assert sum(1 for q in all_questions if q["hasErrata"]) == 14

    assert len(clin_eval_qs) == 28
    clin_by_id = {q["id"]: q for q in clin_eval_qs}
    assert clin_by_id["1118_ClinEval-19"]["answer"] == "A"
    assert clin_by_id["1118_ClinEval-19"]["hasErrata"] is True
    assert clin_by_id["1118_ClinEval-23"]["hasErrata"] is True
    assert clin_by_id["1118_ClinEval-23"]["acceptedAnswers"] == ["A", "B", "C", "D"]
    assert sum(1 for q in clin_eval_qs if q["yearGroup"] == "M67_Note") == 8

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
    cur_by_id: dict[str, dict] = {}
    for unit_meta in exam_manifest["units"]:
        unit_data = json.loads((EXAM_DIR / unit_meta["file"]).read_text(encoding="utf-8"))
        for q in unit_data["questions"]:
            cur_by_id[q["id"]] = q

    assert len(cur_by_id) >= len(src_questions)
    for src in src_questions:
        assert src["id"] in cur_by_id
        if src.get("image"):
            rec = cur_by_id[src["id"]]
            assert rec["image"] is not None
            img_path = EXAM_DIR / rec["image"]
            assert img_path.is_file()
            raw_b64 = src["image"].split(",", 1)[1]
            assert img_path.read_bytes() == base64.b64decode(raw_b64)
