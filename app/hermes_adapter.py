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
        completed = subprocess.run(["wsl.exe", "-l", "-v"], capture_output=True, check=False)
    except FileNotFoundError:
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


def _run_wsl_command(distro: str, command: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["wsl.exe", "-d", distro, "bash", "-lc", command],
        capture_output=True,
        check=False,
    )


def inspect_hermes_environment(preferred_distro: str | None = None) -> HermesEnvironmentStatus:
    distros = list_wsl_distros()
    status = HermesEnvironmentStatus(wsl_available=True, usable_distros=distros)
    if not distros:
        status.summary = "?????? WSL Linux ????"
        status.notes = [
            "Hermes Agent ???? Linux?macOS ? WSL2?????? Windows?",
            "???????? docker-desktop WSL??? Ubuntu ?????????",
            "???????? Ubuntu for WSL???????? Hermes?",
        ]
        return status

    selected = preferred_distro if preferred_distro in distros else distros[0]
    status.selected_distro = selected
    version_check = _run_wsl_command(selected, "command -v hermes >/dev/null 2>&1 && hermes --version || true")
    output = (_decode_wsl_output(version_check.stdout) + "\n" + _decode_wsl_output(version_check.stderr)).strip()
    if version_check.returncode == 0 and output:
        status.hermes_available = True
        status.hermes_version = output.splitlines()[0].strip()
        status.summary = f"Hermes ?? WSL ??? {selected} ????"
        status.notes = [
            f"???????????{status.hermes_version}",
            "?????????? help?doctor ????????",
            "??? Hermes ???????? WSL ????????? prompt_toolkit ????????",
        ]
        return status

    status.summary = f"???? WSL ??? {selected}?????? Hermes?"
    status.notes = [
        "???? Ubuntu WSL ??? Hermes ???????",
        "????????????? Agent?????????????",
    ]
    return status


def run_hermes_command(command: str, *, distro: str | None = None) -> tuple[bool, str, str]:
    status = inspect_hermes_environment(distro)
    if not status.selected_distro:
        raise RuntimeError(status.summary + "\n" + "\n".join(status.notes))
    if not status.hermes_available:
        raise RuntimeError(status.summary + "\n" + "\n".join(status.notes))

    completed = _run_wsl_command(status.selected_distro, f"source ~/.bashrc >/dev/null 2>&1; {command}")
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
