"""Tests for GitHub Pages static site generator."""

from __future__ import annotations

import json
from pathlib import Path

from backend.config import EXAMS_DIR, FRONTEND_DIR
from scripts.build_static_site import build_static_site


def test_build_static_site_bundle(tmp_path: Path):
    out_dir = tmp_path / "site"
    stats = build_static_site(EXAMS_DIR, FRONTEND_DIR, out_dir)
    assert stats["exams"] == 1
    assert stats["blocks"] == 4
    assert stats["readyBlocks"] == 1
    assert stats["questions"] == 567
    assert stats["images"] == 9
    ver = stats["assetVersion"]
    assert len(ver) == 10

    assert (out_dir / ".nojekyll").is_file()
    assert (out_dir / "styles" / "tokens.css").is_file()
    assert (out_dir / "js" / "main.js").is_file()
    assert (out_dir / "js" / "components" / "blockPortal.js").is_file()
    assert (out_dir / "js" / "components" / "analytics.js").is_file()

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "window.__YIKAO_STATIC_MODE__ = true;" in index_html
    assert f'window.__YIKAO_ASSET_VERSION__ = "{ver}";' in index_html
    assert f'href="./styles/tokens.css?v={ver}"' in index_html
    assert f'src="./js/main.js?v={ver}"' in index_html
    assert 'id="portalView"' in index_html
    assert 'id="quizWorkspaceView"' in index_html
    assert 'id="analyticsView"' in index_html
    assert 'id="backToPortalBtn"' in index_html
    assert 'id="openAnalyticsBtn"' in index_html
    assert 'id="portalAnalyticsBtn"' in index_html
    assert "adminAuthModal" not in index_html
    assert "questionEditorModal" not in index_html

    built_main_js = (out_dir / "js" / "main.js").read_text(encoding="utf-8")
    assert f"from './api.js?v={ver}'" in built_main_js
    assert f"from './components/blockPortal.js?v={ver}'" in built_main_js

    blocks_json = json.loads((out_dir / "static-api" / "blocks.json").read_text(encoding="utf-8"))
    assert blocks_json["readyBlocks"] == 1
    assert blocks_json["plannedBlocks"] == 3
    assert blocks_json["totalBlocks"] == 4
    assert blocks_json["terms"][0]["code"] == "y3-s1"

    exams_json = json.loads((out_dir / "static-api" / "exams.json").read_text(encoding="utf-8"))
    assert len(exams_json) == 1
    assert exams_json[0]["slug"] == "cmu-int2-msk"
    assert exams_json[0]["block"]["term"] == "y3-s1"

    detail_json = json.loads(
        (out_dir / "static-api" / "exams" / "cmu-int2-msk" / "detail.json").read_text(
            encoding="utf-8"
        )
    )
    assert detail_json["totalQuestions"] == 567
    assert detail_json["unitCount"] == 22

    qs_json = json.loads(
        (out_dir / "static-api" / "exams" / "cmu-int2-msk" / "questions.json").read_text(
            encoding="utf-8"
        )
    )
    assert qs_json["total"] == 567
    assert len(qs_json["questions"]) == 567

    img_qs = [q for q in qs_json["questions"] if q["image"]]
    assert len(img_qs) == 12
    for q in img_qs:
        assert q["image"].startswith("./static-api/exams/cmu-int2-msk/images/")
        rel = q["image"].removeprefix("./")
        assert (out_dir / rel).is_file()

    offline_html = out_dir / "static-api" / "exams" / "cmu-int2-msk" / "offline.html"
    assert offline_html.is_file()
    assert "window.__YIKAO_OFFLINE_DATA__" in offline_html.read_text(encoding="utf-8")
