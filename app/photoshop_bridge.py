from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import winreg
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
PHOTOSHOP_REGISTRY_KEYS = [
    r"SOFTWARE\Adobe\Photoshop",
    r"SOFTWARE\WOW6432Node\Adobe\Photoshop",
]
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def detect_photoshop_executable() -> Path | None:
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in PHOTOSHOP_REGISTRY_KEYS:
            try:
                with winreg.OpenKey(hive, key_path) as root:
                    index = 0
                    while True:
                        try:
                            version = winreg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(root, version) as version_key:
                                application_path = winreg.QueryValueEx(version_key, "ApplicationPath")[0]
                        except OSError:
                            continue
                        candidate = Path(application_path) / "Photoshop.exe"
                        if candidate.exists():
                            return candidate
            except OSError:
                continue
    fallback = Path(r"C:\Program Files\Adobe\Adobe Photoshop (Beta)\Photoshop.exe")
    return fallback if fallback.exists() else None


def resolve_photoshop_executable(path_text: str | Path | None = None) -> Path | None:
    if path_text:
        candidate = Path(path_text)
        if candidate.is_dir():
            exe = candidate / "Photoshop.exe"
            if exe.exists():
                return exe
        if candidate.exists() and candidate.name.lower() == "photoshop.exe":
            return candidate
    return detect_photoshop_executable()


def image_count_in_directory(input_dir: Path) -> int:
    return sum(1 for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def open_template_in_photoshop(template_path: Path, photoshop_executable: Path | None = None) -> tuple[list[str], str]:
    photoshop_path = resolve_photoshop_executable(photoshop_executable) if photoshop_executable else detect_photoshop_executable()
    if photoshop_path and photoshop_path.exists():
        command = [str(photoshop_path), str(template_path)]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        return command, str(photoshop_path)
    os.startfile(str(template_path))
    return [str(template_path)], "system-association"


def run_droplet_on_folder(
    droplet_path: Path,
    input_dir: Path,
    *,
    timeout_sec: int = 1800,
) -> subprocess.CompletedProcess[str] | None:
    command = [str(droplet_path), str(input_dir)]
    if timeout_sec <= 0:
        subprocess.Popen(command, creationflags=CREATE_NO_WINDOW)
        return None
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )


def wait_for_template_ready(wait_sec: int) -> None:
    if wait_sec > 0:
        time.sleep(wait_sec)


def close_photoshop_processes(*, timeout_sec: int = 30) -> tuple[bool, str]:
    completed = subprocess.run(
        ["taskkill", "/IM", "Photoshop.exe", "/T", "/F"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode == 0:
        return True, stdout or "已关闭 Photoshop。"
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    if "找不到进程" in combined or "not found" in combined.lower():
        return True, "当前没有正在运行的 Photoshop 进程。"
    deadline = time.time() + min(timeout_sec, 12)
    while time.time() < deadline:
        probe = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Photoshop.exe"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        listing = (probe.stdout or "") + (probe.stderr or "")
        if "Photoshop.exe" not in listing:
            return True, combined or "已关闭 Photoshop。"
        time.sleep(0.6)
    return False, combined or "关闭 Photoshop 失败。"


def _jsx_safe_path(path: Path) -> str:
    return path.as_posix().replace("'", "\\'")


def prepare_batch_source_directory(input_dir: Path, output_dir: Path) -> tuple[Path, int]:
    if input_dir.resolve() == output_dir.resolve():
        output_dir.mkdir(parents=True, exist_ok=True)
        existing = image_count_in_directory(output_dir)
        return output_dir, existing
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        shutil.copy2(path, output_dir / path.name)
        copied += 1
    return output_dir, copied


def run_photoshop_action_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    action_set: str,
    action_name: str,
    photoshop_executable: Path | None = None,
    timeout_sec: int = 3600,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    photoshop_path = resolve_photoshop_executable(photoshop_executable) if photoshop_executable else detect_photoshop_executable()
    if not photoshop_path or not photoshop_path.exists():
        raise FileNotFoundError("未找到 Photoshop 可执行文件。")

    working_dir, copied = prepare_batch_source_directory(input_dir, output_dir)
    jsx_content = f"""
var inputFolder = new Folder('{_jsx_safe_path(working_dir)}');
if (!inputFolder.exists) {{
    throw new Error('Input folder missing: ' + inputFolder.fsName);
}}
app.displayDialogs = DialogModes.NO;
var opts = new BatchOptions();
opts.destination = BatchDestinationType.SAVEANDCLOSE;
opts.overrideOpen = true;
opts.overrideSave = false;
app.batch(inputFolder, '{action_name}', '{action_set}', opts);
app.quit();
"""
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False, encoding="utf-8") as handle:
        handle.write(jsx_content.strip())
        jsx_path = Path(handle.name)
    command = [str(photoshop_path), "-r", str(jsx_path)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    finally:
        try:
            jsx_path.unlink(missing_ok=True)
        except OSError:
            pass
    return completed, command + [f"--prepared={copied}", f"--working-dir={working_dir}"]
