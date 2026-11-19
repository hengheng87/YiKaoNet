# 貢獻指南 (Contributing)

歡迎透過 GitHub Pull Request 一起維護與擴充「易考網 YiKao」題庫！每次合併至 `main` 後，GitHub Actions 會自動驗證資料並重新建置發佈公開靜態網站。

## 提交題目勘誤或補充詳解

1. 到 `data/exams/<slug>/exam.json` 查找對應共筆的 `unitCode`。
2. 編輯 `data/exams/<slug>/units/<unitCode>.json` 內的該道題目：
   - 若為申覆多解或送分題，請更新 `acceptedAnswers`（例如 `["B", "D"]`）、`answerDisplay` 並將 `hasErrata` 設為 `true`。
   - 詳解支援基本行內 Markdown（`**粗體**`、`*斜體*`、`` `程式碼` ``、`[連結文字](https://...)`）。
3. 執行檢查確認格式、圖片路徑與所有測試全數通過：
   ```bash
   python scripts/validate_data.py
   python -m pytest -v
   ```

## 從共筆或 PDF 引入新單元／新考科

1. 新增考科：`python scripts/ingest.py init-exam <slug> --title "<考科名稱>"`
2. 萃取共筆：`python scripts/ingest.py extract-pdf <pdf> --exam <slug> --unit <unitCode> --extract-images --parse-mcq`（或 `parse-text` / `from-notebooklm`）。
3. 審閱 `data/staging/` 下的草稿後，使用 `python scripts/ingest.py import-json ... --auto-mark-cross-dup` 正式匯入，並執行 `validate_data.py` 與 `pytest -v` 確認無誤後提交 PR。
