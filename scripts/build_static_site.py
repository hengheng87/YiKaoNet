"""Static site generator for zero-cost GitHub Pages / Cloudflare Pages deployment."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import EXAMS_DIR, FRONTEND_DIR
from backend.database import init_db
from backend.offline_builder import build_offline_html
from backend.queries import query_exam_questions
from backend.routers.exams import get_exam_detail, list_exams
from backend.sync_data import sync_all_exams


def build_static_site(
    exams_dir: Path,
    frontend_dir: Path,
    out_dir: Path,
    *,
    db_path: Path | None = None,
    include_offline_html: bool = True,
) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copytree(frontend_dir / "styles", out_dir / "styles")
    shutil.copytree(frontend_dir / "js", out_dir / "js")

    index_html = (frontend_dir / "index.html").read_text(encoding="utf-8")
    marker = '<script type="module" src="./js/main.js"></script>'
    if marker not in index_html:
        raise RuntimeError(f"Could not find module script tag '{marker}' in index.html")
    injected = f"<script>window.__YIKAO_STATIC_MODE__ = true;</script>\n  {marker}"
    (out_dir / "index.html").write_text(
        index_html.replace(marker, injected, 1),
        encoding="utf-8",
    )

    conn = sqlite3.connect(str(db_path) if db_path else ":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    total_questions = 0
    total_images = 0
    try:
        init_db(conn)
        sync_all_exams(conn, exams_dir=exams_dir, force=True)

        summaries = list_exams(conn)
        static_api_dir = out_dir / "static-api"
        static_api_dir.mkdir(parents=True, exist_ok=True)
        (static_api_dir / "exams.json").write_text(
            json.dumps([s.model_dump() for s in summaries], ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

        for summary in summaries:
            slug = summary.slug
            exam_out = static_api_dir / "exams" / slug
            exam_out.mkdir(parents=True, exist_ok=True)

            detail = get_exam_detail(slug, conn)
            (exam_out / "detail.json").write_text(
                json.dumps(detail.model_dump(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            src_images = exams_dir / slug / "images"
            if src_images.is_dir():
                dst_images = exam_out / "images"
                dst_images.mkdir(parents=True, exist_ok=True)
                for img_file in sorted(src_images.iterdir()):
                    if img_file.is_file():
                        shutil.copy2(img_file, dst_images / img_file.name)
                        total_images += 1

            _, questions = query_exam_questions(conn, slug)
            q_dicts: list[dict] = []
            api_prefix = f"/api/exams/{slug}/images/"
            for q in questions:
                item = q.model_dump()
                if item.get("image") and item["image"].startswith(api_prefix):
                    filename = item["image"][len(api_prefix) :]
                    item["image"] = f"./static-api/exams/{slug}/images/{filename}"
                q_dicts.append(item)

            total_questions += len(q_dicts)
            (exam_out / "questions.json").write_text(
                json.dumps(
                    {
                        "examSlug": slug,
                        "total": len(q_dicts),
                        "filtered": len(q_dicts),
                        "questions": q_dicts,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            if include_offline_html:
                offline_html = build_offline_html(
                    conn, exams_dir, frontend_dir, exam_slugs=[slug]
                )
                (exam_out / "offline.html").write_text(offline_html, encoding="utf-8")

        return {
            "exams": len(summaries),
            "questions": total_questions,
            "images": total_images,
            "outDir": str(out_dir),
        }
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="建置可免費託管於 GitHub Pages / Cloudflare Pages 的靜態網站目錄"
    )
    parser.add_argument(
        "--out",
        default=str(BASE_DIR / "dist" / "site"),
        help="輸出靜態網站目錄（預設：dist/site）",
    )
    parser.add_argument(
        "--no-offline-html",
        action="store_true",
        help="略過產生各考科可供下載的離線 offline.html",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    stats = build_static_site(
        EXAMS_DIR,
        FRONTEND_DIR,
        Path(args.out),
        include_offline_html=not args.no_offline_html,
    )
    print(
        f"Built static site at {stats['outDir']}: "
        f"{stats['exams']} exam(s), {stats['questions']} question(s), {stats['images']} image(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
