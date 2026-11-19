"""Unified co-note & reference material ingestion CLI for YiKao."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import DB_PATH, EXAMS_DIR, STAGING_DIR
from backend.ingestion import (
    commit_questions_import,
    extract_json_payload,
    extract_pdf_source,
    extract_text_source,
    init_exam,
    parse_plain_text_mcqs,
    prepare_staging_bundle,
    run_nlm_query,
    scan_exam_duplicates,
)


def _resolve_notebook_id(exam_slug: str, notebook_id: str | None) -> str:
    if notebook_id:
        return notebook_id.strip()
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
        description="易考網 YiKao 共筆與參考資料匯入工作流 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-exam", help="建立全新考科資料夾與預設 exam.json")
    p_init.add_argument("slug", help="考科代碼 slug（僅限小寫英數字與 -，例如 cmu-int3-neuro）")
    p_init.add_argument("--title", required=True, help="考科名稱")
    p_init.add_argument("--badge", default="", help="頁首徽章文字")
    p_init.add_argument("--subtitle", default="", help="考科副標題說明")
    p_init.add_argument("--source-name", default="", help="知識庫／共筆來源名稱")
    p_init.add_argument("--source-url", default="", help="來源網址")
    p_init.add_argument("--notebook-id", default=None, help="NotebookLM Notebook UUID")
    p_init.add_argument("--block-term", default=None, help="所屬學期代碼（如 y3-s1、y3-s2）")
    p_init.add_argument("--block-term-label", default=None, help="學期分區顯示標題（如 大三下學期整合考）")
    p_init.add_argument("--block-term-short-label", default=None, help="學期頁籤簡稱（如 大三下）")
    p_init.add_argument("--block-exam-label", default=None, help="整合考次標籤（如 第一次整合考）")
    p_init.add_argument("--block-name", default=None, help="系統 Block 名稱（如 基礎醫學概論）")
    p_init.add_argument("--block-en-name", default=None, help="系統 Block 英文名稱")
    p_init.add_argument("--block-icon", default=None, help="系統卡片 Emoji 圖示")
    p_init.add_argument("--block-accent", default=None, help="系統卡片色系（indigo/blue/rose/amber/emerald）")
    p_init.add_argument("--block-order", type=int, default=None, help="系統卡片排序數字")
    p_init.add_argument("--block-desc", default=None, help="系統卡片說明文字")

    p_pdf = sub.add_parser("extract-pdf", help="從 PDF 共筆萃取純文字、圖片並產出待審草稿")
    p_pdf.add_argument("pdf_file", help="PDF 檔案路徑")
    p_pdf.add_argument("--exam", required=True, help="目標考科 slug")
    p_pdf.add_argument("--unit", required=True, help="目標單元 unitCode")
    p_pdf.add_argument("--extract-images", action="store_true", help="一併擷取 PDF 內嵌圖片至暫存區")
    p_pdf.add_argument("--parse-mcq", action="store_true", help="嘗試以規則剖析選擇題草稿")
    p_pdf.add_argument("--year", default="114 學年度", help="預設學年度文字")
    p_pdf.add_argument("--year-group", default="114", help="預設年份群組代碼")
    p_pdf.add_argument("--out", default=None, help="指定草稿 JSON 輸出路徑（預設存於 data/staging/）")

    p_txt = sub.add_parser("parse-text", help="從文字或 Markdown 共筆剖析選擇題草稿")
    p_txt.add_argument("text_file", help="文字／Markdown 檔案路徑")
    p_txt.add_argument("--exam", required=True, help="目標考科 slug")
    p_txt.add_argument("--unit", required=True, help="目標單元 unitCode")
    p_txt.add_argument("--year", default="114 學年度", help="預設學年度文字")
    p_txt.add_argument("--year-group", default="114", help="預設年份群組代碼")
    p_txt.add_argument("--out", default=None, help="指定草稿 JSON 輸出路徑（預設存於 data/staging/）")

    p_nlm = sub.add_parser("from-notebooklm", help="透過 nlm CLI 查詢 NotebookLM 並直接匯入")
    p_nlm.add_argument("--exam", required=True, help="目標考科 slug")
    p_nlm.add_argument("--unit", required=True, help="目標單元 unitCode")
    p_nlm.add_argument("--prompt", required=True, help="向 NotebookLM 查詢／整理題目的指令")
    p_nlm.add_argument("--notebook-id", help="NotebookLM UUID（預設讀考科 exam.json）")
    p_nlm.add_argument("--source-ids", help="限制查詢的來源 UUID（以逗號分隔）")
    p_nlm.add_argument("--timeout", type=int, default=180, help="nlm 查詢逾時秒數（預設 180）")
    p_nlm.add_argument("--save-raw", help="將 NotebookLM 原始回應儲存至指定檔案")
    p_nlm.add_argument("--auto-mark-cross-dup", action="store_true", help="自動比對並標記跨單元重複題")
    p_nlm.add_argument("--dry-run", action="store_true", help="僅驗證並試算結果，不寫入檔案")
    p_nlm.add_argument("--update-existing", action="store_true", help="若題目 id 已存在則覆寫更新")
    p_nlm.add_argument("--no-sync", action="store_true", help="跳過同步寫入 SQLite")
    _add_unit_creation_flags(p_nlm)

    p_imp = sub.add_parser("import-json", help="驗證並提交草稿 JSON 或 Markdown 題目至考科單元")
    p_imp.add_argument("input_file", help="輸入 .json 或含 ```json ... ``` 區塊的檔案")
    p_imp.add_argument("--exam", required=True, help="目標考科 slug")
    p_imp.add_argument("--unit", help="目標單元 unitCode（若輸入檔已含 unitCode 可省略）")
    p_imp.add_argument("--auto-mark-cross-dup", action="store_true", help="自動比對並標記跨單元重複題")
    p_imp.add_argument("--dry-run", action="store_true", help="僅驗證並試算結果，不寫入檔案")
    p_imp.add_argument("--update-existing", action="store_true", help="若題目 id 已存在則覆寫更新")
    p_imp.add_argument("--no-sync", action="store_true", help="跳過同步寫入 SQLite")
    _add_unit_creation_flags(p_imp)

    p_dup = sub.add_parser("check-duplicates", help="掃描考科內跨單元高度相似／重複題目")
    p_dup.add_argument("--exam", required=True, help="目標考科 slug")
    p_dup.add_argument("--threshold", type=float, default=0.88, help="相似度門檻（預設 0.88）")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-exam":
        block_payload: dict = {}
        for attr, dest in (
            ("block_term", "term"),
            ("block_term_label", "termLabel"),
            ("block_term_short_label", "termShortLabel"),
            ("block_exam_label", "examLabel"),
            ("block_name", "name"),
            ("block_en_name", "englishName"),
            ("block_icon", "icon"),
            ("block_accent", "accent"),
            ("block_order", "order"),
            ("block_desc", "description"),
        ):
            val = getattr(args, attr, None)
            if val is not None:
                block_payload[dest] = val

        exam_dir = init_exam(
            EXAMS_DIR,
            slug=args.slug,
            title=args.title,
            badge=args.badge,
            subtitle=args.subtitle,
            source_name=args.source_name,
            source_url=args.source_url,
            notebook_id=args.notebook_id,
            block=block_payload or None,
        )
        print(f"Created exam scaffold at {exam_dir}")
        return 0

    if args.command == "extract-pdf":
        pdf_path = Path(args.pdf_file)
        img_dir = (
            STAGING_DIR / f"{args.exam}_{args.unit}_images"
            if args.extract_images
            else None
        )
        pdf_res = extract_pdf_source(pdf_path, extract_images_dir=img_dir)
        parsed = (
            parse_plain_text_mcqs(
                pdf_res["fullText"],
                default_year=args.year,
                default_year_group=args.year_group,
            )
            if args.parse_mcq
            else []
        )
        bundle = prepare_staging_bundle(
            EXAMS_DIR,
            STAGING_DIR,
            exam_slug=args.exam,
            unit_code=args.unit,
            source_name=pdf_path.name,
            raw_text=pdf_res["fullText"],
            parsed_questions=parsed,
            extracted_images=pdf_res["images"],
            out_path=Path(args.out) if args.out else None,
        )
        print(
            json.dumps(
                {
                    "stagingFile": bundle["stagingFile"],
                    "pageCount": pdf_res["pageCount"],
                    "imagesExtracted": len(pdf_res["images"]),
                    "parsedQuestions": bundle["parsedCount"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "parse-text":
        txt_path = Path(args.text_file)
        raw_text = extract_text_source(txt_path)
        parsed = parse_plain_text_mcqs(
            raw_text,
            default_year=args.year,
            default_year_group=args.year_group,
        )
        bundle = prepare_staging_bundle(
            EXAMS_DIR,
            STAGING_DIR,
            exam_slug=args.exam,
            unit_code=args.unit,
            source_name=txt_path.name,
            raw_text=raw_text,
            parsed_questions=parsed,
            out_path=Path(args.out) if args.out else None,
        )
        print(
            json.dumps(
                {
                    "stagingFile": bundle["stagingFile"],
                    "parsedQuestions": bundle["parsedCount"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "import-json":
        raw_text = Path(args.input_file).read_text(encoding="utf-8")
        file_unit_meta, questions = extract_json_payload(raw_text)
        cli_unit_meta = _collect_unit_meta_from_args(args)
        merged_meta = {**(file_unit_meta or {}), **(cli_unit_meta or {})} or None
        report = commit_questions_import(
            EXAMS_DIR,
            DB_PATH,
            args.exam,
            questions,
            unit_code=args.unit,
            unit_meta=merged_meta,
            dry_run=args.dry_run,
            update_existing=args.update_existing,
            auto_mark_cross_dup=args.auto_mark_cross_dup,
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
        report = commit_questions_import(
            EXAMS_DIR,
            DB_PATH,
            args.exam,
            questions,
            unit_code=args.unit,
            unit_meta=merged_meta,
            dry_run=args.dry_run,
            update_existing=args.update_existing,
            auto_mark_cross_dup=args.auto_mark_cross_dup,
            sync_db=not args.no_sync,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "check-duplicates":
        pairs = scan_exam_duplicates(
            EXAMS_DIR / args.exam, similarity_threshold=args.threshold
        )
        print(
            json.dumps(
                {"examSlug": args.exam, "duplicatePairs": len(pairs), "pairs": pairs},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
