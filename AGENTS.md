# AGENTS.md — AI Agent 協作與省 Token 指引

本專案專為低 Token 消耗的人機／AI 協作與 GitHub Pages 自動部署設計。修改程式或題庫時請遵守以下規則：

## 1. 題庫修改與共筆匯入原則（極度重要）

- **禁止一次讀取全部單元 JSON**：`data/exams/<slug>/units/` 內含多個共筆單元，切勿全部載入上下文。
- **定位與編輯步驟**：
  1. 先讀取目標考科的 `data/exams/<slug>/exam.json`（僅數十行），確認 `unitCode` 與對應的 `units/<unitCode>.json` 檔名。
  2. 只開啟並編輯目標 `units/<unitCode>.json` 檔案。
  3. 圖片請放於 `data/exams/<slug>/images/` 並於題目 `"image"` 欄位填寫相對路徑 `"images/<filename>.jpg"`（嚴禁再塞入 base64）。
- **每題欄位繼承**：共筆預設欄位（`unitTitle`, `session`, `subject`, `subjectTitle`, `prof`, `examRange`, `unitUrl`）定義於單元 JSON 頂層；僅在單題與單元預設不同時才於該題覆寫（例如 `1021_BonePath.json` 的少數 M65 補充題有不同 `prof`）。
- **引入新共筆／PDF 參考資料**：優先使用 `python scripts/ingest.py`（`extract-pdf`、`parse-text`、`from-notebooklm`、`import-json`、`check-duplicates`、`init-exam`），草稿集中暫存於 `data/staging/`（已列入 `.gitignore`），試算 `--dry-run` 確認無誤再提交至 `data/exams/`。

## 2. 程式碼架構與修改範圍

- **後端與匯入引擎 (`backend/`)**：
  - `config.py`：路徑設定（`DATA_DIR`, `EXAMS_DIR`, `STAGING_DIR`, `DB_PATH`, `FRONTEND_DIR`）。
  - `database.py` & `sync_data.py`：SQLite Schema（`exams`, `units`, `questions`, `user_progress`）與 SHA-256 增量同步。
  - `ingestion/`：`extractors.py`（PDF/文字/圖片/nlm）、`parser.py`（JSON/純文字題庫剖析與跨單元去重）、`pipeline.py`（考科建立、草稿暫存、原子驗證提交）。
  - `offline_builder.py`：將 CSS、ES Modules（需保持跨檔頂層符號唯一）與考科資料打包為單檔離線 HTML。
  - `queries.py` & `routers/`：本機 FastAPI 查詢與匯出端點（`exams.py`, `questions.py`, `progress.py`, `export.py`）。
- **前端 (`frontend/`)**：
  - 原生 ES Modules + CSS（無需 Node/Vite），以相對路徑 `./` 載入資源，同時支援 **本機 FastAPI**、**GitHub Pages 靜態模式 (`window.__YIKAO_STATIC_MODE__`)** 與 **單檔離線模式 (`window.__YIKAO_OFFLINE_DATA__`)**；新增頂層宣告時請維持跨檔案唯一命名。
  - `js/api.js` & `js/store.js` 負責資料來源切換與 `localStorage`（含 `v1.0.6` 自動遷移）。
  - `js/components/`：`header.js`、`filters.js`、`questionList.js`、`resumeBar.js`、`modals.js`、`toast.js`。
- **CLI 工具 (`scripts/`)**：
  - `ingest.py`、`import_questions.py`、`validate_data.py`、`build_static_site.py`、`build_offline_html.py`、`sync_db.py`。

## 3. 修改後必須執行的驗證

```bash
python scripts/validate_data.py
python -m pytest -v
```
