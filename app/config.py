from __future__ import annotations

import os
import sys
from pathlib import Path


IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
PROJECT_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(os.environ.get("GEMINI_ROOT", PROJECT_ROOT))


def _workspace_or_bundle(path_from_workspace: Path, path_from_bundle: Path) -> Path:
    return path_from_workspace if path_from_workspace.exists() else path_from_bundle


RUNTIME_ROOT = Path(
    os.environ.get(
        "REMBG_RUNTIME_DIR",
        _workspace_or_bundle(WORKSPACE_ROOT / "runtime" / "rembg", BUNDLE_ROOT / "runtime" / "rembg"),
    )
)
MODELS_ROOT = Path(
    os.environ.get("REMBG_MODELS_ROOT", WORKSPACE_ROOT / "models" / ".u2net")
)
DATA_ROOT = Path(
    os.environ.get(
        "BACKGROUND_APP_DATA_DIR", WORKSPACE_ROOT / "data" / "background-desktop"
    )
)
REPORTS_ROOT = Path(
    os.environ.get("BACKGROUND_APP_REPORTS_DIR", WORKSPACE_ROOT / "reports")
)
DOCS_ROOT = Path(
    os.environ.get(
        "BACKGROUND_APP_DOCS_DIR",
        _workspace_or_bundle(WORKSPACE_ROOT / "docs", BUNDLE_ROOT / "docs"),
    )
)
REMBG_SOURCE_ROOT = Path(os.environ.get("REMBG_SOURCE_DIR", WORKSPACE_ROOT / "rembg"))
PATCH_ROOT = _workspace_or_bundle(WORKSPACE_ROOT / "patches", BUNDLE_ROOT / "patches")
ASSETS_ROOT = Path(
    os.environ.get(
        "CUTCANVAS_ASSETS_DIR",
        _workspace_or_bundle(WORKSPACE_ROOT / "assets", BUNDLE_ROOT / "assets"),
    )
)
BRANDING_ROOT = ASSETS_ROOT / "branding"
ICON_PNG = BRANDING_ROOT / "cutcanvas-icon.png"
ICON_ICO = BRANDING_ROOT / "cutcanvas.ico"
LOGO_PNG = BRANDING_ROOT / "cutcanvas-logo.png"
SPLASH_PNG = BRANDING_ROOT / "cutcanvas-splash.png"
