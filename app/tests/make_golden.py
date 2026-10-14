"""Makes the reference answers that app/tests/ai.html compares the on-phone AI with (run on GitHub, see web-app.yml).

    python app/tests/make_golden.py        needs numpy, scipy, pandas, onnx, onnxruntime (pip, not on a laptop)

Runs the Python AI (ai/preprocess.py, ai/quality.py, ai/inference.py, ai/service.py) on a set of made-up
recordings, with a small stand-in model of the real model's shape (input "spec" [n, 1, 64, 251], 4 logits), and
writes everything to app/tests/golden/: the model in model/ (as the app expects it, with a demo clip) and every
intermediate result in golden.json. The JavaScript must then give the same numbers.
"""
import base64
import io
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "golden"
MODEL = OUT / "model"
os.environ["RESPIRAI_WEIGHTS"] = str(MODEL / "resp_cnn.onnx")        # service.py loads this model...
os.environ["RESPIRAI_DEMO_DIR"] = str(MODEL / "demo_clips")          # ...and these demo clips
sys.path.insert(0, str(ROOT / "ai"))

import onnx  # noqa: E402
from onnx import TensorProto, helper, numpy_helper  # noqa: E402
from scipy.io import wavfile  # noqa: E402

import preprocess as pp  # noqa: E402
from icbhi import CLASSES  # noqa: E402
from quality import quality  # noqa: E402

SR = pp.DEVICE_SR
rng = np.random.default_rng(2026)
b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def make_model():
    """Flatten -> Gemm: tiny, but takes exactly what the real model takes and gives logits that vary with the input."""
    n = pp.N_MELS * pp.N_FRAMES
    w = rng.normal(0, 0.01, (n, len(CLASSES))).astype(np.float32)
    b = rng.normal(0, 0.1, len(CLASSES)).astype(np.float32)
    graph = helper.make_graph(
        [helper.make_node("Flatten", ["spec"], ["flat"], axis=1), helper.make_node("Gemm", ["flat", "w", "b"], ["logits"])],
        "golden",
        [helper.make_tensor_value_info("spec", TensorProto.FLOAT, ["batch", 1, pp.N_MELS, pp.N_FRAMES])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", len(CLASSES)])],
        initializer=[numpy_helper.from_array(w, "w"), numpy_helper.from_array(b, "b")],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    MODEL.mkdir(parents=True, exist_ok=True)
    onnx.save(model, MODEL / "resp_cnn.onnx")
    meta = {"model_version": "golden-test", "classes": CLASSES, "input_shape": [1, pp.N_MELS, pp.N_FRAMES],
            "preprocess": pp.params(), "metrics": {}}
    (MODEL / "resp_cnn.json").write_text(json.dumps(meta, indent=2))


def breath(seconds, level=0.1):
    """Breath-like band noise swelling every 4.5 s, a few crackle clicks and a wheeze tone: int16 at 8 kHz."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    noise = np.convolve(rng.normal(0, 1, n), np.hanning(9), mode="same")
    x = noise / noise.std() * level * (0.4 + 0.6 * np.abs(np.sin(np.pi * t / 4.5)))
    for at in rng.uniform(0, seconds - 0.01, 12):    # crackles: short decaying clicks
        i = int(at * SR)
        x[i:i + 40] += 0.3 * level * np.exp(-np.arange(min(40, n - i)) / 6) * np.sin(np.arange(min(40, n - i)) * 1.3)
    x += 0.2 * level * np.sin(2 * np.pi * 420 * t) * (np.sin(np.pi * t / 4.5) > 0.7)   # wheeze: a tone in some breaths
    return np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16)


def recordings():
    clipped = breath(18, 0.5)
    clipped[::40] = 32767
    gappy = breath(18)
    for i in range(0, len(gappy), 2000):
        gappy[i:i + 320] = 0                                  # lost packets, filled with silence by the app
    knocked = breath(18, 0.02)
    for i in range(0, len(knocked), 8000):
        knocked[i:i + 800] = np.clip(knocked[i:i + 800].astype(np.int32) * 40, -32768, 32767)
    return {
        "breath-18s": breath(18), "breath-5s": breath(5), "breath-3s": breath(3), "breath-2.5s": breath(2.5),
        "quiet-18s": breath(18, 0.0006), "loud-clipped": clipped, "lost-packets": gappy, "knocks": knocked,
        "too-short-1.5s": breath(1.5),
    }


def wav_bytes(x):
    buf = io.BytesIO()
    wavfile.write(buf, SR, x)
    return buf.getvalue()


def main():
    make_model()
    clips = MODEL / "demo_clips"
    clips.mkdir(exist_ok=True)
    demo = breath(10)
    (clips / "crackles_Al.wav").write_bytes(wav_bytes(demo))
    (clips / "manifest.json").write_text(json.dumps({"crackles/Al": "crackles_Al.wav"}))

    import service   # after the files exist: it loads the model and the demo clips when imported
    from inference import Analyzer
    analyzer = Analyzer(MODEL / "resp_cnn.onnx")
    assert service.analyzer is not None and service.MODEL_VERSION == "golden-test"

    out = {"params": pp.params(), "health": service.health(), "recordings": []}
    for name, x in recordings().items():
        r = {"name": name, "sr": SR, "samples": b64(x.astype("<i2"))}
        score, checks = quality(x, SR)
        r["quality"] = {"score": score, "checks": checks}
        try:
            r["service"] = service.analyze("Al", "golden", wav_bytes(x))
        except service.ServiceError as e:
            r["service_error"] = e.status
        if len(x) >= 2 * SR:
            clean = pp.clean(x, SR)
            specs, starts = pp.recording_to_specs(x, SR)
            r.update(clean=b64(clean.astype("<f4")), specs=b64(specs.astype("<f4")), count=len(specs), starts=starts,
                     window_probs=analyzer.window_probs(specs).tolist(), analysis=analyzer.analyze(x, SR))
        out["recordings"].append(r)
    out["demo"] = service.analyze("Al", "golden", demo=True, demo_case="crackles")
    (OUT / "golden.json").write_text(json.dumps(out))
    print(f"golden: {len(out['recordings'])} recordings, model {service.MODEL_VERSION}, "
          f"{(OUT / 'golden.json').stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()
