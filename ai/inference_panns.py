"""PANNs CNN14 per chest point + RandomForest per patient (server only, needs PyTorch and scikit-learn).

    analyze(audio, sr)              one recording -> normal / abnormal, confidence, prob_abnormal
    summarize_patient(positions)    {point: [prob_abnormal, ...]} -> "Normal" / "Go see a doctor" + percentage

Weights in ai/weights/ (not committed):
    best_panns_finetuned_mel_hop10ms_bp50_1800_spike6ms_fade20ms_top2blocks.pt   (mel_train_finetune.py)
    patient_doctor_rf_model.pkl                                                (icbhi_patient_doctor_classifier.py)
"""
import pickle
from pathlib import Path

import numpy as np
import torch

import preprocess_panns as pp
from icbhi_patient_doctor_classifier import predict_single_patient_screening
from mel_panns_model import RespirPANNsCNN14

CLASSES = ["normal", "abnormal"]   # the model's two outputs, in order
WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
DEFAULT_MODEL = WEIGHTS_DIR / "best_panns_finetuned_mel_hop10ms_bp50_1800_spike6ms_fade20ms_top2blocks.pt"
DEFAULT_PATIENT = WEIGHTS_DIR / "patient_doctor_rf_model.pkl"

# P(abnormal) from which a place counts as abnormal. Not 0.5: on our device the model scores a healthy chest at
# 0.23-0.84 (it was trained on other stethoscopes; the sides score highest), so 0.5 made most places of a healthy
# person abnormal. calibrate_panns.py, 15 Nov 2026, one healthy person (Denis), 10 recordings at Tc Al Ar Ll Lr,
# 90 pieces of 6 s: highest 0.840, + 0.03 margin -> 0.87; one recording left out at a time: 2.2 % of its pieces
# abnormal. Only false alarms could be measured: a higher threshold also misses more real crackles and wheezes.
POINT_THRESHOLD = 0.87


class _Stub:
    """Stands in for any xgboost object in the pickle: the bundle's other models are never used."""
    def __init__(self, *a, **k):
        pass

    def __setstate__(self, state):
        self.__dict__["_state"] = state


class _BundleUnpickler(pickle.Unpickler):
    """The .pkl also holds an XGBClassifier (all_models); load it without xgboost installed."""
    def find_class(self, module, name):
        if module == "xgboost" or module.startswith("xgboost."):
            return _Stub
        if module.startswith("numpy._core"):       # pickled with NumPy 2; harmless alias on NumPy 1
            try:
                import numpy._core  # noqa: F401
            except ImportError:
                module = module.replace("numpy._core", "numpy.core", 1)
        return super().find_class(module, name)


def load_patient_bundle(path):
    with open(path, "rb") as f:
        return _BundleUnpickler(f).load()


class PannsAnalyzer:
    def __init__(self, model_path=DEFAULT_MODEL, patient_path=DEFAULT_PATIENT, threshold=POINT_THRESHOLD):
        self.threshold = threshold
        ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
        self.model = RespirPANNsCNN14(num_classes=2)
        self.model.load_state_dict(ckpt["model_state_dict"])
        self.model.eval()
        self.model_version = f"panns-cnn14-ft-e{ckpt.get('epoch', '?')}"
        self.metrics = {k: ckpt[k] for k in ("best_icbhi", "test_se", "test_sp", "test_acc") if k in ckpt}
        del ckpt                                          # drops the optimizer state (most of the 877 MB)
        self.patient_bundle = load_patient_bundle(patient_path)

    @torch.inference_mode()
    def prob_abnormal(self, x):
        """[1, 1, 64, 501] -> P(abnormal)."""
        logits = self.model(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)))
        return float(torch.softmax(logits, dim=-1)[0, 1])

    def analyze(self, audio, sr):
        """-> {"finding", "confidence", "prob_abnormal"}; finding "unusable" if the repairs leave nothing."""
        try:
            x = pp.recording_to_input(audio, sr)
        except pp.Unusable:
            return {"finding": "unusable", "confidence": 0.0, "prob_abnormal": None}
        p, th = self.prob_abnormal(x), self.threshold
        # confidence: how far past the threshold, 0.5 (on it) to 1 (at 0 or 1), as the patient verdict's percentage
        if p >= th:
            finding, confidence = "abnormal", 0.5 + 0.5 * (p - th) / max(1e-6, 1 - th)
        else:
            finding, confidence = "normal", 0.5 + 0.5 * (th - p) / max(1e-6, th)
        return {"finding": finding, "confidence": round(confidence, 2), "prob_abnormal": round(p, 4)}

    def summarize_patient(self, position_sounds, threshold=None):
        """{point: [prob_abnormal, ...]} -> verdict, percentage, display, risk_probability.

        The RandomForest was trained on ICBHI's annotated cycle labels, exactly 0 or 1: a healthy patient had 0
        everywhere. PANNs probabilities are never 0, and fed raw any score above ~0.05 already reads as
        "Go see a doctor". So each score becomes the 0/1 the model saw in training, at the point threshold.
        """
        th = self.threshold if threshold is None else threshold
        labels = {p: [1.0 if v >= th else 0.0 for v in vals] for p, vals in position_sounds.items()}
        return predict_single_patient_screening(labels, self.patient_bundle)
