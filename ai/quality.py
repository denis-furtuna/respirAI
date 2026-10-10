"""Recording quality score, 0-1 (task D7).

Four simple checks, each giving a score between 0 and 1; the final quality is
their product. Below 0.4 the app asks the user to record that point again.
The thresholds are first guesses: tune them on our own recordings (task D9).
"""
import numpy as np

from preprocess import to_float

SILENCE_DBFS = (-70.0, -55.0)   # below the first: silent; above the second: fine
CLIP_LEVEL = 0.98
CLIP_FRAC_MAX = 0.01            # 1 % clipped samples -> score 0
GAP_MS = 10                     # a run of exact zeros this long is a dropped BLE packet
GAP_FRAC_MAX = 0.20             # 20 % of the recording missing -> score 0
FRAME_MS = 50
SPIKE_RATIO = 6.0               # a frame this much louder than usual is a bump or rub
SPIKE_FRAC_MAX = 0.25
MIN_SECONDS = 5.0


def _ramp(x, lo, hi):
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def quality(audio, sr):
    """-> (score 0-1, dict of the individual checks)."""
    x = to_float(audio)
    if len(x) == 0:
        return 0.0, {"empty": 0.0}
    checks = {}

    rms = np.sqrt(np.mean(x ** 2)) + 1e-12
    checks["level"] = _ramp(20 * np.log10(rms), *SILENCE_DBFS)

    clipped = np.mean(np.abs(x) >= CLIP_LEVEL)
    checks["clipping"] = 1.0 - _ramp(clipped, 0.0, CLIP_FRAC_MAX)

    # Dropped packets arrive as exact zeros (the app fills gaps with silence).
    zero = np.concatenate([[0], (x == 0).astype(np.int8), [0]])
    edges = np.flatnonzero(np.diff(zero))
    runs = edges[1::2] - edges[::2]
    gap_samples = runs[runs >= sr * GAP_MS / 1000].sum()
    checks["dropouts"] = 1.0 - _ramp(gap_samples / len(x), 0.0, GAP_FRAC_MAX)

    frame = max(1, int(sr * FRAME_MS / 1000))
    n = len(x) // frame
    if n >= 4:
        frame_rms = np.sqrt(np.mean(x[:n * frame].reshape(n, frame) ** 2, axis=1))
        spikes = np.mean(frame_rms > SPIKE_RATIO * (np.median(frame_rms) + 1e-9))
        checks["handling_noise"] = 1.0 - _ramp(spikes, 0.0, SPIKE_FRAC_MAX)

    checks["length"] = _ramp(len(x) / sr, 0.0, MIN_SECONDS)

    score = float(np.prod(list(checks.values())))
    return round(score, 2), {k: round(v, 2) for k, v in checks.items()}
