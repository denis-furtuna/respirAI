"""ICBHI 2017 dataset helpers (tasks D1 and D3).

File names look like 101_1b1_Al_sc_Meditron.wav:
patient _ recording index _ chest point _ acquisition mode _ device.
Each .wav has a .txt next to it with one breathing cycle per line:
start_s  end_s  crackles(0/1)  wheezes(0/1).
"""
from pathlib import Path

import numpy as np
import pandas as pd

from preprocess import DEVICE_SR, WINDOW_S, resample, to_float

CLASSES = ["normal", "crackles", "wheezes", "both"]
POINTS = ["Tc", "Al", "Ar", "Pl", "Pr", "Ll", "Lr"]  # contract order, n = 0..6


def label_of(crackles, wheezes):
    return int(bool(crackles)) + 2 * int(bool(wheezes))  # 0 normal, 1 crackles, 2 wheezes, 3 both


def find_audio_dir(root="/kaggle/input"):
    """The folder holding the .wav/.txt pairs, wherever Kaggle mounted it."""
    for txt in Path(root).rglob("*.txt"):
        if txt.with_suffix(".wav").exists():
            return txt.parent
    raise FileNotFoundError(
        f"No ICBHI .wav/.txt pairs under {root}. "
        "Add the 'Respiratory Sound Database' dataset to the notebook (Add Input)."
    )


def read_cycles(txt_path):
    """-> float array of shape (n_cycles, 4): start, end, crackles, wheezes."""
    return np.loadtxt(txt_path, ndmin=2)


def load_index(audio_dir):
    """One row per recording, with patient, chest point and cycle counts."""
    rows = []
    for wav in sorted(Path(audio_dir).glob("*.wav")):
        parts = wav.stem.split("_")
        cycles = read_cycles(wav.with_suffix(".txt"))
        rows.append({
            "stem": wav.stem,
            "path": str(wav),
            "patient": int(parts[0]),
            "point": parts[2],
            "mode": parts[3],
            "device": parts[4],
            "n_cycles": len(cycles),
            "crackle_cycles": int(cycles[:, 2].sum()),
            "wheeze_cycles": int(cycles[:, 3].sum()),
        })
    df = pd.DataFrame(rows)
    df["label"] = [label_of(c, w) for c, w in zip(df.crackle_cycles, df.wheeze_cycles)]
    return df


def load_diagnosis(root="/kaggle/input"):
    """patient -> diagnosis, from patient_diagnosis.csv. Only for exploring; we never train on it."""
    for csv in Path(root).rglob("patient_diagnosis.csv"):
        return pd.read_csv(csv, header=None, names=["patient", "diagnosis"])
    return None


def as_device(audio, sr):
    """Make dataset audio look like what the device sends: 8 kHz, 16-bit."""
    audio = resample(to_float(audio), sr, DEVICE_SR)
    return np.clip(np.round(audio * 32767), -32768, 32767).astype(np.int16)


def window_label(cycles, start_s, window_s=WINDOW_S, min_overlap_s=0.5):
    """Label for the window [start_s, start_s + window_s), or None if no cycle is really in it.

    A cycle counts when at least min_overlap_s of it (or half of it, if it is
    short) falls inside the window. The window has crackles if any counted
    cycle has crackles, same for wheezes.
    """
    end_s = start_s + window_s
    crackles = wheezes = False
    counted = 0
    for c_start, c_end, c_crackle, c_wheeze in cycles:
        overlap = min(c_end, end_s) - max(c_start, start_s)
        if overlap >= min(min_overlap_s, 0.5 * (c_end - c_start)) and overlap > 0:
            counted += 1
            crackles |= bool(c_crackle)
            wheezes |= bool(c_wheeze)
    return label_of(crackles, wheezes) if counted else None


def patient_split(df, test_frac=0.2, val_frac=0.15, seed=42):
    """Assign every patient to train, val or test. A patient never appears in two splits.

    Stratified on the recording labels so each split gets some of every class.
    Returns a Series patient -> split name.
    """
    from sklearn.model_selection import StratifiedGroupKFold

    def take(frame, frac, seed):
        k = max(2, round(1 / frac))
        sgkf = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed)
        _, held = next(sgkf.split(frame, frame.label, groups=frame.patient))
        return set(frame.iloc[held].patient)

    test = take(df, test_frac, seed)
    rest = df[~df.patient.isin(test)]
    val = take(rest, val_frac / (1 - test_frac), seed + 1)
    split = {p: "test" if p in test else "val" if p in val else "train" for p in df.patient.unique()}
    return pd.Series(split, name="split")
