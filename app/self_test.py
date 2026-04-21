from __future__ import annotations

import argparse
from pathlib import Path

from app.executor import LocalExecutor
from app.hardware import detect_hardware_profile
from app.models import SingleRunRequest
from app.planner import build_runtime_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a quick self-test for the background desktop app")
    parser.add_argument("--input", help="Optional image path for a real inference smoke test")
    parser.add_argument("--output", help="Optional output path for a real inference smoke test")
    parser.add_argument("--model", default="u2netp")
    parser.add_argument("--backend", default="auto")
    args = parser.parse_args()

    profile = detect_hardware_profile()
    plan = build_runtime_plan()
    executor = LocalExecutor()

    print("Hardware profile:")
    print(profile.model_dump())
    print()
    print("Runtime plan:")
    print(plan.model_dump())
    print()
    print("Available backends:")
    print(executor.available_backends())

    if args.input and args.output:
        result = executor.run_single(
            SingleRunRequest(
                input_path=str(Path(args.input)),
                output_path=str(Path(args.output)),
                model=args.model,
                backend=args.backend,
            )
        )
        print()
        print("Smoke test:")
        print(result.model_dump())
        return 0 if result.ok else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
