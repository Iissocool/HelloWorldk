from __future__ import annotations

from .hardware import detect_hardware_profile
from .models import BackendPlan, RuntimePlan


BACKEND_DISPLAY = {
    "directml": "DirectML",
    "openvino": "OpenVINO",
    "cuda": "CUDA",
    "tensorrt": "TensorRT",
    "migraphx": "MIGraphX",
    "cpu": "CPU",
}


VIRTUAL_GPU_TOKENS = ("microsoft basic", "parallels", "vmware", "virtual", "remote display")


def _pick_primary_vendor(profile) -> str:
    ranked = {"nvidia": 3, "intel": 2, "amd": 2, "unknown": 0}
    real_gpus = [
        gpu
        for gpu in profile.gpus
        if not any(token in gpu.name.lower() for token in VIRTUAL_GPU_TOKENS)
    ]
    gpu_pool = real_gpus or profile.gpus
    if not gpu_pool:
        return "unknown"
    ordered = sorted(gpu_pool, key=lambda gpu: ranked.get(gpu.vendor, 0), reverse=True)
    return ordered[0].vendor


def build_runtime_plan() -> RuntimePlan:
    profile = detect_hardware_profile()
    primary_vendor = _pick_primary_vendor(profile)
    system = profile.os.lower()
    plans: list[BackendPlan] = []
    notes: list[str] = []

    if system == "windows":
        if primary_vendor == "nvidia":
            plans = [
                BackendPlan(backend="tensorrt", priority=1, rationale="Highest-performance NVIDIA path for personal Windows deployments."),
                BackendPlan(backend="cuda", priority=2, rationale="General NVIDIA GPU fallback when TensorRT is unavailable."),
                BackendPlan(backend="directml", priority=3, rationale="Broad DX12 fallback on Windows."),
                BackendPlan(backend="cpu", priority=4, rationale="Safe universal fallback."),
            ]
        elif primary_vendor == "intel":
            plans = [
                BackendPlan(backend="directml", priority=1, rationale="Best validated full-model path for Intel Arc on this Windows deployment."),
                BackendPlan(backend="openvino", priority=2, rationale="Intel-specific acceleration path for targeted benchmarks and compatible models."),
                BackendPlan(backend="cpu", priority=3, rationale="Safe universal fallback."),
            ]
        elif primary_vendor == "amd":
            plans = [
                BackendPlan(backend="directml", priority=1, rationale="Best practical Windows-wide AMD route."),
                BackendPlan(backend="cpu", priority=2, rationale="Safe universal fallback."),
            ]
        else:
            plans = [BackendPlan(backend="cpu", priority=1, rationale="No supported GPU detected yet.")]
        notes.append("Windows V1 ships with DirectML as the broad baseline, with vendor-specific packs layered on top.")
    else:
        if primary_vendor == "nvidia":
            plans = [
                BackendPlan(backend="tensorrt", priority=1, rationale="Preferred Linux NVIDIA deployment path."),
                BackendPlan(backend="cuda", priority=2, rationale="Standard ONNX Runtime NVIDIA fallback."),
                BackendPlan(backend="cpu", priority=3, rationale="Safe universal fallback."),
            ]
        elif primary_vendor == "intel":
            plans = [
                BackendPlan(backend="openvino", priority=1, rationale="Intel-optimized Linux path."),
                BackendPlan(backend="cpu", priority=2, rationale="Safe fallback."),
            ]
        elif primary_vendor == "amd":
            plans = [
                BackendPlan(backend="migraphx", priority=1, rationale="AMD-recommended path for newer Linux deployments."),
                BackendPlan(backend="cpu", priority=2, rationale="Safe fallback."),
            ]
        else:
            plans = [BackendPlan(backend="cpu", priority=1, rationale="No supported GPU detected yet.")]
        notes.append("AMD ROCm EP is deprecated in ONNX Runtime; production Linux AMD work should move to MIGraphX.")

    return RuntimePlan(detected_vendor=primary_vendor, recommended_stack=plans, notes=notes)

