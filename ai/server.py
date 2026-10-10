"""respirAI inference server: contract 2 in docs/ARCHITECTURE.md, as HTTP routes.

Run from the ai/ folder:
    uvicorn server:app --host 0.0.0.0 --port 8000

All the logic lives in service.py; this file only turns it into HTTP.
"""
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import service

app = FastAPI(title="respirAI inference", version=service.MODEL_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(service.ServiceError)
async def _service_error(request: Request, exc: service.ServiceError):
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    fields = [str(e["loc"][-1]) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": f"Invalid or missing fields: {', '.join(fields)}"})


@app.get("/health")
def health():
    return service.health()


@app.post("/analyze")
async def analyze(
    point: str = Form(...),
    session_id: str = Form(...),
    audio: Optional[UploadFile] = File(None),
    demo: bool = Form(False),
    demo_case: Optional[str] = Form(None),
):
    audio_bytes = await audio.read() if audio is not None else None
    return service.analyze(point, session_id, audio_bytes, demo, demo_case)


@app.get("/session/{session_id}/summary")
def summary(session_id: str):
    return service.summary(session_id)
