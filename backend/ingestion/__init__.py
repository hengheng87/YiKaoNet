"""Reference & co-note ingestion workflow package."""

from backend.ingestion.extractors import (
    extract_pdf_source,
    extract_text_source,
    import_image_asset,
    run_nlm_query,
    run_nlm_source_list,
)
from backend.ingestion.parser import (
    extract_json_payload,
    find_cross_unit_duplicates,
    normalize_stem,
    parse_plain_text_mcqs,
    scan_exam_duplicates,
)
from backend.ingestion.pipeline import (
    commit_questions_import,
    init_exam,
    prepare_staging_bundle,
)

__all__ = [
    "commit_questions_import",
    "extract_json_payload",
    "extract_pdf_source",
    "extract_text_source",
    "find_cross_unit_duplicates",
    "import_image_asset",
    "init_exam",
    "normalize_stem",
    "parse_plain_text_mcqs",
    "prepare_staging_bundle",
    "run_nlm_query",
    "run_nlm_source_list",
    "scan_exam_duplicates",
]
