import argparse
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("GEMINI_ROOT", Path(__file__).resolve().parents[2]))
MODEL_HOME = ROOT / "models" / ".u2net"
OPENVINO_VENV = ROOT / "venvs" / "rembg-openvino"
OPENVINO_FALLBACK_VENV = ROOT / "venvs" / "rembg"
OPENVINO_LIB = OPENVINO_VENV / "Lib" / "site-packages" / "openvino" / "libs"
OPENVINO_ORT_CAPI = OPENVINO_VENV / "Lib" / "site-packages" / "onnxruntime" / "capi"


def prepare_env(backend: str) -> None:
    os.environ.setdefault("U2NET_HOME", str(MODEL_HOME))
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
    if backend == "openvino":
        active_openvino_venv = OPENVINO_VENV if OPENVINO_VENV.exists() else OPENVINO_FALLBACK_VENV
        path_parts = os.environ.get("PATH", "").split(";") if os.environ.get("PATH") else []
        for required in [
            str(active_openvino_venv / "Lib" / "site-packages" / "openvino" / "libs"),
            str(active_openvino_venv / "Lib" / "site-packages" / "onnxruntime" / "capi"),
        ]:
            if required not in path_parts:
                path_parts.insert(0, required)
        os.environ["PATH"] = ";".join(path_parts)


def parse_json_arg(raw: str, arg_name: str):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{arg_name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{arg_name} must decode to a JSON object")
    return data


def build_providers(backend: str):
    if backend == "cpu":
        return ["CPUExecutionProvider"]
    if backend == "openvino":
        return [("OpenVINOExecutionProvider", {"device_type": "GPU"}), "CPUExecutionProvider"]
    if backend == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if backend == "tensorrt":
        return ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    raise SystemExit(f"Unsupported backend: {backend}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rembg with a selected hardware backend")
    parser.add_argument("--backend", choices=["cpu", "openvino", "cuda", "tensorrt"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--session-json", default="{}")
    parser.add_argument("--remove-json", default="{}")
    args = parser.parse_args()

    prepare_env(args.backend)

    import onnxruntime as ort
    from rembg import new_session, remove

    available_providers = ort.get_available_providers()
    requested_providers = build_providers(args.backend)
    requested_names = [provider[0] if isinstance(provider, tuple) else provider for provider in requested_providers]

    if args.backend != "cpu" and requested_names[0] not in available_providers:
        raise SystemExit(
            f"Requested provider {requested_names[0]} is not available in this runtime. Available: {available_providers}"
        )

    session_kwargs = parse_json_arg(args.session_json, "--session-json")
    remove_kwargs = parse_json_arg(args.remove_json, "--remove-json")

    session = new_session(args.model, providers=requested_providers, **session_kwargs)
    inner = getattr(session, "inner_session", None)
    if inner is not None:
        active_providers = inner.get_providers()
    else:
        encoder = getattr(session, "encoder", None)
        active_providers = encoder.get_providers() if encoder is not None else []

    if args.backend != "cpu" and requested_names[0] not in active_providers:
        raise SystemExit(
            f"Requested backend {args.backend} did not stay active. Active providers: {active_providers}"
        )

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = remove(input_path.read_bytes(), session=session, force_return_bytes=True, **remove_kwargs)
    output_path.write_bytes(result)

    print("Model:", args.model)
    print("Requested backend:", args.backend)
    print("Requested providers:", requested_providers)
    print("Available providers:", available_providers)
    print("Active providers:", active_providers)
    print("Saved:", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
