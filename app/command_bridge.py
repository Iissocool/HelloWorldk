from __future__ import annotations

import argparse
import json
import sys

from .executor import ExecutionError, LocalExecutor
from .hardware import detect_hardware_profile
from .models import AIImageRunRequest, AIImageTestRequest, BatchRunRequest, RenameRunRequest, SingleRunRequest, SmartRunRequest
from .planner import build_runtime_plan


executor = LocalExecutor()


def _print_json(payload: dict, ok: bool = True) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    sys.stdout.write(text + "\n")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neonpilot", description="NeonPilot app command bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Return app health")
    sub.add_parser("hardware", help="Return detected hardware profile")
    sub.add_parser("plan", help="Return runtime plan")

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "health":
            return _print_json({"ok": True, "available_backends": executor.available_backends()})
        if args.command == "hardware":
            return _print_json(detect_hardware_profile().model_dump())
        if args.command == "plan":
            return _print_json(build_runtime_plan().model_dump())
        if args.command == "single":
            result = executor.run_single(SingleRunRequest(input_path=args.input, output_path=args.output, model=args.model, backend=args.backend), log_history=False)
            return _print_json(result.model_dump(), ok=result.ok)
        if args.command == "batch":
            result = executor.run_batch(BatchRunRequest(input_dir=args.input_dir, output_dir=args.output_dir, model=args.model, backend=args.backend, overwrite=args.overwrite, recurse=args.recurse, include_generated=args.include_generated), log_history=False)
            return _print_json(result.model_dump(), ok=result.ok)
        if args.command == "smart":
            result = executor.run_smart(SmartRunRequest(input_dir=args.input_dir, output_dir=args.output_dir, strategy=args.strategy, backend=args.backend, overwrite=args.overwrite, recurse=args.recurse, include_generated=args.include_generated), log_history=False)
            return _print_json(result.model_dump(), ok=result.ok)
        if args.command == "rename":
            result = executor.run_rename(RenameRunRequest(input_dir=args.input_dir, mode=args.mode, template=args.template, fresh_name=args.fresh_name, find_text=args.find_text, replace_text=args.replace_text, prefix=args.prefix, suffix=args.suffix, start_index=args.start_index, step=args.step, padding_width=args.padding_width, recurse=args.recurse, extensions=args.extensions, case_sensitive=args.case_sensitive, keep_extension=not args.no_keep_extension), log_history=False)
            return _print_json(result.model_dump(), ok=result.ok)
        if args.command == "ai-test":
            result = executor.run_ai_test(AIImageTestRequest(base_url=args.base_url, api_key=args.api_key, timeout_sec=args.timeout), log_history=False)
            return _print_json(result.model_dump(), ok=result.ok)
        if args.command == "ai-generate":
            result = executor.run_ai_image(AIImageRunRequest(base_url=args.base_url, api_key=args.api_key, model=args.model, prompt=args.prompt, output_dir=args.output_dir, image_count=args.count, size=args.size, quality=args.quality, file_prefix=args.prefix, timeout_sec=args.timeout), log_history=False)
            return _print_json(result.model_dump(), ok=result.ok)
    except ExecutionError as exc:
        return _print_json({"ok": False, "error": str(exc)}, ok=False)
    except Exception as exc:
        return _print_json({"ok": False, "error": str(exc)}, ok=False)
    return _print_json({"ok": False, "error": "unsupported command"}, ok=False)


if __name__ == "__main__":
    raise SystemExit(main())
