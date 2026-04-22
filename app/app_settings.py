from __future__ import annotations

import json
from pathlib import Path

from .config import APP_SETTINGS_PATH, BACKGROUND_GIF, DATA_ROOT, migrate_legacy_data
from .models import AppSettings


def load_app_settings() -> AppSettings:
    migrate_legacy_data()
    if not APP_SETTINGS_PATH.exists():
        return AppSettings(background_gif_path=str(BACKGROUND_GIF) if BACKGROUND_GIF.exists() else "")
    try:
        payload = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
        settings = AppSettings(**payload)
        if not settings.background_gif_path and BACKGROUND_GIF.exists():
            settings.background_gif_path = str(BACKGROUND_GIF)
        return settings
    except Exception:
        return AppSettings(background_gif_path=str(BACKGROUND_GIF) if BACKGROUND_GIF.exists() else "")


def save_app_settings(settings: AppSettings) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    APP_SETTINGS_PATH.write_text(settings.model_dump_json(indent=2), encoding="utf-8")


def resolve_background_gif(settings: AppSettings) -> Path | None:
    candidates = []
    if settings.background_gif_path:
        candidates.append(Path(settings.background_gif_path))
    if BACKGROUND_GIF.exists():
        candidates.append(BACKGROUND_GIF)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
