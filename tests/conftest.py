"""Pytest fixtures providing an isolated SQLite database and FastAPI TestClient."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import EXAMS_DIR, FRONTEND_DIR
from backend.main import create_app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test_yikao.db"
    app = create_app(
        db_path=db_path,
        exams_dir=EXAMS_DIR,
        frontend_dir=FRONTEND_DIR,
    )
    with TestClient(app) as test_client:
        yield test_client
