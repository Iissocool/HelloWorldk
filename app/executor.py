from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Iterable

from .ai_image import generate_images, test_ai_provider
from .catalog import MODEL_MAP
from .config import RUNTIME_ROOT, WORKSPACE_ROOT
from .hardware import detect_hardware_profile
from .history import HistoryStore
from .models import (
    AIImageRunRequest,
    AIImageTestRequest,
    BatchRunRequest,
    ExecutionResult,
    RenameRunRequest,
    SingleRunRequest,
    SmartRunRequest,
)
from .planner import build_runtime_plan
from .renamer import build_rename_plan, execute_rename_plan
from .selection import analyze_image, choose_category, choose_model


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


class LocalExecutor:
    def __init__(self, history_store: HistoryStore | None = None) -> None:
        self.history_store = history_store or HistoryStore()

    def available_backends(self) -> list[str]:
        ordered = ["auto", "directml", "amd", "openvino", "cuda", "tensorrt", "cpu"]
        return [
            backend
            for backend in ordered
            if backend == "auto" or self._runner_path(backend).exists()
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
        return runner

    def _profile(self):
        return detect_hardware_profile()

    def _can_attempt_backend(self, backend: str) -> bool:
        normalized = "directml" if backend == "amd" else backend
        if normalized == "cpu":
            return self._runner_path("cpu").exists()
        if normalized not in RUNNERS:
            return False
        if not self._runner_path(normalized).exists():
            return False
        capability_key = BACKEND_CAPABILITY_KEYS.get(backend)
        if capability_key is None:
            return True
        profile = self._profile()
        return bool(profile.capabilities.get(capability_key, False))

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

        raise ExecutionError("No usable backend runner is available on this machine.")

    def _run(self, command: list[str]) -> ExecutionResult:
        completed = subprocess.run(
            command,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
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
        report_path: Path,
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
            report_path=str(report_path),
            backend_used=backend_values[0] if len(backend_values) == 1 else ("mixed" if backend_values else None),
            model_used=model_values[0] if len(model_values) == 1 else ("multiple" if model_values else None),
            summary=summary,
        )

    def run_single(self, request: SingleRunRequest, *, log_history: bool = True) -> ExecutionResult:
        backend = self.resolve_backend(request.backend, request.model)
        command = self._build_single_command(backend, request)
        result = self._run(command)
        result.output_path = request.output_path
        result.backend_used = backend
        result.model_used = request.model
        result.summary = self._summarize_single(result)
        if log_history:
            self._log_job(
                job_type="single",
                backend=backend,
                model=request.model,
                input_ref=request.input_path,
                output_ref=request.output_path,
                result=result,
            )
        return result

    def run_batch(self, request: BatchRunRequest, *, log_history: bool = True) -> ExecutionResult:
        input_dir = Path(request.input_dir)
        output_dir = Path(request.output_dir)
        if not input_dir.is_dir():
            raise ExecutionError(f"Input directory does not exist: {input_dir}")

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

        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "_batch_report.csv"
        with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["input", "output", "model", "backend", "status", "reason"],
            )
            writer.writeheader()
            writer.writerows(rows)

        result = self._aggregate_result(
            job_type="batch",
            report_path=report_path,
            rows=rows,
            stdout_lines=stdout_lines + [f"Report: {report_path}"],
            backends_used=[backend],
            models_used=[request.model],
        )
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

        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "_smart_report.csv"
        with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["input", "output", "strategy", "category", "model", "backend", "status", "reason"],
            )
            writer.writeheader()
            writer.writerows(rows)

        result = self._aggregate_result(
            job_type="smart",
            report_path=report_path,
            rows=rows,
            stdout_lines=stdout_lines + [f"Report: {report_path}"],
            backends_used=backends_used,
            models_used=models_used,
        )
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

        report_path = input_dir / "_rename_report.csv"
        with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["input", "output", "model", "backend", "status", "reason"],
            )
            writer.writeheader()
            writer.writerows(rows)

        success_count = sum(1 for row in rows if row["status"] == "ok")
        fail_count = sum(1 for row in rows if row["status"] == "fail")
        skip_count = sum(1 for row in rows if row["status"] == "skipped")
        result = ExecutionResult(
            ok=fail_count == 0,
            command=["internal:rename"],
            stdout="\n".join(stdout_lines + [f"Report: {report_path}"]),
            stderr="",
            return_code=0 if fail_count == 0 else 1,
            report_path=str(report_path),
            backend_used="internal",
            model_used=f"rename:{request.mode}",
            summary=(
                f"rename processed {len(rows)} files: "
                f"{success_count} renamed, {fail_count} failed, {skip_count} skipped."
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

