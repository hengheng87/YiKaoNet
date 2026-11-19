"""FastAPI application entry point for YiKao."""

from __future__ import annotations

import mimetypes

# Windows registry frequently maps .js to text/plain, breaking <script type="module">.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import BLOCKS_CATALOG_PATH, DB_PATH, EXAMS_DIR, FRONTEND_DIR
from backend.database import get_connection, init_db
from backend.routers import exams, export, progress, questions
from backend.sync_data import sync_all_exams


def create_app(
    *,
    db_path: Path | None = None,
    exams_dir: Path | None = None,
    frontend_dir: Path | None = None,
    blocks_catalog_path: Path | None = None,
) -> FastAPI:
    resolved_db = db_path or DB_PATH
    resolved_exams = exams_dir or EXAMS_DIR
    resolved_frontend = frontend_dir or FRONTEND_DIR
    resolved_blocks_catalog = (
        blocks_catalog_path if blocks_catalog_path is not None else BLOCKS_CATALOG_PATH
    )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        conn = get_connection(resolved_db)
        init_db(conn)
        sync_all_exams(conn, exams_dir=resolved_exams)
        app_instance.state.db = conn
        app_instance.state.exams_dir = resolved_exams
        app_instance.state.frontend_dir = resolved_frontend
        app_instance.state.blocks_catalog_path = resolved_blocks_catalog
        try:
            yield
        finally:
            conn.close()

    application = FastAPI(
        title="易考網 YiKao API",
        version="2.0.0",
        description="模組化醫學整合考互動題庫系統",
        lifespan=lifespan,
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000)

    application.include_router(exams.router)
    application.include_router(questions.router)
    application.include_router(progress.router)
    application.include_router(export.router)

    @application.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(resolved_frontend / "index.html")

    js_dir = resolved_frontend / "js"
    styles_dir = resolved_frontend / "styles"
    if js_dir.is_dir():
        application.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    if styles_dir.is_dir():
        application.mount(
            "/styles", StaticFiles(directory=str(styles_dir)), name="styles"
        )

    return application


app = create_app()
