from __future__ import annotations

import os
import subprocess
import time
import winreg
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
PHOTOSHOP_REGISTRY_KEYS = [
    r"SOFTWARE\Adobe\Photoshop",
    r"SOFTWARE\WOW6432Node\Adobe\Photoshop",
]


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


def image_count_in_directory(input_dir: Path) -> int:
    return sum(1 for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def open_template_in_photoshop(template_path: Path, photoshop_executable: Path | None = None) -> tuple[list[str], str]:
    photoshop_path = photoshop_executable or detect_photoshop_executable()
    if photoshop_path and photoshop_path.exists():
        command = [str(photoshop_path), str(template_path)]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        subprocess.Popen(command)
        return None
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
    )


def wait_for_template_ready(wait_sec: int) -> None:
    if wait_sec > 0:
        time.sleep(wait_sec)
