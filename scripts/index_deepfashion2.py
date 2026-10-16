"""Index the local DeepFashion2 validation photos for the demo wardrobe."""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from wardrobe.config import Settings  # noqa: E402
from wardrobe.storage import Store, timestamp  # noqa: E402
from wardrobe.vision import ATTRIBUTES, FashionVision  # noqa: E402


LABELS = [
    ("tops", "short sleeve top"),
    ("tops", "long sleeve top"),
    ("outerwear", "short sleeve outerwear"),
    ("outerwear", "long sleeve outerwear"),
    ("outerwear", "vest"),
    ("tops", "sling top"),
    ("bottoms", "shorts"),
    ("bottoms", "trousers"),
    ("bottoms", "skirt"),
    ("one-piece", "short sleeve dress"),
    ("one-piece", "long sleeve dress"),
    ("one-piece", "vest dress"),
    ("one-piece", "sling dress"),
]


def index_photos(source_dir, store, vision, batch_size, limit=None):
    import torch

    photos = sorted(source_dir.glob("*.jpg"))
    known = {item["id"] for item in store.items("deepfashion2")}
    pending = [photo for photo in photos if f"df2-{photo.stem}" not in known]
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        print(f"Already indexed {len(known):,} DeepFashion2 photos.")
        return
    vision.load()
    label_vectors = vision.encode_text(
        [f"A photo of a {subtype}." for _, subtype in LABELS]
    )
    attribute_vectors = {
        key: vision.encode_text([f"A photo of {value} clothing." for value in values])
        for key, values in ATTRIBUTES.items()
    }
    indexed = 0
    failed = 0
    for start in range(0, len(pending), batch_size):
        paths = []
        tensors = []
        for path in pending[start : start + batch_size]:
            try:
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    tensors.append(vision.preprocess(image))
                paths.append(path)
            except (OSError, ValueError):
                failed += 1
        if not tensors:
            continue
        with torch.inference_mode():
            vectors = vision.model.encode_image(
                torch.stack(tensors), normalize=True
            ).cpu().numpy()
        label_scores = vectors @ label_vectors.T
        attribute_scores = {
            key: vectors @ text_vectors.T
            for key, text_vectors in attribute_vectors.items()
        }
        records = []
        for index, path in enumerate(paths):
            label_index = int(np.argmax(label_scores[index]))
            category, subtype = LABELS[label_index]
            attributes = {
                key: choices[int(np.argmax(attribute_scores[key][index]))]
                for key, choices in ATTRIBUTES.items()
            }
            item_id = f"df2-{path.stem}"
            records.append(
                {
                    "id": item_id,
                    "wardrobe": "deepfashion2",
                    "name": f"{attributes['color']} {subtype}".capitalize(),
                    "category": category,
                    "subtype": subtype,
                    **attributes,
                    "available": True,
                    "embedding": vectors[index].tolist(),
                    "filename": path.name,
                    "thumbnail": path.name,
                    "image_url": f"/media/{item_id}",
                    "thumbnail_url": f"/media/{item_id}?thumbnail=true",
                    "suggestions": {},
                    "alternatives": [
                        LABELS[int(choice)][1]
                        for choice in np.argsort(label_scores[index])[-3:][::-1]
                    ],
                    "edited_fields": [],
                    "created_at": timestamp(),
                    "analysis_status": "ready",
                    "analysis_error": None,
                }
            )
        store.save_items(records)
        indexed += len(records)
        if indexed % (batch_size * 10) < batch_size:
            print(f"Indexed {indexed:,}/{len(pending):,} photos", flush=True)
    print(f"Done: {indexed:,} new items, {failed:,} unreadable photos.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    settings = Settings()
    source_dir = settings.data_dir / "deepfashion2"
    if not source_dir.is_dir():
        parser.error(f"DeepFashion2 photos are missing from {source_dir}")
    index_photos(
        source_dir, Store(settings.data_dir), FashionVision(settings.model_dir),
        args.batch_size, args.limit,
    )


if __name__ == "__main__":
    main()
