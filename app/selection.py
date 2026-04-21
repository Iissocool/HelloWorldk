from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image


KEYWORD_RULES = {
    "anime": [
        "anime",
        "manga",
        "manhwa",
        "manhua",
        "chibi",
        "cartoon",
        "comic",
        "illustration",
        "waifu",
        "vtuber",
    ],
    "portrait": [
        "portrait",
        "person",
        "people",
        "human",
        "selfie",
        "headshot",
        "model",
        "woman",
        "man",
        "girl",
        "boy",
        "face",
    ],
    "detail": [
        "animal",
        "plant",
        "flower",
        "leaf",
        "tree",
        "fur",
        "hair",
        "pet",
        "cat",
        "dog",
        "product",
        "jewelry",
        "watch",
        "glass",
        "bottle",
    ],
    "general": [
        "car",
        "vehicle",
        "bike",
        "motor",
        "truck",
        "bus",
    ],
}



def keyword_category(path: Path) -> Tuple[str | None, List[str]]:
    haystack = f"{path.stem} {path.parent.name}".lower()
    for category, keywords in KEYWORD_RULES.items():
        matched = [keyword for keyword in keywords if keyword in haystack]
        if matched:
            return category, matched
    return None, []



def analyze_image(path: Path) -> Dict[str, float]:
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        rgb.thumbnail((256, 256), Image.Resampling.LANCZOS)
        arr = np.asarray(rgb, dtype=np.float32) / 255.0
        width, height = rgb.width, rgb.height

    gray = arr.mean(axis=2)
    edge_mag = np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean()

    min_rgb = arr.min(axis=2)
    max_rgb = arr.max(axis=2)
    saturation = np.where(max_rgb > 0, (max_rgb - min_rgb) / np.maximum(max_rgb, 1e-6), 0)

    quantized = np.round(arr * 15).astype(np.uint8).reshape(-1, 3)
    color_richness = len(np.unique(quantized, axis=0)) / 4096.0

    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]
    skin_mask = (
        (r > 0.35)
        & (g > 0.2)
        & (b > 0.15)
        & ((r - g) > 0.02)
        & (r > b)
        & ((r - np.minimum(g, b)) > 0.05)
    )

    return {
        "width": float(width),
        "height": float(height),
        "aspect_ratio": float(width / max(height, 1)),
        "edge_density": float(edge_mag),
        "saturation_mean": float(saturation.mean()),
        "color_richness": float(color_richness),
        "skin_ratio": float(skin_mask.mean()),
        "green_ratio": float(((g > r) & (g > b) & (g > 0.25)).mean()),
    }



def choose_category(path: Path, metrics: Dict[str, float]) -> Tuple[str, str]:
    keyword_hit, matched = keyword_category(path)
    if keyword_hit is not None:
        return keyword_hit, f"filename keywords: {', '.join(matched)}"

    if (
        metrics["saturation_mean"] > 0.22
        and metrics["color_richness"] < 0.12
        and metrics["edge_density"] > 0.07
        and metrics["skin_ratio"] < 0.16
    ):
        return "anime", "flat colors plus strong edges suggest illustration or anime"

    if metrics["skin_ratio"] > 0.18 and 0.55 < metrics["aspect_ratio"] < 1.6:
        return "portrait", "skin ratio and framing suggest a human portrait"

    if (
        metrics["green_ratio"] > 0.22
        or metrics["edge_density"] > 0.11
        or metrics["color_richness"] > 0.28
    ):
        return "detail", "dense edges or rich texture suggest a detail-heavy subject"

    return "general", "defaulted to general scene handling"



def choose_model(category: str, strategy: str) -> str:
    if strategy == "speed":
        return {
            "anime": "isnet-anime",
            "portrait": "u2net_human_seg",
            "detail": "isnet-general-use",
            "general": "u2netp",
        }[category]

    if strategy == "balanced":
        return {
            "anime": "isnet-anime",
            "portrait": "u2net_human_seg",
            "detail": "birefnet-general-lite",
            "general": "bria-rmbg",
        }[category]

    return {
        "anime": "isnet-anime",
        "portrait": "bria-rmbg",
        "detail": "birefnet-general-lite",
        "general": "bria-rmbg",
    }[category]
