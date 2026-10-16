from dataclasses import replace
from time import sleep

from fastapi.testclient import TestClient
from PIL import Image

from wardrobe.app import create_app
from wardrobe.benchmark import CASES, run_suite
from wardrobe.config import Settings
from wardrobe.recommendations import reference_matches
from wardrobe.recommendations import Ollama


class Vision:
    def ready(self):
        return True


class Stylist:
    def __init__(self):
        self.calls = []

    def recommend(self, prompt, items, conversation):
        self.calls.append((prompt, items, conversation))
        return {
            "message": "One option.",
            "outfits": [{
                "title": "Look",
                "explanation": "A simple combination.",
                "item_ids": ["df2-top", "df2-bottom"],
                "missing_components": ["footwear"],
            }],
        }, {"query": prompt}


def item(item_id, category, filename):
    return {
        "id": item_id,
        "wardrobe": "deepfashion2",
        "name": category,
        "category": category,
        "subtype": category,
        "color": "blue",
        "pattern": "solid",
        "style": "casual",
        "available": True,
        "embedding": [1, 0],
        "filename": filename,
        "thumbnail": filename,
        "image_url": f"/media/{item_id}",
        "thumbnail_url": f"/media/{item_id}?thumbnail=true",
        "suggestions": {},
        "alternatives": [],
        "edited_fields": [],
        "created_at": "2026-10-08T00:00:00+00:00",
        "analysis_status": "ready",
        "analysis_error": None,
    }


def test_dataset_is_separate_read_only_and_paginated(tmp_path, monkeypatch):
    settings = replace(Settings(), data_dir=tmp_path / "data", frontend_dir=tmp_path / "dist")
    folder = settings.data_dir / "deepfashion2"
    folder.mkdir(parents=True)
    for filename in ("000001.jpg", "000002.jpg"):
        Image.new("RGB", (20, 20), "blue").save(folder / filename)
    app = create_app(settings, Vision(), Stylist())
    app.state.store.save_items([
        item("df2-top", "tops", "000001.jpg"),
        item("df2-bottom", "bottoms", "000002.jpg"),
    ])
    with TestClient(app) as client:
        assert client.get("/api/items").json() == []
        assert client.get("/api/deepfashion2/status").json()["ready"]
        page = client.get("/api/deepfashion2/items?limit=1").json()
        assert page["total"] == 2
        assert len(page["items"]) == 1
        assert client.get("/api/deepfashion2/items?category=tops").json()["total"] == 1
        assert client.get("/media/df2-top").status_code == 200
        assert client.patch("/api/items/df2-top", json={"name": "changed"}).status_code == 403
        assert client.delete("/api/items/df2-top").status_code == 403
        personal = client.post("/api/conversations").json()
        dataset = client.post("/api/conversations?wardrobe=deepfashion2").json()
        assert personal["wardrobe"] == "personal"
        assert dataset["wardrobe"] == "deepfashion2"
        assert client.get("/api/conversations/latest").json()["id"] == personal["id"]
        assert client.get("/api/conversations/latest?wardrobe=deepfashion2").json()["id"] == dataset["id"]
        monkeypatch.setattr(Ollama, "status", lambda self: True)
        started = client.post("/api/benchmarks")
        assert started.status_code == 202
        for _ in range(100):
            result = client.get(f"/api/benchmarks/{started.json()['id']}").json()
            if result["status"] == "complete":
                break
            sleep(0.01)
        assert result["status"] == "complete"
        assert len(result["cases"]) == 10
        assert result["cases"][0]["outfits"][0]["items"][0]["id"] == "df2-top"


def test_benchmark_uses_only_dataset_items_and_reports_partial_outfits():
    stylist = Stylist()
    records = [item("df2-top", "tops", "000001.jpg"), item("df2-bottom", "bottoms", "000002.jpg")]
    result = {"cases": [], "status": "running"}
    run_suite(stylist, records, lambda _: None, result)
    assert len(CASES) == len(result["cases"]) == 10
    assert result["status"] == "complete"
    assert all(case["outfit_count"] == case["partial_count"] == 1 for case in result["cases"])
    assert all(call[1] is records for call in stylist.calls)
    follow_up = next(call for call in stylist.calls if call[0] == "Make option 2 more casual.")
    assert len(follow_up[2]["messages"]) == 2


def test_generic_black_clothing_exclusion_matches_color():
    black = item("df2-black", "tops", "000001.jpg")
    black["color"] = "black"
    assert reference_matches("black clothing", [black]) == [black]
