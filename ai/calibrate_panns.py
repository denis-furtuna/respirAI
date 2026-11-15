"""Choose the PANNs per-point threshold on healthy people recorded with our device.

    python calibrate_panns.py [data/denis_*.wav ...]

Each recording is cut into 6 s pieces (what the app sends: one breath), every 0.5 s, and scored like the server
does. The threshold is the highest healthy score plus a margin, so a healthy place reads normal. It is checked
leaving one recording out at a time: the threshold from the others, the pieces of the one left out scored with it.

Only false alarms can be measured this way (no sick person has been recorded with our device yet): a higher
threshold also hides some real abnormal sounds. Put the chosen value in POINT_THRESHOLD in inference_panns.py.
"""
import glob
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy.io import wavfile

warnings.filterwarnings("ignore")
import preprocess_panns as pp  # noqa: E402
from inference_panns import DEFAULT_MODEL, DEFAULT_PATIENT, PannsAnalyzer  # noqa: E402

PIECE_S, STEP_S = 6.0, 0.5
MARGIN = 0.03


def pieces(x, sr):
    n, step = int(PIECE_S * sr), int(STEP_S * sr)
    return [x[s:s + n] for s in range(0, len(x) - n + 1, step)]


def main(files):
    a = PannsAnalyzer(DEFAULT_MODEL, DEFAULT_PATIENT)
    scores = {}
    for f in files:
        sr, x = wavfile.read(f)
        scores[f] = np.array([a.prob_abnormal(pp.recording_to_input(p, sr)) for p in pieces(x, sr)])
        s = scores[f]
        print(f"{Path(f).name:18s} {len(s):2d} pieces  min {s.min():.3f}  median {np.median(s):.3f}  max {s.max():.3f}")
    every = np.concatenate(list(scores.values()))
    print(f"\nall {len(every)} pieces: p50 {np.quantile(every, .5):.3f}  p90 {np.quantile(every, .9):.3f}  "
          f"p95 {np.quantile(every, .95):.3f}  max {every.max():.3f}")

    print("\nleave one recording out (threshold = max of the others + margin):")
    fa = []
    for f in files:
        rest = np.concatenate([s for g, s in scores.items() if g != f])
        th = min(0.99, rest.max() + MARGIN)
        alarms = float(np.mean(scores[f] >= th))
        fa.append(alarms)
        print(f"  {Path(f).name:18s} threshold {th:.3f}  false alarms {100 * alarms:5.1f} %")
    th = min(0.99, every.max() + MARGIN)
    print(f"\nper-piece false alarms on an unseen recording: {100 * np.mean(fa):.1f} %")
    print(f"suggested POINT_THRESHOLD = {th:.2f}")

    # A whole check: one random piece per place. The RandomForest says "Go see a doctor" if any place is abnormal.
    rng = np.random.default_rng(0)
    by_point = {}
    for f, s in scores.items():
        by_point.setdefault(Path(f).stem.split("_")[1], []).append(s)
    pools = {p: np.concatenate(v) for p, v in by_point.items()}
    verdicts = []
    for _ in range(2000):
        sounds = {p: [float(rng.choice(v))] for p, v in pools.items()}
        verdicts.append(a.summarize_patient(sounds, threshold=th)["verdict"])
    print(f"simulated checks over {sorted(pools)}: {100 * np.mean([v == 'Normal' for v in verdicts]):.1f} % Normal")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(glob.glob(str(Path(__file__).resolve().parent / "data" / "denis_*.wav"))))
