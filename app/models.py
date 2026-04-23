from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


LicenseClass = Literal[
    "personal-use",
    "personal-use-review",
    "personal-use-restricted",
]
BackendId = Literal[
    "auto",
    "directml",
    "amd",
    "openvino",
    "cuda",
    "tensorrt",
    "migraphx",
    "cpu",
]
JobType = Literal[
    "single",
    "batch",
    "smart",
    "rename",
    "image",
    "ai_test",
    "ps_batch",
    "upscale",
    "background_replace",
    "agent",
    "cli",
]
RenameMode = Literal["template", "replace", "fresh"]


@dataclass(slots=True)
class ModelSpec:
    id: str
    title: str
    category: str
    quality_tier: str
    speed_tier: str
    license_class: LicenseClass
    license_note: str
    recommended_backends: list[BackendId] = field(default_factory=list)


class GPUInfo(BaseModel):
    name: str
    vendor: str
    memory_mb: int | None = None
    driver_version: str | None = None
    adapter_index: int = 0
    is_integrated: bool = False


class HardwareProfile(BaseModel):
    os: str
    os_version: str
    cpu_name: str
    total_memory_gb: float
    gpus: list[GPUInfo] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)


class BackendPlan(BaseModel):
    backend: BackendId
    priority: int
    rationale: str


class RuntimePlan(BaseModel):
    detected_vendor: str
    recommended_stack: list[BackendPlan]
    notes: list[str] = Field(default_factory=list)


class SingleRunRequest(BaseModel):
    input_path: str
    output_path: str
    model: str = "bria-rmbg"
    backend: BackendId = "auto"
    session_json: dict = Field(default_factory=dict)
    remove_json: dict = Field(default_factory=dict)


class BatchRunRequest(BaseModel):
    input_dir: str
    output_dir: str
    model: str = "bria-rmbg"
    backend: BackendId = "auto"
    overwrite: bool = False
    recurse: bool = False
    include_generated: bool = False
    session_json: dict = Field(default_factory=dict)
    remove_json: dict = Field(default_factory=dict)


class SmartRunRequest(BaseModel):
    input_dir: str
    output_dir: str
    strategy: Literal["quality", "balanced", "speed"] = "quality"
    backend: BackendId = "auto"
    overwrite: bool = False
    recurse: bool = False
    include_generated: bool = False
    session_json: dict = Field(default_factory=dict)
    remove_json: dict = Field(default_factory=dict)


class RenameRunRequest(BaseModel):
    input_dir: str
    mode: RenameMode = "template"
    template: str = "{index:03d}_{name}"
    fresh_name: str = "image"
    find_text: str = ""
    replace_text: str = ""
    prefix: str = ""
    suffix: str = ""
    start_index: int = 1
    step: int = 1
    padding_width: int = 3
    recurse: bool = False
    extensions: str = ""
    case_sensitive: bool = False
    keep_extension: bool = True


class AIProviderSettings(BaseModel):
    base_url: str = "https://api.openai.com"
    model: str = "gpt-image-1"
    api_key: str = ""
    timeout_sec: int = 120


class AIImageTestRequest(BaseModel):
    base_url: str
    api_key: str
    timeout_sec: int = 30


class AIImageRunRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    prompt: str
    output_dir: str
    image_count: int = 1
    size: str = "1024x1024"
    quality: str = "auto"
    file_prefix: str = "image_"
    timeout_sec: int = 180


class UpscaleRunRequest(BaseModel):
    input_dir: str
    output_dir: str
    scale: int = 2
    mode: Literal["quality", "balanced", "speed"] = "quality"
    recurse: bool = False
    overwrite: bool = False


class BackgroundReplaceRunRequest(BaseModel):
    input_dir: str
    output_dir: str
    subject_name: str
    background_prompt: str
    background_style: str = "custom"
    recurse: bool = True
    overwrite: bool = False
    preserve_structure: bool = True
    matt_model: str = "bria-rmbg"
    matt_backend: BackendId = "auto"
    retry_count: int = 1


class PhotoshopBatchRequest(BaseModel):
    template_path: str
    droplet_path: str
    input_dir: str
    output_dir: str = ""
    photoshop_path: str = ""
    template_wait_sec: int = 8
    timeout_sec: int = 1800
    collect_wait_sec: int = 15
    close_photoshop_when_done: bool = False


class AppSettings(BaseModel):
    agent_session_name: str = "neonpilot"


class ExecutionResult(BaseModel):
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    return_code: int
    output_path: str | None = None
    report_path: str | None = None
    backend_used: str | None = None
    model_used: str | None = None
    summary: str | None = None
    artifacts: list[str] = Field(default_factory=list)
