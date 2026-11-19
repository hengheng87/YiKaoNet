# 易考網 YiKao 2.0

模組化、可免費託管於 GitHub Pages 的醫學整合考互動題庫與共筆匯入系統。

本專案將原先 `2.33 MB` 的單一 HTML 檔重構為極省 Token 的模組化題庫與純靜態檢視架構，核心資料源自 NotebookLM「[大三整合2 知識庫](https://notebook.google.com/notebook/01b3322a-9c0a-498f-91ce-4c29f24657f5)」，完整收錄中國醫三上第二次整合考（骨骼肌肉系統）22 個共筆單元、共 547 題考古題與大 R 題庫。

## 核心特色

- **純檢視靜態網站（可 \$0 永久免費託管於 GitHub Pages）**：
  - 所有同學免登入即可於線上刷題、模擬考、關鍵字搜尋、續讀跳轉與匯出 Notion 摺疊題庫。
  - 內建一鍵下載「單檔離線互動 HTML」與作答紀錄 JSON 備份匯出／匯入。
- **模組化題庫結構（大幅降低 AI 協作 Token 消耗）**：
  - `data/exams/<slug>/exam.json`：考科設定、場次、科目與單元索引。
  - `data/exams/<slug>/units/<unitCode>.json`：依共筆單元分檔（每檔約 9–124 KB），修改單題或勘誤不需載入全體題庫。
  - `data/exams/<slug>/images/*.jpg`：從 base64 抽離並以 SHA-256 去重的圖片資產。
- **完整共筆與參考資料匯入工作流 (`backend/ingestion/` & `scripts/ingest.py`)**：
  - **建立新考科 (`init-exam`)**：一鍵建立新考試目錄與 `exam.json`。
  - **PDF 共筆萃取 (`extract-pdf`)**：透過 PyMuPDF 萃取出純文字與內嵌圖片，並嘗試剖析選擇題草稿存入 `data/staging/`。
  - **文字／Markdown 剖析 (`parse-text`)**：自動辨識台灣醫學系共筆常見題號、`(A)-(G)` 選項、答案／多解送分與詳解段落。
  - **NotebookLM 整合 (`from-notebooklm`)**：透過 `nlm` CLI 直接從筆記本來源整理題目並匯入。
  - **跨單元去重與圖片去重匯入 (`import-json` / `check-duplicates`)**：支援 `--auto-mark-cross-dup` 比對跨單元重複題、自動匯入並 SHA-256 去重圖片資產、通過 Schema 驗證後原子寫回 JSON。

## 專案目錄結構

```text
├── backend/                  # 本機開發／匯入／建置核心
│   ├── main.py               # FastAPI 本機開發伺服器與靜態資源掛載
│   ├── config.py             # 路徑與環境變數設定
│   ├── database.py           # SQLite Schema 與連線管理
│   ├── schemas.py            # Pydantic v2 資料模型
│   ├── queries.py            # 題庫查詢與篩選邏輯
│   ├── sync_data.py          # JSON -> SQLite 增量同步引擎
│   ├── offline_builder.py    # 單檔離線互動 HTML 建置器
│   ├── ingestion/            # 共筆萃取 (extractors)、剖析去重 (parser)、提交流程 (pipeline)
│   └── routers/              # API 路由 (exams / questions / progress / export)
├── frontend/                 # 原生 ES Modules 前端（支援 FastAPI、GitHub Pages 靜態模式與單檔離線模式）
├── data/
│   ├── schema/               # exam.schema.json / unit.schema.json
│   └── exams/cmu-int2-msk/   # 骨骼肌肉系統 22 單元 JSON 與 9 張圖片
├── scripts/
│   ├── ingest.py             # 共筆／PDF／NotebookLM 統一匯入工作流 CLI
│   ├── import_questions.py   # 舊版相容匯入 CLI
│   ├── validate_data.py      # 題庫 Schema 與圖片完整性檢查 CLI
│   ├── build_static_site.py  # 產生 GitHub Pages 靜態網站 (`dist/site/`)
│   ├── build_offline_html.py # 產生單檔離線 HTML
│   ├── sync_db.py            # 強制重建本機 SQLite 索引 CLI
│   └── migrate_v106.py       # 舊版單檔 HTML 無損拆解腳本
├── .github/workflows/        # GitHub Actions (PR 驗證 ci.yml + 自動發佈 deploy-pages.yml)
├── tests/                    # pytest 資料完整性、匯入工作流、靜態建置與 API 測試
└── run.py                    # 本機開發啟動腳本
```

## 上架到 GitHub Pages（\$0 免費永久公開網站）

1. 將本專案 Push 到您的 GitHub Repository（預設分支 `main`）。
2. 前往 GitHub Repo 的 **Settings → Pages**，將 **Build and deployment → Source** 改為 **GitHub Actions**。
3. 之後每次更新 `data/exams/` 下的單元 JSON 並 push 到 `main`，[.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml) 會自動執行：
   - `python scripts/validate_data.py`（驗證所有題庫與圖片）
   - `python -m pytest -v`（執行全部測試）
   - `python scripts/build_static_site.py --out dist/site`（建置靜態網站與可下載離線包）
   - 自動部署至 `https://<您的帳號>.github.io/<專案名稱>/`。

## 本機開發與日常維護

```bash
# 1. 安裝依賴（若需 PDF 萃取可加裝 pip install pymupdf）
pip install -r requirements.txt

# 2. 本機啟動測試伺服器（http://127.0.0.1:8000）
python run.py

# 3. 驗證題庫與執行測試
python scripts/validate_data.py
python -m pytest -v

# 4. 本機預覽建置後的靜態網站目錄
python scripts/build_static_site.py --out dist/site
```

## 從新共筆或參考資料匯入題目

```bash
# 建立全新考科（選用）
python scripts/ingest.py init-exam cmu-int3-neuro --title "大三第三次整合考：神經系統"

# 從 PDF 共筆萃取純文字與內嵌圖片，並產出待審草稿（存於 data/staging/）
python scripts/ingest.py extract-pdf ./notes/neuro_ch1.pdf --exam cmu-int2-msk --unit 1014_Physio1 --extract-images --parse-mcq

# 或從純文字／Markdown 共筆剖析草稿
python scripts/ingest.py parse-text ./notes/raw.txt --exam cmu-int2-msk --unit 1014_Physio1

# 審閱／修正草稿 JSON 後試算匯入（自動標記跨單元重複題）
python scripts/ingest.py import-json data/staging/cmu-int2-msk_1014_Physio1_draft.json --exam cmu-int2-msk --unit 1014_Physio1 --auto-mark-cross-dup --dry-run

# 確認無誤後正式寫入單元 JSON（完成後 git push 即自動更新公開網站）
python scripts/ingest.py import-json data/staging/cmu-int2-msk_1014_Physio1_draft.json --exam cmu-int2-msk --unit 1014_Physio1 --auto-mark-cross-dup

# 或直接從 NotebookLM 整理並匯入
python scripts/ingest.py from-notebooklm --exam cmu-int2-msk --unit 1014_Physio1 --prompt "整理最新考古題" --auto-mark-cross-dup

# 掃描考科內跨單元重複題
python scripts/ingest.py check-duplicates --exam cmu-int2-msk
```

## 授權條款

本專案採用 [MIT License](LICENSE) 開源釋出。
