"""Build a self-contained single-file offline HTML bundle from modular frontend & exam data."""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from fastapi import HTTPException

from backend.blocks import build_blocks_catalog
from backend.config import BLOCKS_CATALOG_PATH
from backend.queries import query_exam_questions
from backend.routers.exams import get_exam_detail, list_exams

CSS_FILES = [
    "tokens.css",
    "utilities.css",
    "components.css",
]

JS_BUNDLE_ORDER = [
    "api.js",
    "markdown.js",
    "components/toast.js",
    "notion.js",
    "store.js",
    "components/blockPortal.js",
    "components/header.js",
    "components/filters.js",
    "components/questionList.js",
    "components/resumeBar.js",
    "components/modals.js",
    "main.js",
]

IMPORT_STMT_RE = re.compile(
    r"^\s*import\s+(?:[\s\S]*?\s+from\s+)?['\"][^'\"]+['\"]\s*;?\s*$",
    re.MULTILINE,
)
EXPORT_DECL_RE = re.compile(
    r"^export\s+(?=(?:async\s+)?(?:function|const|let|var|class)\b)",
    re.MULTILINE,
)
TOP_LEVEL_DECL_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
STYLESHEET_TAG_RE = re.compile(
    r'\s*<link\s+rel="stylesheet"\s+href="\.?/styles/[^"]+"\s*/?>',
    re.IGNORECASE,
)
MODULE_SCRIPT_TAG_RE = re.compile(
    r'<script\s+type="module"\s+src="\.?/js/main\.js"\s*></script>',
    re.IGNORECASE,
)


def strip_esm_syntax(js_source: str) -> str:
    without_imports = IMPORT_STMT_RE.sub("", js_source)
    return EXPORT_DECL_RE.sub("", without_imports).strip()


def check_no_duplicate_top_level_symbols(modules: list[tuple[str, str]]) -> None:
    locations: dict[str, list[str]] = defaultdict(list)
    for rel_name, source in modules:
        for match in TOP_LEVEL_DECL_RE.finditer(source):
            locations[match.group(1)].append(rel_name)

    duplicates = {k: v for k, v in locations.items() if len(v) > 1}
    if duplicates:
        raise RuntimeError(
            f"Duplicate top-level JS symbols detected during offline bundling: {duplicates}"
        )


def _encode_image_data_uri(exam_dir: Path, image_url: str | None) -> str | None:
    if not image_url:
        return None
    filename = image_url.rsplit("/", 1)[-1]
    img_path = (exam_dir / "images" / filename).resolve()
    images_root = (exam_dir / "images").resolve()
    if not img_path.is_relative_to(images_root) or not img_path.is_file():
        raise FileNotFoundError(f"Missing image asset for offline export: {img_path}")

    ext = img_path.suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_offline_html(
    conn: sqlite3.Connection,
    exams_dir: Path,
    frontend_dir: Path,
    exam_slugs: list[str] | None = None,
    *,
    blocks_catalog_path: Path | None = None,
) -> str:
    all_summaries = list_exams(conn)
    if exam_slugs is not None:
        wanted = set(exam_slugs)
        selected_summaries = [s for s in all_summaries if s.slug in wanted]
        missing = wanted - {s.slug for s in selected_summaries}
        if missing:
            raise HTTPException(
                status_code=404, detail=f"找不到題庫：{', '.join(sorted(missing))}"
            )
    else:
        selected_summaries = all_summaries

    if not selected_summaries:
        raise HTTPException(status_code=404, detail="找不到可供匯出的題庫")

    details_map: dict[str, dict] = {}
    questions_map: dict[str, list[dict]] = {}

    for summary in selected_summaries:
        slug = summary.slug
        detail = get_exam_detail(slug, conn)
        _, questions = query_exam_questions(conn, slug)
        exam_dir = exams_dir / slug

        q_dicts: list[dict] = []
        for q in questions:
            item = q.model_dump()
            item["image"] = _encode_image_data_uri(exam_dir, item.get("image"))
            q_dicts.append(item)

        details_map[slug] = detail.model_dump()
        questions_map[slug] = q_dicts

    resolved_catalog = (
        blocks_catalog_path if blocks_catalog_path is not None else BLOCKS_CATALOG_PATH
    )
    selected_slugs = {s.slug for s in selected_summaries}
    blocks_catalog = build_blocks_catalog(
        conn, catalog_path=resolved_catalog, only_slugs=selected_slugs
    )

    offline_payload = {
        "singleExamMode": len(selected_summaries) == 1,
        "blocks": blocks_catalog.model_dump(),
        "exams": [s.model_dump() for s in selected_summaries],
        "details": details_map,
        "questions": questions_map,
    }
    escaped_json = json.dumps(offline_payload, ensure_ascii=False).replace("</", "<\\/")

    css_parts = [
        (frontend_dir / "styles" / css_name).read_text(encoding="utf-8")
        for css_name in CSS_FILES
    ]
    inline_style = f"<style>\n{chr(10).join(css_parts)}\n  </style>"

    raw_modules = [
        (
            js_rel,
            (frontend_dir / "js" / js_rel).read_text(encoding="utf-8"),
        )
        for js_rel in JS_BUNDLE_ORDER
    ]
    check_no_duplicate_top_level_symbols(raw_modules)

    stripped_parts = [
        f"// === {js_rel} ===\n{strip_esm_syntax(src)}"
        for js_rel, src in raw_modules
    ]
    bundled_js = (
        "(function () {\n'use strict';\n\n"
        + "\n\n".join(stripped_parts)
        + "\n})();"
    ).replace("</script", "<\\/script")

    html = (frontend_dir / "index.html").read_text(encoding="utf-8")

    # Replace the first stylesheet link with the combined inline <style>, remove the rest
    first_replaced = False

    def _replace_style(_match: re.Match) -> str:
        nonlocal first_replaced
        if not first_replaced:
            first_replaced = True
            return "\n  " + inline_style
        return ""

    html = STYLESHEET_TAG_RE.sub(_replace_style, html)

    inline_scripts = (
        f"<script>\nwindow.__YIKAO_OFFLINE_DATA__ = {escaped_json};\n</script>\n"
        f"  <script>\n{bundled_js}\n  </script>"
    )
    if not MODULE_SCRIPT_TAG_RE.search(html):
        raise RuntimeError("Could not locate <script type='module' src='/js/main.js'> tag")
    html = MODULE_SCRIPT_TAG_RE.sub(lambda _: inline_scripts, html, count=1)
    return html
