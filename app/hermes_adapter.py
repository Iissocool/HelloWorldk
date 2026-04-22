from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .config import APP_NAME, APP_SLUG, HERMES_DATA_ROOT, HERMES_EXPORT_ROOT


DOCKER_IMAGE = "nousresearch/hermes-agent:latest"
DOCKER_CONTAINER = f"{APP_SLUG}-hermes"
DOCKER_PORT = 8642
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
WINDOWS_CREATION_FLAGS = CREATE_NO_WINDOW
DOCKER_DESKTOP_CANDIDATES = [
    Path(os.environ.get("ProgramFiles", "")) / "Docker" / "Docker" / "Docker Desktop.exe",
    Path(os.environ.get("LocalAppData", "")) / "Programs" / "Docker" / "Docker" / "Docker Desktop.exe",
]


@dataclass(slots=True)
class HermesEnvironmentStatus:
    docker_cli_available: bool
    docker_desktop_available: bool
    docker_daemon_running: bool
    docker_desktop_path: str = ""
    image_present: bool = False
    service_container_exists: bool = False
    service_running: bool = False
    hermes_available: bool = False
    hermes_version: str = ""
    container_name: str = DOCKER_CONTAINER
    image_name: str = DOCKER_IMAGE
    data_root: str = ""
    summary: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HermesModelSettings:
    default_model: str = ""
    provider: str = "auto"
    base_url: str = ""


def _run_process(command: Iterable[str], *, timeout_sec: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout_sec,
        creationflags=WINDOWS_CREATION_FLAGS,
    )


def _run_docker(*args: str, timeout_sec: int = 20) -> subprocess.CompletedProcess[str]:
    return _run_process(["docker", *args], timeout_sec=timeout_sec)


def docker_desktop_path() -> Path | None:
    for candidate in DOCKER_DESKTOP_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def hermes_data_root() -> Path:
    root = HERMES_DATA_ROOT
    root.mkdir(parents=True, exist_ok=True)
    for child in ["skills", "sessions", "memories", "logs", "cron", "hooks"]:
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


def hermes_config_path() -> Path:
    return hermes_data_root() / "config.yaml"


def load_hermes_model_settings() -> HermesModelSettings:
    config_path = hermes_config_path()
    if not config_path.exists():
        return HermesModelSettings()
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return HermesModelSettings()
    model = payload.get("model") or {}
    return HermesModelSettings(
        default_model=str(model.get("default") or ""),
        provider=str(model.get("provider") or "auto"),
        base_url=str(model.get("base_url") or ""),
    )


def save_hermes_model_settings(settings: HermesModelSettings) -> Path:
    config_path = hermes_config_path()
    payload: dict = {}
    if config_path.exists():
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            payload = {}
    payload.setdefault("model", {})
    payload["model"]["default"] = settings.default_model.strip()
    payload["model"]["provider"] = settings.provider.strip() or "auto"
    payload["model"]["base_url"] = settings.base_url.strip()
    config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return config_path


def detect_interactive_command(command: str) -> str | None:
    tokens = shlex.split(command)
    if tokens and tokens[0].lower() == "hermes":
        tokens = tokens[1:]
    if not tokens:
        return "请输入有效命令。"
    head = tokens[0].lower()
    second = tokens[1].lower() if len(tokens) > 1 else ""
    if head == "model":
        return "hermes model 是交互式命令。请使用程序里的“模型设置”区域。"
    if head in {"chat", "setup", "dashboard"}:
        return f"hermes {head} 需要交互终端，当前命令框不支持。"
    if head == "config" and second == "edit":
        return "hermes config edit 会打开交互编辑器，当前命令框不支持。"
    if head == "auth" and second in {"add", "login"}:
        return f"hermes auth {second} 需要交互流程，当前命令框不支持。"
    if head in {"login", "logout"}:
        return f"hermes {head} 需要交互流程，当前命令框不支持。"
    return None


def docker_volume_path(path: Path) -> str:
    return str(path.resolve())


def docker_daemon_ready() -> bool:
    try:
        completed = _run_docker("info", timeout_sec=12)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def docker_image_present(image: str = DOCKER_IMAGE) -> bool:
    try:
        completed = _run_docker("image", "inspect", image, timeout_sec=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def docker_container_state(name: str = DOCKER_CONTAINER) -> tuple[bool, bool]:
    try:
        completed = _run_docker(
            "container",
            "inspect",
            name,
            "--format",
            "{{json .State}}",
            timeout_sec=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, False
    if completed.returncode != 0:
        return False, False
    try:
        state = json.loads((completed.stdout or "").strip())
    except json.JSONDecodeError:
        return True, False
    return True, bool(state.get("Running"))


def start_docker_desktop(wait_sec: int = 120) -> tuple[bool, str]:
    if docker_daemon_ready():
        return True, "Docker 已可用。"
    desktop = docker_desktop_path()
    if desktop is None:
        return False, "未发现 Docker Desktop。"

    subprocess.Popen(
        [str(desktop)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        close_fds=True,
    )

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if docker_daemon_ready():
            return True, "Docker Desktop 已启动。"
        time.sleep(3)
    return False, "Docker Desktop 已尝试启动，但守护进程还未就绪。"


def pull_hermes_image(image: str = DOCKER_IMAGE) -> tuple[bool, str, str]:
    completed = _run_docker("pull", image, timeout_sec=1800)
    return completed.returncode == 0, completed.stdout, completed.stderr


def inspect_hermes_environment() -> HermesEnvironmentStatus:
    desktop = docker_desktop_path()
    status = HermesEnvironmentStatus(
        docker_cli_available=True,
        docker_desktop_available=desktop is not None,
        docker_daemon_running=False,
        docker_desktop_path=str(desktop) if desktop else "",
        data_root=str(hermes_data_root()),
    )

    try:
        status.docker_daemon_running = docker_daemon_ready()
    except FileNotFoundError:
        status.docker_cli_available = False
        status.summary = "未检测到 Docker CLI。"
        status.notes = ["请先安装 Docker Desktop，再回到 Agent 页点击刷新。"]
        return status

    if not status.docker_daemon_running:
        status.summary = "Docker 已安装，但当前没有运行。"
        status.notes = [
            "点击“启动 Docker”即可在后台拉起 Docker Desktop。",
            "这条路线不会再弹出 Ubuntu 终端窗口，命令会留在程序里执行。",
            f"Hermes 数据目录固定在：{status.data_root}",
        ]
        return status

    status.image_present = docker_image_present()
    exists, running = docker_container_state()
    status.service_container_exists = exists
    status.service_running = running
    status.hermes_available = status.image_present

    if status.image_present:
        version_ok, version_stdout, _version_stderr = run_hermes_command("hermes version", ensure_image=False)
        if version_ok and version_stdout.strip():
            for line in version_stdout.splitlines():
                text = line.strip()
                if text.startswith("Hermes Agent "):
                    status.hermes_version = text
                    break

    if running:
        status.summary = "Docker Hermes 服务正在运行。"
        status.notes = [
            "可以直接在下方运行 Hermes 命令。",
            f"数据目录：{status.data_root}",
            f"容器名：{DOCKER_CONTAINER}",
        ]
    elif exists:
        status.summary = "Docker Hermes 容器已存在，但当前没有运行。"
        status.notes = [
            "点击“启动 Hermes”即可恢复后台服务。",
            f"数据目录：{status.data_root}",
        ]
    elif status.image_present:
        status.summary = "Docker 已就绪，Hermes 镜像已准备好。"
        status.notes = [
            "点击“启动 Hermes”即可创建后台服务。",
            f"数据目录：{status.data_root}",
        ]
    else:
        status.summary = "Docker 已就绪，但 Hermes 镜像还未下载。"
        status.notes = [
            "点击“启动 Hermes”时程序会自动拉取镜像。",
            f"数据目录：{status.data_root}",
        ]
    return status


def start_hermes_service() -> tuple[bool, str, str]:
    ready, message = start_docker_desktop()
    if not ready:
        return False, "", message

    data_root = hermes_data_root()
    if not docker_image_present():
        ok, stdout, stderr = pull_hermes_image()
        if not ok:
            return False, stdout, stderr

    exists, running = docker_container_state()
    if running:
        return True, f"Hermes 服务已在运行。\n数据目录：{data_root}", ""
    if exists:
        completed = _run_docker("start", DOCKER_CONTAINER, timeout_sec=60)
        return completed.returncode == 0, completed.stdout, completed.stderr

    completed = _run_docker(
        "run",
        "-d",
        "--name",
        DOCKER_CONTAINER,
        "--restart",
        "unless-stopped",
        "--memory=2g",
        "--cpus=2",
        "--shm-size=1g",
        "-p",
        f"{DOCKER_PORT}:{DOCKER_PORT}",
        "-v",
        f"{docker_volume_path(data_root)}:/opt/data",
        DOCKER_IMAGE,
        "gateway",
        "run",
        timeout_sec=120,
    )
    return completed.returncode == 0, completed.stdout, completed.stderr


def stop_hermes_service() -> tuple[bool, str, str]:
    exists, running = docker_container_state()
    if not exists:
        return True, "Hermes 容器当前还不存在。", ""
    if not running:
        return True, "Hermes 服务已经是停止状态。", ""
    completed = _run_docker("stop", DOCKER_CONTAINER, timeout_sec=60)
    return completed.returncode == 0, completed.stdout, completed.stderr


def read_hermes_logs(tail: int = 200) -> tuple[bool, str, str]:
    exists, _running = docker_container_state()
    if not exists:
        return False, "", "Hermes 容器还不存在，暂时没有日志。"
    completed = _run_docker("logs", f"--tail={tail}", DOCKER_CONTAINER, timeout_sec=60)
    if completed.returncode == 0:
        return True, completed.stdout or completed.stderr, ""
    return False, completed.stdout, completed.stderr


def run_hermes_command(command: str, *, ensure_image: bool = True) -> tuple[bool, str, str]:
    interactive_message = detect_interactive_command(command)
    if interactive_message:
        raise RuntimeError(interactive_message)

    ready, message = start_docker_desktop()
    if not ready:
        raise RuntimeError(message)

    data_root = hermes_data_root()
    if ensure_image and not docker_image_present():
        ok, stdout, stderr = pull_hermes_image()
        if not ok:
            raise RuntimeError((stdout + "\n" + stderr).strip())

    tokens = shlex.split(command)
    if tokens and tokens[0].lower() == "hermes":
        tokens = tokens[1:]
    if not tokens:
        raise RuntimeError("请输入有效的 Hermes 命令，例如 hermes --help 或 hermes doctor。")

    completed = _run_docker(
        "run",
        "--rm",
        "-v",
        f"{docker_volume_path(data_root)}:/opt/data",
        DOCKER_IMAGE,
        *tokens,
        timeout_sec=600,
    )
    return completed.returncode == 0, completed.stdout, completed.stderr


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
Run these from Hermes inside Docker with `powershell.exe`:

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
