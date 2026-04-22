from __future__ import annotations

import json
import os
import shlex
import sqlite3
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
PROVIDER_ENV_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "huggingface": "HF_TOKEN",
    "ollama-cloud": "OLLAMA_API_KEY",
    "zai": "GLM_API_KEY",
    "kimi-coding": "KIMI_API_KEY",
    "kimi-coding-cn": "KIMI_CN_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "arcee": "ARCEEAI_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}
PROVIDER_BASE_URL_ENV_KEYS = {
    "gemini": "GEMINI_BASE_URL",
    "ollama-cloud": "OLLAMA_BASE_URL",
    "zai": "GLM_BASE_URL",
    "kimi-coding": "KIMI_BASE_URL",
    "kimi-coding-cn": "KIMI_BASE_URL",
    "minimax": "MINIMAX_BASE_URL",
    "minimax-cn": "MINIMAX_CN_BASE_URL",
    "arcee": "ARCEE_BASE_URL",
}


def resolve_effective_provider(provider: str, base_url: str = "") -> str:
    normalized = (provider or "").strip().lower()
    if normalized in {"", "auto"} and (base_url or "").strip():
        return "openai"
    return normalized or "auto"


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


@dataclass(slots=True)
class HermesProviderSettings:
    provider: str = "openrouter"
    api_key: str = ""
    api_env_key: str = ""
    base_url: str = ""
    base_url_env_key: str = ""


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


def hermes_env_path() -> Path:
    path = hermes_data_root() / ".env"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def hermes_state_db_path() -> Path:
    return hermes_data_root() / "state.db"


def hermes_session_map_path() -> Path:
    return hermes_data_root() / "neonpilot_sessions.json"


def _read_env_pairs() -> dict[str, str]:
    path = hermes_env_path()
    pairs: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


def _update_env_pairs(updates: dict[str, str]) -> Path:
    path = hermes_env_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    used: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        replaced = False
        for key, value in updates.items():
            if stripped.startswith(f"{key}=") or stripped.startswith(f"#{key}=") or stripped.startswith(f"# {key}="):
                new_lines.append(f"{key}={value}")
                used.add(key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in used:
            new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")
    return path


def _load_session_map() -> dict[str, str]:
    path = hermes_session_map_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if key and value}


def _save_session_map(payload: dict[str, str]) -> Path:
    path = hermes_session_map_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _session_exists(session_id: str) -> bool:
    db_path = hermes_state_db_path()
    if not db_path.exists() or not session_id.strip():
        return False
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("select 1 from sessions where id = ? limit 1", (session_id.strip(),)).fetchone()
        finally:
            conn.close()
    except Exception:
        return False
    return bool(row)


def _latest_tool_session_id() -> str:
    db_path = hermes_state_db_path()
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                """
                select id
                from sessions
                where source = 'tool'
                order by started_at desc
                limit 1
                """
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return ""
    return str(row[0]) if row and row[0] else ""


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


def load_hermes_provider_settings(provider: str, base_url: str = "") -> HermesProviderSettings:
    env_pairs = _read_env_pairs()
    effective_provider = resolve_effective_provider(provider, base_url)
    api_env_key = PROVIDER_ENV_KEYS.get(effective_provider, "")
    base_url_env_key = PROVIDER_BASE_URL_ENV_KEYS.get(effective_provider, "")
    return HermesProviderSettings(
        provider=provider,
        api_key=env_pairs.get(api_env_key, "") if api_env_key else "",
        api_env_key=api_env_key,
        base_url=env_pairs.get(base_url_env_key, "") if base_url_env_key else "",
        base_url_env_key=base_url_env_key,
    )


def save_hermes_provider_settings(settings: HermesProviderSettings) -> Path:
    updates: dict[str, str] = {}
    if settings.api_env_key:
        updates[settings.api_env_key] = settings.api_key.strip()
    if settings.base_url_env_key:
        updates[settings.base_url_env_key] = settings.base_url.strip()
    return _update_env_pairs(updates)


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


def is_chat_query_supported() -> bool:
    return True


def run_hermes_query(
    prompt: str,
    *,
    session_name: str = "neonpilot",
    model: str = "",
    provider: str = "",
    base_url: str = "",
) -> tuple[bool, str, str]:
    ready, message = start_docker_desktop()
    if not ready:
        raise RuntimeError(message)
    if not docker_image_present():
        ok, stdout, stderr = pull_hermes_image()
        if not ok:
            raise RuntimeError((stdout + "\n" + stderr).strip())

    data_root = hermes_data_root()
    command = [
        "run",
        "--rm",
        "-v",
        f"{docker_volume_path(data_root)}:/opt/data",
        DOCKER_IMAGE,
        "chat",
        "-q",
        prompt,
        "-Q",
        "--source",
        "tool",
    ]
    session_map = _load_session_map()
    session_id = session_map.get(session_name, "")
    if session_id and _session_exists(session_id):
        command.extend(["--resume", session_id])
    if model.strip():
        command.extend(["-m", model.strip()])
    if provider.strip() and provider.strip() != "auto":
        command.extend(["--provider", provider.strip()])
    completed = _run_docker(*command, timeout_sec=1800)
    if completed.returncode == 0:
        latest_session_id = _latest_tool_session_id()
        if latest_session_id:
            session_map[session_name] = latest_session_id
            _save_session_map(session_map)
    return completed.returncode == 0, completed.stdout, completed.stderr


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
