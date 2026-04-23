from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}
SUPPORTED_AI_SIZES = ['1024x1024', '1536x1024', '1024x1536']
BACKGROUND_STYLE_PRESETS = {
    'custom': '',
    'clean-ecommerce': '纯净电商棚拍背景，浅色干净台面，柔和高端商业灯光。',
    'cream-home': '奶油风家居场景，柔和自然光，温暖但干净，高级生活方式氛围。',
    'minimal-bathroom': '极简浴室空间，材质高级，留白干净，自然漫反射光线。',
    'outdoor-sunlit': '明亮户外生活场景，阳光自然，背景高级但不过度复杂。',
    'luxury-dark': '深色高级商业场景，光影克制，适合突出主体质感。',
}


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


def build_output_path(input_path: Path, input_root: Path, output_root: Path, preserve_structure: bool) -> Path:
    if preserve_structure:
        return output_root / input_path.relative_to(input_root)
    return output_root / input_path.name


def build_background_prompt(subject_name: str, background_prompt: str, *, style: str = 'custom') -> str:
    preset = BACKGROUND_STYLE_PRESETS.get(style, '')
    style_text = f' 风格参考：{preset}' if preset else ''
    return (
        '请生成仅包含背景的电商场景图，不要出现商品主体、人物、文字、水印、logo。'
        f' 主体商品是：{subject_name}。'
        f' 背景要求：{background_prompt}。'
        f'{style_text}'
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
