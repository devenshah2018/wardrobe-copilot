import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    data_dir: Path = Path(os.getenv("WARDROBE_DATA_DIR", PROJECT_ROOT / "data"))
    model_dir: Path = Path(
        os.getenv("WARDROBE_MODEL_DIR", PROJECT_ROOT / "models" / "fashionclip")
    )
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    frontend_dir: Path = PROJECT_ROOT / "frontend" / "dist"
    max_image_bytes: int = 10 * 1024 * 1024
