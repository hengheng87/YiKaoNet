"""Convenient local startup runner for YiKao web server."""

from __future__ import annotations

import os
import uvicorn


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload_flag = os.getenv("YIKAO_RELOAD", "false").lower() in ("1", "true", "yes")
    print(f"易考網 YiKao 啟動中：http://{host}:{port}")
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload_flag,
    )


if __name__ == "__main__":
    main()
