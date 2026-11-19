"""CLI utility to force-sync modular exam JSON files into SQLite."""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import DB_PATH, EXAMS_DIR
from backend.database import get_connection, init_db
from backend.sync_data import sync_all_exams


def main() -> int:
    conn = get_connection(DB_PATH)
    try:
        init_db(conn)
        summary = sync_all_exams(conn, exams_dir=EXAMS_DIR, force=True)
    finally:
        conn.close()

    print(
        f"Synced {summary['exams']} exam(s), {summary['units']} unit(s), "
        f"{summary['questions']} question(s) into {DB_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
