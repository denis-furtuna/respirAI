"""What the server does, without the web framework (tasks D5-D8).

server.py wraps these functions in FastAPI routes. Keeping the logic here
means it can be tested with plain Python, no web server needed.

Without a trained model in ai/weights/resp_cnn.onnx (+ resp_cnn.json, both
downloaded from the Kaggle notebook's output) it runs in dummy mode: same
request and response shapes, fixed answers. That lets the app be built
before the model exists.
"""
import io
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from icbhi import CLASSES, POINTS
from quality import quality

AI_DIR = Path(__file__).resolve().parent
WEIGHTS = Path(os.environ.get("RESPIRAI_WEIGHTS", AI_DIR / "weights" / "resp_cnn.onnx"))
DEMO_DIR = Path(os.environ.get("RESPIRAI_DEMO_DIR", AI_DIR / "demo_clips"))
UNUSABLE_BELOW = 0.4      # contract: below this the app asks for a re-record
MIN_S, MAX_S = 2.0, 60.0
DISCLAIMER = "Screening aid only. Not a diagnosis. Consult a doctor."

log = logging.getLogger("respirai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


class ServiceError(Exception):
    """A problem with the request; becomes HTTP `status` with {"error": message}."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


analyzer = None
if WEIGHTS.exists():
    from inference import Analyzer
    analyzer = Analyzer(WEIGHTS)
    MODEL_VERSION = analyzer.model_version
    log.info("Loaded model %s from %s", MODEL_VERSION, WEIGHTS)
else:
    MODEL_VERSION = "dummy-0.0"
    log.warning("No model at %s: running in DUMMY mode (fixed answers).", WEIGHTS)

demo_manifest = {}
if (DEMO_DIR / "manifest.json").exists():
    demo_manifest = json.loads((DEMO_DIR / "manifest.json").read_text())

sessions = {}  # session_id -> {point: result}; in memory, gone when the server restarts


def read_wav(data):
    """WAV bytes -> (mono samples, sample rate). Any rate or bit depth; the contract asks for 8 kHz 16-bit."""
    try:
        sr, x = wavfile.read(io.BytesIO(data))
    except Exception:
        raise ServiceError(400, "The audio file is not a readable WAV.")
    if x.dtype == np.int16:
        x = x.astype(np.float32) / 32768.0
    elif x.dtype == np.int32:
        x = x.astype(np.float32) / 2**31
    elif x.dtype == np.uint8:
        x = (x.astype(np.float32) - 128) / 128
    else:
        x = x.astype(np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    seconds = len(x) / sr
    if not MIN_S <= seconds <= MAX_S:
        raise ServiceError(400, f"Recording is {seconds:.1f} s; send between {MIN_S:.0f} and {MAX_S:.0f} s.")
    return x, sr


def _demo_clip(case, point):
    name = demo_manifest.get(f"{case}/{point}")
    if not name or not (DEMO_DIR / name).exists():
        raise ServiceError(404, f"No demo clip for {case} at {point}. Copy the notebook's demo_clips/ into ai/.")
    sr, x = wavfile.read(DEMO_DIR / name)
    return x, sr


def health():
    return {"status": "ok", "model_version": MODEL_VERSION, "dummy": analyzer is None,
            "demo_clips": len(demo_manifest)}


def analyze(point, session_id, audio_bytes=None, demo=False, demo_case=None):
    """POST /analyze. Returns the response dict from contract 2."""
    t0 = time.perf_counter()
    if point not in POINTS:
        raise ServiceError(400, f"Unknown point '{point}'. Use one of {', '.join(POINTS)}.")
    if not session_id:
        raise ServiceError(400, "session_id is required.")

    if demo:
        if demo_case not in CLASSES:
            raise ServiceError(400, f"Demo mode needs demo_case, one of {', '.join(CLASSES)}.")
        if analyzer is None:
            q, result = 0.95, {"finding": demo_case, "confidence": 0.9}
        else:
            x, sr = _demo_clip(demo_case, point)
            q, _ = quality(x, sr)
            result = analyzer.analyze(x, sr)
    else:
        if not audio_bytes:
            raise ServiceError(400, "Send the recording in the 'audio' field, or set demo=true.")
        x, sr = read_wav(audio_bytes)
        q, checks = quality(x, sr)
        log.info("point=%s quality=%.2f %s", point, q, checks)
        if q < UNUSABLE_BELOW:
            result = {"finding": "unusable", "confidence": 0.0}
        elif analyzer is None:
            result = {"finding": "normal", "confidence": 0.5}
        else:
            result = analyzer.analyze(x, sr)

    response = {
        "point": point,
        "finding": result["finding"],
        "confidence": result["confidence"],
        "quality": q,
        "model_version": MODEL_VERSION,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }
    if demo:
        response["demo"] = True
    sessions.setdefault(session_id, {})[point] = response
    return response


def summary(session_id):
    """GET /session/{session_id}/summary."""
    points = sessions.get(session_id)
    if not points:
        raise ServiceError(404, f"No recordings for session '{session_id}'.")
    usable = [r for r in points.values() if r["finding"] != "unusable"]
    if not usable:
        overall, confidence = "unusable", 0.0
    else:
        crackles = any(r["finding"] in ("crackles", "both") for r in usable)
        wheezes = any(r["finding"] in ("wheezes", "both") for r in usable)
        overall = CLASSES[int(crackles) + 2 * int(wheezes)]
        # How sure we are of the overall result: the points that support it.
        support = [r["confidence"] for r in usable
                   if r["finding"] == overall or (overall == "both" and r["finding"] != "normal")]
        confidence = round(float(np.mean(support)), 2)
    return {
        "session_id": session_id,
        "points_recorded": len(points),
        "overall": overall,
        "confidence": confidence,
        "per_point": [{"point": p, "finding": r["finding"], "confidence": r["confidence"]}
                      for p, r in sorted(points.items(), key=lambda kv: POINTS.index(kv[0]))],
        "disclaimer": DISCLAIMER,
    }
