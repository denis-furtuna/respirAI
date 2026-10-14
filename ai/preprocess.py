"""Audio preprocessing shared by training and serving (task D2).

Training (the Kaggle notebook) and the FastAPI server both import this file,
so the model always sees audio prepared in exactly the same way.

Pipeline: any sample rate -> 4 kHz -> band-pass 100-1800 Hz -> fixed 4 s
windows -> log-mel spectrogram (64 mel bands x 251 frames).

Only NumPy and SciPy, on purpose: the server has to run on a laptop where
heavier libraries (librosa/numba, PyTorch) may not be allowed to load.
"""
from math import gcd

import numpy as np
from scipy.signal import butter, get_window, resample_poly, sosfiltfilt

DEVICE_SR = 8000          # what the respirAI device sends (contract 1)
TARGET_SR = 4000          # what the model works at
BAND_HZ = (100, 1800)     # lung sounds live here; cuts heartbeat rumble and hiss
WINDOW_S = 4.0            # one model input; about one to two breathing cycles
HOP_S = 2.0               # windows overlap by half when scanning a recording
N_FFT = 256               # 64 ms at 4 kHz
HOP_LENGTH = 64           # 16 ms per spectrogram frame
N_MELS = 64

WINDOW_SAMPLES = int(WINDOW_S * TARGET_SR)
HOP_SAMPLES = int(HOP_S * TARGET_SR)
N_FRAMES = WINDOW_SAMPLES // HOP_LENGTH + 1

_SOS = butter(5, BAND_HZ, btype="bandpass", fs=TARGET_SR, output="sos")


def to_float(audio):
    """int16 PCM or float audio -> float32 in [-1, 1]."""
    audio = np.asarray(audio)
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    return audio.astype(np.float32)


def resample(audio, sr_in, sr_out):
    if sr_in == sr_out:
        return audio.astype(np.float32)
    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(audio, sr_out // g, sr_in // g).astype(np.float32)


def clean(audio, sr):
    """Raw audio at any rate -> band-passed float32 audio at TARGET_SR."""
    audio = resample(to_float(audio), sr, TARGET_SR)
    if len(audio) > 30:
        audio = sosfiltfilt(_SOS, audio).astype(np.float32)
    return audio


def windows(audio):
    """Cut clean audio into WINDOW_S windows with HOP_S hop.

    Returns (list of arrays, list of start times in seconds). A recording
    shorter than one window is zero-padded to a single window.
    """
    if len(audio) <= WINDOW_SAMPLES:
        return [np.pad(audio, (0, WINDOW_SAMPLES - len(audio)))], [0.0]
    starts = list(range(0, len(audio) - WINDOW_SAMPLES + 1, HOP_SAMPLES))
    if starts[-1] + WINDOW_SAMPLES < len(audio):
        starts.append(len(audio) - WINDOW_SAMPLES)  # don't drop the tail
    return [audio[s:s + WINDOW_SAMPLES] for s in starts], [s / TARGET_SR for s in starts]


def _hz_to_mel(f):
    """Slaney mel scale: linear below 1 kHz, logarithmic above (same as librosa's default)."""
    f = np.asarray(f, dtype=np.float64)
    lin = f / (200.0 / 3)
    log = 15.0 + np.log(np.maximum(f, 1e-9) / 1000.0) / (np.log(6.4) / 27.0)
    return np.where(f >= 1000.0, log, lin)


def _mel_to_hz(m):
    m = np.asarray(m, dtype=np.float64)
    lin = m * (200.0 / 3)
    log = 1000.0 * np.exp((np.log(6.4) / 27.0) * (m - 15.0))
    return np.where(m >= 15.0, log, lin)


def _mel_filterbank():
    """(N_MELS, N_FFT // 2 + 1) triangular filters between BAND_HZ, area-normalised."""
    fft_hz = np.linspace(0, TARGET_SR / 2, N_FFT // 2 + 1)
    edges = _mel_to_hz(np.linspace(_hz_to_mel(BAND_HZ[0]), _hz_to_mel(BAND_HZ[1]), N_MELS + 2))
    lower = (fft_hz[None, :] - edges[:-2, None]) / np.diff(edges)[:-1, None]
    upper = (edges[2:, None] - fft_hz[None, :]) / np.diff(edges)[1:, None]
    fb = np.maximum(0, np.minimum(lower, upper))
    fb *= (2.0 / (edges[2:] - edges[:-2]))[:, None]
    return fb.astype(np.float32)


_MEL_FB = _mel_filterbank()
_HANN = get_window("hann", N_FFT, fftbins=True).astype(np.float32)


def log_mel(window):
    """One clean window -> standardised log-mel spectrogram, shape (N_MELS, N_FRAMES)."""
    window = np.pad(window, (0, max(0, WINDOW_SAMPLES - len(window))))[:WINDOW_SAMPLES]
    padded = np.pad(window, N_FFT // 2)  # centre each frame on its time step
    idx = np.arange(N_FFT)[None, :] + HOP_LENGTH * np.arange(N_FRAMES)[:, None]
    power = np.abs(np.fft.rfft(padded[idx] * _HANN, axis=1)) ** 2   # (frames, bins)
    db = 10.0 * np.log10(np.maximum(_MEL_FB @ power.T, 1e-10))       # (mels, frames)
    return ((db - db.mean()) / (db.std() + 1e-6)).astype(np.float32)


def params():
    """The settings a trained model depends on; saved next to the weights and checked on load."""
    return {"TARGET_SR": TARGET_SR, "BAND_HZ": list(BAND_HZ), "WINDOW_S": WINDOW_S,
            "N_FFT": N_FFT, "HOP_LENGTH": HOP_LENGTH, "N_MELS": N_MELS}


def recording_to_specs(audio, sr):
    """Whole recording -> (stack of spectrograms (n, N_MELS, N_FRAMES), window start times)."""
    wins, starts = windows(clean(audio, sr))
    return np.stack([log_mel(w) for w in wins]), starts
