"""API tests for exams, questions, filtering, CJK search, images, Notion export, and static assets."""

from __future__ import annotations


def test_health_and_exam_metadata(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "exams": 1, "questions": 567}

    exams = client.get("/api/exams")
    assert exams.status_code == 200
    items = exams.json()
    assert len(items) == 1
    assert items[0]["slug"] == "cmu-int2-msk"
    assert items[0]["totalQuestions"] == 567

    detail = client.get("/api/exams/cmu-int2-msk")
    assert detail.status_code == 200
    body = detail.json()
    assert body["totalQuestions"] == 567
    assert body["uniqueQuestions"] == 477
    assert body["errataCount"] == 14
    assert body["outOfScopeCount"] == 12
    assert body["unitCount"] == 22

    missing = client.get("/api/exams/does-not-exist")
    assert missing.status_code == 404


def test_question_filters_and_cjk_search(client):
    res_a = client.get("/api/exams/cmu-int2-msk/questions?unit=SESSION_A")
    assert res_a.status_code == 200
    assert res_a.json()["filtered"] == 339

    res_pharm = client.get("/api/exams/cmu-int2-msk/questions?unit=SUBJ_Pharm")
    assert res_pharm.status_code == 200
    assert res_pharm.json()["filtered"] == 142

    res_oos = client.get("/api/exams/cmu-int2-msk/questions?unit=OUT_OF_SCOPE")
    assert res_oos.status_code == 200
    assert res_oos.json()["filtered"] == 12

    # Robbins_Ch7_Neo is exempt from cross-dup hiding when filtered directly
    res_robbins = client.get(
        "/api/exams/cmu-int2-msk/questions?unit=Robbins_Ch7_Neo&hide_cross_dup=true"
    )
    assert res_robbins.status_code == 200
    assert res_robbins.json()["filtered"] == 70

    res_dedup = client.get("/api/exams/cmu-int2-msk/questions?hide_cross_dup=true")
    assert res_dedup.status_code == 200
    assert res_dedup.json()["filtered"] == 477

    res_year = client.get("/api/exams/cmu-int2-msk/questions?year=114")
    assert res_year.status_code == 200
    assert res_year.json()["filtered"] == 169

    res_errata = client.get("/api/exams/cmu-int2-msk/questions?has_errata=true")
    assert res_errata.status_code == 200
    assert res_errata.json()["filtered"] == 14

    # CJK 2-character substring search
    res_cjk = client.get("/api/exams/cmu-int2-msk/questions?search=皮節")
    assert res_cjk.status_code == 200
    cjk_items = res_cjk.json()["questions"]
    assert len(cjk_items) >= 1
    for q in cjk_items:
        joined = " ".join(
            [q["stem"], *q["options"].values(), q["unitTitle"], q["prof"], *q["explanations"]]
        )
        assert "皮節" in joined

    # Case-insensitive English search
    res_en = client.get("/api/exams/cmu-int2-msk/questions?search=bethanechol")
    assert res_en.status_code == 200
    assert res_en.json()["filtered"] >= 1

    # Random non-cross-dup sampling
    res_rand = client.get("/api/exams/cmu-int2-msk/questions?random_count=25")
    assert res_rand.status_code == 200
    rand_items = res_rand.json()["questions"]
    assert len(rand_items) == 25
    assert len({q["id"] for q in rand_items}) == 25
    assert all(not q["isCrossDup"] for q in rand_items)


def test_single_question_and_images_and_static_mime(client):
    q_res = client.get("/api/exams/cmu-int2-msk/questions/1014_Physio1-1")
    assert q_res.status_code == 200
    assert q_res.json()["globalIndex"] == 1

    q_missing = client.get("/api/exams/cmu-int2-msk/questions/nonexistent")
    assert q_missing.status_code == 404

    img_ok = client.get("/api/exams/cmu-int2-msk/images/1007_Neo1-6.jpg")
    assert img_ok.status_code == 200
    assert img_ok.headers["content-type"].startswith("image/jpeg")
    assert img_ok.content.startswith(b"\xff\xd8\xff")

    img_404 = client.get("/api/exams/cmu-int2-msk/images/missing.jpg")
    assert img_404.status_code == 404

    img_traversal = client.get("/api/exams/cmu-int2-msk/images/..%2Fexam.json")
    assert img_traversal.status_code in (400, 404)

    # Static assets and critical JS MIME type check on Windows
    idx = client.get("/")
    assert idx.status_code == 200
    assert "text/html" in idx.headers["content-type"]

    js = client.get("/js/main.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]

    css = client.get("/styles/tokens.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]


def test_notion_export_endpoint(client):
    res_errata = client.post(
        "/api/exams/cmu-int2-msk/export/notion",
        json={"scope": "ERRATA"},
    )
    assert res_errata.status_code == 200
    assert res_errata.json()["count"] == 14
    assert "<details><summary>" in res_errata.json()["markdown"]

    res_ids = client.post(
        "/api/exams/cmu-int2-msk/export/notion",
        json={"questionIds": ["1014_Physio1-1"]},
    )
    assert res_ids.status_code == 200
    assert res_ids.json()["count"] == 1
    assert "[#1｜" in res_ids.json()["markdown"]
