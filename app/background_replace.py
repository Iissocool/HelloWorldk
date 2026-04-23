from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}
SUPPORTED_AI_SIZES = ['1024x1024', '1536x1024', '1024x1536']


def choose_generation_size(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return '1024x1024'
    aspect = width / height
    candidates = {
        '1024x1024': 1.0,
        '1536x1024': 1.5,
        '1024x1536': 1024 / 1536,
    }
    return min(candidates, key=lambda key: abs(candidates[key] - aspect))


def image_paths_from_dir(input_dir: Path, recurse: bool) -> list[Path]:
    pattern = '**/*' if recurse else '*'
    return sorted(
        path
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def build_background_prompt(subject_name: str, background_prompt: str) -> str:
    return (
        '请生成仅包含背景的电商场景图，不要出现商品主体、人物、文字、水印、logo。'
        f' 主体商品是：{subject_name}。'
        f' 背景要求：{background_prompt}。'
        ' 画面需要为主体预留自然摆放位置，光线统一、干净、适合后期合成。'
    )


def composite_subject_over_background(subject_cutout: Path, background_image: Path, output_path: Path) -> Path:
    subject = Image.open(subject_cutout)
    subject = ImageOps.exif_transpose(subject).convert('RGBA')
    background = Image.open(background_image)
    background = ImageOps.exif_transpose(background).convert('RGBA')
    if background.size != subject.size:
        background = background.resize(subject.size, Image.Resampling.LANCZOS)
    merged = background.copy()
    merged.alpha_composite(subject)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {'.jpg', '.jpeg'}:
        merged = merged.convert('RGB')
        merged.save(output_path, quality=96, subsampling=0)
    else:
        merged.save(output_path)
    return output_path
