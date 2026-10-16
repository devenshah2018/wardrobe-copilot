import io
import threading
import warnings
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .benchmark import run_suite
from .config import Settings
from .recommendations import ModelError, Ollama, Stylist, validate_outfits
from .schemas import (
    Constraints,
    Conversation,
    BenchmarkRun,
    DatasetStatus,
    Garment,
    GarmentUpdate,
    ItemPage,
    MessageRequest,
    ModelStatus,
    Proposal,
    WardrobeId,
)
from .storage import Store, public_item, timestamp
from .vision import FashionVision

Image.MAX_IMAGE_PIXELS = 25_000_000


def create_app(settings=None, vision=None, stylist=None):
    settings = settings or Settings()
    store = Store(settings.data_dir)
    image_dir = settings.data_dir / "images"
    image_dir.mkdir(exist_ok=True)
    dataset_dir = settings.data_dir / "deepfashion2"
    vision = vision or FashionVision(settings.model_dir)
    language_model = Ollama(settings.ollama_url, settings.ollama_model)
    stylist = stylist or Stylist(language_model, vision)
    chat_lock = threading.Lock()
    item_lock = threading.RLock()
    app = FastAPI(title="Wardrobe Copilot", docs_url=None, redoc_url=None)
    app.state.store = store
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed_origins = {
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and origin
            and origin not in allowed_origins
        ):
            return JSONResponse(
                {"detail": "This app accepts requests from its local interface only."},
                status_code=403,
            )
        if request.url.path == "/api/items" and request.method == "POST":
            try:
                length = int(request.headers.get("content-length", 0))
            except ValueError:
                return JSONResponse({"detail": "Invalid upload size."}, status_code=400)
            if length > settings.max_image_bytes + 1024 * 1024:
                return JSONResponse(
                    {"detail": "Each photo must be 10 MB or smaller."}, status_code=413
                )
        return await call_next(request)

    def get_item(item_id, personal_only=False):
        item = store.item(item_id)
        if not item:
            raise HTTPException(404, "This wardrobe item no longer exists.")
        if personal_only and item.get("wardrobe", "personal") != "personal":
            raise HTTPException(403, "The DeepFashion2 wardrobe is read-only.")
        return item

    def analyze(item):
        attributes, embedding, alternatives, failure = None, [], [], None
        try:
            attributes, embedding, alternatives = vision.analyze(
                image_dir / item["filename"]
            )
        except Exception as error:
            failure = (
                str(error)
                if isinstance(error, RuntimeError)
                else "Photo saved. Analysis failed; retry or set the category manually."
            )
        with item_lock:
            item = get_item(item["id"])
            if attributes:
                item["suggestions"] = attributes
                item["alternatives"] = alternatives
                item["embedding"] = embedding
                for key, value in attributes.items():
                    if key not in item["edited_fields"]:
                        item[key] = value
                if (
                    "name" not in item["edited_fields"]
                    and item["category"] != "unrecognized"
                ):
                    item["name"] = (
                        f"{item['color']} {item['subtype']}".strip().capitalize()
                    )
                item["analysis_status"] = (
                    "ready" if attributes["category"] != "unrecognized" else "review"
                )
            else:
                item["analysis_status"] = "failed"
            item["analysis_error"] = failure
            store.save_item(item)
        return public_item(item)

    def present_conversation(conversation):
        for message in conversation["messages"]:
            for outfit in message.get("outfits", []):
                outfit["items"] = [
                    public_item(item)
                    if (item := store.item(item_id))
                    else {
                        "id": item_id,
                        "name": "Removed item",
                        "available": False,
                        "deleted": True,
                        "image_url": None,
                        "thumbnail_url": None,
                    }
                    for item_id in outfit["item_ids"]
                ]
        return conversation

    def present_benchmark(result):
        if result is None:
            return None
        for case in result["cases"]:
            for outfit in case["outfits"]:
                outfit["items"] = [
                    public_item(item)
                    if (item := store.item(item_id))
                    else {
                        "id": item_id,
                        "name": "Removed item",
                        "available": False,
                        "deleted": True,
                        "image_url": None,
                        "thumbnail_url": None,
                    }
                    for item_id in outfit["item_ids"]
                ]
        return result

    @app.get("/api/status", response_model=ModelStatus)
    def status():
        return {
            "vision_ready": vision.ready(),
            "ollama_ready": language_model.status(),
            "ollama_model": settings.ollama_model,
            "setup_hint": ".venv/bin/python scripts/download_models.py; ollama pull gemma3:4b",
        }

    @app.get("/api/items", response_model=list[Garment])
    def list_items(category: str | None = None):
        return [
            public_item(item)
            for item in store.items()
            if category is None or item["category"] == category
        ]

    @app.get("/api/deepfashion2/status", response_model=DatasetStatus)
    def deepfashion2_status():
        photo_count = sum(1 for _ in dataset_dir.glob("*.jpg"))
        indexed_count = store.count_items("deepfashion2")
        return {
            "photo_count": photo_count,
            "indexed_count": indexed_count,
            "ready": photo_count > 0 and photo_count == indexed_count,
        }

    @app.get("/api/deepfashion2/items", response_model=ItemPage)
    def deepfashion2_items(
        category: str | None = None,
        search: str = "",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=48, ge=1, le=100),
    ):
        items, total = store.item_page(
            "deepfashion2", category, search.strip()[:120], offset, limit
        )
        return {"items": [public_item(item) for item in items], "total": total}

    @app.post("/api/items", status_code=201, response_model=Garment)
    def upload_item(file: UploadFile = File(...)):
        content = file.file.read(settings.max_image_bytes + 1)
        if len(content) > settings.max_image_bytes:
            raise HTTPException(413, "Each photo must be 10 MB or smaller.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as source:
                    if source.format not in ("JPEG", "PNG", "WEBP"):
                        raise HTTPException(415, "Choose a JPEG, PNG, or WebP photo.")
                    image = ImageOps.exif_transpose(source).convert("RGBA")
                    background = Image.new("RGBA", image.size, "#f8f7f3")
                    background.alpha_composite(image)
                    image = background.convert("RGB")
                    image.thumbnail((1800, 1800))
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            raise HTTPException(
                400,
                "This image could not be opened. Choose a valid photo under 25 megapixels.",
            ) from error
        item_id = str(uuid4())
        filename, thumbnail = f"{item_id}.jpg", f"{item_id}-thumb.jpg"
        image.save(image_dir / filename, quality=90)
        image.thumbnail((480, 480))
        image.save(image_dir / thumbnail, quality=85)
        item = {
            "id": item_id,
            "name": "New wardrobe item",
            "category": "unrecognized",
            "subtype": "",
            "color": "",
            "pattern": "",
            "style": "",
            "available": True,
            "embedding": [],
            "filename": filename,
            "thumbnail": thumbnail,
            "image_url": f"/media/{item_id}",
            "thumbnail_url": f"/media/{item_id}?thumbnail=true",
            "suggestions": {},
            "alternatives": [],
            "edited_fields": [],
            "created_at": timestamp(),
            "analysis_status": "pending",
            "analysis_error": None,
        }
        with item_lock:
            store.save_item(item)
        return analyze(item)

    @app.patch("/api/items/{item_id}", response_model=Garment)
    def update_item(item_id: str, changes: GarmentUpdate):
        with item_lock:
            item = get_item(item_id, personal_only=True)
            updates = changes.model_dump(exclude_unset=True)
            item.update(updates)
            item["edited_fields"] = list(set(item["edited_fields"]) | set(updates))
            store.save_item(item)
            return public_item(item)

    @app.post("/api/items/{item_id}/analyze", response_model=Garment)
    def retry_analysis(item_id: str):
        return analyze(get_item(item_id, personal_only=True))

    @app.delete("/api/items", status_code=204)
    def clear_wardrobe():
        if not chat_lock.acquire(blocking=False):
            raise HTTPException(
                409, "Wait for the stylist to finish, then clear your wardrobe."
            )
        try:
            with item_lock:
                try:
                    for item in store.items():
                        for key in ("thumbnail", "filename"):
                            (image_dir / item[key]).unlink(missing_ok=True)
                        store.delete_item(item["id"])
                    store.reset_constraints()
                except OSError as error:
                    raise HTTPException(
                        503,
                        "Could not finish removing photos. Some pieces may already be removed. Check that the image folder is writable, then retry to finish clearing.",
                    ) from error
        finally:
            chat_lock.release()

    @app.delete("/api/items/{item_id}", status_code=204)
    def delete_item(item_id: str):
        with item_lock:
            item = get_item(item_id, personal_only=True)
            store.delete_item(item_id)
            for key in ("filename", "thumbnail"):
                (image_dir / item[key]).unlink(missing_ok=True)

    @app.get("/media/{item_id}")
    def media(item_id: str, thumbnail: bool = False):
        item = get_item(item_id)
        directory = (
            dataset_dir if item.get("wardrobe") == "deepfashion2" else image_dir
        )
        return FileResponse(
            directory / item["thumbnail" if thumbnail else "filename"],
            media_type="image/jpeg",
        )

    @app.get("/api/conversations/latest", response_model=Conversation | None)
    def latest_conversation(wardrobe: WardrobeId = "personal"):
        conversation = store.latest_conversation(wardrobe)
        return present_conversation(conversation) if conversation else None

    @app.post("/api/conversations", status_code=201, response_model=Conversation)
    def new_conversation(wardrobe: WardrobeId = "personal"):
        return store.create_conversation(wardrobe)

    @app.get("/api/conversations/{conversation_id}", response_model=Conversation)
    def get_conversation(conversation_id: str):
        conversation = store.conversation(conversation_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found.")
        return present_conversation(conversation)

    @app.post(
        "/api/conversations/{conversation_id}/messages", response_model=Conversation
    )
    def send_message(conversation_id: str, message: MessageRequest):
        if not chat_lock.acquire(blocking=False):
            raise HTTPException(
                409, "The stylist is finishing another request. Try again in a moment."
            )
        try:
            conversation = store.conversation(conversation_id)
            if not conversation:
                raise HTTPException(404, "Conversation not found.")
            try:
                reply, constraints = stylist.recommend(
                    message.text, store.items(conversation["wardrobe"]), conversation
                )
            except ModelError as error:
                raise HTTPException(503, str(error)) from error
            if reply["outfits"]:
                # A garment can be edited or deleted while the model is thinking.
                proposal = Proposal.model_validate(reply)
                checked, errors = validate_outfits(
                    proposal, store.items(conversation["wardrobe"]),
                    Constraints.model_validate(constraints)
                )
                reply["outfits"] = checked
                if errors and not checked:
                    reply["message"] = (
                        "Your wardrobe changed while I was styling. Ask again to use the updated pieces."
                    )
            store.save_exchange(conversation_id, message.text, reply, constraints)
            return present_conversation(store.conversation(conversation_id))
        finally:
            chat_lock.release()

    @app.get("/api/benchmarks/latest", response_model=BenchmarkRun | None)
    def latest_benchmark():
        return present_benchmark(store.latest_benchmark())

    @app.get("/api/benchmarks/{benchmark_id}", response_model=BenchmarkRun)
    def get_benchmark(benchmark_id: str):
        result = store.benchmark(benchmark_id)
        if result is None:
            raise HTTPException(404, "Benchmark run not found.")
        return present_benchmark(result)

    @app.post("/api/benchmarks", status_code=202, response_model=BenchmarkRun)
    def start_benchmark():
        state = deepfashion2_status()
        if not state["ready"]:
            raise HTTPException(
                409,
                "Index the DeepFashion2 photos first: .venv/bin/python scripts/index_deepfashion2.py",
            )
        if not language_model.status():
            raise HTTPException(503, "Start Ollama and install gemma3:4b first.")
        if not chat_lock.acquire(blocking=False):
            raise HTTPException(409, "The stylist is already working. Try again shortly.")
        result = {
            "id": str(uuid4()),
            "created_at": timestamp(),
            "status": "running",
            "photo_count": state["photo_count"],
            "indexed_count": state["indexed_count"],
            "cases": [],
            "error": None,
        }
        store.save_benchmark(result)

        def worker():
            try:
                run_suite(
                    stylist, store.items("deepfashion2"),
                    store.save_benchmark, result,
                )
            except Exception:
                result["status"] = "failed"
                result["error"] = "The benchmark stopped unexpectedly. Run it again."
                store.save_benchmark(result)
            finally:
                chat_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return result

    if (settings.frontend_dir / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=settings.frontend_dir / "assets"),
            name="assets",
        )

    @app.get("/")
    def index():
        if not (settings.frontend_dir / "index.html").is_file():
            return JSONResponse(
                {
                    "detail": "Build the frontend first: cd frontend && npm install && npm run build"
                },
                status_code=503,
            )
        return FileResponse(settings.frontend_dir / "index.html")

    return app


app = create_app()
