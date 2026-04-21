from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(os.environ.get("GEMINI_ROOT", PROJECT_ROOT))
RUNTIME_ROOT = Path(
    os.environ.get("REMBG_RUNTIME_DIR", WORKSPACE_ROOT / "runtime" / "rembg")
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
DOCS_ROOT = Path(os.environ.get("BACKGROUND_APP_DOCS_DIR", WORKSPACE_ROOT / "docs"))
REMBG_SOURCE_ROOT = Path(os.environ.get("REMBG_SOURCE_DIR", WORKSPACE_ROOT / "rembg"))
PATCH_ROOT = PROJECT_ROOT / "patches"
