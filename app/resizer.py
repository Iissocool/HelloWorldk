from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass(slots=True)
class ResizeSummary:
    input_path: str
    output_path: str
    width: int
    height: int
    dpi_x: float | None
    dpi_y: float | None
    mode: str
    engine: str


def image_paths_from_dir(input_dir: Path, recurse: bool) -> list[Path]:
    pattern = "**/*" if recurse else "*"
    return sorted(
        path
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _target_dimensions(source_size: tuple[int, int], width: int, height: int) -> tuple[int, int]:
    src_w, src_h = source_size
    if width <= 0 and height <= 0:
        raise ValueError("width 和 height 不能同时为空。")
    if width <= 0:
        width = max(1, round(src_w * (height / src_h)))
    if height <= 0:
        height = max(1, round(src_h * (width / src_w)))
    return max(1, width), max(1, height)


def _preserve_or_convert(image: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(image)
    if transposed.mode in {"RGB", "RGBA"}:
        return transposed
    if "A" in transposed.getbands():
        return transposed.convert("RGBA")
    return transposed.convert("RGB")


def _compose_contain(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    contained = ImageOps.contain(image, target_size, method=Image.Resampling.LANCZOS)
    if "A" in contained.getbands():
        canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
        offset = ((target_size[0] - contained.width) // 2, (target_size[1] - contained.height) // 2)
        canvas.paste(contained, offset, contained.getchannel("A"))
        return canvas
    canvas = Image.new("RGB", target_size, "#ffffff")
    offset = ((target_size[0] - contained.width) // 2, (target_size[1] - contained.height) // 2)
    canvas.paste(contained, offset)
    return canvas


def _compose_keep_ratio(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    return ImageOps.contain(image, target_size, method=Image.Resampling.LANCZOS)


def _save_image(image: Image.Image, output_path: Path, *, dpi: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict = {"dpi": (dpi, dpi)}
    suffix = output_path.suffix.lower()
    final = image
    if suffix in {".jpg", ".jpeg"}:
        if final.mode == "RGBA":
            background = Image.new("RGB", final.size, "#ffffff")
            background.paste(final, mask=final.getchannel("A"))
            final = background
        else:
            final = final.convert("RGB")
        save_kwargs["quality"] = 95
        save_kwargs["subsampling"] = 0
    final.save(output_path, **save_kwargs)


def resize_image(
    input_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    dpi: int = 300,
    mode: str = "contain-pad",
) -> ResizeSummary:
    with Image.open(input_path) as opened:
        image = _preserve_or_convert(opened)
        target_size = _target_dimensions(image.size, width, height)
        if mode == "stretch":
            resized = image.resize(target_size, Image.Resampling.LANCZOS)
        elif mode == "cover-crop":
            resized = ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS)
        elif mode == "keep-ratio":
            resized = _compose_keep_ratio(image, target_size)
        else:
            resized = _compose_contain(image, target_size)

    _save_image(resized, output_path, dpi=dpi)

    with Image.open(output_path) as verify:
        dpi_info = verify.info.get("dpi") or (None, None)
        dpi_x = round(float(dpi_info[0]), 2) if dpi_info[0] else None
        dpi_y = round(float(dpi_info[1]), 2) if dpi_info[1] else None
        out_w, out_h = verify.size

    return ResizeSummary(
        input_path=str(input_path),
        output_path=str(output_path),
        width=out_w,
        height=out_h,
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        mode=mode,
        engine="pillow-native",
    )
