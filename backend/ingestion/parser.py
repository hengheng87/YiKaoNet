"""Parsers for structured JSON, plain-text medical co-note MCQs, and duplicate detection."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)
Q_HEADER_RE = re.compile(
    r"^\s*(?:Q\s*(\d+)|第\s*(\d+)\s*題|(\d+)\s*[.、)])\s*(.*)$",
    re.IGNORECASE,
)
OPTION_LINE_RE = re.compile(
    r"^\s*(?:\(([A-G])\)|([A-G])\s*[.)、])\s*(.+)$"
)
ANSWER_LINE_RE = re.compile(
    r"^\s*(?:答案|正解|標準答案|Ans(?:wer)?)\s*[:：]\s*(.+)$",
    re.IGNORECASE,
)
EXPL_LINE_RE = re.compile(
    r"^\s*(?:詳解|解析|說明|Explanation)\s*[:：]\s*(.*)$",
    re.IGNORECASE,
)
YEAR_TAG_RE = re.compile(r"[\[\【〈(]\s*(1\d{2})\s*(?:學年度)?\s*[\]\】〉)]")
NORM_PUNCT_RE = re.compile(r"[\s？?。.,，:：;；!！()（）「」『』\[\]【】]+")


def normalize_stem(stem: str) -> str:
    return NORM_PUNCT_RE.sub("", stem).lower()


def extract_json_payload(raw_text: str) -> tuple[dict | None, list[dict]]:
    text = raw_text.strip()
    if not text:
        raise ValueError("輸入內容為空，無法解析題目 JSON")

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        for match in FENCED_JSON_RE.finditer(text):
            candidate = match.group(1).strip()
            try:
                parsed = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue

    if parsed is None:
        arr_start = text.find("[")
        arr_end = text.rfind("]")
        obj_start = text.find("{")
        obj_end = text.rfind("}")
        candidates = []
        if arr_start != -1 and arr_end > arr_start:
            candidates.append(text[arr_start : arr_end + 1])
        if obj_start != -1 and obj_end > obj_start:
            candidates.append(text[obj_start : obj_end + 1])
        for cand in candidates:
            try:
                parsed = json.loads(cand)
                break
            except json.JSONDecodeError:
                continue

    if parsed is None:
        raise ValueError("無法從輸入中解析有效的 JSON 題目陣列或物件")

    if isinstance(parsed, list):
        return None, parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
        unit_meta = parsed.get("unit") if isinstance(parsed.get("unit"), dict) else None
        if not unit_meta and "unitCode" in parsed:
            unit_meta = {
                k: parsed[k]
                for k in (
                    "unitCode",
                    "unitTitle",
                    "shortLabel",
                    "session",
                    "subject",
                    "subjectTitle",
                    "prof",
                    "examRange",
                    "unitUrl",
                    "highlight",
                    "isOutOfScope",
                    "exemptFromCrossDupFilter",
                )
                if k in parsed
            }
        return unit_meta, parsed["questions"]

    raise ValueError("JSON 格式需為題目陣列 [...] 或包含 'questions' 的物件")


def parse_plain_text_mcqs(
    raw_text: str,
    *,
    default_year: str = "114 學年度",
    default_year_group: str = "114",
) -> list[dict]:
    """Best-effort parser for Taiwanese medical co-note MCQ plain text / Markdown."""
    lines = raw_text.splitlines()
    blocks: list[dict] = []
    current: dict | None = None
    mode = "stem"  # 'stem' | 'options' | 'expl'

    def _finalize(blk: dict | None) -> None:
        if not blk:
            return
        stem_text = "\n".join(blk["stem_lines"]).strip()
        if not stem_text or len(blk["options"]) < 2 or not blk["accepted"]:
            return
        accepted = [a for a in blk["accepted"] if a in blk["options"]]
        if not accepted:
            return
        answer = accepted[0]
        year_group = blk["yearGroup"] or default_year_group
        year = blk["year"] or default_year
        explanations = [e.strip() for e in blk["expl_lines"] if e.strip()]
        if not explanations:
            explanations = ["待補充詳解（匯入自文字共筆）"]

        has_errata = len(accepted) > 1 or blk["bonus_flag"]
        if blk["bonus_flag"] and len(accepted) == 1 and len(blk["options"]) >= 2:
            accepted = list(blk["options"].keys())
        if len(accepted) > 1 and not blk["bonus_flag"]:
            disp = f"({'/'.join(accepted)})（申覆並列給分）"
        elif blk["bonus_flag"]:
            disp = f"({answer})（申覆送分）"
        else:
            disp = f"({answer})"

        blocks.append(
            {
                "qNum": blk["qNum"],
                "origQ": f"Q{blk['qNum']}" if blk["qNum"] else None,
                "year": year,
                "yearGroup": year_group,
                "hasErrata": has_errata,
                "stem": stem_text,
                "options": blk["options"],
                "answer": answer,
                "acceptedAnswers": accepted,
                "answerDisplay": disp,
                "explanations": explanations,
            }
        )

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        ans_match = ANSWER_LINE_RE.match(line)
        if ans_match and current is not None:
            ans_body = ans_match.group(1)
            letters = []
            for ch in re.findall(r"\b([A-G])\b|\(([A-G])\)", ans_body.upper()):
                letter = ch[0] or ch[1]
                if letter and letter not in letters:
                    letters.append(letter)
            current["accepted"] = letters
            if "送分" in ans_body or "皆給分" in ans_body:
                current["bonus_flag"] = True
            mode = "expl"
            continue

        expl_match = EXPL_LINE_RE.match(line)
        if expl_match and current is not None:
            body = expl_match.group(1).strip()
            if body:
                current["expl_lines"].append(body)
            mode = "expl"
            continue

        opt_match = OPTION_LINE_RE.match(line)
        if opt_match and current is not None:
            letter = (opt_match.group(1) or opt_match.group(2)).upper()
            text = opt_match.group(3).strip()
            current["options"][letter] = text
            mode = "options"
            continue

        hdr_match = Q_HEADER_RE.match(line)
        is_likely_new_q = bool(
            hdr_match
            and (
                current is None
                or len(current["options"]) >= 2
                or current["accepted"]
                or line.lstrip().upper().startswith(("Q", "第"))
            )
        )
        if is_likely_new_q and hdr_match:
            _finalize(current)
            q_num_str = hdr_match.group(1) or hdr_match.group(2) or hdr_match.group(3)
            rest = hdr_match.group(4).strip()
            ym = YEAR_TAG_RE.search(rest)
            detected_yg = ym.group(1) if ym else None
            detected_y = f"{detected_yg} 學年度" if detected_yg else None
            current = {
                "qNum": int(q_num_str) if q_num_str else None,
                "year": detected_y,
                "yearGroup": detected_yg,
                "stem_lines": [rest] if rest else [],
                "options": {},
                "accepted": [],
                "bonus_flag": False,
                "expl_lines": [],
            }
            mode = "stem"
            continue

        if current is not None:
            if mode == "stem":
                current["stem_lines"].append(line)
            elif mode == "options" and current["options"]:
                last_key = list(current["options"].keys())[-1]
                current["options"][last_key] += " " + line
            else:
                current["expl_lines"].append(line)

    _finalize(current)
    return blocks


def _load_other_unit_stems(
    exam_dir: Path,
    exclude_unit_code: str | None = None,
) -> list[dict]:
    manifest = json.loads((exam_dir / "exam.json").read_text(encoding="utf-8"))
    entries: list[dict] = []
    for u_entry in manifest.get("units", []):
        uc = u_entry["unitCode"]
        if exclude_unit_code and uc == exclude_unit_code:
            continue
        u_path = (exam_dir / u_entry["file"]).resolve()
        if not u_path.is_file():
            continue
        u_data = json.loads(u_path.read_text(encoding="utf-8"))
        for q in u_data.get("questions", []):
            entries.append(
                {
                    "id": q["id"],
                    "unitCode": uc,
                    "globalIndex": int(q["globalIndex"]),
                    "normStem": normalize_stem(q["stem"]),
                }
            )
    return entries


def find_cross_unit_duplicates(
    exam_dir: Path,
    candidate_questions: list[dict],
    target_unit_code: str,
    *,
    similarity_threshold: float = 0.88,
) -> dict[int, dict]:
    other_entries = _load_other_unit_stems(exam_dir, exclude_unit_code=target_unit_code)
    exact_map: dict[str, dict] = {}
    for entry in other_entries:
        exact_map.setdefault(entry["normStem"], entry)

    matches: dict[int, dict] = {}
    for idx, q in enumerate(candidate_questions):
        norm_cand = normalize_stem(q["stem"])
        if not norm_cand:
            continue
        if norm_cand in exact_map:
            hit = exact_map[norm_cand]
            matches[idx] = {
                "matchedId": hit["id"],
                "matchedUnit": hit["unitCode"],
                "matchedGlobalIndex": hit["globalIndex"],
                "ratio": 1.0,
            }
            continue

        best_ratio = 0.0
        best_hit: dict | None = None
        cand_len = len(norm_cand)
        for entry in other_entries:
            other_norm = entry["normStem"]
            if not other_norm:
                continue
            other_len = len(other_norm)
            if min(cand_len, other_len) / max(cand_len, other_len) < similarity_threshold:
                continue
            ratio = SequenceMatcher(None, norm_cand, other_norm).ratio()
            if ratio >= similarity_threshold and ratio > best_ratio:
                best_ratio = ratio
                best_hit = entry

        if best_hit is not None:
            matches[idx] = {
                "matchedId": best_hit["id"],
                "matchedUnit": best_hit["unitCode"],
                "matchedGlobalIndex": best_hit["globalIndex"],
                "ratio": round(best_ratio, 3),
            }
    return matches


def scan_exam_duplicates(
    exam_dir: Path,
    *,
    similarity_threshold: float = 0.88,
) -> list[dict]:
    entries = sorted(
        _load_other_unit_stems(exam_dir, exclude_unit_code=None),
        key=lambda e: e["globalIndex"],
    )
    pairs: list[dict] = []
    exact_seen: dict[str, dict] = {}

    for i, a in enumerate(entries):
        norm_a = a["normStem"]
        if not norm_a:
            continue
        if norm_a in exact_seen and exact_seen[norm_a]["unitCode"] != a["unitCode"]:
            first = exact_seen[norm_a]
            pairs.append({"q1": first, "q2": a, "ratio": 1.0})
            continue
        exact_seen.setdefault(norm_a, a)

        len_a = len(norm_a)
        for b in entries[i + 1 :]:
            if a["unitCode"] == b["unitCode"]:
                continue
            norm_b = b["normStem"]
            if not norm_b:
                continue
            len_b = len(norm_b)
            if min(len_a, len_b) / max(len_a, len_b) < similarity_threshold:
                continue
            if norm_a == norm_b:
                continue
            ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
            if ratio >= similarity_threshold:
                pairs.append({"q1": a, "q2": b, "ratio": round(ratio, 3)})
    return pairs
