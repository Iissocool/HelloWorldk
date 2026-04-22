from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request

from .config import AI_SETTINGS_PATH
from .models import AIImageRunRequest, AIImageTestRequest, AIProviderSettings
from .secure_store import decrypt_text, encrypt_text


def _build_candidate_urls(base_url: str, suffix: str) -> list[str]:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("服务地址不能为空。")
    if base.endswith("/v1"):
        return [f"{base}{suffix}"]
    return [f"{base}{suffix}", f"{base}/v1{suffix}"]


def _json_request(url: str, *, method: str, headers: dict[str, str], payload: dict | None, timeout_sec: int) -> dict:
    body = None
    final_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        final_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=final_headers, method=method)
    with request.urlopen(req, timeout=timeout_sec) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _download_bytes(url: str, *, headers: dict[str, str], timeout_sec: int) -> bytes:
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=timeout_sec) as response:
        return response.read()


def mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def load_ai_settings() -> AIProviderSettings:
    if not AI_SETTINGS_PATH.exists():
        return AIProviderSettings()
    try:
        payload = json.loads(AI_SETTINGS_PATH.read_text(encoding="utf-8"))
        api_key = decrypt_text(payload.get("api_key_encrypted", "")) if payload.get("api_key_encrypted") else ""
        return AIProviderSettings(
            base_url=payload.get("base_url", "https://api.openai.com"),
            model=payload.get("model", "gpt-image-1"),
            api_key=api_key,
            timeout_sec=int(payload.get("timeout_sec", 120)),
        )
    except Exception:
        return AIProviderSettings()


def save_ai_settings(settings: AIProviderSettings) -> None:
    AI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_url": settings.base_url.strip(),
        "model": settings.model.strip(),
        "timeout_sec": settings.timeout_sec,
        "api_key_encrypted": encrypt_text(settings.api_key.strip()) if settings.api_key.strip() else "",
    }
    AI_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ai_provider(settings: AIImageTestRequest) -> tuple[str, list[str]]:
    headers = {
        "Authorization": f"Bearer {settings.api_key.strip()}",
        "Accept": "application/json",
    }
    errors: list[str] = []
    for url in _build_candidate_urls(settings.base_url, "/models"):
        try:
            payload = _json_request(url, method="GET", headers=headers, payload=None, timeout_sec=settings.timeout_sec)
            models = [item.get("id", "") for item in payload.get("data", []) if isinstance(item, dict)]
            preview = [model for model in models[:10] if model]
            summary = f"连接成功：{url}"
            if preview:
                summary += f"\n可见模型：{', '.join(preview)}"
            return summary, preview
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{url} -> HTTP {exc.code}: {detail or exc.reason}")
        except Exception as exc:
            errors.append(f"{url} -> {exc}")
    raise RuntimeError("连接测试失败。\n" + "\n".join(errors))


def generate_images(request_data: AIImageRunRequest) -> tuple[list[str], list[str]]:
    output_dir = Path(request_data.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "Authorization": f"Bearer {request_data.api_key.strip()}",
        "Accept": "application/json",
    }
    payload: dict[str, object] = {
        "model": request_data.model.strip(),
        "prompt": request_data.prompt.strip(),
        "n": request_data.image_count,
        "size": request_data.size,
        "response_format": "b64_json",
    }
    if request_data.quality.strip() and request_data.quality.strip() != "auto":
        payload["quality"] = request_data.quality.strip()

    errors: list[str] = []
    response_payload: dict | None = None
    used_url = ""
    for url in _build_candidate_urls(request_data.base_url, "/images/generations"):
        try:
            response_payload = _json_request(
                url,
                method="POST",
                headers=headers,
                payload=payload,
                timeout_sec=request_data.timeout_sec,
            )
            used_url = url
            break
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{url} -> HTTP {exc.code}: {detail or exc.reason}")
        except Exception as exc:
            errors.append(f"{url} -> {exc}")
    if response_payload is None:
        raise RuntimeError("图片生成失败。\n" + "\n".join(errors))

    data_items = response_payload.get("data", [])
    if not isinstance(data_items, list) or not data_items:
        raise RuntimeError("接口已连接，但没有返回图片数据。")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = request_data.file_prefix.strip() or "image_"
    saved_files: list[str] = []
    logs = [f"生成接口：{used_url}", f"输出目录：{output_dir}"]

    for index, item in enumerate(data_items, start=1):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            image_bytes = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            image_bytes = _download_bytes(item["url"], headers=headers, timeout_sec=request_data.timeout_sec)
        else:
            raise RuntimeError("返回结果中缺少 b64_json/url，无法保存图片。")
        file_path = output_dir / f"{prefix}{timestamp}_{index:02d}.png"
        file_path.write_bytes(image_bytes)
        saved_files.append(str(file_path))
        logs.append(f"已保存：{file_path.name}")

    return saved_files, logs
