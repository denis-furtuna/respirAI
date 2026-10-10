"""Whole recording -> one finding. Used by the server and by the notebook's final checks.

Runs the exported ONNX model with ONNX Runtime, so serving needs no PyTorch.

The model scores each 4 s window. A recording has crackles if its most
crackly windows do, and the same for wheezes, so one short abnormal stretch
is not averaged away by a long normal one.
"""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

import preprocess as pp
from icbhi import CLASSES

TOP_K = 2  # how many of the most abnormal windows decide the recording


def combine(window_probs, top_k=TOP_K):
    """(n_windows, 4) softmax outputs -> dict class -> probability for the whole recording."""
    p = np.asarray(window_probs)
    p_crackle = p[:, 1] + p[:, 3]
    p_wheeze = p[:, 2] + p[:, 3]
    k = min(top_k, len(p))
    c = float(np.sort(p_crackle)[-k:].mean())
    w = float(np.sort(p_wheeze)[-k:].mean())
    return {"normal": (1 - c) * (1 - w), "crackles": c * (1 - w),
            "wheezes": (1 - c) * w, "both": c * w}


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class Analyzer:
    def __init__(self, onnx_path):
        onnx_path = Path(onnx_path)
        meta = json.loads(onnx_path.with_suffix(".json").read_text())
        if meta["classes"] != CLASSES:
            raise ValueError(f"Model classes {meta['classes']} differ from {CLASSES}.")
        if meta["preprocess"] != pp.params():
            raise ValueError(f"Model was trained with preprocessing {meta['preprocess']}, "
                             f"but preprocess.py now has {pp.params()}. Retrain or revert.")
        self.session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.model_version = meta["model_version"]
        self.metrics = meta.get("metrics", {})

    def window_probs(self, specs):
        x = np.asarray(specs, dtype=np.float32)[:, None, :, :]
        return softmax(self.session.run(None, {self.input_name: x})[0])

    def analyze(self, audio, sr):
        specs, _ = pp.recording_to_specs(audio, sr)
        probs = combine(self.window_probs(specs))
        finding = max(probs, key=probs.get)
        return {"finding": finding, "confidence": round(probs[finding], 2),
                "probabilities": {k: round(v, 3) for k, v in probs.items()}}
