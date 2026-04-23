from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict

from .executor import ExecutionError, LocalExecutor
from .hardware import detect_hardware_profile
from .hermes_adapter import (
    HermesModelSettings,
    HermesProviderSettings,
    auxiliary_provider_status,
    export_hermes_skill,
    inspect_hermes_environment,
    load_hermes_model_settings,
    load_hermes_provider_settings,
    read_hermes_logs,
    run_hermes_command,
    save_auxiliary_provider_key,
    save_hermes_model_settings,
    save_hermes_provider_settings,
    start_docker_desktop,
    start_hermes_service,
    stop_hermes_service,
)
from .models import (
    AIImageRunRequest,
    AIImageTestRequest,
    BackgroundReplaceRunRequest,
    BatchRunRequest,
    PhotoshopBatchRequest,
    RenameRunRequest,
    SingleRunRequest,
    SmartRunRequest,
    UpscaleRunRequest,
)
from .planner import build_runtime_plan
from .config import PROJECT_ROOT
from .runtime_manager import (
    build_model_manage_command,
    build_runtime_manage_command,
    model_statuses,
    runtime_component_statuses,
)


executor = LocalExecutor()


def _print_json(payload: dict, ok: bool = True) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neonpilot", description="NeonPilot app command bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Return app health")
    sub.add_parser("hardware", help="Return detected hardware profile")
    sub.add_parser("plan", help="Return runtime plan")
    sub.add_parser("runtime-status", help="Return optional runtime component status")
    sub.add_parser("model-status", help="Return local model asset status")
    runtime_install = sub.add_parser("runtime-install", help="Install runtime components")
    runtime_install.add_argument("--components", nargs="+", required=True)
    runtime_uninstall = sub.add_parser("runtime-uninstall", help="Uninstall runtime components")
    runtime_uninstall.add_argument("--components", nargs="+", required=True)
    model_install = sub.add_parser("model-install", help="Download one model on demand")
    model_install.add_argument("--model", required=True)
    model_install.add_argument("--backend", default="cpu")
    model_uninstall = sub.add_parser("model-uninstall", help="Remove one model from local storage")
    model_uninstall.add_argument("--model", required=True)
    sub.add_parser("hermes-status", help="Return Docker Hermes status")
    sub.add_parser("hermes-start-docker", help="Start Docker Desktop in the background")
    sub.add_parser("hermes-start", help="Start the Docker Hermes service container")
    sub.add_parser("hermes-stop", help="Stop the Docker Hermes service container")
    hermes_logs = sub.add_parser("hermes-logs", help="Read Docker Hermes logs")
    hermes_logs.add_argument("--tail", type=int, default=200)
    hermes_exec = sub.add_parser("hermes-exec", help="Run a Hermes command inside Docker")
    hermes_exec.add_argument("--text", required=True)
    sub.add_parser("hermes-export-skill", help="Export the NeonPilot Hermes skill into the Hermes data directory")
    sub.add_parser("hermes-config-show", help="Show current Hermes model/provider configuration")
    hermes_config_set = sub.add_parser("hermes-config-set", help="Update Hermes model/provider configuration")
    hermes_config_set.add_argument("--model", default="")
    hermes_config_set.add_argument("--provider", default="")
    hermes_config_set.add_argument("--base-url", default="")
    hermes_config_set.add_argument("--api-key", default="")
    hermes_config_set.add_argument("--provider-base-url", default="")
    aux_set = sub.add_parser("hermes-aux-set", help="Update auxiliary compression provider key")
    aux_set.add_argument("--api-key", default="")

    single = sub.add_parser("single", help="Run one image matting job")
    single.add_argument("--input", required=True)
    single.add_argument("--output", required=True)
    single.add_argument("--model", default="bria-rmbg")
    single.add_argument("--backend", default="auto")

    batch = sub.add_parser("batch", help="Run fixed-model batch processing")
    batch.add_argument("--input-dir", required=True)
    batch.add_argument("--output-dir", required=True)
    batch.add_argument("--model", default="bria-rmbg")
    batch.add_argument("--backend", default="auto")
    batch.add_argument("--overwrite", action="store_true")
    batch.add_argument("--recurse", action="store_true")
    batch.add_argument("--include-generated", action="store_true")

    smart = sub.add_parser("smart", help="Run smart batch processing")
    smart.add_argument("--input-dir", required=True)
    smart.add_argument("--output-dir", required=True)
    smart.add_argument("--strategy", default="quality", choices=["quality", "balanced", "speed"])
    smart.add_argument("--backend", default="auto")
    smart.add_argument("--overwrite", action="store_true")
    smart.add_argument("--recurse", action="store_true")
    smart.add_argument("--include-generated", action="store_true")

    rename = sub.add_parser("rename", help="Run batch rename")
    rename.add_argument("--input-dir", required=True)
    rename.add_argument("--mode", default="template", choices=["template", "replace", "fresh"])
    rename.add_argument("--template", default="{index:03d}_{name}")
    rename.add_argument("--fresh-name", default="image_")
    rename.add_argument("--find-text", default="")
    rename.add_argument("--replace-text", default="")
    rename.add_argument("--prefix", default="")
    rename.add_argument("--suffix", default="")
    rename.add_argument("--start-index", type=int, default=1)
    rename.add_argument("--step", type=int, default=1)
    rename.add_argument("--padding-width", type=int, default=3)
    rename.add_argument("--extensions", default="")
    rename.add_argument("--recurse", action="store_true")
    rename.add_argument("--case-sensitive", action="store_true")
    rename.add_argument("--no-keep-extension", action="store_true")

    ai_test = sub.add_parser("ai-test", help="Test an OpenAI-compatible image endpoint")
    ai_test.add_argument("--base-url", required=True)
    ai_test.add_argument("--api-key", required=True)
    ai_test.add_argument("--timeout", type=int, default=30)

    ai_gen = sub.add_parser("ai-generate", help="Generate images through an OpenAI-compatible endpoint")
    ai_gen.add_argument("--base-url", required=True)
    ai_gen.add_argument("--api-key", required=True)
    ai_gen.add_argument("--model", required=True)
    ai_gen.add_argument("--prompt", required=True)
    ai_gen.add_argument("--output-dir", required=True)
    ai_gen.add_argument("--count", type=int, default=1)
    ai_gen.add_argument("--size", default="1024x1024")
    ai_gen.add_argument("--quality", default="auto")
    ai_gen.add_argument("--prefix", default="image_")
    ai_gen.add_argument("--timeout", type=int, default=180)

    upscale = sub.add_parser("upscale-batch", help="Run local batch upscale workflow")
    upscale.add_argument("--input-dir", required=True)
    upscale.add_argument("--output-dir", required=True)
    upscale.add_argument("--scale", type=int, default=2, choices=[2, 4])
    upscale.add_argument("--mode", default="quality", choices=["quality", "balanced", "speed"])
    upscale.add_argument("--recurse", action="store_true")
    upscale.add_argument("--overwrite", action="store_true")

    background_refresh = sub.add_parser("background-refresh", help="Replace backgrounds while keeping the product subject")
    background_refresh.add_argument("--input-dir", required=True)
    background_refresh.add_argument("--output-dir", required=True)
    background_refresh.add_argument("--subject", required=True)
    background_refresh.add_argument("--background", required=True)
    background_refresh.add_argument("--style", default="custom")
    background_refresh.add_argument("--recurse", action="store_true")
    background_refresh.add_argument("--overwrite", action="store_true")
    background_refresh.add_argument("--flatten", action="store_true")
    background_refresh.add_argument("--matt-model", default="bria-rmbg")
    background_refresh.add_argument("--matt-backend", default="auto")
    background_refresh.add_argument("--retry", type=int, default=1)

    ps_batch = sub.add_parser("ps-batch", help="Run Photoshop PSD + Droplet batch workflow")
    ps_batch.add_argument("--template", required=True)
    ps_batch.add_argument("--droplet", required=True)
    ps_batch.add_argument("--input-dir", required=True)
    ps_batch.add_argument("--output-dir", default="")
    ps_batch.add_argument("--photoshop", default="")
    ps_batch.add_argument("--template-wait", type=int, default=8)
    ps_batch.add_argument("--timeout", type=int, default=1800)
    ps_batch.add_argument("--collect-wait", type=int, default=15)
    ps_batch.add_argument("--close-photoshop", action="store_true")
    return parser


def execute_namespace(args: argparse.Namespace) -> tuple[bool, dict]:
    try:
        if args.command == "health":
            return True, {"ok": True, "available_backends": executor.available_backends()}
        if args.command == "hardware":
            return True, detect_hardware_profile().model_dump()
        if args.command == "plan":
            return True, build_runtime_plan().model_dump()
        if args.command == "runtime-status":
            return True, {"components": [asdict(item) for item in runtime_component_statuses()]}
        if args.command == "model-status":
            return True, {"models": [asdict(item) for item in model_statuses()]}
        if args.command == "runtime-install":
            completed = subprocess.run(build_runtime_manage_command("install", args.components), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            return completed.returncode == 0, {"ok": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}
        if args.command == "runtime-uninstall":
            completed = subprocess.run(build_runtime_manage_command("uninstall", args.components), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            return completed.returncode == 0, {"ok": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}
        if args.command == "model-install":
            completed = subprocess.run(build_model_manage_command("install", args.model, backend=args.backend), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            return completed.returncode == 0, {"ok": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}
        if args.command == "model-uninstall":
            completed = subprocess.run(build_model_manage_command("uninstall", args.model), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            return completed.returncode == 0, {"ok": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}
        if args.command == "hermes-status":
            return True, asdict(inspect_hermes_environment())
        if args.command == "hermes-start-docker":
            ok, message = start_docker_desktop()
            return ok, {"ok": ok, "message": message}
        if args.command == "hermes-start":
            ok, stdout, stderr = start_hermes_service()
            return ok, {"ok": ok, "stdout": stdout, "stderr": stderr}
        if args.command == "hermes-stop":
            ok, stdout, stderr = stop_hermes_service()
            return ok, {"ok": ok, "stdout": stdout, "stderr": stderr}
        if args.command == "hermes-logs":
            ok, stdout, stderr = read_hermes_logs(args.tail)
            return ok, {"ok": ok, "stdout": stdout, "stderr": stderr}
        if args.command == "hermes-exec":
            ok, stdout, stderr = run_hermes_command(args.text)
            return ok, {"ok": ok, "stdout": stdout, "stderr": stderr}
        if args.command == "hermes-export-skill":
            skill_path = export_hermes_skill(PROJECT_ROOT, PROJECT_ROOT / "scripts" / "run_neonpilot_cli.ps1")
            return True, {"ok": True, "skill_path": str(skill_path)}
        if args.command == "hermes-config-show":
            model_settings = load_hermes_model_settings()
            provider_settings = load_hermes_provider_settings(model_settings.provider, model_settings.base_url)
            aux_ok, aux_message = auxiliary_provider_status()
            return True, {
                "ok": True,
                "model": {
                    "default": model_settings.default_model,
                    "provider": model_settings.provider,
                    "base_url": model_settings.base_url,
                },
                "provider": {
                    "api_env": provider_settings.api_env_key,
                    "api_key_configured": bool(provider_settings.api_key.strip()),
                    "base_env": provider_settings.base_url_env_key,
                    "provider_base_url": provider_settings.base_url,
                },
                "auxiliary": {"ok": aux_ok, "message": aux_message},
            }
        if args.command == "hermes-config-set":
            current_model = load_hermes_model_settings()
            provider_value = args.provider.strip() or current_model.provider or "auto"
            base_url_value = args.base_url if args.base_url != "" else current_model.base_url
            model_value = args.model.strip() or current_model.default_model
            model_path = save_hermes_model_settings(
                HermesModelSettings(
                    default_model=model_value,
                    provider=provider_value,
                    base_url=base_url_value.strip(),
                )
            )
            resolved_provider = load_hermes_provider_settings(provider_value, base_url_value)
            provider_path = None
            if any(
                value != ""
                for value in [args.api_key, args.provider_base_url]
            ):
                provider_path = save_hermes_provider_settings(
                    HermesProviderSettings(
                        provider=provider_value,
                        api_key=args.api_key.strip() if args.api_key != "" else resolved_provider.api_key,
                        api_env_key=resolved_provider.api_env_key,
                        base_url=args.provider_base_url.strip() if args.provider_base_url != "" else resolved_provider.base_url,
                        base_url_env_key=resolved_provider.base_url_env_key,
                    )
                )
            return True, {
                "ok": True,
                "config_path": str(model_path),
                "env_path": str(provider_path) if provider_path else None,
                "model": model_value,
                "provider": provider_value,
                "base_url": base_url_value.strip(),
                "api_env": resolved_provider.api_env_key or "",
                "base_env": resolved_provider.base_url_env_key or "",
            }
        if args.command == "hermes-aux-set":
            env_path = save_auxiliary_provider_key(args.api_key)
            ok, message = auxiliary_provider_status()
            return ok, {"ok": ok, "env_path": str(env_path), "message": message}
        if args.command == "single":
            result = executor.run_single(SingleRunRequest(input_path=args.input, output_path=args.output, model=args.model, backend=args.backend), log_history=False)
            return result.ok, result.model_dump()
        if args.command == "batch":
            result = executor.run_batch(BatchRunRequest(input_dir=args.input_dir, output_dir=args.output_dir, model=args.model, backend=args.backend, overwrite=args.overwrite, recurse=args.recurse, include_generated=args.include_generated), log_history=False)
            return result.ok, result.model_dump()
        if args.command == "smart":
            result = executor.run_smart(SmartRunRequest(input_dir=args.input_dir, output_dir=args.output_dir, strategy=args.strategy, backend=args.backend, overwrite=args.overwrite, recurse=args.recurse, include_generated=args.include_generated), log_history=False)
            return result.ok, result.model_dump()
        if args.command == "rename":
            result = executor.run_rename(RenameRunRequest(input_dir=args.input_dir, mode=args.mode, template=args.template, fresh_name=args.fresh_name, find_text=args.find_text, replace_text=args.replace_text, prefix=args.prefix, suffix=args.suffix, start_index=args.start_index, step=args.step, padding_width=args.padding_width, recurse=args.recurse, extensions=args.extensions, case_sensitive=args.case_sensitive, keep_extension=not args.no_keep_extension), log_history=False)
            return result.ok, result.model_dump()
        if args.command == "ai-test":
            result = executor.run_ai_test(AIImageTestRequest(base_url=args.base_url, api_key=args.api_key, timeout_sec=args.timeout), log_history=False)
            return result.ok, result.model_dump()
        if args.command == "ai-generate":
            result = executor.run_ai_image(AIImageRunRequest(base_url=args.base_url, api_key=args.api_key, model=args.model, prompt=args.prompt, output_dir=args.output_dir, image_count=args.count, size=args.size, quality=args.quality, file_prefix=args.prefix, timeout_sec=args.timeout), log_history=False)
            return result.ok, result.model_dump()
        if args.command == "upscale-batch":
            result = executor.run_upscale_batch(
                UpscaleRunRequest(
                    input_dir=args.input_dir,
                    output_dir=args.output_dir,
                    scale=args.scale,
                    mode=args.mode,
                    recurse=args.recurse,
                    overwrite=args.overwrite,
                ),
                log_history=False,
            )
            return result.ok, result.model_dump()
        if args.command == "background-refresh":
            result = executor.run_background_replace(
                BackgroundReplaceRunRequest(
                    input_dir=args.input_dir,
                    output_dir=args.output_dir,
                    subject_name=args.subject,
                    background_prompt=args.background,
                    background_style=args.style,
                    recurse=args.recurse,
                    overwrite=args.overwrite,
                    preserve_structure=not args.flatten,
                    matt_model=args.matt_model,
                    matt_backend=args.matt_backend,
                    retry_count=args.retry,
                ),
                log_history=False,
            )
            return result.ok, result.model_dump()
        if args.command == "ps-batch":
            result = executor.run_photoshop_batch(
                PhotoshopBatchRequest(
                    template_path=args.template,
                    droplet_path=args.droplet,
                    input_dir=args.input_dir,
                    output_dir=args.output_dir,
                    photoshop_path=args.photoshop,
                    template_wait_sec=args.template_wait,
                    timeout_sec=args.timeout,
                    collect_wait_sec=args.collect_wait,
                    close_photoshop_when_done=args.close_photoshop,
                ),
                log_history=False,
            )
            return result.ok, result.model_dump()
    except ExecutionError as exc:
        return False, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return False, {"ok": False, "error": str(exc)}
    return False, {"ok": False, "error": "unsupported command"}


def execute_command(argv: list[str]) -> tuple[bool, dict]:
    parser = build_parser()
    args = parser.parse_args(argv)
    return execute_namespace(args)


def main(argv: list[str] | None = None) -> int:
    try:
        ok, payload = execute_command(argv if argv is not None else sys.argv[1:])
        return _print_json(payload, ok=ok)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())
