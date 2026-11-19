"""Centralized path and runtime configuration for YiKao backend."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("YIKAO_DATA_DIR", str(BASE_DIR / "data")))
EXAMS_DIR = Path(os.getenv("YIKAO_EXAMS_DIR", str(DATA_DIR / "exams")))
STAGING_DIR = Path(os.getenv("YIKAO_STAGING_DIR", str(DATA_DIR / "staging")))
DB_PATH = Path(os.getenv("YIKAO_DB_PATH", str(DATA_DIR / "yikao.db")))
FRONTEND_DIR = BASE_DIR / "frontend"
