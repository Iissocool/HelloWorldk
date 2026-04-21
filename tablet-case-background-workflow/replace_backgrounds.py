from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


Point = tuple[int, int]
Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class CleanupOverlay:
    rect: Rect
    fill: tuple[int, int, int, int]
    radius: int = 0


@dataclass(frozen=True)
class LayoutConfig:
    polygons: tuple[tuple[Point, ...], ...]
    theme: str
    cleanup_overlays: tuple[CleanupOverlay, ...] = ()


CONFIGS: dict[str, LayoutConfig] = {
    "1-(1)_01.jpg": LayoutConfig(
        polygons=(
            ((34, 76), (68, 44), (536, 47), (590, 92), (590, 1048), (540, 1080), (54, 1062), (22, 1028)),
            ((584, 566), (1138, 726), (1032, 944), (1076, 1020), (968, 1098), (480, 940), (604, 560)),
            ((426, 946), (575, 806), (655, 818), (498, 1040), (398, 1008)),
        ),
        theme="warm_lifestyle",
    ),
    "1-(1)_02.jpg": LayoutConfig(
        polygons=(
            ((108, 790), (594, 168), (1076, 282), (822, 1128), (106, 804)),
        ),
        theme="warm_lifestyle",
    ),
    "1-(1)_03.jpg": LayoutConfig(
        polygons=(
            ((86, 268), (336, 186), (460, 302), (460, 1084), (86, 1086)),
            ((346, 152), (923, 248), (940, 1016), (816, 1070), (238, 1098), (236, 342)),
            ((910, 332), (1062, 338), (1078, 786), (986, 848), (906, 824)),
        ),
        theme="warm_lifestyle",
        cleanup_overlays=(
            CleanupOverlay((640, 76, 1092, 144), (227, 215, 203, 245), 18),
            CleanupOverlay((650, 188, 708, 234), (232, 220, 209, 242), 18),
        ),
    ),
    "1-(1)_04.jpg": LayoutConfig(
        polygons=(
            ((38, 550), (176, 458), (392, 140), (970, 242), (1040, 318), (970, 1000), (784, 1038), (302, 1018), (118, 920), (36, 852)),
            ((828, 286), (1020, 322), (1002, 870), (844, 872)),
        ),
        theme="blush_studio",
        cleanup_overlays=(
            CleanupOverlay((802, 968, 1114, 1088), (229, 215, 211, 245), 22),
        ),
    ),
    "1-(1)_05.jpg": LayoutConfig(
        polygons=(
            ((268, 254), (824, 252), (948, 1048), (218, 1044)),
        ),
        theme="protective_dark",
    ),
}
def draw_rounded_rect(draw: ImageDraw.ImageDraw, rect, radius: int, fill: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(rect, radius=radius, fill=fill)


def make_background(size: tuple[int, int], theme: str) -> Image.Image:
    width, height = size
    base = Image.new("RGBA", size, (245, 240, 232, 255))
    draw = ImageDraw.Draw(base)

    if theme == "warm_lifestyle":
        for y in range(height):
            t = y / max(height - 1, 1)
            color = (
                int(246 - 18 * t),
                int(241 - 11 * t),
                int(235 - 8 * t),
                255,
            )
            draw.line((0, y, width, y), fill=color)

        draw.rectangle((0, int(height * 0.72), width, height), fill=(230, 220, 209, 255))
        draw_rounded_rect(draw, (int(width * 0.58), int(height * 0.68), int(width * 0.92), int(height * 0.9)), 36, (236, 228, 217, 255))
        draw_rounded_rect(draw, (int(width * 0.06), int(height * 0.12), int(width * 0.34), int(height * 0.34)), 30, (239, 231, 221, 180))
        draw_rounded_rect(draw, (int(width * 0.76), int(height * 0.1), int(width * 0.98), int(height * 0.3)), 42, (224, 213, 199, 170))

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        o = ImageDraw.Draw(overlay)
        o.polygon(
            [
                (int(width * 0.08), int(height * 0.08)),
                (int(width * 0.24), int(height * 0.03)),
                (int(width * 0.34), int(height * 0.2)),
                (int(width * 0.18), int(height * 0.28)),
            ],
            fill=(255, 255, 255, 70),
        )
        o.ellipse((int(width * 0.78), int(height * 0.08), int(width * 1.05), int(height * 0.34)), fill=(255, 255, 255, 55))
        o.arc((int(width * 0.68), int(height * 0.48), int(width * 1.08), int(height * 0.92)), 220, 320, fill=(188, 176, 162, 120), width=10)
        base.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(18)))

    elif theme == "blush_studio":
        for y in range(height):
            t = y / max(height - 1, 1)
            color = (
                int(243 - 10 * t),
                int(231 - 6 * t),
                int(229 - 3 * t),
                255,
            )
            draw.line((0, y, width, y), fill=color)

        draw.rectangle((0, int(height * 0.74), width, height), fill=(229, 215, 210, 255))
        draw_rounded_rect(draw, (int(width * 0.67), int(height * 0.6), int(width * 0.95), int(height * 0.84)), 38, (241, 230, 226, 255))
        draw_rounded_rect(draw, (int(width * 0.07), int(height * 0.18), int(width * 0.27), int(height * 0.5)), 28, (239, 224, 220, 170))

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        o = ImageDraw.Draw(overlay)
        o.ellipse((int(width * 0.02), int(height * 0.04), int(width * 0.42), int(height * 0.42)), fill=(255, 255, 255, 60))
        o.rectangle((int(width * 0.8), int(height * 0.18), int(width * 0.93), int(height * 0.48)), fill=(225, 209, 203, 90))
        o.polygon(
            [
                (int(width * 0.78), int(height * 0.1)),
                (int(width * 0.96), int(height * 0.2)),
                (int(width * 0.88), int(height * 0.48)),
                (int(width * 0.7), int(height * 0.38)),
            ],
            fill=(255, 255, 255, 50),
        )
        base.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(20)))

    elif theme == "protective_dark":
        for y in range(height):
            t = y / max(height - 1, 1)
            color = (
                int(42 + 14 * t),
                int(46 + 12 * t),
                int(54 + 10 * t),
                255,
            )
            draw.line((0, y, width, y), fill=color)

        draw.rectangle((0, int(height * 0.76), width, height), fill=(47, 50, 58, 255))
        draw_rounded_rect(draw, (int(width * 0.08), int(height * 0.66), int(width * 0.31), int(height * 0.9)), 26, (64, 69, 78, 255))
        draw_rounded_rect(draw, (int(width * 0.74), int(height * 0.6), int(width * 0.94), int(height * 0.84)), 26, (59, 63, 72, 255))

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        o = ImageDraw.Draw(overlay)
        o.ellipse((int(width * 0.04), int(height * 0.04), int(width * 0.4), int(height * 0.36)), fill=(120, 130, 150, 40))
        o.ellipse((int(width * 0.6), int(height * 0.06), int(width * 1.02), int(height * 0.42)), fill=(130, 140, 165, 32))
        o.polygon(
            [
                (int(width * 0.12), int(height * 0.58)),
                (int(width * 0.23), int(height * 0.45)),
                (int(width * 0.34), int(height * 0.57)),
                (int(width * 0.26), int(height * 0.72)),
            ],
            fill=(90, 96, 108, 120),
        )
        o.polygon(
            [
                (int(width * 0.83), int(height * 0.56)),
                (int(width * 0.96), int(height * 0.48)),
                (int(width * 1.03), int(height * 0.68)),
                (int(width * 0.88), int(height * 0.74)),
            ],
            fill=(88, 94, 106, 110),
        )
        base.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(22)))

    else:
        raise ValueError(f"Unknown theme: {theme}")

    return base


def extract_foreground(image: Image.Image, config: LayoutConfig) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = Image.new("L", rgba.size, 0)
    draw = ImageDraw.Draw(alpha)
    for polygon in config.polygons:
        draw.polygon(polygon, fill=255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(2.2))
    rgba.putalpha(alpha)
    return rgba


def add_drop_shadow(background: Image.Image, alpha: Image.Image) -> Image.Image:
    shadow = Image.new("RGBA", background.size, (0, 0, 0, 0))
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(16))
    shadow.putalpha(shadow_alpha)
    tint = Image.new("RGBA", background.size, (40, 34, 30, 88))
    shadow = Image.composite(tint, shadow, shadow_alpha)
    shadow = shadow.transform(
        background.size,
        Image.AFFINE,
        (1, 0, 18, 0, 1, 24),
        resample=Image.Resampling.BICUBIC,
    )
    return Image.alpha_composite(background, shadow)


def compose(image: Image.Image, config: LayoutConfig) -> tuple[Image.Image, Image.Image]:
    foreground = extract_foreground(image, config)
    background = make_background(image.size, config.theme)
    background = add_drop_shadow(background, foreground.getchannel("A"))
    composed = Image.alpha_composite(background, foreground)
    if config.cleanup_overlays:
        draw = ImageDraw.Draw(composed)
        for overlay in config.cleanup_overlays:
            if overlay.radius:
                draw.rounded_rectangle(overlay.rect, radius=overlay.radius, fill=overlay.fill)
            else:
                draw.rectangle(overlay.rect, fill=overlay.fill)
    return composed.convert("RGB"), foreground


def process_folder(input_dir: Path, output_dir: Path, mask_dir: Path | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if mask_dir is not None:
        mask_dir.mkdir(parents=True, exist_ok=True)

    for image_path in sorted(input_dir.glob("*.jpg")):
        config = CONFIGS.get(image_path.name)
        if config is None:
            print(f"Skip {image_path.name}: no config")
            continue

        source = Image.open(image_path)
        result, foreground = compose(source, config)
        out_path = output_dir / f"{image_path.stem}-styled.jpg"
        result.save(out_path, quality=95)
        print(f"Saved {out_path}")

        if mask_dir is not None:
            preview = Image.new("RGBA", source.size, (250, 244, 238, 255))
            preview.alpha_composite(foreground)
            preview.convert("RGB").save(mask_dir / f"{image_path.stem}-mask-preview.jpg", quality=95)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace tablet-case marketing backgrounds while preserving the product.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Folder containing the source JPG images.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Folder for the styled outputs.")
    parser.add_argument("--mask-preview-dir", type=Path, help="Optional folder for foreground preview images.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process_folder(args.input_dir, args.output_dir, args.mask_preview_dir)


if __name__ == "__main__":
    main()
