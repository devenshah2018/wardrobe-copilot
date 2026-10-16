import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from wardrobe.app import create_app
from wardrobe.config import Settings
from wardrobe.recommendations import ModelError, Stylist, validate_outfits
from wardrobe.schemas import Constraints, Proposal


class Vision:
    failure = False
    callback = None

    def ready(self):
        return not self.failure

    def analyze(self, path):
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        if self.failure:
            raise RuntimeError("Model needs setup")
        return (
            {
                "category": "tops",
                "subtype": "shirt",
                "color": "blue",
                "pattern": "solid",
                "style": "casual",
            },
            [1, 0],
            ["shirt"],
        )

    def rank(self, query, items):
        return items


class Model:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.contexts = []

    def generate(self, instruction, context, schema):
        self.contexts.append(context.copy())
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return schema.model_validate(response)


@pytest.fixture
def client(tmp_path):
    settings = replace(
        Settings(), data_dir=tmp_path / "data", frontend_dir=tmp_path / "dist"
    )
    vision = Vision()
    app = create_app(settings, vision, Stylist(Model(), vision))
    with TestClient(app) as client:
        client.vision = vision
        client.settings = settings
        yield client


def photo(format="JPEG", orientation=None):
    buffer = io.BytesIO()
    image = Image.new("RGB", (80, 120), "blue")
    kwargs = {}
    if orientation:
        exif = image.getexif()
        exif[274] = orientation
        kwargs["exif"] = exif
    image.save(buffer, format=format, **kwargs)
    return buffer.getvalue()


def upload(client, content=None, filename="shirt.jpg"):
    return client.post(
        "/api/items",
        files={
            "file": (
                filename,
                content if content is not None else photo(),
                "image/jpeg",
            )
        },
    )


def garment(item_id, category="tops", color="blue", subtype="shirt", available=True):
    return {
        "id": item_id,
        "name": f"{color} {subtype}",
        "category": category,
        "color": color,
        "subtype": subtype,
        "pattern": "solid",
        "style": "casual",
        "available": available,
        "embedding": [1, 0],
    }


def proposal(*outfits):
    return {
        "message": "",
        "outfits": [
            {"title": f"Look {i}", "explanation": "A combination.", "item_ids": ids}
            for i, ids in enumerate(outfits)
        ],
    }


def test_upload_edit_persistence_and_delete(client):
    first = upload(client).json()
    second = upload(client).json()
    assert first["id"] != second["id"]
    assert "embedding" not in first
    assert first["category"] == "tops"
    response = client.patch(
        "/api/items/" + first["id"],
        json={"name": "My favorite", "color": "navy", "available": False},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "My favorite"
    retry = client.post("/api/items/" + first["id"] + "/analyze").json()
    assert (
        retry["name"] == "My favorite"
        and retry["color"] == "navy"
        and not retry["available"]
    )
    reopened = TestClient(create_app(client.settings, Vision()))
    assert len(reopened.get("/api/items").json()) == 2
    assert client.delete("/api/items/" + first["id"]).status_code == 204
    assert client.get(first["image_url"]).status_code == 404
    assert client.get(second["image_url"]).status_code == 200


@pytest.mark.parametrize(
    "payload,status", [(b"not an image", 400), (b"x" * (10 * 1024 * 1024 + 1), 413)]
)
def test_invalid_upload(client, payload, status):
    assert upload(client, payload).status_code == status
    assert client.get("/api/items").json() == []


def test_unsupported_format_and_orientation(client):
    assert upload(client, photo("GIF")).status_code == 415
    item = upload(client, photo(orientation=6)).json()
    image = Image.open(io.BytesIO(client.get(item["image_url"]).content))
    assert image.size == (120, 80)


def test_failed_analysis_is_saved_and_can_be_corrected(client):
    client.vision.failure = True
    item = upload(client).json()
    assert item["analysis_status"] == "failed"
    assert client.get(item["image_url"]).status_code == 200
    assert (
        client.patch("/api/items/" + item["id"], json={"category": "bottoms"}).json()[
            "category"
        ]
        == "bottoms"
    )


def test_retry_preserves_concurrent_edit(client):
    item = upload(client).json()
    client.vision.callback = lambda: client.patch(
        "/api/items/" + item["id"],
        json={"name": "Renamed during analysis", "color": "red"},
    )
    result = client.post("/api/items/" + item["id"] + "/analyze")
    assert result.json()["name"] == "Renamed during analysis"
    assert result.json()["color"] == "red"


def test_retry_does_not_resurrect_deleted_item(client):
    item = upload(client).json()
    client.vision.callback = lambda: client.delete("/api/items/" + item["id"])
    assert client.post("/api/items/" + item["id"] + "/analyze").status_code == 404
    assert client.get("/api/items").json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"name": "  "},
        {"category": None},
        {"category": "fake"},
        {"embedding": [1]},
    ],
)
def test_invalid_updates(client, changes):
    item = upload(client).json()
    assert client.patch("/api/items/" + item["id"], json=changes).status_code == 422


def test_external_origin_cannot_mutate(client):
    assert (
        client.post(
            "/api/conversations", headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "selected,kwargs",
    [
        (["missing"], {}),
        (["top", "top"], {}),
        (["top", "top2"], {}),
        (["top", "dress"], {}),
        (["away"], {}),
        (["unknown"], {}),
        (["top"], {"exclude_ids": ["top"]}),
        (["top"], {"include_ids": ["shoe"]}),
        (["top"], {"exclude_categories": ["tops"]}),
        (["top"], {"exclude_colors": ["BLUE"]}),
        (["top"], {"exclude_subtypes": ["SHIRT"]}),
    ],
)
def test_outfit_rejections(selected, kwargs):
    items = [
        garment("top"),
        garment("top2"),
        garment("dress", "one-piece"),
        garment("away", available=False),
        garment("unknown", "unrecognized"),
        garment("shoe", "footwear"),
    ]
    outfits, errors = validate_outfits(
        Proposal.model_validate(proposal(selected)), items, Constraints(**kwargs)
    )
    assert not outfits and errors


def test_partial_and_distinct_outfits():
    items = [garment("top")]
    outfits, errors = validate_outfits(
        Proposal.model_validate(proposal(["top"], ["top"])), items, Constraints()
    )
    assert len(outfits) == 1 and errors
    assert outfits[0]["missing_components"] == ["bottom", "footwear"]


def test_ambiguous_reference_asks_question():
    model = Model({"include_references": ["blue shirt"]})
    reply, _ = Stylist(model, Vision()).recommend(
        "Use my blue shirt",
        [garment("a"), garment("b")],
        {"messages": [], "constraints": {}},
    )
    assert (
        "Which" in reply["message"]
        and not reply["outfits"]
        and len(model.contexts) == 1
    )


def test_replacement_releases_previous_required_garment():
    model = Model(
        {"include_references": ["red shirt"], "exclude_references": ["blue shirt"]},
        proposal(["red"]),
    )
    reply, constraints = Stylist(model, Vision()).recommend(
        "Use red instead of blue",
        [garment("blue"), garment("red", color="red")],
        {"messages": [], "constraints": {"include_ids": ["blue"]}},
    )
    assert reply["outfits"][0]["item_ids"] == ["red"]
    assert constraints["include_ids"] == ["red"]


def test_relaxing_prior_exclusion():
    model = Model({"allow_colors": ["blue"]}, proposal(["blue"]))
    reply, constraints = Stylist(model, Vision()).recommend(
        "Blue is fine now",
        [garment("blue")],
        {"messages": [], "constraints": {"exclude_colors": ["blue"]}},
    )
    assert constraints["exclude_colors"] == [] and reply["outfits"]


def test_targeted_replacement_keeps_other_pieces():
    items = [garment("top"), garment("old", "footwear"), garment("new", "footwear")]
    model = Model(
        {"replace_categories": ["footwear"], "reference_outfit": 1},
        proposal(["top", "new"]),
    )
    conversation = {
        "constraints": {},
        "messages": [{"outfits": proposal(["top", "old"])["outfits"]}],
    }
    reply, constraints = Stylist(model, Vision()).recommend(
        "Replace the shoes", items, conversation
    )
    assert constraints["include_ids"] == ["top"] and constraints["exclude_ids"] == [
        "old"
    ]
    assert reply["outfits"][0]["item_ids"] == ["top", "new"]


def test_invalid_response_gets_one_correction():
    model = Model({}, proposal(["invented"]), proposal(["top"]))
    reply, _ = Stylist(model, Vision()).recommend(
        "Casual", [garment("top")], {"messages": []}
    )
    assert len(model.contexts) == 3 and reply["outfits"][0]["item_ids"] == ["top"]
    assert "correction" in model.contexts[-1]


def test_malformed_response_failure_is_bounded():
    model = Model({}, ModelError("malformed"), ModelError("malformed"))
    with pytest.raises(ModelError):
        Stylist(model, Vision()).recommend("Casual", [garment("top")], {"messages": []})
    assert len(model.contexts) == 3


def test_empty_wardrobe_needs_no_model():
    reply, _ = Stylist(Model(), Vision()).recommend("Casual", [], {"messages": []})
    assert not reply["outfits"] and "Add a few" in reply["message"]


def test_conversation_persists_and_missing_items_are_rendered(client):
    item = upload(client).json()
    conversation = client.post("/api/conversations").json()
    client.app.state.store.save_exchange(
        conversation["id"],
        "A look",
        {
            "outfits": [
                {
                    **proposal([item["id"]])["outfits"][0],
                    "missing_components": ["bottom", "footwear"],
                }
            ],
            "message": "Here you go",
        },
        {},
    )
    client.delete("/api/items/" + item["id"])
    latest = client.get("/api/conversations/latest").json()
    assert len(latest["messages"]) == 2
    removed = latest["messages"][1]["outfits"][0]["items"][0]
    assert removed["deleted"] and removed["image_url"] is None


def test_ollama_maps_short_references_and_requires_selection(monkeypatch):
    import json
    import httpx
    from wardrobe.recommendations import Ollama

    def post(url, **kwargs):
        request = kwargs["json"]
        context = json.loads(request["messages"][1]["content"])
        assert context["candidates"][0]["id"] == "piece_1"
        assert request["format"]["properties"]["outfits"]["minItems"] == 1
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"message": {"content": json.dumps(proposal(["piece_1"]))}},
        )

    monkeypatch.setattr(httpx, "post", post)
    result = Ollama("http://127.0.0.1:11434", "gemma3:4b").generate(
        "Style", {"candidates": [garment("stored-id")]}, Proposal
    )
    assert result.outfits[0].item_ids == ["stored-id"]


@pytest.mark.parametrize("failure", ["timeout", "malformed", "wrong-schema"])
def test_ollama_failure_is_recoverable(monkeypatch, failure):
    import httpx
    from wardrobe.recommendations import Ollama

    def post(url, **kwargs):
        if failure == "timeout":
            raise httpx.ReadTimeout("Timed out")
        content = "not json" if failure == "malformed" else '{"outfits": "wrong"}'
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"message": {"content": content}},
        )

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(ModelError):
        Ollama("http://127.0.0.1:11434", "gemma3:4b").generate("Style", {}, Proposal)


def test_missing_available_role_requires_correction():
    result, errors = validate_outfits(
        Proposal.model_validate(proposal(["top"])),
        [garment("top"), garment("shoes", "footwear")],
        Constraints(),
    )
    assert not result and "available missing roles" in errors[0]


@pytest.mark.parametrize(
    "body",
    [
        [],
        None,
        {"message": []},
        {"message": {"content": None}},
        {"message": {"content": "[]"}},
        {"message": {"content": "null"}},
    ],
)
def test_malformed_ollama_envelope_is_recoverable(monkeypatch, body):
    import httpx
    from wardrobe.recommendations import Ollama
    from wardrobe.schemas import Intent

    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json=body
        ),
    )
    with pytest.raises(ModelError):
        Ollama("http://127.0.0.1:11434", "gemma3:4b").generate("Interpret", {}, Intent)


def test_available_dress_completes_shoes_only_proposal():
    outfits, errors = validate_outfits(
        Proposal.model_validate(proposal(["shoes"])),
        [garment("shoes", "footwear"), garment("dress", "one-piece")],
        Constraints(),
    )
    assert not outfits and errors


def test_excluding_previously_required_piece_releases_it():
    model = Model({"exclude_references": ["blue shirt"]}, proposal(["red"]))
    reply, constraints = Stylist(model, Vision()).recommend(
        "Do not use my blue shirt anymore",
        [garment("blue"), garment("red", color="red")],
        {"messages": [], "constraints": {"include_ids": ["blue"]}},
    )
    assert reply["outfits"] and constraints["include_ids"] == []
    assert constraints["exclude_descriptions"] == ["blue shirt"]


def test_description_exclusions_apply_to_new_items():
    constraints = Constraints(exclude_descriptions=["jeans"])
    from wardrobe.recommendations import excluded

    assert excluded(garment("new-jeans", "bottoms", subtype="jeans"), constraints)


def test_compact_request_parsing(monkeypatch):
    import json
    import httpx
    from wardrobe.recommendations import Ollama
    from wardrobe.schemas import Intent

    payload = {
        "query": "casual",
        "count": 3,
        "required_pieces": [],
        "avoided_pieces": ["jeans"],
        "allowed_pieces": [],
        "released_pieces": ["blue shirt"],
        "replacement_category": "",
        "outfit_number": 0,
        "start_over": False,
    }
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"message": {"content": json.dumps(payload)}},
        ),
    )
    result = Ollama("http://127.0.0.1:11434", "gemma3:4b").generate(
        "Interpret", {}, Intent
    )
    assert result.exclude_references == ["jeans"] and result.release_references == [
        "blue shirt"
    ]


def test_combination_search_respects_required_core():
    from wardrobe.recommendations import assemble_combinations

    items = [
        garment("top"),
        garment("other"),
        garment("bottom", "bottoms"),
        garment("shoes", "footwear"),
        garment("dress", "one-piece"),
    ]
    combinations = assemble_combinations(items, Constraints(include_ids=["top"]))
    assert combinations == [{"item_ids": ["top", "bottom", "shoes"]}]


def test_combination_search_never_adds_second_layer():
    from wardrobe.recommendations import assemble_combinations

    items = [
        garment("top"),
        garment("coat1", "outerwear"),
        garment("coat2", "outerwear"),
    ]
    combinations = assemble_combinations(items, Constraints(include_ids=["coat1"]))
    assert combinations == [{"item_ids": ["top", "coat1"]}]


def test_combination_cap_retains_separates_and_dresses():
    from wardrobe.recommendations import assemble_combinations

    items = [
        garment(f"{category}-{index}", category)
        for category in ("tops", "bottoms", "one-piece", "footwear")
        for index in range(8)
    ]
    combinations = assemble_combinations(items, Constraints())
    assert len(combinations) <= 80
    assert any(
        any(item.startswith("tops-") for item in outfit["item_ids"])
        for outfit in combinations
    )
    assert any(
        any(item.startswith("one-piece-") for item in outfit["item_ids"])
        for outfit in combinations
    )


def test_explicit_replacement_does_not_require_ambiguous_shoes():
    from wardrobe.recommendations import resolve_replacement_request
    from wardrobe.schemas import Intent

    intent = Intent(include_references=["shoes"], query="footwear")
    resolve_replacement_request(
        "Replace the shoes in option 2, keeping the rest", intent, "casual"
    )
    assert intent.include_references == []
    assert intent.replace_categories == ["footwear"]
    assert intent.reference_outfit == 2 and intent.query == "casual"


@pytest.mark.parametrize(
    "text,query,expected",
    [
        ("Do not replace the shoes; just make the outfit more casual", "casual", []),
        ("Replace the shoes with something formal", "formal", ["footwear"]),
    ],
)
def test_replacement_preserves_negation_and_explicit_style(text, query, expected):
    from wardrobe.recommendations import resolve_replacement_request
    from wardrobe.schemas import Intent

    intent = Intent(query=query)
    resolve_replacement_request(text, intent, "business casual")
    assert intent.replace_categories == expected and intent.query == query


def test_clear_wardrobe_removes_photos_and_preserves_history(client):
    first = upload(client).json()
    upload(client)
    conversation = client.post("/api/conversations").json()
    client.app.state.store.save_exchange(
        conversation["id"],
        "A look",
        {
            "message": "Here you go",
            "outfits": [
                {
                    **proposal([first["id"]])["outfits"][0],
                    "missing_components": ["bottom", "footwear"],
                }
            ],
        },
        {"include_ids": [first["id"]]},
    )
    assert len(list((client.settings.data_dir / "images").iterdir())) == 4
    assert client.delete("/api/items").status_code == 204
    assert client.get("/api/items").json() == []
    assert list((client.settings.data_dir / "images").iterdir()) == []
    restored = client.get("/api/conversations/" + conversation["id"]).json()
    assert restored["constraints"] == {}
    assert len(restored["messages"]) == 2
    assert restored["messages"][1]["outfits"][0]["items"][0]["deleted"]
    assert client.delete("/api/items").status_code == 204
    assert client.get("/media/" + first["id"]).status_code == 404


def test_clear_wardrobe_file_failure_can_be_retried(client, monkeypatch):
    from pathlib import Path

    upload(client)
    original = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path.parent == client.settings.data_dir / "images":
            raise PermissionError("Read-only directory")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    assert client.delete("/api/items").status_code == 503
    assert len(client.get("/api/items").json()) == 1
    monkeypatch.setattr(Path, "unlink", original)
    assert client.delete("/api/items").status_code == 204
    assert client.get("/api/items").json() == []
    assert list((client.settings.data_dir / "images").iterdir()) == []
