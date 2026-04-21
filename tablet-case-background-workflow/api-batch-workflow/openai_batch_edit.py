from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


Point = tuple[int, int]

PROMPT_SUFFIX = """
Only edit the masked background area outside the product.
Remove all descriptive text, slogans, feature labels, callouts, and marketing copy from the edited area.
Keep the tablet case product unchanged in structure and appearance.
Do not redesign or repaint the shell, clear bumper, camera holes, cutouts, folds, stand shape, reflections, buttons, ports, or printed artwork.
Return a clean ecommerce-ready product background with tasteful lifestyle accents that suit a tablet case listing.
""".strip()


@dataclass(frozen=True)
class ImageMask:
    polygons: tuple[tuple[Point, ...], ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-edit product images with the OpenAI Images API while compositing the original product pixels back on top."
    )
    parser.add_argument("--input-dir", type=Path, required=True, help="Folder containing the source images.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Folder for final edited images.")
    parser.add_argument("--mask-config", type=Path, required=True, help="JSON file containing preserve polygons.")
    parser.add_argument("--prompt", help="User prompt describing the desired background replacement.")
    parser.add_argument("--prompt-file", type=Path, help="Text file containing the desired background replacement prompt.")
    parser.add_argument("--model", default="gpt-image-1", help="Images API model name. Override if your account uses a newer default.")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel image jobs.")
    parser.add_argument("--feather", type=float, default=2.0, help="Mask feather radius in pixels at original resolution.")
    parser.add_argument("--api-size", choices=["auto", "1024x1024", "1536x1024", "1024x1536"], default="1024x1024")
    parser.add_argument(
        "--input-fidelity",
        choices=["omit", "low", "high"],
        default="omit",
        help="Optional input_fidelity value. Leave as omit if your target model/account does not accept it."
    )
    parser.add_argument("--save-intermediates", action="store_true", help="Save API-sized PNGs, masks, and raw API outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Create masks and job metadata but do not call the OpenAI API.")
    return parser.parse_args()


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return args.prompt_file.read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    raise SystemExit("A prompt is required. Pass --prompt or --prompt-file.")


def load_masks(mask_config_path: Path) -> dict[str, ImageMask]:
    payload = json.loads(mask_config_path.read_text(encoding="utf-8"))
    result: dict[str, ImageMask] = {}
    for filename, item in payload.get("images", {}).items():
        polygons = []
        for polygon in item.get("polygons", []):
            polygons.append(tuple((int(x), int(y)) for x, y in polygon))
        result[filename] = ImageMask(polygons=tuple(polygons))
    return result


def build_preserve_alpha(size: tuple[int, int], polygons: tuple[tuple[Point, ...], ...], feather: float) -> Image.Image:
    alpha = Image.new("L", size, 0)
    draw = ImageDraw.Draw(alpha)
    for polygon in polygons:
        draw.polygon(polygon, fill=255)
    if feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    return alpha


def scale_polygons(
    polygons: tuple[tuple[Point, ...], ...],
    src_size: tuple[int, int],
    dst_size: tuple[int, int],
) -> tuple[tuple[Point, ...], ...]:
    src_w, src_h = src_size
    dst_w, dst_h = dst_size
    scaled: list[tuple[Point, ...]] = []
    for polygon in polygons:
        scaled_polygon = []
        for x, y in polygon:
            scaled_x = round(x * dst_w / src_w)
            scaled_y = round(y * dst_h / src_h)
            scaled_polygon.append((scaled_x, scaled_y))
        scaled.append(tuple(scaled_polygon))
    return tuple(scaled)


def render_mask_for_edit(size: tuple[int, int], preserve_alpha: Image.Image) -> Image.Image:
    mask = Image.new("RGBA", size, (0, 0, 0, 0))
    protected = Image.new("RGBA", size, (255, 255, 255, 255))
    return Image.composite(protected, mask, preserve_alpha)


def composite_original_subject(original: Image.Image, edited_background: Image.Image, preserve_alpha: Image.Image) -> Image.Image:
    original_rgba = original.convert("RGBA")
    edited_rgba = edited_background.convert("RGBA").resize(original.size, Image.Resampling.LANCZOS)

    foreground = original_rgba.copy()
    foreground.putalpha(preserve_alpha)
    return Image.alpha_composite(edited_rgba, foreground).convert("RGB")


def render_mask_preview(original: Image.Image, preserve_alpha: Image.Image) -> Image.Image:
    preview = Image.new("RGBA", original.size, (246, 242, 236, 255))
    foreground = original.convert("RGBA")
    foreground.putalpha(preserve_alpha)
    preview.alpha_composite(foreground)
    return preview.convert("RGB")


def read_edited_image_b64(response: Any) -> bytes:
    data = getattr(response, "data", None) or response["data"]
    first = data[0]
    if hasattr(first, "b64_json"):
        b64_payload = first.b64_json
    else:
        b64_payload = first["b64_json"]
    return base64.b64decode(b64_payload)


def final_prompt(user_prompt: str, filename: str) -> str:
    prompt = user_prompt.replace("{filename}", filename).strip()
    return f"{prompt}\n\n{PROMPT_SUFFIX}"


def call_images_api(
    image_path: Path,
    mask_path: Path,
    prompt: str,
    model: str,
    api_size: str,
    input_fidelity: str,
) -> bytes:
    from openai import OpenAI

    client = OpenAI()
    request: dict[str, Any] = {
        "model": model,
        "image": image_path.open("rb"),
        "mask": mask_path.open("rb"),
        "prompt": prompt,
        "size": api_size,
    }
    if input_fidelity != "omit":
        request["input_fidelity"] = input_fidelity

    try:
        response = client.images.edit(**request)
        return read_edited_image_b64(response)
    finally:
        request["image"].close()
        request["mask"].close()


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def build_job(
    image_path: Path,
    mask: ImageMask,
    base_prompt: str,
    output_dir: Path,
    run_dir: Path,
    api_size: str,
    feather: float,
) -> dict[str, Any]:
    original = Image.open(image_path).convert("RGB")
    original_size = original.size

    if api_size == "auto":
        api_width, api_height = original_size
    else:
        api_width, api_height = (int(part) for part in api_size.split("x"))
    api_size_tuple = (api_width, api_height)

    scaled_polygons = scale_polygons(mask.polygons, original_size, api_size_tuple)
    preserve_alpha_original = build_preserve_alpha(original_size, mask.polygons, feather)
    preserve_alpha_api = build_preserve_alpha(api_size_tuple, scaled_polygons, max(0.5, feather * api_width / max(original_size[0], 1)))

    api_input_image = original.resize(api_size_tuple, Image.Resampling.LANCZOS)
    api_mask_image = render_mask_for_edit(api_size_tuple, preserve_alpha_api)

    temp_dir = run_dir / "temp"
    api_input_path = temp_dir / f"{image_path.stem}-api-input.png"
    api_mask_path = temp_dir / f"{image_path.stem}-api-mask.png"

    save_png(api_input_image, api_input_path)
    save_png(api_mask_image, api_mask_path)

    return {
        "image_path": image_path,
        "filename": image_path.name,
        "original": original,
        "preserve_alpha_original": preserve_alpha_original,
        "api_input_path": api_input_path,
        "api_mask_path": api_mask_path,
        "prompt": final_prompt(base_prompt, image_path.name),
        "output_path": output_dir / f"{image_path.stem}-api-final.png",
        "mask_preview_path": run_dir / "mask-previews" / f"{image_path.stem}-mask-preview.jpg",
        "raw_api_path": run_dir / "raw-api" / f"{image_path.stem}-raw-api.png",
    }


def ensure_openai_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Export it before running the API workflow.")


def process_job(
    job: dict[str, Any],
    model: str,
    api_size: str,
    input_fidelity: str,
    save_intermediates: bool,
    dry_run: bool,
    log_lock: threading.Lock,
) -> dict[str, Any]:
    image_path = job["image_path"]

    job["mask_preview_path"].parent.mkdir(parents=True, exist_ok=True)
    render_mask_preview(job["original"], job["preserve_alpha_original"]).save(job["mask_preview_path"], quality=95)

    if dry_run:
        return {
            "file": image_path.name,
            "status": "dry-run",
            "output": str(job["output_path"]),
            "mask_preview": str(job["mask_preview_path"]),
        }

    edited_bytes = None
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            edited_bytes = call_images_api(
                image_path=job["api_input_path"],
                mask_path=job["api_mask_path"],
                prompt=job["prompt"],
                model=model,
                api_size=api_size,
                input_fidelity=input_fidelity,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(8, 2 ** attempt))

    if edited_bytes is None:
        raise RuntimeError(f"OpenAI API failed for {image_path.name}: {last_error}") from last_error

    job["raw_api_path"].parent.mkdir(parents=True, exist_ok=True)
    job["raw_api_path"].write_bytes(edited_bytes)
    edited_image = Image.open(job["raw_api_path"]).convert("RGBA")
    final_image = composite_original_subject(job["original"], edited_image, job["preserve_alpha_original"])

    job["output_path"].parent.mkdir(parents=True, exist_ok=True)
    final_image.save(job["output_path"], format="PNG")

    if not save_intermediates:
        try:
            job["raw_api_path"].unlink(missing_ok=True)
            job["api_input_path"].unlink(missing_ok=True)
            job["api_mask_path"].unlink(missing_ok=True)
        except OSError:
            pass

    with log_lock:
        print(f"Processed {image_path.name} -> {job['output_path']}")

    return {
        "file": image_path.name,
        "status": "ok",
        "output": str(job["output_path"]),
        "mask_preview": str(job["mask_preview_path"]),
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_prompt = read_prompt(args)
    masks = load_masks(args.mask_config)

    input_dir = args.input_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.dry_run:
        ensure_openai_api_key()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / "_runs" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    missing_masks = [p.name for p in image_paths if p.name not in masks]
    if missing_masks:
        raise SystemExit(f"Missing mask config for: {', '.join(missing_masks)}")

    jobs = [
        build_job(
            image_path=image_path,
            mask=masks[image_path.name],
            base_prompt=base_prompt,
            output_dir=output_dir,
            run_dir=run_dir,
            api_size=args.api_size,
            feather=args.feather,
        )
        for image_path in image_paths
    ]

    summary: list[dict[str, Any]] = []
    log_lock = threading.Lock()
    worker_count = max(1, args.workers)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                process_job,
                job,
                args.model,
                args.api_size,
                args.input_fidelity,
                args.save_intermediates,
                args.dry_run,
                log_lock,
            )
            for job in jobs
        ]
        for future in as_completed(futures):
            summary.append(future.result())

    manifest = {
        "model": args.model,
        "api_size": args.api_size,
        "input_fidelity": args.input_fidelity,
        "workers": worker_count,
        "dry_run": args.dry_run,
        "prompt": base_prompt,
        "images": sorted(summary, key=lambda item: item["file"]),
    }
    write_manifest(run_dir / "run-manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
