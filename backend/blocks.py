"""Block catalog aggregation combining blocks.json blueprint with SQLite exams."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.config import BLOCKS_CATALOG_PATH
from backend.queries import compute_exam_counts
from backend.schemas import (
    BlockItem,
    BlockSubjectTag,
    BlocksCatalogResponse,
    SourceInfo,
    TermSection,
)

DEFAULT_CATALOG_META = {
    "version": "1.0.0",
    "title": "易考網 YiKao 整合考系統題庫",
    "subtitle": "依年級學期與器官系統 Block 分類，點選系統即可進入共筆單元作題畫面",
    "terms": [],
    "blocks": [],
}


def load_blocks_catalog_file(catalog_path: Path | None) -> dict:
    if catalog_path is None or not catalog_path.is_file():
        return {
            "version": DEFAULT_CATALOG_META["version"],
            "title": DEFAULT_CATALOG_META["title"],
            "subtitle": DEFAULT_CATALOG_META["subtitle"],
            "terms": [],
            "blocks": [],
        }
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def _pick_str(*candidates: object, default: str = "") -> str:
    for val in candidates:
        if isinstance(val, str) and val.strip():
            return val.strip()
    return default


def _pick_int(*candidates: object, default: int = 999) -> int:
    for val in candidates:
        if val is not None and not isinstance(val, bool):
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return default


def build_blocks_catalog(
    conn: sqlite3.Connection,
    catalog_path: Path | None = BLOCKS_CATALOG_PATH,
    *,
    only_slugs: set[str] | None = None,
) -> BlocksCatalogResponse:
    raw_catalog = load_blocks_catalog_file(catalog_path)

    exam_rows = conn.execute("SELECT * FROM exams ORDER BY slug ASC").fetchall()
    exams_by_slug: dict[str, dict] = {}
    for row in exam_rows:
        slug = row["slug"]
        counts = compute_exam_counts(conn, slug)
        subj_counts = {
            r["subject"]: int(r["cnt"])
            for r in conn.execute(
                "SELECT subject, COUNT(*) AS cnt FROM questions WHERE exam_slug = ? GROUP BY subject",
                (slug,),
            ).fetchall()
        }
        block_meta = json.loads(row["block_json"] or "{}") if "block_json" in row.keys() else {}
        exams_by_slug[slug] = {
            "row": row,
            "counts": counts,
            "subj_counts": subj_counts,
            "source": json.loads(row["source_json"]),
            "subjects": json.loads(row["subjects_json"]),
            "block": block_meta if isinstance(block_meta, dict) else {},
        }

    terms_map: dict[str, TermSection] = {}
    for raw_term in raw_catalog.get("terms", []):
        code = str(raw_term["code"]).strip()
        terms_map[code] = TermSection(
            code=code,
            label=str(raw_term.get("label", code)).strip(),
            shortLabel=str(raw_term.get("shortLabel", code)).strip(),
            description=str(raw_term.get("description", "")).strip(),
            order=int(raw_term.get("order", 999)),
        )

    def _ensure_term_section(
        term_code: str, block_meta: dict
    ) -> TermSection:
        if term_code in terms_map:
            return terms_map[term_code]
        if term_code == "other":
            label = _pick_str(block_meta.get("termLabel"), default="其他整合考科")
            short_label = _pick_str(block_meta.get("termShortLabel"), default="其他")
        else:
            label = _pick_str(block_meta.get("termLabel"), default=term_code)
            short_label = _pick_str(block_meta.get("termShortLabel"), default=label)
        section = TermSection(
            code=term_code,
            label=label,
            shortLabel=short_label,
            description="",
            order=999,
        )
        terms_map[term_code] = section
        return section

    seen_slugs: set[str] = set()

    for entry in raw_catalog.get("blocks", []):
        slug = str(entry["slug"]).strip()
        seen_slugs.add(slug)
        if only_slugs is not None and slug not in only_slugs:
            continue

        exam_info = exams_by_slug.get(slug)
        counts = exam_info["counts"] if exam_info else None
        is_ready = bool(exam_info and counts and counts["total"] > 0)
        exam_block = exam_info["block"] if exam_info else {}
        exam_row = exam_info["row"] if exam_info else None

        term_code = _pick_str(
            exam_block.get("term") if is_ready else "",
            entry.get("term"),
            default="other",
        )
        section = _ensure_term_section(term_code, exam_block)

        if is_ready and exam_info and exam_row:
            subjects = [
                BlockSubjectTag(
                    label=s["label"],
                    emoji=s.get("emoji", ""),
                    questionCount=exam_info["subj_counts"].get(s["code"], 0),
                )
                for s in exam_info["subjects"]
            ]
            if not subjects:
                subjects = [
                    BlockSubjectTag(label=str(name))
                    for name in entry.get("subjectsPreview", [])
                ]
            source_obj = SourceInfo(**exam_info["source"])
            source_hint = _pick_str(
                entry.get("sourceHint"),
                f"對應知識庫：{source_obj.name}" if source_obj.name else "",
            )
            item = BlockItem(
                slug=slug,
                term=term_code,
                examLabel=_pick_str(exam_block.get("examLabel"), entry.get("examLabel")),
                name=_pick_str(
                    exam_block.get("name"),
                    entry.get("name"),
                    exam_row["title"],
                    default=slug,
                ),
                englishName=_pick_str(
                    exam_block.get("englishName"),
                    entry.get("englishName"),
                    exam_row["badge"],
                ),
                icon=_pick_str(exam_block.get("icon"), entry.get("icon"), default="📚"),
                accent=_pick_str(
                    exam_block.get("accent"), entry.get("accent"), default="indigo"
                ),
                order=_pick_int(exam_block.get("order"), entry.get("order"), default=999),
                status="ready",
                description=_pick_str(
                    exam_block.get("description"),
                    entry.get("description"),
                    exam_row["subtitle"],
                ),
                sourceHint=source_hint,
                source=source_obj,
                subjects=subjects,
                totalQuestions=counts["total"],
                uniqueQuestions=counts["unique"],
                errataCount=counts["errata"],
                unitCount=counts["unit_count"],
            )
        else:
            subjects = [
                BlockSubjectTag(label=str(name))
                for name in entry.get("subjectsPreview", [])
            ]
            item = BlockItem(
                slug=slug,
                term=term_code,
                examLabel=_pick_str(entry.get("examLabel")),
                name=_pick_str(entry.get("name"), default=slug),
                englishName=_pick_str(entry.get("englishName")),
                icon=_pick_str(entry.get("icon"), default="📚"),
                accent=_pick_str(entry.get("accent"), default="indigo"),
                order=_pick_int(entry.get("order"), default=999),
                status="planned",
                description=_pick_str(entry.get("description")),
                sourceHint=_pick_str(entry.get("sourceHint"), default="尚未匯入共筆題庫"),
                source=SourceInfo(**exam_info["source"]) if exam_info else None,
                subjects=subjects,
                totalQuestions=0,
                uniqueQuestions=0,
                errataCount=0,
                unitCount=0,
            )

        section.blocks.append(item)

    # Include any exams present in SQLite that are not listed in blocks.json
    for slug, exam_info in exams_by_slug.items():
        if slug in seen_slugs:
            continue
        if only_slugs is not None and slug not in only_slugs:
            continue

        exam_row = exam_info["row"]
        counts = exam_info["counts"]
        exam_block = exam_info["block"]
        is_ready = counts["total"] > 0

        term_code = _pick_str(exam_block.get("term"), default="other")
        section = _ensure_term_section(term_code, exam_block)

        source_obj = SourceInfo(**exam_info["source"])
        subjects = [
            BlockSubjectTag(
                label=s["label"],
                emoji=s.get("emoji", ""),
                questionCount=exam_info["subj_counts"].get(s["code"], 0),
            )
            for s in exam_info["subjects"]
        ]
        item = BlockItem(
            slug=slug,
            term=term_code,
            examLabel=_pick_str(exam_block.get("examLabel"), exam_row["badge"]),
            name=_pick_str(exam_block.get("name"), exam_row["title"], default=slug),
            englishName=_pick_str(exam_block.get("englishName"), exam_row["badge"]),
            icon=_pick_str(exam_block.get("icon"), default="📚"),
            accent=_pick_str(exam_block.get("accent"), default="indigo"),
            order=_pick_int(exam_block.get("order"), default=999),
            status="ready" if is_ready else "planned",
            description=_pick_str(exam_block.get("description"), exam_row["subtitle"]),
            sourceHint=f"對應知識庫：{source_obj.name}" if source_obj.name else "",
            source=source_obj,
            subjects=subjects,
            totalQuestions=counts["total"] if is_ready else 0,
            uniqueQuestions=counts["unique"] if is_ready else 0,
            errataCount=counts["errata"] if is_ready else 0,
            unitCount=counts["unit_count"] if is_ready else 0,
        )
        section.blocks.append(item)

    kept_sections: list[TermSection] = []
    for section in terms_map.values():
        if not section.blocks:
            continue
        section.blocks.sort(key=lambda b: (b.order, b.slug))
        section.readyCount = sum(1 for b in section.blocks if b.status == "ready")
        section.totalCount = len(section.blocks)
        kept_sections.append(section)

    kept_sections.sort(key=lambda s: (s.order, s.code))

    ready_blocks = sum(s.readyCount for s in kept_sections)
    total_blocks = sum(s.totalCount for s in kept_sections)
    planned_blocks = total_blocks - ready_blocks
    total_questions = sum(
        b.totalQuestions
        for s in kept_sections
        for b in s.blocks
        if b.status == "ready"
    )
    total_units = sum(
        b.unitCount
        for s in kept_sections
        for b in s.blocks
        if b.status == "ready"
    )

    return BlocksCatalogResponse(
        version=str(raw_catalog.get("version", DEFAULT_CATALOG_META["version"])),
        title=str(raw_catalog.get("title", DEFAULT_CATALOG_META["title"])),
        subtitle=str(raw_catalog.get("subtitle", DEFAULT_CATALOG_META["subtitle"])),
        readyBlocks=ready_blocks,
        plannedBlocks=planned_blocks,
        totalBlocks=total_blocks,
        totalQuestions=total_questions,
        totalUnits=total_units,
        terms=kept_sections,
    )
