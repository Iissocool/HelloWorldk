from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .models import RenameRunRequest


INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


@dataclass(slots=True)
class RenamePlanItem:
    source_path: Path
    target_path: Path | None
    status: str
    reason: str
    index_value: int


def parse_extension_filter(raw_value: str) -> set[str]:
    values: set[str] = set()
    for token in raw_value.replace(";", ",").split(","):
        value = token.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        values.add(value)
    return values


def collect_rename_files(
    input_dir: Path,
    *,
    recurse: bool,
    extensions: set[str],
) -> list[Path]:
    pattern = "**/*" if recurse else "*"
    files: list[Path] = []
    for path in sorted(input_dir.glob(pattern)):
        if not path.is_file():
            continue
        if path.name.lower() == "_rename_report.csv":
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        files.append(path)
    return files


def apply_replace(text: str, find_text: str, replace_text: str, *, case_sensitive: bool) -> str:
    if case_sensitive:
        return text.replace(find_text, replace_text)

    if not find_text:
        return text

    lowered_text = text.lower()
    lowered_find = find_text.lower()
    start = 0
    parts: list[str] = []
    while True:
        index = lowered_text.find(lowered_find, start)
        if index < 0:
            parts.append(text[start:])
            break
        parts.append(text[start:index])
        parts.append(replace_text)
        start = index + len(find_text)
    return "".join(parts)


def validate_filename(name: str) -> str | None:
    if not name:
        return "文件名不能为空"
    if any(char in INVALID_FILENAME_CHARS for char in name):
        return "文件名包含 Windows 不允许的字符"
    if name.endswith(" ") or name.endswith("."):
        return "文件名不能以空格或句点结尾"
    if name in {".", ".."}:
        return "文件名不能是保留名称"
    return None


def build_rename_plan(request: RenameRunRequest) -> list[RenamePlanItem]:
    input_dir = Path(request.input_dir)
    extensions = parse_extension_filter(request.extensions)
    files = collect_rename_files(input_dir, recurse=request.recurse, extensions=extensions)
    index_value = request.start_index
    plan: list[RenamePlanItem] = []

    if request.mode == "replace" and not request.find_text:
        raise ValueError("当前是“查找替换”模式，必须填写“查找文本”。")
    if request.step <= 0:
        raise ValueError("步长必须大于 0。")

    for source_path in files:
        try:
            if request.mode == "template":
                rendered_name = request.template.format(
                    index=index_value,
                    num=index_value,
                    name=source_path.stem,
                    stem=source_path.stem,
                    parent=source_path.parent.name,
                    ext=source_path.suffix.lstrip("."),
                )
            else:
                rendered_name = apply_replace(
                    source_path.stem,
                    request.find_text,
                    request.replace_text,
                    case_sensitive=request.case_sensitive,
                )
        except Exception as exc:
            plan.append(
                RenamePlanItem(
                    source_path=source_path,
                    target_path=None,
                    status="fail",
                    reason=f"模板解析失败：{exc}",
                    index_value=index_value,
                )
            )
            index_value += request.step
            continue

        new_stem = f"{request.prefix}{rendered_name}{request.suffix}"
        new_name = f"{new_stem}{source_path.suffix if request.keep_extension else ''}"
        invalid_reason = validate_filename(new_name)
        if invalid_reason:
            plan.append(
                RenamePlanItem(
                    source_path=source_path,
                    target_path=None,
                    status="fail",
                    reason=invalid_reason,
                    index_value=index_value,
                )
            )
            index_value += request.step
            continue

        target_path = source_path.with_name(new_name)
        if target_path == source_path:
            plan.append(
                RenamePlanItem(
                    source_path=source_path,
                    target_path=target_path,
                    status="skipped",
                    reason="文件名没有变化",
                    index_value=index_value,
                )
            )
        else:
            plan.append(
                RenamePlanItem(
                    source_path=source_path,
                    target_path=target_path,
                    status="planned",
                    reason="",
                    index_value=index_value,
                )
            )
        index_value += request.step

    seen_targets: dict[str, Path] = {}
    moving_source_keys = {
        str(item.source_path).lower()
        for item in plan
        if item.status == "planned" and item.target_path is not None
    }
    for item in plan:
        if item.status != "planned" or item.target_path is None:
            continue
        target_key = str(item.target_path).lower()
        if target_key in seen_targets:
            item.status = "fail"
            item.reason = f"目标文件名重复，和 {seen_targets[target_key].name} 冲突"
            continue
        seen_targets[target_key] = item.source_path

        if (
            item.target_path.exists()
            and item.target_path != item.source_path
            and target_key not in moving_source_keys
        ):
            item.status = "fail"
            item.reason = "目标文件已经存在"

    return plan


def execute_rename_plan(plan: Iterable[RenamePlanItem]) -> tuple[list[RenamePlanItem], list[str]]:
    staged: list[tuple[Path, Path, Path]] = []
    completed: list[tuple[Path, Path]] = []
    stdout_lines: list[str] = []

    actionable_items = [item for item in plan if item.status == "planned" and item.target_path is not None]

    try:
        for item in actionable_items:
            temp_path = item.source_path.with_name(
                f".cutcanvas_rename_{uuid4().hex}{item.source_path.suffix}"
            )
            item.source_path.rename(temp_path)
            staged.append((temp_path, item.source_path, item.target_path))

        for temp_path, original_path, target_path in staged:
            temp_path.rename(target_path)
            completed.append((target_path, original_path))
            stdout_lines.append(f"已重命名：{original_path.name} -> {target_path.name}")
    except Exception as exc:
        for target_path, original_path in reversed(completed):
            try:
                if target_path.exists() and not original_path.exists():
                    target_path.rename(original_path)
            except OSError:
                pass
        for temp_path, original_path, _target_path in reversed(staged):
            try:
                if temp_path.exists() and not original_path.exists():
                    temp_path.rename(original_path)
            except OSError:
                pass

        for item in actionable_items:
            item.status = "fail"
            item.reason = f"批量命名已中止：{exc}"
        stdout_lines.append(f"批量命名已中止：{exc}")
        return list(plan), stdout_lines

    for item in actionable_items:
        item.status = "ok"

    for item in plan:
        if item.status == "skipped":
            stdout_lines.append(f"跳过 {item.source_path.name}: {item.reason}")
        elif item.status == "fail":
            stdout_lines.append(f"失败 {item.source_path.name}: {item.reason}")

    return list(plan), stdout_lines
