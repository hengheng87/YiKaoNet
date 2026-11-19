"""Batch question importer CLI (thin wrapper over backend.ingestion)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import DB_PATH, EXAMS_DIR
from backend.ingestion.extractors import run_nlm_query, run_nlm_source_list
from backend.ingestion.parser import extract_json_payload
from backend.ingestion.pipeline import commit_questions_import

SCHEMA_TEMPLATE = {
    "prompt_hint": (
        "請根據指定共筆來源整理考古題，嚴格輸出一個 ```json ... ``` 陣列，"
        "每題包含 year、yearGroup、stem、options (物件如 {\"A\":\"...\"})、"
        "answer、acceptedAnswers、answerDisplay、hasErrata、explanations (字串陣列)。"
    ),
    "unit": {
        "unitCode": "EXAMPLE_Unit1",
        "unitTitle": "範例單元標題",
        "shortLabel": "範例單元",
        "session": "A",
        "subject": "Physio",
        "subjectTitle": "生理學 (一)",
        "prof": "授課教授",
        "examRange": "A卷 Q1–20",
        "unitUrl": "https://notebook.google.com/notebook/01b3322a-9c0a-498f-91ce-4c29f24657f5",
    },
    "questions": [
        {
            "year": "114 學年度",
            "yearGroup": "114",
            "stem": "範例題幹內容？",
            "options": {
                "A": "選項 A 敘述",
                "B": "選項 B 敘述",
                "C": "選項 C 敘述",
                "D": "選項 D 敘述",
            },
            "answer": "A",
            "acceptedAnswers": ["A"],
            "answerDisplay": "(A)",
            "hasErrata": False,
            "explanations": [
                "📘 **【核心考點】**：此處填寫核心觀念與機制詳解。",
                "**(A) 正確**：說明為何應選此選項。",
            ],
        }
    ],
}


def import_questions_into_exam(
    exams_dir: Path,
    db_path: Path,
    exam_slug: str,
    raw_questions: list[dict],
    *,
    unit_code: str | None = None,
    unit_meta: dict | None = None,
    dry_run: bool = False,
    update_existing: bool = False,
    sync_db: bool = True,
) -> dict:
    return commit_questions_import(
        exams_dir,
        db_path,
        exam_slug,
        raw_questions,
        unit_code=unit_code,
        unit_meta=unit_meta,
        dry_run=dry_run,
        update_existing=update_existing,
        sync_db=sync_db,
    )


def _resolve_notebook_id(exam_slug: str | None, notebook_id: str | None) -> str:
    if notebook_id:
        return notebook_id.strip()
    if exam_slug:
        manifest_path = EXAMS_DIR / exam_slug / "exam.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            nb_id = (manifest.get("source") or {}).get("notebookId")
            if nb_id:
                return nb_id
    raise ValueError("請提供 --notebook-id，或確認考科 exam.json 內設有 source.notebookId")


def _collect_unit_meta_from_args(args: argparse.Namespace) -> dict | None:
    keys = (
        ("unit_title", "unitTitle"),
        ("short_label", "shortLabel"),
        ("session", "session"),
        ("subject", "subject"),
        ("subject_title", "subjectTitle"),
        ("prof", "prof"),
        ("exam_range", "examRange"),
        ("unit_url", "unitUrl"),
    )
    meta: dict = {}
    for attr, dest in keys:
        val = getattr(args, attr, None)
        if val is not None:
            meta[dest] = val
    for flag, dest in (
        ("is_out_of_scope", "isOutOfScope"),
        ("highlight", "highlight"),
        ("exempt_cross_dup", "exemptFromCrossDupFilter"),
    ):
        if getattr(args, flag, False):
            meta[dest] = True
    return meta or None


def _add_unit_creation_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--unit-title", help="建立新單元時的完整標題")
    parser.add_argument("--short-label", help="建立新單元時的標籤短名")
    parser.add_argument("--session", help="建立新單元時的節次代碼（如 A / B）")
    parser.add_argument("--subject", help="建立新單元時的科目代碼（如 Physio / Patho）")
    parser.add_argument("--subject-title", help="建立新單元時的科目顯示名稱")
    parser.add_argument("--prof", help="建立新單元時的預設授課教授")
    parser.add_argument("--exam-range", help="建立新單元時的考題範圍說明")
    parser.add_argument("--unit-url", help="建立新單元時的共筆來源連結")
    parser.add_argument("--is-out-of-scope", action="store_true", help="標記為歷屆補充單元")
    parser.add_argument("--highlight", action="store_true", help="高亮顯示單元標籤")
    parser.add_argument(
        "--exempt-cross-dup", action="store_true", help="豁免跨共筆去重篩選"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="易考網 YiKao 批次匯入 CLI（支援 JSON / Markdown fenced JSON / NotebookLM）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_schema = sub.add_parser("schema", help="印出匯入 JSON 範本與 NotebookLM 提示詞")
    p_schema.add_argument("--out", help="將範本寫入指定 JSON 檔")

    p_sources = sub.add_parser("list-sources", help="列出 NotebookLM 筆記本來源檔案")
    p_sources.add_argument("--notebook-id", help="NotebookLM Notebook UUID")
    p_sources.add_argument("--exam", default="cmu-int2-msk", help="從考科 exam.json 讀取 Notebook ID")

    p_json = sub.add_parser("from-json", help="從 JSON 或 Markdown 檔增量匯入題目")
    p_json.add_argument("input_file", help="輸入 .json 或含 ```json ... ``` 區塊的 .md/.txt 檔")
    p_json.add_argument("--exam", required=True, help="目標考科 slug（如 cmu-int2-msk）")
    p_json.add_argument("--unit", help="目標單元 unitCode（若輸入檔已含 unit.unitCode 可省略）")
    p_json.add_argument("--dry-run", action="store_true", help="僅驗證並試算結果，不寫入檔案")
    p_json.add_argument("--update-existing", action="store_true", help="若題目 id 已存在則覆寫更新")
    p_json.add_argument("--no-sync", action="store_true", help="跳過同步寫入 SQLite")
    _add_unit_creation_flags(p_json)

    p_nlm = sub.add_parser("from-notebooklm", help="透過 nlm CLI 查詢 NotebookLM 並直接匯入")
    p_nlm.add_argument("--exam", required=True, help="目標考科 slug")
    p_nlm.add_argument("--unit", required=True, help="目標單元 unitCode")
    p_nlm.add_argument("--prompt", required=True, help="向 NotebookLM 查詢／整理題目的指令")
    p_nlm.add_argument("--notebook-id", help="NotebookLM UUID（預設讀考科 exam.json）")
    p_nlm.add_argument("--source-ids", help="限制查詢的來源 UUID（以逗號分隔）")
    p_nlm.add_argument("--timeout", type=int, default=180, help="nlm 查詢逾時秒數（預設 180）")
    p_nlm.add_argument("--save-raw", help="將 NotebookLM 原始回應儲存至指定檔案")
    p_nlm.add_argument("--dry-run", action="store_true", help="僅驗證並試算結果，不寫入檔案")
    p_nlm.add_argument("--update-existing", action="store_true", help="若題目 id 已存在則覆寫更新")
    p_nlm.add_argument("--no-sync", action="store_true", help="跳過同步寫入 SQLite")
    _add_unit_creation_flags(p_nlm)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "schema":
        text = json.dumps(SCHEMA_TEMPLATE, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Schema template written to {args.out}")
        else:
            print(text)
        return 0

    if args.command == "list-sources":
        nb_id = _resolve_notebook_id(args.exam, args.notebook_id)
        sources = run_nlm_source_list(nb_id)
        print(f"Notebook {nb_id} sources ({len(sources)}):")
        for src in sources:
            print(f"  - {src.get('id', '?')} | {src.get('title', '')}")
        return 0

    if args.command == "from-json":
        raw_text = Path(args.input_file).read_text(encoding="utf-8")
        file_unit_meta, questions = extract_json_payload(raw_text)
        cli_unit_meta = _collect_unit_meta_from_args(args)
        merged_meta = {**(file_unit_meta or {}), **(cli_unit_meta or {})} or None
        report = import_questions_into_exam(
            EXAMS_DIR,
            DB_PATH,
            args.exam,
            questions,
            unit_code=args.unit,
            unit_meta=merged_meta,
            dry_run=args.dry_run,
            update_existing=args.update_existing,
            sync_db=not args.no_sync,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "from-notebooklm":
        nb_id = _resolve_notebook_id(args.exam, args.notebook_id)
        exam_manifest = json.loads(
            (EXAMS_DIR / args.exam / "exam.json").read_text(encoding="utf-8")
        )
        valid_years = [y["code"] for y in exam_manifest.get("yearGroups", [])]
        full_prompt = (
            f"{args.prompt}\n\n"
            "請嚴格只輸出一個 ```json ... ``` 程式碼區塊內的 JSON 陣列（不要附加其他格式或無法解析的註解）。\n"
            f"每題物件需包含欄位：year (字串)、yearGroup (僅限 {valid_years})、stem (題幹)、"
            'options (物件如 {"A":"...","B":"...","C":"...","D":"..."})、'
            "answer (正解字母)、acceptedAnswers (給分字母陣列)、answerDisplay (顯示文字)、"
            "hasErrata (布林值)、explanations (詳解段落字串陣列)。"
        )
        raw_answer = run_nlm_query(
            nb_id,
            full_prompt,
            source_ids=args.source_ids,
            timeout=args.timeout,
        )
        if args.save_raw:
            Path(args.save_raw).write_text(raw_answer, encoding="utf-8")

        file_unit_meta, questions = extract_json_payload(raw_answer)
        cli_unit_meta = _collect_unit_meta_from_args(args)
        merged_meta = {**(file_unit_meta or {}), **(cli_unit_meta or {})} or None
        report = import_questions_into_exam(
            EXAMS_DIR,
            DB_PATH,
            args.exam,
            questions,
            unit_code=args.unit,
            unit_meta=merged_meta,
            dry_run=args.dry_run,
            update_existing=args.update_existing,
            sync_db=not args.no_sync,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
