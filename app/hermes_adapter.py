from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import APP_NAME, APP_SLUG, HERMES_EXPORT_ROOT


DOCKER_DISTROS = {"docker-desktop", "docker-desktop-data"}


@dataclass(slots=True)
class HermesEnvironmentStatus:
    wsl_available: bool
    usable_distros: list[str] = field(default_factory=list)
    selected_distro: str | None = None
    hermes_available: bool = False
    hermes_version: str = ""
    summary: str = ""
    notes: list[str] = field(default_factory=list)


def _decode_wsl_output(raw: bytes) -> str:
    if not raw:
        return ""
    if raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def list_wsl_distros() -> list[str]:
    try:
        completed = subprocess.run(["wsl.exe", "-l", "-v"], capture_output=True, check=False, timeout=12)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []

    text = _decode_wsl_output(completed.stdout)
    distros: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.replace("\x00", "").strip()
        if not line or line.upper().startswith("NAME"):
            continue
        line = line.lstrip("*").strip()
        parts = re.split(r"\s{2,}", line)
        if not parts:
            continue
        name = parts[0].strip()
        if name and name not in DOCKER_DISTROS:
            distros.append(name)
    return distros


def _run_wsl_command(distro: str, command: str, *, timeout_sec: int = 12) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["wsl.exe", "-d", distro, "bash", "-lc", command],
            capture_output=True,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or b"") + b"\nWSL command timed out."
        return subprocess.CompletedProcess(exc.cmd or [], 124, exc.stdout or b"", stderr)


def inspect_hermes_environment(preferred_distro: str | None = None) -> HermesEnvironmentStatus:
    distros = list_wsl_distros()
    status = HermesEnvironmentStatus(wsl_available=True, usable_distros=distros)
    if not distros:
        status.summary = "未发现可用的 WSL Linux 发行版。"
        status.notes = [
            "Hermes Agent 官方支持 Linux、macOS 与 WSL2，不支持原生 Windows。",
            "这台机器当前只有 docker-desktop WSL，没有 Ubuntu 之类的可用发行版。",
            "下一步需要先安装 Ubuntu for WSL，然后在其中安装 Hermes。",
        ]
        return status

    selected = preferred_distro if preferred_distro in distros else distros[0]
    status.selected_distro = selected
    version_check = _run_wsl_command(selected, "command -v hermes >/dev/null 2>&1 && hermes --version || true")
    output = (_decode_wsl_output(version_check.stdout) + "\n" + _decode_wsl_output(version_check.stderr)).strip()
    if version_check.returncode == 0 and output:
        status.hermes_available = True
        status.hermes_version = output.splitlines()[0].strip()
        status.summary = f"Hermes 已在 WSL 发行版 {selected} 中可用。"
        status.notes = [
            f"当前检测到的版本信息：{status.hermes_version}",
            "现在可以在程序里运行 help、doctor 这类非交互命令。",
            "完整的 Hermes 终端会话仍建议在 WSL 终端中运行，以保持 prompt_toolkit 的完整交互体验。",
        ]
        return status

    if version_check.returncode == 124:
        status.summary = f"已检测到 WSL 发行版 {selected}，但它还没有完成首启初始化。"
        status.notes = [
            "这通常表示 Ubuntu 第一次启动仍在等待创建 Linux 用户或完成发行版初始化。",
            "先手动打开一次 Ubuntu，完成首启设置，再回到程序里刷新 Agent。",
        ]
        return status

    status.summary = f"已检测到 WSL 发行版 {selected}，但尚未安装 Hermes。"
    status.notes = [
        "可以先在 Ubuntu WSL 中运行 Hermes 官方安装脚本。",
        "装好后回到程序里点击“刷新 Agent”即可接管检测与命令执行。",
    ]
    return status


def run_hermes_command(command: str, *, distro: str | None = None) -> tuple[bool, str, str]:
    status = inspect_hermes_environment(distro)
    if not status.selected_distro:
        raise RuntimeError(status.summary + "\n" + "\n".join(status.notes))
    if not status.hermes_available:
        raise RuntimeError(status.summary + "\n" + "\n".join(status.notes))

    completed = _run_wsl_command(status.selected_distro, f"source ~/.bashrc >/dev/null 2>&1; {command}", timeout_sec=20)
    stdout = _decode_wsl_output(completed.stdout).replace("\x00", "")
    stderr = _decode_wsl_output(completed.stderr).replace("\x00", "")
    return completed.returncode == 0, stdout, stderr


def export_hermes_skill(project_root: Path, runner_script: Path, *, export_root: Path | None = None) -> Path:
    export_base = export_root or HERMES_EXPORT_ROOT
    skill_root = export_base / f"{APP_SLUG}-control-skill"
    skill_root.mkdir(parents=True, exist_ok=True)
    skill_path = skill_root / "SKILL.md"
    runner = str(runner_script.resolve())
    project = str(project_root.resolve())
    content = f"""# {APP_NAME} Control Skill

Use this skill when Hermes needs to drive the Windows app project instead of inventing shell steps.

## Purpose
- Run {APP_NAME} image matting, batch processing, renaming, and AI image generation through the app's own CLI.
- Prefer the CLI wrapper so outputs stay structured JSON and match the desktop app's behavior.

## Rules
- Start with a health check before the first task in a fresh session.
- Prefer `auto` backend unless the user explicitly asks for a specific backend.
- Return parsed JSON summaries instead of paraphrasing shell output.
- If a command fails, surface stderr and stop before retrying.

## Windows CLI Wrapper
Run these from Hermes inside WSL with `powershell.exe`:

```bash
powershell.exe -ExecutionPolicy Bypass -File '{runner}' health
powershell.exe -ExecutionPolicy Bypass -File '{runner}' hardware
powershell.exe -ExecutionPolicy Bypass -File '{runner}' plan
```

## Common Commands

Single image:
```bash
powershell.exe -ExecutionPolicy Bypass -File '{runner}' single --input 'W:\\images\\in.png' --output 'W:\\images\\out.png' --model 'bria-rmbg' --backend auto
```

Batch process:
```bash
powershell.exe -ExecutionPolicy Bypass -File '{runner}' batch --input-dir 'W:\\images\\input' --output-dir 'W:\\images\\output' --model 'bria-rmbg' --backend auto --recurse
```

Fresh rename:
```bash
powershell.exe -ExecutionPolicy Bypass -File '{runner}' rename --input-dir 'W:\\images\\input' --mode fresh --fresh-name 'product_' --start-index 1 --padding-width 3 --extensions '.png,.jpg,.jpeg'
```

AI provider self-test:
```bash
powershell.exe -ExecutionPolicy Bypass -File '{runner}' ai-test --base-url 'https://api.openai.com' --api-key 'YOUR_KEY' --timeout 30
```

AI image generation:
```bash
powershell.exe -ExecutionPolicy Bypass -File '{runner}' ai-generate --base-url 'https://api.openai.com' --api-key 'YOUR_KEY' --model 'gpt-image-1' --prompt 'cyberpunk product poster' --output-dir 'W:\\images\\generated' --count 2 --size '1024x1024'
```

## Project Root
`{project}`
"""
    skill_path.write_text(content, encoding="utf-8")
    return skill_path
