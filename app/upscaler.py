from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .config import UPSCALE_BINARY


IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}


@dataclass(slots=True)
class UpscaleSummary:
    input_path: str
    output_path: str
    scale: int
    mode: str
    engine: str


def image_paths_from_dir(input_dir: Path, recurse: bool) -> list[Path]:
    pattern = '**/*' if recurse else '*'
    return sorted(
        path
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def external_upscale_available() -> bool:
    return UPSCALE_BINARY.exists()


def _upscale_with_realesrgan(input_path: Path, output_path: Path, *, scale: int, mode: str) -> UpscaleSummary:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tile_size = '200' if mode == 'quality' else '128'
    command = [
        str(UPSCALE_BINARY),
        '-i', str(input_path),
        '-o', str(output_path),
        '-s', str(scale),
        '-f', output_path.suffix.lower().lstrip('.') or 'png',
        '-t', tile_size,
        '-g', '0',
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or 'Real-ESRGAN 执行失败。').strip())
    return UpscaleSummary(
        input_path=str(input_path),
        output_path=str(output_path),
        scale=scale,
        mode=mode,
        engine='realesrgan-ncnn-vulkan',
    )


def _upscale_with_internal_fallback(input_path: Path, output_path: Path, *, scale: int = 2, mode: str = 'quality') -> UpscaleSummary:
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
        engine='internal-fallback',
    )


def upscale_image(input_path: Path, output_path: Path, *, scale: int = 2, mode: str = 'quality') -> UpscaleSummary:
    if external_upscale_available():
        return _upscale_with_realesrgan(input_path, output_path, scale=scale, mode=mode)
    return _upscale_with_internal_fallback(input_path, output_path, scale=scale, mode=mode)
