from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}


@dataclass(slots=True)
class UpscaleSummary:
    input_path: str
    output_path: str
    scale: int
    mode: str


def image_paths_from_dir(input_dir: Path, recurse: bool) -> list[Path]:
    pattern = '**/*' if recurse else '*'
    return sorted(
        path
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def upscale_image(input_path: Path, output_path: Path, *, scale: int = 2, mode: str = 'quality') -> UpscaleSummary:
    image = Image.open(input_path)
    image = ImageOps.exif_transpose(image)
    if image.mode not in {'RGB', 'RGBA'}:
        image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')

    width, height = image.size
    resized = image.resize((max(1, width * scale), max(1, height * scale)), Image.Resampling.LANCZOS)

    if mode == 'quality':
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1.8, percent=145, threshold=2))
        resized = ImageEnhance.Contrast(resized).enhance(1.06)
        resized = ImageEnhance.Sharpness(resized).enhance(1.10)
    elif mode == 'balanced':
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1.3, percent=110, threshold=2))
        resized = ImageEnhance.Sharpness(resized).enhance(1.05)
    else:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=0.9, percent=85, threshold=3))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {}
    suffix = output_path.suffix.lower()
    if suffix in {'.jpg', '.jpeg'}:
        if resized.mode == 'RGBA':
            flattened = Image.new('RGB', resized.size, '#101826')
            flattened.paste(resized, mask=resized.getchannel('A'))
            resized = flattened
        else:
            resized = resized.convert('RGB')
        save_kwargs['quality'] = 96
        save_kwargs['subsampling'] = 0
    resized.save(output_path, **save_kwargs)
    return UpscaleSummary(
        input_path=str(input_path),
        output_path=str(output_path),
        scale=scale,
        mode=mode,
    )
