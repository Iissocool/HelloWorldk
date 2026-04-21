from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .catalog import MODEL_CATALOG
from .executor import ExecutionError, LocalExecutor
from .models import BatchRunRequest, SingleRunRequest, SmartRunRequest
from .planner import build_runtime_plan
from .hardware import detect_hardware_profile


BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Background Desktop App Console", version="0.2.1")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
executor = LocalExecutor()


def render_index(request: Request, **overrides) -> HTMLResponse:
    context = {
        "hardware": detect_hardware_profile(),
        "plan": build_runtime_plan(),
        "models": MODEL_CATALOG,
        "backends": executor.available_backends(),
        "history": executor.history_store.list_recent(40),
        "single_result": None,
        "batch_result": None,
        "smart_result": None,
        "error": None,
    }
    context.update(overrides)
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/hardware")
def hardware() -> dict:
    return detect_hardware_profile().model_dump()


@app.get("/api/runtime-plan")
def runtime_plan() -> dict:
    return build_runtime_plan().model_dump()


@app.get("/api/models")
def models() -> list[dict]:
    return [model.__dict__ for model in MODEL_CATALOG]


@app.get("/api/history")
def history(limit: int = 100) -> list[dict]:
    return [record.__dict__ for record in executor.history_store.list_recent(limit)]


@app.get("/api/history/{job_id}")
def history_detail(job_id: int) -> JSONResponse:
    record = executor.history_store.get(job_id)
    if record is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(record.__dict__)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return render_index(request)


@app.post("/run/single", response_class=HTMLResponse)
def run_single(
    request: Request,
    input_path: str = Form(...),
    output_path: str = Form(...),
    model: str = Form("bria-rmbg"),
    backend: str = Form("auto"),
) -> HTMLResponse:
    try:
        single_result = executor.run_single(
            SingleRunRequest(
                input_path=input_path,
                output_path=output_path,
                model=model,
                backend=backend,
            )
        )
        return render_index(request, single_result=single_result)
    except ExecutionError as exc:
        return render_index(request, error=str(exc))


@app.post("/run/batch", response_class=HTMLResponse)
def run_batch(
    request: Request,
    input_dir: str = Form(...),
    output_dir: str = Form(...),
    model: str = Form("bria-rmbg"),
    backend: str = Form("auto"),
    recurse: bool = Form(False),
    overwrite: bool = Form(False),
    include_generated: bool = Form(False),
) -> HTMLResponse:
    try:
        batch_result = executor.run_batch(
            BatchRunRequest(
                input_dir=input_dir,
                output_dir=output_dir,
                model=model,
                backend=backend,
                recurse=recurse,
                overwrite=overwrite,
                include_generated=include_generated,
            )
        )
        return render_index(request, batch_result=batch_result)
    except ExecutionError as exc:
        return render_index(request, error=str(exc))


@app.post("/run/smart", response_class=HTMLResponse)
def run_smart(
    request: Request,
    input_dir: str = Form(...),
    output_dir: str = Form(...),
    strategy: str = Form("quality"),
    backend: str = Form("auto"),
    recurse: bool = Form(False),
    overwrite: bool = Form(False),
    include_generated: bool = Form(False),
) -> HTMLResponse:
    try:
        smart_result = executor.run_smart(
            SmartRunRequest(
                input_dir=input_dir,
                output_dir=output_dir,
                strategy=strategy,
                backend=backend,
                recurse=recurse,
                overwrite=overwrite,
                include_generated=include_generated,
            )
        )
        return render_index(request, smart_result=smart_result)
    except ExecutionError as exc:
        return render_index(request, error=str(exc))


@app.get("/refresh")
def refresh() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=303)

