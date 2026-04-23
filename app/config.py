from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "NeonPilot"
APP_SLUG = "neonpilot"
APP_VERSION = "0.9.0"
APP_TAGLINE = "Cyberpunk AI imaging cockpit"

IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
PROJECT_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parents[1]


def _existing(path: Path) -> bool:
    return path.exists()


def _discover_workspace_root() -> Path:
    env_root = os.environ.get("GEMINI_ROOT")
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root))
    if Path("W:/gemini").exists():
        candidates.append(Path("W:/gemini"))
    candidates.extend([PROJECT_ROOT, PROJECT_ROOT.parent, PROJECT_ROOT.parent.parent])

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "models" / ".u2net").exists() or (candidate / "runtime" / "rembg").exists():
            return candidate
    return Path(env_root) if env_root else PROJECT_ROOT


def _workspace_or_bundle(path_from_workspace: Path, path_from_bundle: Path) -> Path:
    return path_from_workspace if _existing(path_from_workspace) else path_from_bundle


WORKSPACE_ROOT = _discover_workspace_root()
RUNTIME_ROOT = Path(
    os.environ.get(
        "REMBG_RUNTIME_DIR",
        _workspace_or_bundle(WORKSPACE_ROOT / "runtime" / "rembg", BUNDLE_ROOT / "runtime" / "rembg"),
    )
)
UPSCALE_RUNTIME_ROOT = Path(os.environ.get("UPSCALE_RUNTIME_DIR", WORKSPACE_ROOT / "runtime" / "upscale"))
UPSCALE_BINARY = UPSCALE_RUNTIME_ROOT / "realesrgan-ncnn-vulkan.exe"
MODELS_ROOT = Path(os.environ.get("REMBG_MODELS_ROOT", WORKSPACE_ROOT / "models" / ".u2net"))
LEGACY_DATA_ROOT = WORKSPACE_ROOT / "data" / "background-desktop"
DATA_ROOT = Path(os.environ.get("BACKGROUND_APP_DATA_DIR", WORKSPACE_ROOT / "data" / APP_SLUG))
AI_SETTINGS_PATH = DATA_ROOT / "ai_provider.json"
APP_SETTINGS_PATH = DATA_ROOT / "app_settings.json"
HERMES_WORKSPACE_ROOT = Path(os.environ.get("NEONPILOT_HERMES_ROOT", "W:/gemini")) if Path("W:/gemini").exists() else WORKSPACE_ROOT
HERMES_DATA_ROOT = Path(os.environ.get("NEONPILOT_HERMES_DATA_DIR", HERMES_WORKSPACE_ROOT / "data" / APP_SLUG / "hermes"))
HERMES_EXPORT_ROOT = HERMES_DATA_ROOT / "skills"
REPORTS_ROOT = Path(os.environ.get("BACKGROUND_APP_REPORTS_DIR", WORKSPACE_ROOT / "reports"))
DOCS_ROOT = Path(
    os.environ.get(
        "BACKGROUND_APP_DOCS_DIR",
        _workspace_or_bundle(WORKSPACE_ROOT / "docs", BUNDLE_ROOT / "docs"),
    )
)
REMBG_SOURCE_ROOT = Path(os.environ.get("REMBG_SOURCE_DIR", WORKSPACE_ROOT / "rembg"))
PATCH_ROOT = _workspace_or_bundle(WORKSPACE_ROOT / "patches", BUNDLE_ROOT / "patches")
SCRIPTS_ROOT = _workspace_or_bundle(WORKSPACE_ROOT / "scripts", BUNDLE_ROOT / "scripts")
ASSETS_ROOT = Path(
    os.environ.get(
        "NEONPILOT_ASSETS_DIR",
        _workspace_or_bundle(WORKSPACE_ROOT / "assets", BUNDLE_ROOT / "assets"),
    )
)
BRANDING_ROOT = ASSETS_ROOT / "branding"
FONTS_ROOT = ASSETS_ROOT / "fonts"
ICON_PNG = BRANDING_ROOT / "neonpilot-icon.png"
ICON_ICO = BRANDING_ROOT / "neonpilot.ico"
LOGO_PNG = BRANDING_ROOT / "neonpilot-logo.png"
SPLASH_PNG = BRANDING_ROOT / "neonpilot-splash.png"
SPLASH_GIF = BRANDING_ROOT / "neonpilot-splash.gif"
BACKGROUND_PNG = BRANDING_ROOT / "neonpilot-bg.png"
BACKGROUND_GIF = BRANDING_ROOT / "neonpilot-bg.gif"
UI_FONT_TTF = FONTS_ROOT / "NotoSansSCVariable.ttf"
DISPLAY_FONT_TTF = FONTS_ROOT / "OrbitronVariable.ttf"
VENV_ROOT = WORKSPACE_ROOT / "venvs"


def migrate_legacy_data() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    if not LEGACY_DATA_ROOT.exists() or LEGACY_DATA_ROOT == DATA_ROOT:
        return

    migrations = [
        (LEGACY_DATA_ROOT / "ai_provider.json", AI_SETTINGS_PATH),
        (LEGACY_DATA_ROOT / "history.sqlite3", DATA_ROOT / "history.sqlite3"),
    ]
    for source, target in migrations:
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
