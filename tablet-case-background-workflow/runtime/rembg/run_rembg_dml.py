import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import onnxruntime as ort

ROOT = Path(os.environ.get("GEMINI_ROOT", Path(__file__).resolve().parents[2]))
MODEL_HOME = ROOT / "models" / ".u2net"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
GENERATED_NAME_MARKERS = (".out", "_cut", "_mask", "_alpha")

os.environ.setdefault("U2NET_HOME", str(MODEL_HOME))
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

from rembg import remove  # noqa: E402
from rembg.sessions import sessions_class  # noqa: E402


SESSION_CLASSES = {sc.name(): sc for sc in sessions_class}
DML_PROVIDERS = ["DmlExecutionProvider", "CPUExecutionProvider"]
BIREFNET_MODELS = {
    "birefnet-general",
    "birefnet-general-lite",
    "birefnet-portrait",
    "birefnet-dis",
    "birefnet-hrsod",
    "birefnet-cod",
    "birefnet-massive",
}


def parse_json_arg(raw: Any, arg_name: str):
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{arg_name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{arg_name} must decode to a JSON object")
    return data


def build_session_options(model: str) -> ort.SessionOptions:
    opts = ort.SessionOptions()
    opts.enable_mem_pattern = False
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    if model in BIREFNET_MODELS:
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    elif model == "bria-rmbg":
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    else:
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    return opts


def create_session(model: str, session_kwargs: Dict[str, Any]):
    if model not in SESSION_CLASSES:
        raise SystemExit(f"Unknown model: {model}")
    cls = SESSION_CLASSES[model]
    opts = build_session_options(model)
    return cls(model, opts, providers=DML_PROVIDERS, **session_kwargs)


def active_providers(session) -> List[str]:
    inner = getattr(session, "inner_session", None)
    if inner is not None:
        return inner.get_providers()
    encoder = getattr(session, "encoder", None)
    if encoder is not None:
        return encoder.get_providers()
    return []


def graph_optimization_level_name(model: str) -> str:
    level = build_session_options(model).graph_optimization_level
    return str(level).split(".", 1)[-1]


def run_model(
    model: str,
    input_path: Path,
    output_path: Path,
    session_kwargs: Dict[str, Any] | None = None,
    remove_kwargs: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    session_kwargs = session_kwargs or {}
    remove_kwargs = remove_kwargs or {}

    t0 = time.perf_counter()
    session = create_session(model, session_kwargs)
    t1 = time.perf_counter()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = remove(
        input_path.read_bytes(),
        session=session,
        force_return_bytes=True,
        **remove_kwargs,
    )
    t2 = time.perf_counter()
    output_path.write_bytes(result)

    return {
        "model": model,
        "graph_optimization_level": graph_optimization_level_name(model),
        "requested_providers": list(DML_PROVIDERS),
        "active_providers": active_providers(session),
        "session_create_seconds": round(t1 - t0, 3),
        "inference_seconds": round(t2 - t1, 3),
        "output_path": str(output_path),
        "output_bytes": len(result),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run rembg on Windows GPU via DirectML with per-model stability tuning"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--session-json", default="{}")
    parser.add_argument("--remove-json", default="{}")
    args = parser.parse_args()

    session_kwargs = parse_json_arg(args.session_json, "--session-json")
    remove_kwargs = parse_json_arg(args.remove_json, "--remove-json")

    input_path = Path(args.input)
    output_path = Path(args.output)
    stats = run_model(args.model, input_path, output_path, session_kwargs, remove_kwargs)

    print("Model:", stats["model"])
    print("GraphOptimizationLevel:", stats["graph_optimization_level"])
    print("Requested providers:", stats["requested_providers"])
    print("Active providers:", stats["active_providers"])
    print("Session create seconds:", stats["session_create_seconds"])
    print("Inference seconds:", stats["inference_seconds"])
    print("Saved:", stats["output_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
