"""Explicit, one-time download. The application itself only loads local files."""

import os
from pathlib import Path

from huggingface_hub import hf_hub_download

model_dir = Path(
    os.getenv(
        "WARDROBE_MODEL_DIR",
        Path(__file__).resolve().parents[1] / "models" / "fashionclip",
    )
)
revision = "44f4c655124ed71e90cbf528d82f508d69d8a81b"
for filename in ("open_clip_config.json", "open_clip_model.safetensors"):
    hf_hub_download(
        "Marqo/marqo-fashionCLIP",
        filename=filename,
        revision=revision,
        local_dir=model_dir,
    )
print(f"FashionCLIP ready in {model_dir}")
print("For the language model, run: ollama pull gemma3:4b")
