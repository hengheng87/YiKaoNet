"""Tests for standalone single-file offline HTML builder API and CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.offline_builder import check_no_duplicate_top_level_symbols, strip_esm_syntax
from scripts import build_offline_html


def test_strip_esm_syntax_and_duplicate_guard():
    sample = (
        "import { a, b } from './x.js';\n"
        "import {\n  c,\n  d,\n} from '../y.js';\n"
        "export const FOO = 1;\n"
        "export async function bar() { return FOO; }\n"
    )
    stripped = strip_esm_syntax(sample)
    assert "import " not in stripped
    assert "export " not in stripped
    assert "const FOO = 1;" in stripped
    assert "async function bar()" in stripped

    with pytest.raises(RuntimeError):
        check_no_duplicate_top_level_symbols(
            [("a.js", "const DUP = 1;"), ("b.js", "function DUP() {}")]
        )


def test_offline_html_export_endpoint(client):
    res = client.get("/api/exams/cmu-int2-msk/export/offline-html")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "yikao-cmu-int2-msk-offline.html" in res.headers["content-disposition"]

    html = res.text
    assert '<link rel="stylesheet"' not in html
    assert '<script type="module"' not in html
    assert "<style>" in html
    assert "window.__YIKAO_OFFLINE_DATA__ =" in html

    # Verify embedded JSON parses cleanly and includes all 567 questions + 12 base64 images
    m = re.search(
        r"window\.__YIKAO_OFFLINE_DATA__\s*=\s*(\{.*?\});\s*\n</script>",
        html,
        re.S,
    )
    assert m, "Embedded offline JSON not found"
    payload = json.loads(m.group(1).replace("<\\/", "</"))
    assert payload["singleExamMode"] is True
    assert payload["blocks"]["readyBlocks"] == 1
    assert payload["blocks"]["totalBlocks"] == 1
    assert len(payload["exams"]) == 1
    qs = payload["questions"]["cmu-int2-msk"]
    assert len(qs) == 567
    img_qs = [q for q in qs if q["image"]]
    assert len(img_qs) == 12
    assert all(q["image"].startswith("data:image/jpeg;base64,") for q in img_qs)

    # Verify no unstripped ESM syntax leaked into the IIFE script bundle
    bundle_m = re.search(r"<script>\s*\(function \(\) \{([\s\S]*)\}\)\(\);\s*</script>", html)
    assert bundle_m, "Bundled JS IIFE not found"
    bundle_code = bundle_m.group(1)
    assert "initBlockPortal" in bundle_code
    assert "adminAuthModal" not in html
    assert "questionEditorModal" not in html
    assert not re.search(r"^\s*import\s+", bundle_code, re.M)
    assert not re.search(r"^\s*export\s+", bundle_code, re.M)


def test_build_offline_html_cli(tmp_path: Path):
    out_file = tmp_path / "out_offline.html"
    rc = build_offline_html.main(
        ["--exam", "cmu-int2-msk", "--out", str(out_file)]
    )
    assert rc == 0
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "window.__YIKAO_OFFLINE_DATA__" in content
    assert len(content) > 1_000_000
