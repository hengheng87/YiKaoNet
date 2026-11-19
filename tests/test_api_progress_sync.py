"""API tests for cloud progress sync, conflict-safe merge, and reset."""

from __future__ import annotations

import re


def test_generate_code_and_crud_roundtrip(client):
    gen = client.post("/api/progress/generate-code")
    assert gen.status_code == 200
    code = gen.json()["syncCode"]
    assert re.fullmatch(r"YK-[A-Z0-9]{4}-[A-Z0-9]{4}", code)

    empty_get = client.get(f"/api/progress/{code}/cmu-int2-msk")
    assert empty_get.status_code == 200
    assert empty_get.json()["exists"] is False

    put_res = client.put(
        f"/api/progress/{code.lower()}/cmu-int2-msk",
        json={
            "answers": {"1014_Physio1-1": "D"},
            "answerTimestamps": {"1014_Physio1-1": 1000},
            "starred": {"1014_Physio1-1": True},
            "starredTimestamps": {"1014_Physio1-1": 1000},
            "lastAnsweredQid": "1014_Physio1-1",
            "lastViewedQid": "1014_Physio1-2",
            "activeFilters": {"unitFilter": "ALL"},
            "updatedAt": 1000,
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["exists"] is True
    assert put_res.json()["syncCode"] == code

    got = client.get(f"/api/progress/{code}/cmu-int2-msk")
    assert got.status_code == 200
    body = got.json()
    assert body["exists"] is True
    assert body["answers"] == {"1014_Physio1-1": "D"}
    assert body["starred"] == {"1014_Physio1-1": True}
    assert body["lastViewedQid"] == "1014_Physio1-2"


def test_timestamp_merge_and_tombstones_and_delete(client):
    code = "DEV-SYNC-01"
    # Device A saves initial state
    client.put(
        f"/api/progress/{code}/cmu-int2-msk",
        json={
            "answers": {"q1": "A", "q2": "B"},
            "answerTimestamps": {"q1": 100, "q2": 200},
            "starred": {"q1": True, "q3": True},
            "starredTimestamps": {"q1": 100, "q3": 100},
            "lastAnsweredQid": "q2",
            "lastViewedQid": "q2",
            "updatedAt": 200,
        },
    )

    # Device B merges newer q1, older/disjoint q4, and unstarring tombstone for q3
    merge_res = client.post(
        f"/api/progress/{code}/cmu-int2-msk/merge",
        json={
            "answers": {"q1": "C", "q4": "D"},
            "answerTimestamps": {"q1": 150, "q4": 120},
            "starred": {"q3": False, "q4": True},
            "starredTimestamps": {"q3": 300, "q4": 120},
            "lastAnsweredQid": "q1",
            "lastViewedQid": "q4",
            "updatedAt": 300,
        },
    )
    assert merge_res.status_code == 200
    merged = merge_res.json()
    assert merged["answers"] == {"q1": "C", "q2": "B", "q4": "D"}
    assert merged["starred"]["q1"] is True
    assert merged["starred"]["q3"] is False
    assert merged["starred"]["q4"] is True
    assert merged["lastViewedQid"] == "q4"

    # Reset keeping stars
    del_keep = client.delete(f"/api/progress/{code}/cmu-int2-msk?keep_starred=true")
    assert del_keep.status_code == 200
    after_keep = client.get(f"/api/progress/{code}/cmu-int2-msk").json()
    assert after_keep["exists"] is True
    assert after_keep["answers"] == {}
    assert after_keep["starred"]["q1"] is True

    # Full delete
    del_full = client.delete(f"/api/progress/{code}/cmu-int2-msk?keep_starred=false")
    assert del_full.status_code == 200
    after_full = client.get(f"/api/progress/{code}/cmu-int2-msk").json()
    assert after_full["exists"] is False


def test_invalid_sync_code_rejected(client):
    res = client.get("/api/progress/ab/cmu-int2-msk")
    assert res.status_code == 400
