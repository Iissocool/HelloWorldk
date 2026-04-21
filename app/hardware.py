from __future__ import annotations

import platform
import re
import shutil
import subprocess
from typing import Iterable

import psutil

from .models import GPUInfo, HardwareProfile


def _safe_run(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return completed.stdout.strip()
    except Exception:
        return ""


def _detect_cpu_name() -> str:
    if platform.system() == "Windows":
        value = _safe_run([
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
        ])
        if value:
            return value
    return platform.processor() or "Unknown CPU"


def _vendor_from_name(name: str) -> str:
    lower = name.lower()
    if any(token in lower for token in ["nvidia", "geforce", "quadro", "rtx", "gtx"]):
        return "nvidia"
    if any(token in lower for token in ["amd", "radeon", "firepro", "rx ", "vega"]):
        return "amd"
    if any(token in lower for token in ["intel", "arc", "iris", "uhd", "xe"]):
        return "intel"
    return "unknown"


def _parse_wmic_memory(raw: str) -> int | None:
    match = re.search(r"(\d+)", raw or "")
    if not match:
        return None
    try:
        return int(int(match.group(1)) / (1024 * 1024))
    except Exception:
        return None


def _detect_windows_gpus() -> list[GPUInfo]:
    output = _safe_run([
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion | ConvertTo-Json -Compress",
    ])
    if not output:
        return []

    import json

    try:
        data = json.loads(output)
    except Exception:
        return []

    records = data if isinstance(data, list) else [data]
    gpus: list[GPUInfo] = []
    for index, record in enumerate(records):
        name = str(record.get("Name") or "Unknown GPU")
        vendor = _vendor_from_name(name)
        gpus.append(
            GPUInfo(
                name=name,
                vendor=vendor,
                memory_mb=_parse_wmic_memory(str(record.get("AdapterRAM", ""))),
                driver_version=str(record.get("DriverVersion") or "") or None,
                adapter_index=index,
                is_integrated=any(token in name.lower() for token in ["uhd", "iris", "integrated"]),
            )
        )
    return gpus


def _detect_linux_gpus() -> list[GPUInfo]:
    output = _safe_run(["sh", "-lc", "lspci | grep -i -E 'vga|3d|display'"])
    gpus: list[GPUInfo] = []
    for index, line in enumerate(filter(None, output.splitlines())):
        name = line.split(":", 2)[-1].strip()
        gpus.append(GPUInfo(name=name, vendor=_vendor_from_name(name), adapter_index=index))
    return gpus


def _capability_flags(gpus: Iterable[GPUInfo]) -> dict[str, bool]:
    gpu_list = list(gpus)
    vendors = {gpu.vendor for gpu in gpu_list}
    system = platform.system().lower()
    return {
        "directml_candidate": system == "windows" and bool(gpu_list),
        "cuda_candidate": "nvidia" in vendors,
        "tensorrt_candidate": "nvidia" in vendors,
        "openvino_candidate": "intel" in vendors or system == "windows",
        "migraphx_candidate": system == "linux" and "amd" in vendors,
        "nvidia_smi_present": shutil.which("nvidia-smi") is not None,
        "local_dml_runner_present": shutil.which("cmd") is not None,
        "w_gemini_runner_present": platform.system() == "Windows" and any(
            [
                shutil.which("cmd") is not None,
            ]
        ),
    }


def detect_hardware_profile() -> HardwareProfile:
    system = platform.system()
    gpus = _detect_windows_gpus() if system == "Windows" else _detect_linux_gpus()
    memory_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    return HardwareProfile(
        os=system,
        os_version=platform.version(),
        cpu_name=_detect_cpu_name(),
        total_memory_gb=memory_gb,
        gpus=gpus,
        capabilities=_capability_flags(gpus),
    )
