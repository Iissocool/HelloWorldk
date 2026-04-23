from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import MODEL_CATALOG
from .config import DATA_ROOT, MODELS_ROOT, SCRIPTS_ROOT, UPSCALE_BINARY, UPSCALE_RUNTIME_ROOT, VENV_ROOT


@dataclass(slots=True)
class RuntimeComponentSpec:
    id: str
    title: str
    description: str
    python_paths: list[Path]
    file_paths: list[Path] | None = None
    required: bool = False


@dataclass(slots=True)
class RuntimeComponentStatus:
    id: str
    title: str
    description: str
    installed: bool
    required: bool
    location: str


@dataclass(slots=True)
class ModelAssetStatus:
    id: str
    title: str
    installed: bool
    files: list[str]
    size_mb: float


RUNTIME_COMPONENTS: list[RuntimeComponentSpec] = [
    RuntimeComponentSpec(
        id='core',
        title='核心桌面依赖',
        description='桌面窗口与本地控制逻辑的最小依赖。',
        python_paths=[Path('.venv') / 'Scripts' / 'python.exe'],
        required=True,
    ),
    RuntimeComponentSpec(
        id='cpu',
        title='CPU 抠图运行时',
        description='最稳的通用抠图运行时，也是首次安装模型的基础。',
        python_paths=[
            VENV_ROOT / 'rembg-cpu' / 'Scripts' / 'python.exe',
            VENV_ROOT / 'rembg' / 'Scripts' / 'python.exe',
        ],
    ),
    RuntimeComponentSpec(
        id='directml',
        title='DirectML GPU 运行时',
        description='Windows 下 AMD / Intel 的通用 GPU 路线。',
        python_paths=[VENV_ROOT / 'rembg-dml' / 'Scripts' / 'python.exe'],
    ),
    RuntimeComponentSpec(
        id='openvino',
        title='OpenVINO 运行时',
        description='Intel 设备专项推理路线。',
        python_paths=[
            VENV_ROOT / 'rembg-openvino' / 'Scripts' / 'python.exe',
            VENV_ROOT / 'rembg' / 'Scripts' / 'python.exe',
        ],
    ),
    RuntimeComponentSpec(
        id='nvidia',
        title='NVIDIA GPU 运行时',
        description='CUDA / TensorRT 所需的可选运行时。',
        python_paths=[
            VENV_ROOT / 'rembg-nvidia' / 'Scripts' / 'python.exe',
            VENV_ROOT / 'rembg-nv' / 'Scripts' / 'python.exe',
        ],
    ),
    RuntimeComponentSpec(
        id='upscale-ai',
        title='AI 高清增强运行时',
        description='Real-ESRGAN ncnn Vulkan 本地超分后端。',
        python_paths=[],
        file_paths=[UPSCALE_BINARY],
    ),
]

RUNTIME_COMPONENT_MAP = {item.id: item for item in RUNTIME_COMPONENTS}
BACKEND_COMPONENT_MAP = {
    'cpu': 'cpu',
    'directml': 'directml',
    'amd': 'directml',
    'openvino': 'openvino',
    'cuda': 'nvidia',
    'tensorrt': 'nvidia',
}

MODEL_FILE_MAP: dict[str, list[str]] = {
    'u2net': ['u2net.onnx'],
    'u2netp': ['u2netp.onnx'],
    'u2net_human_seg': ['u2net_human_seg.onnx'],
    'u2net_cloth_seg': ['u2net_cloth_seg.onnx'],
    'silueta': ['silueta.onnx'],
    'isnet-general-use': ['isnet-general-use.onnx'],
    'isnet-anime': ['isnet-anime.onnx'],
    'sam': ['sam_vit_b_01ec64.encoder.onnx', 'sam_vit_b_01ec64.decoder.onnx'],
    'birefnet-general': ['birefnet-general.onnx'],
    'birefnet-general-lite': ['birefnet-general-lite.onnx'],
    'birefnet-portrait': ['birefnet-portrait.onnx'],
    'birefnet-dis': ['birefnet-dis.onnx'],
    'birefnet-hrsod': ['birefnet-hrsod.onnx'],
    'birefnet-cod': ['birefnet-cod.onnx'],
    'birefnet-massive': ['birefnet-massive.onnx'],
    'bria-rmbg': ['bria-rmbg.onnx'],
}


def runtime_component_for_backend(backend: str) -> str:
    return BACKEND_COMPONENT_MAP.get(backend, 'cpu')


def runtime_component_installed(component_id: str) -> bool:
    component = RUNTIME_COMPONENT_MAP[component_id]
    search_paths = component.python_paths + (component.file_paths or [])
    return any(path.exists() for path in search_paths)


def runtime_component_location(component_id: str) -> str:
    component = RUNTIME_COMPONENT_MAP[component_id]
    search_paths = component.python_paths + (component.file_paths or [])
    for path in search_paths:
        if path.exists():
            return str(path.parent.parent if path.name == 'python.exe' else path.parent)
    if component.python_paths:
        return str(component.python_paths[0].parent.parent)
    if component.file_paths:
        return str(component.file_paths[0].parent)
    return str(UPSCALE_RUNTIME_ROOT)


def runtime_component_statuses() -> list[RuntimeComponentStatus]:
    statuses: list[RuntimeComponentStatus] = []
    for component in RUNTIME_COMPONENTS:
        statuses.append(
            RuntimeComponentStatus(
                id=component.id,
                title=component.title,
                description=component.description,
                installed=runtime_component_installed(component.id),
                required=component.required,
                location=runtime_component_location(component.id),
            )
        )
    return statuses


def build_runtime_manage_command(action: str, components: list[str]) -> list[str]:
    command = [
        'powershell',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        str(SCRIPTS_ROOT / 'setup_windows_runtime.ps1'),
        '-Action',
        action,
    ]
    if components:
        command.extend(['-Components', ','.join(components)])
    return command


def model_files(model_id: str) -> list[Path]:
    return [MODELS_ROOT / file_name for file_name in MODEL_FILE_MAP.get(model_id, [f'{model_id}.onnx'])]


def model_installed(model_id: str) -> bool:
    files = model_files(model_id)
    return bool(files) and all(path.exists() for path in files)


def model_statuses() -> list[ModelAssetStatus]:
    statuses: list[ModelAssetStatus] = []
    for model in MODEL_CATALOG:
        files = model_files(model.id)
        existing = [path for path in files if path.exists()]
        size_mb = round(sum(path.stat().st_size for path in existing) / 1024 / 1024, 1) if existing else 0.0
        statuses.append(
            ModelAssetStatus(
                id=model.id,
                title=model.title,
                installed=len(existing) == len(files),
                files=[path.name for path in files],
                size_mb=size_mb,
            )
        )
    return statuses


def choose_model_install_backend() -> str | None:
    for backend, component_id in [('cpu', 'cpu'), ('directml', 'directml'), ('openvino', 'openvino'), ('cuda', 'nvidia')]:
        if runtime_component_installed(component_id):
            return backend
    return None


def build_model_manage_command(action: str, model_id: str, *, backend: str = 'cpu') -> list[str]:
    return [
        'powershell',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        str(SCRIPTS_ROOT / 'manage_model_assets.ps1'),
        '-Action',
        action,
        '-ModelId',
        model_id,
        '-Backend',
        backend,
    ]


def model_install_workspace() -> Path:
    path = DATA_ROOT / 'model-installer'
    path.mkdir(parents=True, exist_ok=True)
    return path
