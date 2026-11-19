"""Validate modular exam and unit JSON datasets under data/exams/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EXAMS_DIR = BASE_DIR / "data" / "exams"

REQUIRED_EXAM_KEYS = {
    "slug",
    "version",
    "badge",
    "title",
    "subtitle",
    "source",
    "sessions",
    "subjects",
    "yearGroups",
    "units",
}
REQUIRED_UNIT_KEYS = {
    "unitCode",
    "unitTitle",
    "session",
    "subject",
    "subjectTitle",
    "prof",
    "examRange",
    "unitUrl",
    "questions",
}
REQUIRED_Q_KEYS = {
    "id",
    "globalIndex",
    "qNum",
    "origQ",
    "year",
    "yearGroup",
    "hasErrata",
    "isCrossDup",
    "stem",
    "image",
    "options",
    "answer",
    "acceptedAnswers",
    "answerDisplay",
    "explanations",
}


def validate_exam_dir(exam_dir: Path) -> tuple[list[str], dict]:
    errors: list[str] = []
    manifest_path = exam_dir / "exam.json"
    if not manifest_path.is_file():
        return [f"{exam_dir.name}: missing exam.json"], {}

    try:
        exam = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{exam_dir.name}: invalid exam.json ({exc})"], {}

    missing = REQUIRED_EXAM_KEYS - exam.keys()
    if missing:
        errors.append(f"{exam_dir.name}: exam.json missing keys {sorted(missing)}")
        return errors, {}

    if exam["slug"] != exam_dir.name:
        errors.append(
            f"{exam_dir.name}: exam.json slug '{exam['slug']}' != directory name"
        )

    session_codes = {s["code"] for s in exam["sessions"]}
    subject_codes = {s["code"] for s in exam["subjects"]}
    year_codes = {y["code"] for y in exam["yearGroups"]}

    seen_ids: set[str] = set()
    seen_indices: set[int] = set()
    seen_unit_codes: set[str] = set()
    images_root = (exam_dir / "images").resolve()
    total_q = 0

    for unit_meta in exam["units"]:
        uc = unit_meta.get("unitCode")
        if not uc or uc in seen_unit_codes:
            errors.append(f"{exam_dir.name}: duplicate or empty unitCode '{uc}'")
            continue
        seen_unit_codes.add(uc)

        unit_file = (exam_dir / unit_meta["file"]).resolve()
        if not unit_file.is_relative_to(exam_dir.resolve()) or not unit_file.is_file():
            errors.append(f"{exam_dir.name}/{uc}: missing unit file {unit_meta['file']}")
            continue

        try:
            unit = json.loads(unit_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{exam_dir.name}/{uc}: invalid JSON ({exc})")
            continue

        missing_u = REQUIRED_UNIT_KEYS - unit.keys()
        if missing_u:
            errors.append(f"{exam_dir.name}/{uc}: missing unit keys {sorted(missing_u)}")
            continue

        if unit["unitCode"] != uc:
            errors.append(f"{exam_dir.name}/{uc}: unitCode mismatch '{unit['unitCode']}'")

        questions = unit.get("questions", [])
        if not isinstance(questions, list) or not questions:
            errors.append(f"{exam_dir.name}/{uc}: questions must be a non-empty list")
            continue

        for q in questions:
            total_q += 1
            missing_q = REQUIRED_Q_KEYS - q.keys()
            if missing_q:
                errors.append(f"{exam_dir.name}/{uc}: question missing keys {sorted(missing_q)}")
                continue

            qid = q["id"]
            if qid in seen_ids:
                errors.append(f"{exam_dir.name}/{uc}: duplicate question id '{qid}'")
            seen_ids.add(qid)

            gidx = q["globalIndex"]
            if not isinstance(gidx, int) or gidx < 1 or gidx in seen_indices:
                errors.append(f"{exam_dir.name}/{qid}: invalid or duplicate globalIndex {gidx}")
            seen_indices.add(gidx)

            eff_session = q.get("session", unit["session"])
            eff_subject = q.get("subject", unit["subject"])
            if eff_session not in session_codes:
                errors.append(f"{exam_dir.name}/{qid}: unknown session '{eff_session}'")
            if eff_subject not in subject_codes:
                errors.append(f"{exam_dir.name}/{qid}: unknown subject '{eff_subject}'")
            if q["yearGroup"] not in year_codes:
                errors.append(f"{exam_dir.name}/{qid}: unknown yearGroup '{q['yearGroup']}'")

            opts = q["options"]
            if not isinstance(opts, dict) or len(opts) < 2:
                errors.append(f"{exam_dir.name}/{qid}: options must have >= 2 choices")
            else:
                if q["answer"] not in opts:
                    errors.append(f"{exam_dir.name}/{qid}: answer '{q['answer']}' not in options")
                for acc in q["acceptedAnswers"]:
                    if acc not in opts:
                        errors.append(f"{exam_dir.name}/{qid}: acceptedAnswer '{acc}' not in options")

            if not q["stem"].strip():
                errors.append(f"{exam_dir.name}/{qid}: empty stem")
            if not isinstance(q["explanations"], list) or not q["explanations"]:
                errors.append(f"{exam_dir.name}/{qid}: explanations must be non-empty list")

            if q["image"] is not None:
                img_path = (exam_dir / q["image"]).resolve()
                if not img_path.is_relative_to(images_root) or not img_path.is_file():
                    errors.append(f"{exam_dir.name}/{qid}: invalid or missing image '{q['image']}'")

    stats = {
        "slug": exam["slug"],
        "units": len(seen_unit_codes),
        "questions": total_q,
    }
    return errors, stats


def validate_all(exams_dir: Path = EXAMS_DIR) -> int:
    if not exams_dir.is_dir():
        print(f"ERROR: exams directory not found: {exams_dir}", file=sys.stderr)
        return 1

    exam_dirs = sorted(p for p in exams_dir.iterdir() if p.is_dir())
    if not exam_dirs:
        print(f"ERROR: no exam directories found in {exams_dir}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    all_stats: list[dict] = []
    for exam_dir in exam_dirs:
        errs, stats = validate_exam_dir(exam_dir)
        all_errors.extend(errs)
        if stats:
            all_stats.append(stats)

    if all_errors:
        print("Validation FAILED:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    total_units = sum(s["units"] for s in all_stats)
    total_questions = sum(s["questions"] for s in all_stats)
    print(
        f"Validation PASSED: {len(all_stats)} exam(s), {total_units} unit(s), "
        f"{total_questions} question(s), 0 errors."
    )
    for s in all_stats:
        print(f"  - {s['slug']}: {s['units']} units, {s['questions']} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate_all())
