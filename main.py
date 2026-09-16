from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services.facebook_service import run_facebook_report
from services.google_service import run_google_report
from services.report_writer import write_report

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "facilities.json"
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Nexion Social Reporting")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

JOBS: dict[str, dict] = {}


def load_facilities() -> list[dict]:
    with DATA_FILE.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    return [r for r in rows if r.get("active", True)]


def check_report_key(x_report_key: str | None) -> None:
    expected = os.getenv("REPORT_PASSWORD", "").strip()
    if expected and x_report_key != expected:
        raise HTTPException(status_code=401, detail="Invalid report password")


class ReportRequest(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    sources: list[Literal["facebook", "google"]]
    facility_id: int | None = None


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/facilities")
def facilities():
    rows = load_facilities()
    return {
        "count": len(rows),
        "facilities": [
            {"id": r["id"], "facility": r["facility"], "state": r["state"]}
            for r in rows
        ],
    }


@app.post("/api/reports")
def create_report(
    req: ReportRequest,
    x_report_key: str | None = Header(default=None),
):
    check_report_key(x_report_key)

    if not req.sources:
        raise HTTPException(
            status_code=400,
            detail="Choose at least one source"
        )

    facilities = load_facilities()

    # If one facility was chosen, only use that facility.
    if req.facility_id is not None:
        facilities = [
            facility
            for facility in facilities
            if facility["id"] == req.facility_id
        ]

        if not facilities:
            raise HTTPException(
                status_code=404,
                detail="Facility not found"
            )

    job_id = uuid.uuid4().hex[:12]

    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "stage": "Preparing",
        "message": "Loading saved facility list",
        "progress": 0,
        "current": 0,
        "total": len(facilities),
        "year": req.year,
        "month": req.month,
        "sources": req.sources,
        "files": {},
        "errors": [],
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    thread = threading.Thread(
        target=run_job,
        args=(
            job_id,
            req.year,
            req.month,
            req.sources,
            facilities,
        ),
        daemon=True,
    )

    thread.start()

    return {"job_id": job_id}


@app.get("/api/reports/{job_id}")
def report_status(job_id: str, x_report_key: str | None = Header(default=None)):
    check_report_key(x_report_key)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Report not found")
    return job


@app.get("/api/reports/{job_id}/download/{source}")
def download_report(
    job_id: str,
    source: Literal["facebook", "google"],
    x_report_key: str | None = Header(default=None),
):
    check_report_key(x_report_key)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Report not found")
    path = job.get("files", {}).get(source)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File not ready")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=Path(path).name,
    )


def update_job(job_id: str, **kwargs):
    if job_id in JOBS:
        JOBS[job_id].update(kwargs)


def run_job(
    job_id: str,
    year: int,
    month: int,
    sources: list[str],
    facilities: list[dict],
):
    total_steps = len(facilities) * len(sources)
    completed_steps = 0

    def progress(source: str, current: int, total: int, facility_name: str):
        nonlocal completed_steps
        completed_steps += 1
        pct = int((completed_steps / max(total_steps, 1)) * 90)
        update_job(
            job_id,
            status="running",
            stage=f"Running {source.title()}",
            message=facility_name,
            progress=pct,
            current=current,
            total=total,
        )

    try:
        update_job(job_id, status="running", progress=3, message="Loaded saved facility list")
        source_results: dict[str, list[dict]] = {}

        if "facebook" in sources:
            source_results["facebook"] = run_facebook_report(
                facilities, year, month,
                progress_callback=lambda c, t, n: progress("facebook", c, t, n),
            )

        if "google" in sources:
            source_results["google"] = run_google_report(
                facilities,
                progress_callback=lambda c, t, n: progress("google", c, t, n),
            )

        update_job(
            job_id,
            stage="Generating files",
            message="Formatting Excel exports",
            progress=94,
        )

        files = {}
        for source, rows in source_results.items():
            path = write_report(
                source=source,
                rows=rows,
                year=year,
                month=month,
                output_dir=GENERATED_DIR,
            )
            files[source] = str(path)

        update_job(
            job_id,
            status="complete",
            stage="Complete",
            message="Your report is ready",
            progress=100,
            current=len(facilities),
            total=len(facilities),
            files=files,
        )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            stage="Error",
            message=str(exc),
            errors=[str(exc)],
        )
