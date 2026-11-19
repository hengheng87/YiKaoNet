"""Tests for the reference & co-note ingestion workflow (PDF, plain text, images, dedup, init-exam)."""

from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from backend.config import EXAMS_DIR
from backend.ingestion import (
    commit_questions_import,
    extract_pdf_source,
    init_exam,
    parse_plain_text_mcqs,
    prepare_staging_bundle,
    scan_exam_duplicates,
)
from scripts.validate_data import validate_exam_dir


def _make_solid_png(width: int, height: int, rgb: tuple[int, int, int] = (30, 90, 200)) -> bytes:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw_row = b"\x00" + bytes(rgb) * width
    compressed = zlib.compress(raw_row * height)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )


def test_init_exam_and_import_new_unit(tmp_path: Path):
    exams_dir = tmp_path / "exams"
    db_path = tmp_path / "ingest.db"
    exam_dir = init_exam(
        exams_dir,
        slug="cmu-int3-neuro",
        title="三上第三次整合考：神經系統",
        notebook_id="00000000-0000-0000-0000-000000000001",
    )
    assert (exam_dir / "exam.json").is_file()

    report = commit_questions_import(
        exams_dir,
        db_path,
        "cmu-int3-neuro",
        [
            {
                "year": "114 學年度",
                "yearGroup": "114",
                "stem": "下列何者為腦幹中腦的構造？",
                "options": {"A": "黑質", "B": "橄欖核", "C": "齒狀核", "D": "視丘"},
                "answer": "A",
                "explanations": ["黑質位於中腦（midbrain）。"],
            }
        ],
        unit_code="1125_Brainstem",
        unit_meta={
            "unitTitle": "11/25 神經解剖：腦幹",
            "shortLabel": "11/25 腦幹",
            "session": "A",
            "subject": "General",
            "subjectTitle": "綜合學科",
            "prof": "測試教授",
            "examRange": "A卷 Q1–10",
            "unitUrl": "https://notebook.google.com/",
        },
    )
    assert report["newUnit"] is True
    assert report["added"] == 1
    assert validate_exam_dir(exam_dir)[0] == []


def test_extract_pdf_text_and_images_and_staging(tmp_path: Path):
    fitz = pytest.importorskip("fitz")
    exams_dir = tmp_path / "exams"
    staging_dir = tmp_path / "staging"
    shutil.copytree(EXAMS_DIR, exams_dir)

    pdf_path = tmp_path / "co_note.pdf"
    png_bytes = _make_solid_png(100, 100)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Q1. Which structure releases Ca2+ in skeletal muscle?\n(A) RyR1\n(B) SERCA\nAns: A")
    page.insert_image(fitz.Rect(72, 140, 172, 240), stream=png_bytes)
    doc.save(str(pdf_path))
    doc.close()

    img_out = staging_dir / "pdf_imgs"
    res = extract_pdf_source(pdf_path, extract_images_dir=img_out)
    assert res["pageCount"] == 1
    assert "RyR1" in res["fullText"]
    assert len(res["images"]) == 1
    assert res["images"][0]["width"] == 100
    assert Path(res["images"][0]["path"]).is_file()

    parsed = parse_plain_text_mcqs(res["fullText"])
    assert len(parsed) == 1
    assert parsed[0]["answer"] == "A"

    staged = prepare_staging_bundle(
        exams_dir,
        staging_dir,
        exam_slug="cmu-int2-msk",
        unit_code="1014_Physio1",
        source_name="co_note.pdf",
        raw_text=res["fullText"],
        parsed_questions=parsed,
        extracted_images=res["images"],
    )
    assert Path(staged["stagingFile"]).is_file()
    assert staged["parsedCount"] == 1


def test_parse_plain_text_mcqs_variants():
    raw_txt = """
1. [113] 關於骨骼肌收縮機制的敘述，何者正確？
(A) 肌鈣蛋白結合鈣離子後使橫橋結合
(B) ATP 水解發生在肌動蛋白上
(C) 橫橋與肌動蛋白永久鍵結
(D) 肌漿網不參與鈣離子儲存
答案：A
詳解：Troponin C 結合鈣離子後移動 tropomyosin 暴露結合位。

第2題 下列哪個藥物屬於直接作用膽鹼致效劑？
A. Bethanechol
B. Physostigmine
C. Atropine
D. Succinylcholine
正解：A, B
解析：假設申覆並列 A 與 B 給分。
"""
    qs = parse_plain_text_mcqs(raw_txt)
    assert len(qs) == 2
    assert qs[0]["yearGroup"] == "113"
    assert qs[0]["answer"] == "A"
    assert qs[0]["hasErrata"] is False

    assert qs[1]["answer"] == "A"
    assert qs[1]["acceptedAnswers"] == ["A", "B"]
    assert qs[1]["hasErrata"] is True


def test_commit_import_with_external_image_and_cross_dup_detection(tmp_path: Path):
    exams_copy = tmp_path / "exams"
    shutil.copytree(EXAMS_DIR, exams_copy)
    db_path = tmp_path / "ingest_dup.db"

    # Grab an existing stem from 1016_Physio2 to test cross-unit duplicate marking
    physio2 = json.loads(
        (exams_copy / "cmu-int2-msk" / "units" / "1016_Physio2.json").read_text(
            encoding="utf-8"
        )
    )
    existing_stem = physio2["questions"][0]["stem"]

    ext_png = tmp_path / "slide_diagram.png"
    ext_png.write_bytes(_make_solid_png(120, 90))

    report = commit_questions_import(
        exams_copy,
        db_path,
        "cmu-int2-msk",
        [
            {
                "year": "114 學年度",
                "yearGroup": "114",
                "stem": existing_stem,
                "image": str(ext_png),
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                "answer": "A",
                "explanations": ["來自共筆圖片與跨單元重複測試"],
            }
        ],
        unit_code="1014_Physio1",
        auto_mark_cross_dup=True,
    )
    assert report["added"] == 1
    assert report["crossDupMarked"] == 1
    assert report["imagesImported"] == 1
    assert validate_exam_dir(exams_copy / "cmu-int2-msk")[0] == []

    physio1 = json.loads(
        (exams_copy / "cmu-int2-msk" / "units" / "1014_Physio1.json").read_text(
            encoding="utf-8"
        )
    )
    added_q = physio1["questions"][-1]
    assert added_q["isCrossDup"] is True
    assert added_q["image"].startswith("images/slide_diagram-")
    assert (exams_copy / "cmu-int2-msk" / added_q["image"]).is_file()


def test_scan_exam_duplicates():
    pairs = scan_exam_duplicates(EXAMS_DIR / "cmu-int2-msk", similarity_threshold=0.92)
    assert len(pairs) > 0
