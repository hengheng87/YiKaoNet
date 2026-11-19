"""CLI utility to build a self-contained single-file offline HTML quiz."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import DB_PATH, EXAMS_DIR, FRONTEND_DIR
from backend.database import get_connection, init_db
from backend.offline_builder import build_offline_html
from backend.sync_data import sync_all_exams


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="將易考網題庫與前後端介面建置為單一可離線開啟／嵌入的 HTML 檔"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--exam",
        default="cmu-int2-msk",
        help="要建置的考科 slug（預設：cmu-int2-msk）",
    )
    group.add_argument(
        "--all-exams",
        action="store_true",
        help="將 data/exams/ 下全部考科合併建置於同一份離線 HTML",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="輸出 HTML 路徑（預設：dist/yikao-<slug>-offline.html 或 dist/yikao-all-offline.html）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    exam_slugs = None if args.all_exams else [args.exam]
    default_name = (
        "yikao-all-offline.html" if args.all_exams else f"yikao-{args.exam}-offline.html"
    )
    out_path = Path(args.out) if args.out else BASE_DIR / "dist" / default_name

    conn = get_connection(DB_PATH)
    try:
        init_db(conn)
        sync_all_exams(conn, exams_dir=EXAMS_DIR)
        html = build_offline_html(
            conn, EXAMS_DIR, FRONTEND_DIR, exam_slugs=exam_slugs
        )
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Built offline HTML: {out_path} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
