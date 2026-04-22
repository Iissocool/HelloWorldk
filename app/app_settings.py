from __future__ import annotations

import json

from .config import APP_SETTINGS_PATH, DATA_ROOT, migrate_legacy_data
from .models import AppSettings


def load_app_settings() -> AppSettings:
    migrate_legacy_data()
    if not APP_SETTINGS_PATH.exists():
        return AppSettings()
    try:
        payload = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
        return AppSettings(**payload)
    except Exception:
        return AppSettings()


def save_app_settings(settings: AppSettings) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    APP_SETTINGS_PATH.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
