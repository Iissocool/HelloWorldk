from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


LicenseClass = Literal[
    "commercial-ok",
    "commercial-review",
    "commercial-agreement-required",
]
BackendId = Literal[
    "auto",
    "directml",
    "openvino",
    "cuda",
    "tensorrt",
    "migraphx",
    "cpu",
]
JobType = Literal["single", "batch", "smart"]


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
