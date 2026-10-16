import json
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

GARMENTS = {
    "tops": [
        "t-shirt",
        "button-down shirt",
        "blouse",
        "polo shirt",
        "sweater",
        "hoodie",
        "tank top",
        "sweatshirt",
    ],
    "bottoms": ["jeans", "trousers", "chinos", "shorts", "skirt", "leggings"],
    "one-piece": ["dress", "jumpsuit", "overalls"],
    "outerwear": [
        "blazer",
        "coat",
        "denim jacket",
        "leather jacket",
        "cardigan",
        "vest",
        "rain jacket",
    ],
    "footwear": [
        "sneakers",
        "loafers",
        "boots",
        "sandals",
        "heels",
        "dress shoes",
        "flats",
    ],
    "accessories": ["handbag", "belt", "scarf", "hat", "tie", "watch", "sunglasses"],
    "unrecognized": [
        "food",
        "furniture",
        "landscape",
        "electronic device",
        "document",
        "empty room",
    ],
}
ATTRIBUTES = {
    "color": [
        "black",
        "white",
        "cream",
        "gray",
        "navy",
        "blue",
        "brown",
        "beige",
        "green",
        "red",
        "pink",
        "purple",
        "yellow",
        "orange",
        "multicolor",
    ],
    "pattern": [
        "solid",
        "striped",
        "plaid",
        "floral",
        "polka dot",
        "graphic",
        "textured",
    ],
    "style": ["casual", "business casual", "formal", "athletic"],
}


class FashionVision:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.model = None
        self.lock = threading.RLock()
        self.text_cache = {}

    def ready(self):
        return all(
            (self.model_dir / filename).is_file()
            for filename in ("open_clip_model.safetensors", "open_clip_config.json")
        )

    def load(self):
        if self.model is not None:
            return
        if not self.ready():
            raise RuntimeError(
                "Download FashionCLIP first: .venv/bin/python scripts/download_models.py"
            )
        import open_clip
        import torch

        torch.set_num_threads(min(4, os.cpu_count() or 1))
        configuration = json.loads(
            (self.model_dir / "open_clip_config.json").read_text()
        )
        preprocessing = configuration["preprocess_cfg"]
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-16",
            pretrained=str(self.model_dir / "open_clip_model.safetensors"),
            device="cpu",
            image_mean=preprocessing["mean"],
            image_std=preprocessing["std"],
            image_interpolation=preprocessing["interpolation"],
            image_resize_mode=preprocessing["resize_mode"],
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-B-16")

    def encode_text(self, descriptions):
        import torch

        with self.lock, torch.inference_mode():
            self.load()
            cache_key = tuple(descriptions)
            if cache_key not in self.text_cache:
                tokens = self.tokenizer(descriptions)
                self.text_cache[cache_key] = (
                    self.model.encode_text(tokens, normalize=True).cpu().numpy()
                )
                if len(self.text_cache) > 64:
                    self.text_cache.pop(next(iter(self.text_cache)))
            return self.text_cache[cache_key]

    def analyze(self, image_path):
        import torch

        with self.lock, torch.inference_mode():
            self.load()
            with Image.open(image_path) as image:
                image_tensor = self.preprocess(image.convert("RGB")).unsqueeze(0)
            embedding = (
                self.model.encode_image(image_tensor, normalize=True).cpu().numpy()[0]
            )
            labels = [
                (category, subtype)
                for category, subtypes in GARMENTS.items()
                for subtype in subtypes
            ]
            similarities = (
                self.encode_text([f"A photo of a {subtype}." for _, subtype in labels])
                @ embedding
            )
            winner = int(np.argmax(similarities))
            category, subtype = labels[winner]
            predictions = {
                "category": category,
                "subtype": subtype if category != "unrecognized" else "",
            }
            for attribute, choices in ATTRIBUTES.items():
                descriptions = [f"A photo of {choice} clothing." for choice in choices]
                scores = self.encode_text(descriptions) @ embedding
                predictions[attribute] = (
                    choices[int(np.argmax(scores))]
                    if category != "unrecognized"
                    else ""
                )
            alternatives = [
                labels[int(index)][1] for index in np.argsort(similarities)[-3:][::-1]
            ]
            return predictions, embedding.tolist(), alternatives

    def rank(self, query, items):
        if not query or not self.ready():
            return items
        query_embedding = self.encode_text([query])[0]
        return sorted(
            items,
            key=lambda item: (
                float(np.dot(item["embedding"], query_embedding))
                if len(item.get("embedding", [])) == len(query_embedding)
                else -1
            ),
            reverse=True,
        )
