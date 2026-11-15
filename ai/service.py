"""What the server does, without the web framework (tasks D5-D8).

server.py wraps these functions in FastAPI routes. Keeping the logic here
means it can be tested with plain Python, no web server needed.

Which model answers, in this order:
1. RESPIRAI_WEIGHTS set: that ONNX ResNet (resp_cnn.onnx + .json). The CI golden tests use this.
2. The PANNs CNN14 checkpoint + the patient RandomForest in ai/weights/ (inference_panns.py, needs
   PyTorch and scikit-learn): normal / abnormal per point, and "Normal" / "Go see a doctor" for the session.
3. ai/weights/resp_cnn.onnx (the Kaggle notebook's output).
4. None: dummy mode, same request and response shapes, fixed answers.
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
from quality import SILENCE_DBFS, SILENCE_DBFS_CALIBRATED, quality

AI_DIR = Path(__file__).resolve().parent
WEIGHTS = Path(os.environ.get("RESPIRAI_WEIGHTS", AI_DIR / "weights" / "resp_cnn.onnx"))
PANNS_WEIGHTS = Path(os.environ.get(
    "RESPIRAI_PANNS", AI_DIR / "weights" / "best_panns_finetuned_mel_hop10ms_bp50_1800_spike6ms_fade20ms_top2blocks.pt"))
PATIENT_WEIGHTS = Path(os.environ.get("RESPIRAI_PATIENT", AI_DIR / "weights" / "patient_doctor_rf_model.pkl"))
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
BACKEND = "dummy"
if "RESPIRAI_WEIGHTS" not in os.environ and PANNS_WEIGHTS.exists() and PATIENT_WEIGHTS.exists():
    from inference_panns import PannsAnalyzer
    analyzer = PannsAnalyzer(PANNS_WEIGHTS, PATIENT_WEIGHTS)
    BACKEND = "panns"
    MODEL_VERSION = analyzer.model_version
    log.info("Loaded model %s from %s, patient model from %s", MODEL_VERSION, PANNS_WEIGHTS, PATIENT_WEIGHTS)
elif WEIGHTS.exists():
    from inference import Analyzer
    analyzer = Analyzer(WEIGHTS)
    BACKEND = "onnx"
    MODEL_VERSION = analyzer.model_version
    log.info("Loaded model %s from %s", MODEL_VERSION, WEIGHTS)
else:
    MODEL_VERSION = "dummy-0.0"
    log.warning("No model at %s or %s: running in DUMMY mode (fixed answers).", PANNS_WEIGHTS, WEIGHTS)
SILENCE = SILENCE_DBFS_CALIBRATED if BACKEND == "panns" else SILENCE_DBFS

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
    out = {"status": "ok", "model_version": MODEL_VERSION, "dummy": analyzer is None,
           "demo_clips": len(demo_manifest)}
    if BACKEND == "panns":   # only then: the golden tests compare /health with the app's own answer exactly
        out["backend"] = BACKEND
    return out


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
            q, _ = quality(x, sr, SILENCE)
            result = analyzer.analyze(x, sr)
    else:
        if not audio_bytes:
            raise ServiceError(400, "Send the recording in the 'audio' field, or set demo=true.")
        x, sr = read_wav(audio_bytes)
        q, checks = quality(x, sr, SILENCE)
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
    if result.get("prob_abnormal") is not None:   # PANNs: the patient model needs it for the summary
        response["prob_abnormal"] = result["prob_abnormal"]
    if demo:
        response["demo"] = True
    sessions.setdefault(session_id, {})[point] = response
    return response


def _patient_verdict(points):
    """PANNs: the RandomForest's verdict over the points that have a score, or None if there are none."""
    position_sounds = {p: [r["prob_abnormal"]] for p, r in points.items()
                       if r["finding"] != "unusable" and r.get("prob_abnormal") is not None}
    if not position_sounds:
        return None
    v = analyzer.summarize_patient(position_sounds)
    return {k: v[k] for k in ("verdict", "percentage", "display", "risk_probability")}


def summary(session_id):
    """GET /session/{session_id}/summary."""
    points = sessions.get(session_id)
    if not points:
        raise ServiceError(404, f"No recordings for session '{session_id}'.")
    usable = [r for r in points.values() if r["finding"] != "unusable"]
    patient = _patient_verdict(points) if BACKEND == "panns" else None
    if not usable:
        overall, confidence = "unusable", 0.0
    elif patient is not None:
        overall = "abnormal" if patient["verdict"] == "Go see a doctor" else "normal"
        confidence = round(patient["percentage"] / 100.0, 3)
    elif any(r["finding"] == "abnormal" for r in usable):   # PANNs, demo answers without a score
        overall = "abnormal"
        confidence = round(float(np.mean([r["confidence"] for r in usable if r["finding"] == "abnormal"])), 2)
    else:
        crackles = any(r["finding"] in ("crackles", "both") for r in usable)
        wheezes = any(r["finding"] in ("wheezes", "both") for r in usable)
        overall = CLASSES[int(crackles) + 2 * int(wheezes)]
        # How sure we are of the overall result: the points that support it.
        support = [r["confidence"] for r in usable
                   if r["finding"] == overall or (overall == "both" and r["finding"] != "normal")]
        confidence = round(float(np.mean(support)), 2)
    out = {
        "session_id": session_id,
        "points_recorded": len(points),
        "overall": overall,
        "confidence": confidence,
        "per_point": [{"point": p, "finding": r["finding"], "confidence": r["confidence"],
                       **({"prob_abnormal": r["prob_abnormal"]} if "prob_abnormal" in r else {})}
                      for p, r in sorted(points.items(), key=lambda kv: POINTS.index(kv[0]))],
        "disclaimer": DISCLAIMER,
    }
    if patient is not None:
        out.update(patient)
    return out
