from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from PIL import Image

from .ai_image import generate_images, load_ai_settings, test_ai_provider
from .background_replace import (
    BACKGROUND_STYLE_PRESETS,
    build_output_path,
    build_background_prompt,
    choose_generation_size,
    composite_subject_over_background,
    image_paths_from_dir as background_image_paths_from_dir,
)
from .catalog import MODEL_MAP
from .config import RUNTIME_ROOT, WORKSPACE_ROOT
from .hardware import detect_hardware_profile
from .history import HistoryStore
from .models import (
    AIImageRunRequest,
    AIImageTestRequest,
    BackgroundReplaceRunRequest,
    BatchRunRequest,
    ExecutionResult,
    ResizeRunRequest,
    PhotoshopBatchRequest,
    RenameRunRequest,
    SingleRunRequest,
    SmartRunRequest,
    UpscaleRunRequest,
)
from .photoshop_bridge import (
    close_photoshop_processes,
    detect_photoshop_executable,
    image_count_in_directory,
    open_template_in_photoshop,
    resolve_photoshop_executable,
    run_droplet_on_folder,
    wait_for_template_ready,
)
from .planner import build_runtime_plan
from .resizer import image_paths_from_dir as resize_image_paths_from_dir, resize_image
from .renamer import build_rename_plan, execute_rename_plan
from .runtime_manager import (
    model_installed,
    runtime_component_for_backend,
    runtime_component_installed,
)
from .selection import analyze_image, choose_category, choose_model
from .upscaler import external_upscale_available, image_paths_from_dir as upscale_image_paths_from_dir, upscale_image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
GENERATED_NAME_MARKERS = (".out", "_cut", "_mask", "_alpha")
RUNNERS = {
    "directml": RUNTIME_ROOT / "run_rembg_dml.cmd",
    "openvino": RUNTIME_ROOT / "run_rembg_openvino.cmd",
    "cuda": RUNTIME_ROOT / "run_rembg_cuda.cmd",
    "tensorrt": RUNTIME_ROOT / "run_rembg_tensorrt.cmd",
    "cpu": RUNTIME_ROOT / "run_rembg_cpu.cmd",
    "amd": RUNTIME_ROOT / "run_rembg_amd.cmd",
}
BACKEND_CAPABILITY_KEYS = {
    "directml": "directml_candidate",
    "openvino": "openvino_candidate",
    "cuda": "cuda_candidate",
    "tensorrt": "tensorrt_candidate",
    "migraphx": "migraphx_candidate",
    "cpu": None,
    "amd": "directml_candidate",
}


class ExecutionError(RuntimeError):
    pass


class RuntimeMissingError(ExecutionError):
    def __init__(self, component_id: str, message: str) -> None:
        super().__init__(message)
        self.component_id = component_id


class ModelMissingError(ExecutionError):
    def __init__(self, model_id: str, message: str) -> None:
        super().__init__(message)
        self.model_id = model_id


class LocalExecutor:
    def __init__(self, history_store: HistoryStore | None = None) -> None:
        self.history_store = history_store or HistoryStore()
        self._creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    def available_backends(self) -> list[str]:
        ordered = ["auto", "directml", "amd", "openvino", "cuda", "tensorrt", "cpu"]
        return [
            backend
            for backend in ordered
            if backend == "auto" or self._backend_ready(backend)
        ]

    def _runner_path(self, backend: str) -> Path:
        normalized = "directml" if backend == "amd" else backend
        try:
            return RUNNERS[normalized]
        except KeyError as exc:
            raise ExecutionError(f"Unsupported backend: {backend}") from exc

    def _ensure_runner(self, backend: str) -> Path:
        runner = self._runner_path(backend)
        if not runner.exists():
            raise ExecutionError(f"Required runner not found: {runner}")
        component_id = runtime_component_for_backend(backend)
        if not runtime_component_installed(component_id):
            raise RuntimeMissingError(component_id, f"当前未安装 {component_id} 运行时。")
        return runner

    def _backend_ready(self, backend: str) -> bool:
        try:
            runner = self._runner_path(backend)
        except ExecutionError:
            return False
        if not runner.exists():
            return False
        component_id = runtime_component_for_backend(backend)
        return runtime_component_installed(component_id)

    def _profile(self):
        return detect_hardware_profile()

    def _can_attempt_backend(self, backend: str) -> bool:
        normalized = "directml" if backend == "amd" else backend
        if normalized not in RUNNERS:
            return False
        if not self._backend_ready(normalized):
            return False
        capability_key = BACKEND_CAPABILITY_KEYS.get(backend)
        if capability_key is None:
            return True
        profile = self._profile()
        return bool(profile.capabilities.get(capability_key, False))

    def _ensure_model_available(self, model: str) -> None:
        if not model_installed(model):
            raise ModelMissingError(model, f"当前未安装模型：{model}")

    def resolve_backend(self, requested_backend: str, model: str | None = None) -> str:
        if requested_backend == "amd":
            profile = self._profile()
            if not any(gpu.vendor == "amd" for gpu in profile.gpus):
                raise ExecutionError("AMD backend was requested, but no AMD GPU was detected.")
            self._ensure_runner("amd")
            return "amd"

        if requested_backend != "auto":
            self._ensure_runner(requested_backend)
            return requested_backend

        allowed = (
            MODEL_MAP.get(model).recommended_backends if model in MODEL_MAP else list(RUNNERS)
        )
        plan = build_runtime_plan()

        for plan_item in plan.recommended_stack:
            if plan_item.backend in allowed and self._can_attempt_backend(plan_item.backend):
                return plan_item.backend

        for backend in allowed:
            if backend in RUNNERS and self._can_attempt_backend(backend):
                return backend

        if self._can_attempt_backend("cpu"):
            return "cpu"

        raise RuntimeMissingError("cpu", "当前还没有可用的抠图运行时。请先安装 CPU 或 GPU 运行时。")

    def _run(self, command: list[str]) -> ExecutionResult:
        completed = subprocess.run(
            command,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=self._creationflags,
        )
        return ExecutionResult(
            ok=completed.returncode == 0,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            return_code=completed.returncode,
        )

    def _log_job(
        self,
        *,
        job_type: str,
        backend: str,
        model: str,
        input_ref: str,
        output_ref: str,
        result: ExecutionResult,
    ) -> None:
        self.history_store.add_job(
            job_type=job_type,
            backend=backend,
            model=model,
            input_ref=input_ref,
            output_ref=output_ref,
            result=result,
        )

    def _output_path_for_input(self, output_dir: Path, input_path: Path, input_root: Path) -> Path:
        relative_path = input_path.relative_to(input_root)
        return output_dir / relative_path.with_suffix(".png")

    def _resolve_single_output_path(self, input_path: Path, output_text: str) -> Path:
        raw = output_text.strip()
        if not raw:
            raise ExecutionError("请填写输出路径。")
        candidate = Path(raw)
        treat_as_dir = (
            raw.endswith(("\\", "/"))
            or (candidate.exists() and candidate.is_dir())
            or candidate.suffix == ""
        )
        if treat_as_dir:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate / f"{input_path.stem}.png"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    def _ensure_distinct_output_dir(self, input_dir: Path, output_dir: Path, *, label: str = "输出目录") -> None:
        try:
            same = input_dir.resolve() == output_dir.resolve()
        except OSError:
            same = input_dir == output_dir
        if same:
            raise ExecutionError(f"{label}不能和输入目录相同。请另外选择一个输出目录。")

    def _should_skip_generated(self, path: Path) -> bool:
        lower_name = path.stem.lower()
        return any(marker in lower_name for marker in GENERATED_NAME_MARKERS)

    def _image_paths_from_dir(
        self,
        input_dir: Path,
        recurse: bool,
        include_generated: bool,
    ) -> list[Path]:
        pattern = "**/*" if recurse else "*"
        return sorted(
            path
            for path in input_dir.glob(pattern)
            if path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and (include_generated or not self._should_skip_generated(path))
        )

    def _collect_image_outputs(self, output_dir: Path) -> list[str]:
        if not output_dir.exists() or not output_dir.is_dir():
            return []
        return [
            str(path)
            for path in sorted(output_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ]

    def _build_single_command(self, backend: str, request: SingleRunRequest) -> list[str]:
        normalized = "directml" if backend == "amd" else backend
        runner = self._ensure_runner(normalized)
        return [
            "cmd",
            "/c",
            str(runner),
            "--model",
            request.model,
            "--input",
            request.input_path,
            "--output",
            request.output_path,
            "--session-json",
            json.dumps(request.session_json, ensure_ascii=False),
            "--remove-json",
            json.dumps(request.remove_json, ensure_ascii=False),
        ]

    def _summarize_single(self, result: ExecutionResult) -> str:
        if result.ok:
            return f"Completed with {result.backend_used} using model {result.model_used}."
        return f"Failed on backend {result.backend_used or 'unknown'} with return code {result.return_code}."

    def _aggregate_result(
        self,
        *,
        job_type: str,
        rows: list[dict[str, str]],
        stdout_lines: list[str],
        backends_used: Iterable[str],
        models_used: Iterable[str],
    ) -> ExecutionResult:
        processed = len(rows)
        success_count = sum(1 for row in rows if row["status"] == "ok")
        fail_count = sum(1 for row in rows if row["status"] == "fail")
        skip_count = sum(1 for row in rows if row["status"] == "skipped")
        backend_values = sorted({value for value in backends_used if value})
        model_values = sorted({value for value in models_used if value})
        summary = (
            f"{job_type} processed {processed} images: "
            f"{success_count} succeeded, {fail_count} failed, {skip_count} skipped."
        )
        return ExecutionResult(
            ok=fail_count == 0,
            command=[f"internal:{job_type}"],
            stdout="\n".join(stdout_lines),
            stderr="",
            return_code=0 if fail_count == 0 else 1,
            backend_used=backend_values[0] if len(backend_values) == 1 else ("mixed" if backend_values else None),
            model_used=model_values[0] if len(model_values) == 1 else ("multiple" if model_values else None),
            summary=summary,
        )

    def run_single(self, request: SingleRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_path = Path(request.input_path)
        if not input_path.is_file():
            raise ExecutionError(f"输入图片不存在：{input_path}")
        self._ensure_model_available(request.model)
        backend = self.resolve_backend(request.backend, request.model)
        resolved_output_path = self._resolve_single_output_path(input_path, request.output_path)
        request = request.model_copy(update={"output_path": str(resolved_output_path)})
        command = self._build_single_command(backend, request)
        result = self._run(command)
        result.output_path = str(resolved_output_path)
        result.artifacts = [str(resolved_output_path)] if resolved_output_path.exists() else []
        result.backend_used = backend
        result.model_used = request.model
        result.summary = (
            f"单图抠图完成：{input_path.name}"
            if result.ok
            else f"单图抠图失败：{input_path.name}"
        )
        if log_history:
            self._log_job(
                job_type="single",
                backend=backend,
                model=request.model,
                input_ref=str(input_path),
                output_ref=str(resolved_output_path),
                result=result,
            )
        return result

    def run_batch(self, request: BatchRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        output_dir = Path(request.output_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"Input directory does not exist: {input_dir}")
        self._ensure_distinct_output_dir(input_dir, output_dir)
        self._ensure_model_available(request.model)

        images = self._image_paths_from_dir(input_dir, request.recurse, request.include_generated)
        if not images:
            raise ExecutionError(f"No supported images found in: {input_dir}")

        backend = self.resolve_backend(request.backend, request.model)
        rows: list[dict[str, str]] = []
        stdout_lines: list[str] = []

        for index, input_path in enumerate(images, start=1):
            output_path = self._output_path_for_input(output_dir, input_path, input_dir)
            if output_path.exists() and not request.overwrite:
                stdout_lines.append(f"[{index}/{len(images)}] skip {input_path.name} -> existing output")
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "model": request.model,
                        "backend": backend,
                        "status": "skipped",
                        "reason": "existing output",
                    }
                )
                continue

            single_result = self.run_single(
                SingleRunRequest(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    model=request.model,
                    backend=backend,
                    session_json=request.session_json,
                    remove_json=request.remove_json,
                ),
                log_history=False,
            )
            if single_result.ok:
                stdout_lines.append(
                    f"[{index}/{len(images)}] ok {input_path.name} -> {request.model} on {backend}"
                )
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "model": request.model,
                        "backend": backend,
                        "status": "ok",
                        "reason": "",
                    }
                )
            else:
                stdout_lines.append(
                    f"[{index}/{len(images)}] fail {input_path.name} -> {request.model} on {backend}: {single_result.stderr.strip() or single_result.stdout.strip()}"
                )
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "model": request.model,
                        "backend": backend,
                        "status": "fail",
                        "reason": (single_result.stderr or single_result.stdout).strip(),
                    }
                )

        result = self._aggregate_result(
            job_type="batch",
            rows=rows,
            stdout_lines=stdout_lines,
            backends_used=[backend],
            models_used=[request.model],
        )
        result.output_path = str(output_dir)
        result.artifacts = self._collect_image_outputs(output_dir)
        result.summary = f"固定批处理完成，成功 {sum(1 for row in rows if row['status'] == 'ok')} 张。"
        if log_history:
            self._log_job(
                job_type="batch",
                backend=backend,
                model=request.model,
                input_ref=str(input_dir),
                output_ref=str(output_dir),
                result=result,
            )
        return result

    def run_smart(self, request: SmartRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        output_dir = Path(request.output_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"Input directory does not exist: {input_dir}")
        self._ensure_distinct_output_dir(input_dir, output_dir)

        images = self._image_paths_from_dir(input_dir, request.recurse, request.include_generated)
        if not images:
            raise ExecutionError(f"No supported images found in: {input_dir}")

        rows: list[dict[str, str]] = []
        stdout_lines: list[str] = []
        backends_used: list[str] = []
        models_used: list[str] = []

        for index, input_path in enumerate(images, start=1):
            output_path = self._output_path_for_input(output_dir, input_path, input_dir)
            metrics = analyze_image(input_path)
            category, reason = choose_category(input_path, metrics)
            model = choose_model(category, request.strategy)
            self._ensure_model_available(model)
            backend = self.resolve_backend(request.backend, model)
            backends_used.append(backend)
            models_used.append(model)

            if output_path.exists() and not request.overwrite:
                stdout_lines.append(
                    f"[{index}/{len(images)}] skip {input_path.name} -> existing output ({model} / {backend})"
                )
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "strategy": request.strategy,
                        "category": category,
                        "model": model,
                        "backend": backend,
                        "status": "skipped",
                        "reason": f"existing output; {reason}",
                    }
                )
                continue

            single_result = self.run_single(
                SingleRunRequest(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    model=model,
                    backend=backend,
                    session_json=request.session_json,
                    remove_json=request.remove_json,
                ),
                log_history=False,
            )
            if single_result.ok:
                stdout_lines.append(
                    f"[{index}/{len(images)}] ok {input_path.name} -> {model} on {backend} ({reason})"
                )
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "strategy": request.strategy,
                        "category": category,
                        "model": model,
                        "backend": backend,
                        "status": "ok",
                        "reason": reason,
                    }
                )
            else:
                stdout_lines.append(
                    f"[{index}/{len(images)}] fail {input_path.name} -> {model} on {backend}: {single_result.stderr.strip() or single_result.stdout.strip()}"
                )
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "strategy": request.strategy,
                        "category": category,
                        "model": model,
                        "backend": backend,
                        "status": "fail",
                        "reason": (single_result.stderr or single_result.stdout).strip() or reason,
                    }
                )

        result = self._aggregate_result(
            job_type="smart",
            rows=rows,
            stdout_lines=stdout_lines,
            backends_used=backends_used,
            models_used=models_used,
        )
        result.output_path = str(output_dir)
        result.artifacts = self._collect_image_outputs(output_dir)
        result.summary = f"智能批处理完成，成功 {sum(1 for row in rows if row['status'] == 'ok')} 张。"
        if log_history:
            backend_label = result.backend_used or request.backend
            model_label = result.model_used or "multiple"
            self._log_job(
                job_type="smart",
                backend=backend_label,
                model=model_label,
                input_ref=str(input_dir),
                output_ref=str(output_dir),
                result=result,
            )
        return result

    def run_rename(self, request: RenameRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"Input directory does not exist: {input_dir}")

        try:
            plan = build_rename_plan(request)
        except ValueError as exc:
            raise ExecutionError(str(exc)) from exc

        if not plan:
            raise ExecutionError(f"No files found in: {input_dir}")

        plan, stdout_lines = execute_rename_plan(plan)
        rows: list[dict[str, str]] = []
        for item in plan:
            rows.append(
                {
                    "input": str(item.source_path),
                    "output": str(item.target_path) if item.target_path else "",
                    "model": request.mode,
                    "backend": "internal",
                    "status": item.status,
                    "reason": item.reason,
                }
            )

        success_count = sum(1 for row in rows if row["status"] == "ok")
        fail_count = sum(1 for row in rows if row["status"] == "fail")
        skip_count = sum(1 for row in rows if row["status"] == "skipped")
        result = ExecutionResult(
            ok=fail_count == 0,
            command=["internal:rename"],
            stdout="\n".join(stdout_lines),
            stderr="",
            return_code=0 if fail_count == 0 else 1,
            backend_used="internal",
            model_used=f"rename:{request.mode}",
            summary=(
                f"批量命名完成：成功 {success_count} 个，失败 {fail_count} 个，跳过 {skip_count} 个。"
            ),
        )
        if log_history:
            self._log_job(
                job_type="rename",
                backend="internal",
                model=f"rename:{request.mode}",
                input_ref=str(input_dir),
                output_ref=str(input_dir),
                result=result,
            )
        return result

    def run_ai_test(self, request: AIImageTestRequest, *, log_history: bool = True) -> ExecutionResult:
        try:
            summary, preview_models = test_ai_provider(request)
        except Exception as exc:
            raise ExecutionError(str(exc)) from exc
        result = ExecutionResult(
            ok=True,
            command=["internal:ai-test"],
            stdout=summary,
            stderr="",
            return_code=0,
            backend_used="openai-compatible",
            model_used=preview_models[0] if preview_models else None,
            summary="AI 接口连接正常。",
        )
        if log_history:
            self._log_job(
                job_type="ai_test",
                backend="openai-compatible",
                model=preview_models[0] if preview_models else "provider-test",
                input_ref=request.base_url,
                output_ref="connection-test",
                result=result,
            )
        return result

    def run_ai_image(self, request: AIImageRunRequest, *, log_history: bool = True) -> ExecutionResult:
        if not request.prompt.strip():
            raise ExecutionError("提示词不能为空。")
        if not request.api_key.strip():
            raise ExecutionError("API Key 不能为空。")
        if request.image_count < 1:
            raise ExecutionError("生成张数必须大于 0。")
        try:
            files, logs = generate_images(request)
        except Exception as exc:
            raise ExecutionError(str(exc)) from exc

        result = ExecutionResult(
            ok=True,
            command=["internal:ai-image"],
            stdout="\n".join(logs),
            stderr="",
            return_code=0,
            output_path=files[0] if files else None,
            backend_used="openai-compatible",
            model_used=request.model,
            summary=f"已生成 {len(files)} 张图片。",
            artifacts=files,
        )
        if log_history:
            self._log_job(
                job_type="image",
                backend="openai-compatible",
                model=request.model,
                input_ref=request.prompt,
                output_ref=request.output_dir,
                result=result,
            )
        return result

    def run_resize_batch(self, request: ResizeRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        output_dir = Path(request.output_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"输入目录不存在：{input_dir}")
        self._ensure_distinct_output_dir(input_dir, output_dir)
        if request.width <= 0 and request.height <= 0:
            raise ExecutionError("宽度和高度不能同时为空。")
        if request.dpi <= 0:
            raise ExecutionError("DPI 必须大于 0。")

        images = resize_image_paths_from_dir(input_dir, request.recurse)
        if not images:
            raise ExecutionError(f"当前目录里没有可处理图片：{input_dir}")

        rows: list[dict[str, str]] = []
        stdout_lines: list[str] = []
        for index, input_path in enumerate(images, start=1):
            relative = input_path.relative_to(input_dir)
            output_path = output_dir / relative
            if output_path.exists() and not request.overwrite:
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "model": f"resize:{request.mode}",
                        "backend": "pillow-native",
                        "status": "skipped",
                        "reason": "existing output",
                    }
                )
                stdout_lines.append(f"[{index}/{len(images)}] skip {relative}")
                continue

            summary = resize_image(
                input_path,
                output_path,
                width=request.width,
                height=request.height,
                dpi=request.dpi,
                mode=request.mode,
            )
            rows.append(
                {
                    "input": summary.input_path,
                    "output": summary.output_path,
                    "model": f"resize:{request.mode}",
                    "backend": summary.engine,
                    "status": "ok",
                    "reason": f"{summary.width}x{summary.height} @ {summary.dpi_x or request.dpi}dpi",
                }
            )
            stdout_lines.append(
                f"[{index}/{len(images)}] ok {relative} -> {summary.width}x{summary.height} @ {summary.dpi_x or request.dpi}dpi ({summary.mode})"
            )

        result = self._aggregate_result(
            job_type="resize",
            rows=rows,
            stdout_lines=stdout_lines,
            backends_used=["pillow-native"],
            models_used=[f"resize:{request.mode}"],
        )
        result.output_path = str(output_dir)
        result.artifacts = self._collect_image_outputs(output_dir)
        result.summary = (
            f"批量调尺寸完成，已输出 {sum(1 for row in rows if row['status'] == 'ok')} 张图片，"
            f"目标 {request.width}x{request.height} @ {request.dpi} DPI。"
            if result.ok
            else "批量调尺寸执行失败。"
        )
        if log_history:
            self._log_job(
                job_type="resize",
                backend="pillow-native",
                model=f"resize:{request.mode}",
                input_ref=str(input_dir),
                output_ref=str(output_dir),
                result=result,
            )
        return result

    def run_photoshop_batch(self, request: PhotoshopBatchRequest, *, log_history: bool = True) -> ExecutionResult:
        template_path = Path(request.template_path)
        droplet_path = Path(request.droplet_path)
        input_dir = Path(request.input_dir)
        if not template_path.exists():
            raise ExecutionError(f"模板文件不存在：{template_path}")
        if not droplet_path.exists():
            raise ExecutionError(f"Droplet 程序不存在：{droplet_path}")
        if not input_dir.exists() or not input_dir.is_dir():
            raise ExecutionError(f"素材目录不存在：{input_dir}")

        image_count = image_count_in_directory(input_dir)
        if image_count == 0:
            raise ExecutionError("当前素材目录里没有可处理的图片。")
        output_dir = Path(request.output_dir) if request.output_dir.strip() else None

        photoshop_path = resolve_photoshop_executable(request.photoshop_path) if request.photoshop_path.strip() else detect_photoshop_executable()
        open_command, open_source = open_template_in_photoshop(template_path, photoshop_path)
        wait_for_template_ready(request.template_wait_sec)

        try:
            completed = run_droplet_on_folder(
                droplet_path,
                input_dir,
                timeout_sec=request.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            artifacts = self._collect_image_outputs(output_dir) if output_dir else []
            result = ExecutionResult(
                ok=True,
                command=[str(droplet_path), str(input_dir)],
                stdout="\n".join(
                    [
                        f"模板已发送到 Photoshop：{template_path}",
                        f"Photoshop 来源：{open_source}",
                        f"打开命令：{' '.join(open_command)}",
                        f"素材目录已发送给 Droplet：{input_dir}",
                        f"图片数量：{image_count}",
                        (f"结果收集目录：{output_dir}" if output_dir else ""),
                        (f"当前已收集结果数：{len(artifacts)}" if output_dir else ""),
                        "Droplet 已启动，当前仍在 Photoshop 中继续执行。",
                        (
                            "已跳过自动关闭 Photoshop，因为 Droplet 还在运行。"
                            if request.close_photoshop_when_done
                            else ""
                        ),
                        stdout,
                    ]
                ).strip(),
                stderr=stderr,
                return_code=0,
                backend_used="photoshop-droplet",
                model_used="photoshop-template",
                summary=f"Photoshop 套图已启动，{image_count} 张图片正在处理。",
                artifacts=artifacts,
            )
            if log_history:
                self._log_job(
                    job_type="ps_batch",
                    backend="photoshop-droplet",
                    model="photoshop-template",
                    input_ref=str(input_dir),
                    output_ref=str(input_dir),
                    result=result,
                )
            return result

        stdout_lines = [
            f"模板已发送到 Photoshop：{template_path}",
            f"Photoshop 来源：{open_source}",
            f"打开命令：{' '.join(open_command)}",
            f"素材目录已发送给 Droplet：{input_dir}",
            f"图片数量：{image_count}",
        ]
        artifacts: list[str] = []
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            stdout_lines.append(f"结果收集目录：{output_dir}")
            if request.collect_wait_sec > 0:
                import time
                time.sleep(request.collect_wait_sec)
            artifacts = self._collect_image_outputs(output_dir)
            stdout_lines.append(f"已收集结果数：{len(artifacts)}")
        else:
            stdout_lines.append("未指定结果收集目录，最终输出仍由该 Droplet 绑定的 Photoshop 动作决定。")
        if request.close_photoshop_when_done:
            closed, close_message = close_photoshop_processes()
            stdout_lines.append(close_message)
            if not closed:
                stdout_lines.append("自动关闭 Photoshop 未完成。")
        result = ExecutionResult(
            ok=completed.returncode == 0 if completed is not None else True,
            command=[str(droplet_path), str(input_dir)],
            stdout="\n".join(stdout_lines + [completed.stdout if completed and completed.stdout else ""]).strip(),
            stderr=completed.stderr if completed else "",
            return_code=completed.returncode if completed else 0,
            backend_used="photoshop-droplet",
            model_used="photoshop-template",
            summary=(
                f"Photoshop 套图执行完成，已发送 {image_count} 张图片。"
                if completed is not None and completed.returncode == 0
                else f"Photoshop 套图已启动，已发送 {image_count} 张图片。"
            ),
            artifacts=artifacts,
        )
        if log_history:
            self._log_job(
                job_type="ps_batch",
                backend="photoshop-droplet",
                model="photoshop-template",
                input_ref=str(input_dir),
                output_ref=str(input_dir),
                result=result,
            )
        return result

    def run_upscale_batch(self, request: UpscaleRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        output_dir = Path(request.output_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"输入目录不存在：{input_dir}")
        self._ensure_distinct_output_dir(input_dir, output_dir)
        if request.scale not in {2, 4}:
            raise ExecutionError("当前转高清仅支持 2x 或 4x。")

        images = upscale_image_paths_from_dir(input_dir, request.recurse)
        if not images:
            raise ExecutionError(f"当前目录里没有可处理图片：{input_dir}")

        rows: list[dict[str, str]] = []
        stdout_lines: list[str] = []
        engine_label = "realesrgan-ncnn-vulkan" if external_upscale_available() else "internal-fallback"
        engines_used: list[str] = []
        for index, input_path in enumerate(images, start=1):
            relative = input_path.relative_to(input_dir)
            output_path = output_dir / relative
            if output_path.exists() and not request.overwrite:
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "model": f"upscale:{request.mode}",
                        "backend": engine_label,
                        "status": "skipped",
                        "reason": "existing output",
                    }
                )
                stdout_lines.append(f"[{index}/{len(images)}] skip {relative}")
                continue
            summary = upscale_image(input_path, output_path, scale=request.scale, mode=request.mode)
            engines_used.append(summary.engine)
            rows.append(
                {
                    "input": summary.input_path,
                    "output": summary.output_path,
                    "model": f"upscale:{request.mode}",
                    "backend": summary.engine,
                    "status": "ok",
                    "reason": f"{request.scale}x",
                }
            )
            stdout_lines.append(f"[{index}/{len(images)}] ok {relative} -> {request.scale}x ({summary.engine})")

        result = self._aggregate_result(
            job_type="upscale",
            rows=rows,
            stdout_lines=stdout_lines,
            backends_used=engines_used or [engine_label],
            models_used=[f"upscale:{request.mode}"],
        )
        result.output_path = str(output_dir)
        result.artifacts = self._collect_image_outputs(output_dir)
        result.summary = f"高清增强完成，成功 {sum(1 for row in rows if row['status'] == 'ok')} 张。"
        if log_history:
            self._log_job(
                job_type="upscale",
                backend=engine_label,
                model=f"upscale:{request.mode}",
                input_ref=str(input_dir),
                output_ref=str(output_dir),
                result=result,
            )
        return result

    def run_background_replace(self, request: BackgroundReplaceRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        output_dir = Path(request.output_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"输入目录不存在：{input_dir}")
        self._ensure_distinct_output_dir(input_dir, output_dir)
        if not request.subject_name.strip():
            raise ExecutionError("请填写主体商品说明。")
        if not request.background_prompt.strip():
            raise ExecutionError("请填写背景修改意愿。")
        if request.background_style not in BACKGROUND_STYLE_PRESETS:
            raise ExecutionError(f"未知背景风格预设：{request.background_style}")

        ai_settings = load_ai_settings()
        if not ai_settings.api_key.strip():
            raise ExecutionError("当前未配置 AI 图片接口。请先在 AI 生图页或 Agent 小组件里配置可用 API。")
        if not ai_settings.model.strip():
            raise ExecutionError("当前未配置 AI 图片模型。")

        images = background_image_paths_from_dir(input_dir, request.recurse)
        if not images:
            raise ExecutionError(f"当前目录里没有可处理图片：{input_dir}")

        self._ensure_model_available(request.matt_model)
        matt_backend = self.resolve_backend(request.matt_backend, request.matt_model)
        rows: list[dict[str, str]] = []
        stdout_lines: list[str] = []

        with tempfile.TemporaryDirectory(prefix="neonpilot-bg-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            cutout_dir = temp_dir / "cutouts"
            generated_dir = temp_dir / "backgrounds"
            for index, input_path in enumerate(images, start=1):
                relative = input_path.relative_to(input_dir)
                output_path = build_output_path(input_path, input_dir, output_dir, request.preserve_structure)
                if output_path.exists() and not request.overwrite:
                    rows.append(
                        {
                            "input": str(input_path),
                            "output": str(output_path),
                            "model": ai_settings.model,
                            "backend": f"{matt_backend}+openai-compatible",
                            "status": "skipped",
                            "reason": "existing output",
                        }
                    )
                    stdout_lines.append(f"[{index}/{len(images)}] skip {relative}")
                    continue

                cutout_path = cutout_dir / relative.with_suffix(".png")
                single_result = self.run_single(
                    SingleRunRequest(
                        input_path=str(input_path),
                        output_path=str(cutout_path),
                        model=request.matt_model,
                        backend=matt_backend,
                    ),
                    log_history=False,
                )
                if not single_result.ok:
                    rows.append(
                        {
                            "input": str(input_path),
                            "output": str(output_path),
                            "model": request.matt_model,
                            "backend": matt_backend,
                            "status": "fail",
                            "reason": (single_result.stderr or single_result.stdout).strip(),
                        }
                    )
                    stdout_lines.append(f"[{index}/{len(images)}] fail cutout {relative}")
                    continue

                with Image.open(input_path) as original_image:
                    size_label = choose_generation_size(*original_image.size)
                prompt = build_background_prompt(
                    request.subject_name,
                    request.background_prompt,
                    style=request.background_style,
                )
                generated_files: list[str] = []
                last_error = ""
                for _attempt in range(max(1, request.retry_count) + 1):
                    generation = AIImageRunRequest(
                        base_url=ai_settings.base_url,
                        api_key=ai_settings.api_key,
                        model=ai_settings.model,
                        prompt=prompt,
                        output_dir=str(generated_dir / relative.parent),
                        image_count=1,
                        size=size_label,
                        quality="high",
                        file_prefix=f"{relative.stem}_bg_",
                        timeout_sec=ai_settings.timeout_sec,
                    )
                    try:
                        generated_files, _logs = generate_images(generation)
                        break
                    except Exception as exc:
                        last_error = str(exc)
                if not generated_files:
                    rows.append(
                        {
                            "input": str(input_path),
                            "output": str(output_path),
                            "model": ai_settings.model,
                            "backend": "openai-compatible",
                            "status": "fail",
                            "reason": last_error or "AI 背景生成失败",
                        }
                    )
                    stdout_lines.append(f"[{index}/{len(images)}] fail background {relative}")
                    continue

                composite_subject_over_background(cutout_path, Path(generated_files[0]), output_path)
                rows.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "model": ai_settings.model,
                        "backend": f"{matt_backend}+openai-compatible",
                        "status": "ok",
                        "reason": f"{request.background_style}: {request.background_prompt.strip()}",
                    }
                )
                stdout_lines.append(f"[{index}/{len(images)}] ok {relative} -> 背景已替换")

        result = self._aggregate_result(
            job_type="background_replace",
            rows=rows,
            stdout_lines=stdout_lines,
            backends_used=[f"{matt_backend}+openai-compatible"],
            models_used=[ai_settings.model],
        )
        result.output_path = str(output_dir)
        result.artifacts = self._collect_image_outputs(output_dir)
        result.summary = f"背景替换完成，成功 {sum(1 for row in rows if row['status'] == 'ok')} 张。"
        if log_history:
            self._log_job(
                job_type="background_replace",
                backend=f"{matt_backend}+openai-compatible",
                model=ai_settings.model,
                input_ref=str(input_dir),
                output_ref=str(output_dir),
                result=result,
            )
        return result

