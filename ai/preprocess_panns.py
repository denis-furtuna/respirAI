"""Preprocessing for the PANNs CNN14 model (server only): one recording -> one log-mel [1, 1, 64, 501].

Stage 0 adapts the device's audio to what the model was trained on (ICBHI at 4 kHz, 5 s cycles):
any rate -> 4 kHz, centre 5 s, band-pass 50-1800 Hz, quiet recordings raised to the training RMS.
Then the same V3 waveform repairs and log-mel as training (code_mel_spectogram.py). The constants and
the repair functions below are copied unchanged from that file; the log-mel is the same computation as
torchaudio's MelSpectrogram(htk, slaney, power 2) + AmplitudeToDB(top_db 60), in NumPy, so serving
needs no torchaudio.

The ONNX ResNet path (preprocess.py, inference.py) is separate and stays as it is: the phone app and the
CI golden tests depend on it.
"""
from math import gcd

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter, uniform_filter1d
from scipy.signal import butter, istft, resample_poly, sosfiltfilt, stft

# ---------- Stage 0: device audio -> training conditions ----------
DEVICE_SR = 8000
TARGET_RMS = 0.025        # typical RMS of the ICBHI 4 kHz training cycles after band-pass
CALIBRATE_BELOW_RMS = 0.015
PEAK_LIMIT = 0.95

# ---------- copied from code_mel_spectogram.py ----------
SAMPLE_RATE = 4000
TARGET_DURATION_SEC = 5.0
TARGET_LEN = int(SAMPLE_RATE * TARGET_DURATION_SEC)  # 20,000 samples

# Parametri Log-Mel Spectrogram aliniati la scara temporala nativa PANNs CNN14 (win=32ms, hop=10ms -> 501 cadre)
MEL_N_FFT = 512
MEL_WIN_LENGTH = 128
MEL_HOP_LENGTH = 40
MEL_N_MELS = 64
MEL_F_MIN = 50.0
MEL_F_MAX = 1800.0
MEL_TOP_DB = 60.0
MEL_SCALE = "htk"
MEL_NORM = "slaney"
TARGET_FRAMES = (TARGET_LEN // MEL_HOP_LENGTH) + 1  # 501 cadre pentru 5.0s (10 ms/cadru)

# Praguri de eliminare definitiva
MIN_VALID_DURATION_SEC = 0.60
MIN_VALID_SAMPLES = int(MIN_VALID_DURATION_SEC * SAMPLE_RATE)  # 2,400 samples
MIN_RMS_SILENCE = 1e-4

# Parametri detectie & reparare DC Latch (V3: include panta de descarcare a condensatorului)
FLATLINE_MIN_SEC = 0.15
FLATLINE_MIN_SAMPLES = int(FLATLINE_MIN_SEC * SAMPLE_RATE)
DC_RECOVERY_SETTLE_THRESH = 0.08

# Parametri detectie & reparare Clipping (V3: repara orice clipping > 0% si <= 10%)
CLIP_HARD_RAIL = 0.97
CLIP_SOFT_RAIL = 0.88
CLIP_SOFT_SLOPE = 3e-3
CLIP_DELETE_THRESHOLD = 0.10       # > 10% (Sever / Distrus) -> Stergere definitiva
CLIP_BLOCK_MERGE_GAP = int(0.025 * SAMPLE_RATE)
CLIP_SHOULDER_PAD = 4

# Parametri Dual-Band De-Spiking (V3: banda larga + banda inalta > 350 Hz, taiere fizica)
DESPIKE_WIN_SEC = 0.12
DESPIKE_HIGH_SCALE_RATIO = 3.8
DESPIKE_HP_SCALE_RATIO = 4.5
DESPIKE_PEAK_SUPPORT_FRAC = 0.45
DESPIKE_MIN_JUMP = 0.14
DESPIKE_HP_MIN_AMP = 0.045
MAX_IMPULSE_SUPPORT_SAMPLES = int(0.004 * SAMPLE_RATE)  # <= 4 ms varf
SPIKE_EXCISE_PAD = int(0.006 * SAMPLE_RATE)             # +/- 6 ms taiere cu cross-fade scurt (10 ms)
SPIKE_EDGE_TRIM_ZONE = int(0.20 * SAMPLE_RATE)          # <= 200 ms de la capete -> trim direct

# Parametri Fade & Cross-Fade
CROSSFADE_MS = 50.0
SPLICE_CROSSFADE_MS = 25.0
SPIKE_SPLICE_CROSSFADE_MS = 10.0
FADE_EDGE_MS = 20.0

def crossfade_concat(seg_a: np.ndarray, seg_b: np.ndarray, xfade_samples: int) -> np.ndarray:
    """Concateneaza doua segmente audio folosind cross-fade raised-cosine."""
    if len(seg_a) == 0:
        return seg_b.copy()
    if len(seg_b) == 0:
        return seg_a.copy()

    xf = min(xfade_samples, len(seg_a) // 2, len(seg_b) // 2)
    if xf <= 0:
        return np.concatenate([seg_a, seg_b])

    t = np.linspace(0.0, np.pi, xf, dtype=np.float32)
    fade_out_w = 0.5 * (1.0 + np.cos(t))
    fade_in_w = 0.5 * (1.0 - np.cos(t))

    overlap = seg_a[-xf:] * fade_out_w + seg_b[:xf] * fade_in_w
    return np.concatenate([seg_a[:-xf], overlap, seg_b[xf:]])


def find_runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Returneaza lista de intervale [start, end) unde mask este True pentru cel putin min_len esantioane."""
    if len(mask) == 0 or not np.any(mask):
        return []
    padded = np.concatenate(([False], mask, [False]))
    starts = np.where(~padded[:-1] & padded[1:])[0]
    ends = np.where(padded[:-1] & ~padded[1:])[0]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if (e - s) >= min_len]


def excise_intervals_with_crossfade(
    sig: np.ndarray,
    bad_intervals: list[tuple[int, int]],
    sr: int,
    xfade_ms: float = SPLICE_CROSSFADE_MS,
) -> np.ndarray:
    """Elimina intervalele problematice: cele de la capete se taie direct, cele interioare cu cross-fade."""
    if not bad_intervals:
        return sig

    bad_intervals = sorted(bad_intervals)
    merged = [bad_intervals[0]]
    for s, e in bad_intervals[1:]:
        prev_s, prev_e = merged[-1]
        if s - prev_e <= CLIP_BLOCK_MERGE_GAP:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))

    valid_segments = []
    cursor = 0
    for s, e in merged:
        if s > cursor:
            valid_segments.append(sig[cursor:s])
        cursor = e
    if cursor < len(sig):
        valid_segments.append(sig[cursor:])

    if not valid_segments:
        return np.array([], dtype=np.float32)

    xfade_len = int((xfade_ms / 1000.0) * sr)
    out = valid_segments[0]
    for seg in valid_segments[1:]:
        out = crossfade_concat(out, seg, xfade_len)
    return out


def repair_dc_latch(sig: np.ndarray, sr: int) -> np.ndarray:
    """
    Detecteaza segmentele blocate pe sina / flatline (>= 150 ms) si extinde taierea
    peste toata panta de revenire a condensatorului pana cand media locala revine la 0.
    """
    n = len(sig)
    if n < FLATLINE_MIN_SAMPLES:
        return sig

    diff_zero = np.abs(np.diff(sig)) < 1e-6
    rail_clamp = np.abs(sig) >= 0.98
    local_mean = uniform_filter1d(sig.astype(np.float32), size=int(0.10 * sr), mode="nearest")

    seeds = []
    for s, e in find_runs(diff_zero, FLATLINE_MIN_SAMPLES):
        seeds.append((s, min(n, e + 1)))
    for s, e in find_runs(rail_clamp, FLATLINE_MIN_SAMPLES):
        seeds.append((s, e))

    if not seeds:
        return sig

    expanded = []
    for s, e in seeds:
        while s > 0 and (abs(local_mean[s - 1]) > DC_RECOVERY_SETTLE_THRESH or abs(sig[s - 1]) >= 0.90):
            s -= 1
        while e < n and (abs(local_mean[e]) > DC_RECOVERY_SETTLE_THRESH or abs(sig[e]) >= 0.90):
            e += 1
        if s <= int(0.15 * sr):
            s = 0
        if (n - e) <= int(0.15 * sr):
            e = n
        expanded.append((s, e))

    return excise_intervals_with_crossfade(sig, expanded, sr)


def get_clipped_sample_mask(sig: np.ndarray) -> tuple[np.ndarray, int]:
    """Identifica atat platourile dure (>=0.97, >=2 esantioane), cat si cele usor inclinate de resampling (>=0.88)."""
    mask = np.zeros(len(sig), dtype=bool)
    if len(sig) < 3:
        return mask, 0

    for s, e in find_runs(np.abs(sig) >= CLIP_HARD_RAIL, 2):
        mask[s:e] = True

    soft_trans = (np.abs(sig[:-1]) >= CLIP_SOFT_RAIL) & (np.abs(np.diff(sig)) < CLIP_SOFT_SLOPE)
    for s, e in find_runs(soft_trans, 2):
        mask[s : e + 1] = True

    return mask, int(np.sum(mask))


def repair_moderate_clipping(sig: np.ndarray, clip_mask: np.ndarray, sr: int) -> np.ndarray:
    """Elimina platourile de clipping (<= 10%, cu +/-4 esantioane umeri) cu cross-fade interior."""
    if not np.any(clip_mask):
        return sig

    n = len(sig)
    padded_intervals = []
    for s, e in find_runs(clip_mask, 1):
        ps = 0 if s <= CLIP_SHOULDER_PAD else (s - CLIP_SHOULDER_PAD)
        pe = n if (n - e) <= CLIP_SHOULDER_PAD else (e + CLIP_SHOULDER_PAD)
        padded_intervals.append((ps, pe))

    repaired = excise_intervals_with_crossfade(sig.astype(np.float32), padded_intervals, sr)
    if len(repaired) > 0:
        peak = float(np.max(np.abs(repaired)))
        if peak > 0.98:
            repaired = repaired * (0.95 / peak)
    return repaired


def apply_highpass(
    sig: np.ndarray,
    sr: int,
    cutoff_hz: float = MEL_F_MIN,
    high_hz: float = MEL_F_MAX,
) -> np.ndarray:
    """Filtreaza semnalul strict in banda utila Mel [50, 1800] Hz cu filtru Butterworth Band-Pass zero-phase."""
    if len(sig) < 64:
        return sig
    sos = butter(4, [cutoff_hz, high_hz], btype="bandpass", fs=sr, output="sos")
    return sosfiltfilt(sos, sig).astype(np.float32)


def despike_dualband(sig: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Elimina spike-urile mecanice inguste (<= 4 ms) in banda larga si > 350 Hz."""
    n = len(sig)
    if n < 64:
        return sig, 0

    out = sig.astype(np.float32).copy()
    win_len = max(5, int(DESPIKE_WIN_SEC * sr) | 1)

    abs_sig = np.abs(out)
    local_scale = np.maximum(median_filter(abs_sig, size=win_len, mode="reflect"), 0.015)
    max_jump = np.zeros(n, dtype=np.float32)
    for step in (1, 2, 3):
        dp = np.abs(out - np.roll(out, step))
        dp[:step] = 0.0
        dn = np.abs(out - np.roll(out, -step))
        dn[-step:] = 0.0
        max_jump = np.maximum(max_jump, np.maximum(dp, dn))

    cand_broad = (abs_sig > DESPIKE_HIGH_SCALE_RATIO * local_scale) & (max_jump > DESPIKE_MIN_JUMP)

    sos_hp = butter(4, 350.0, btype="highpass", fs=sr, output="sos")
    sig_hp = sosfiltfilt(sos_hp, out).astype(np.float32)
    abs_hp = np.abs(sig_hp)
    hp_scale = np.maximum(median_filter(abs_hp, size=win_len, mode="reflect"), 0.005)
    cand_hp = (abs_hp > DESPIKE_HP_SCALE_RATIO * hp_scale) & (abs_hp > DESPIKE_HP_MIN_AMP)

    candidates = np.where(cand_broad | cand_hp)[0]
    if len(candidates) == 0:
        return out, 0

    half_win = int(0.012 * sr)
    covered = np.zeros(n, dtype=bool)
    bad_intervals = []
    removed_spikes = 0

    score = np.maximum(abs_sig / local_scale, abs_hp / hp_scale)
    for idx in candidates[np.argsort(score[candidates])[::-1]]:
        if covered[idx]:
            continue

        left = max(0, idx - half_win)
        right = min(n, idx + half_win + 1)

        is_narrow_broad = False
        if cand_broad[idx]:
            sup_b = int(
                np.sum(abs_sig[left:right] > max(DESPIKE_PEAK_SUPPORT_FRAC * abs_sig[idx], 2.5 * local_scale[idx]))
            )
            is_narrow_broad = sup_b <= MAX_IMPULSE_SUPPORT_SAMPLES

        is_narrow_hp = False
        if cand_hp[idx]:
            sup_hp = int(
                np.sum(abs_hp[left:right] > max(DESPIKE_PEAK_SUPPORT_FRAC * abs_hp[idx], 2.8 * hp_scale[idx]))
            )
            is_narrow_hp = sup_hp <= MAX_IMPULSE_SUPPORT_SAMPLES

        if is_narrow_broad or is_narrow_hp:
            s_cut = max(0, idx - SPIKE_EXCISE_PAD)
            e_cut = min(n, idx + SPIKE_EXCISE_PAD)
            if s_cut <= SPIKE_EDGE_TRIM_ZONE:
                s_cut = 0
            if (n - e_cut) <= SPIKE_EDGE_TRIM_ZONE:
                e_cut = n
            covered[s_cut:e_cut] = True
            bad_intervals.append((s_cut, e_cut))
            removed_spikes += 1

    if bad_intervals:
        out = excise_intervals_with_crossfade(out, bad_intervals, sr, xfade_ms=SPIKE_SPLICE_CROSSFADE_MS)

    return out, removed_spikes


def suppress_horizontal_lines(sig: np.ndarray, sr: int) -> np.ndarray:
    """
    Elimina benzile orizontale stationare pe rezolutie inalta (STFT -> iSTFT) inainte ca
    banca de filtre triunghiulare Mel sa intinda rezonanta pe mai multe benzi.
    """
    n = len(sig)
    if n < 512:
        return sig

    freqs, _, Zxx = stft(sig, fs=sr, window="hann", nperseg=256, noverlap=192)
    mag = np.abs(Zxx) + 1e-7
    log_mag = np.log(mag)

    temporal_med = np.median(log_mag, axis=1)
    smooth_trend = gaussian_filter1d(temporal_med, sigma=6.0, mode="nearest")

    deviation = temporal_med - smooth_trend
    bin_iqr = np.quantile(log_mag, 0.85, axis=1) - np.quantile(log_mag, 0.15, axis=1)
    stationarity = np.clip((1.05 - bin_iqr) / 0.40, 0.0, 1.0)
    active_bins = (freqs >= 150.0) & (deviation > 0.65)
    correction = np.zeros_like(deviation)
    correction[active_bins] = (
        np.clip(deviation[active_bins] - 0.65, 0.0, 1.2) * stationarity[active_bins]
    )

    gain = np.exp(-0.55 * correction)[:, None]
    _, rec = istft(Zxx * gain, fs=sr, window="hann", nperseg=256, noverlap=192)
    rec = rec[:n].astype(np.float32)
    if len(rec) < n:
        rec = np.pad(rec, (0, n - len(rec)))
    return rec


def trim_dead_edges(sig: np.ndarray, sr: int) -> np.ndarray:
    """Inlatura eventualele zone complet mute (> 20 ms de zero absolut) de la capete inainte de duplicare."""
    non_zero = np.where(np.abs(sig) > 1e-5)[0]
    if len(non_zero) == 0:
        return np.array([], dtype=np.float32)
    start = int(non_zero[0])
    end = int(non_zero[-1]) + 1
    min_trim = int(0.02 * sr)
    s_idx = start if start >= min_trim else 0
    e_idx = end if (len(sig) - end) >= min_trim else len(sig)
    return sig[s_idx:e_idx]


def apply_edge_fades_and_headroom(sig: np.ndarray, sr: int) -> np.ndarray:
    """Aplica un singur fade-in/out scurt (20ms) la marginile 0.0s si 5.0s si garanteaza headroom <= 0.95."""
    out = sig.astype(np.float32).copy()
    fade_len = int((FADE_EDGE_MS / 1000.0) * sr)
    if fade_len > 0 and len(out) >= 2 * fade_len:
        t = np.linspace(0.0, np.pi, fade_len, dtype=np.float32)
        out[:fade_len] *= 0.5 * (1.0 - np.cos(t))
        out[-fade_len:] *= 0.5 * (1.0 + np.cos(t))

    if len(out) > 0:
        peak = float(np.max(np.abs(out)))
        if peak > 0.96:
            out = out * (0.95 / peak)
    return out


def standardize_to_5s(sig: np.ndarray, sr: int) -> np.ndarray:
    """Standardizare fizica stricta la 5.0 secunde (20,000 esantioane)."""
    if len(sig) < TARGET_LEN:
        xfade_len = min(int((CROSSFADE_MS / 1000.0) * sr), len(sig) // 4)
        out = sig.astype(np.float32).copy()
        while len(out) < TARGET_LEN:
            out = crossfade_concat(out, sig, xfade_len)
        out = out[:TARGET_LEN]
    else:
        out = sig[:TARGET_LEN].astype(np.float32).copy()

    return apply_edge_fades_and_headroom(out, sr)


# ---------- log-mel (NumPy twin of the torchaudio transforms used in training) ----------
def _mel_filterbank() -> np.ndarray:
    """(n_mels, n_fft//2+1) HTK mel triangles with Slaney area norm: torchaudio.functional.melscale_fbanks."""
    m_min = 2595.0 * np.log10(1.0 + MEL_F_MIN / 700.0)
    m_max = 2595.0 * np.log10(1.0 + MEL_F_MAX / 700.0)
    f_pts = 700.0 * (10.0 ** (np.linspace(m_min, m_max, MEL_N_MELS + 2) / 2595.0) - 1.0)
    fft_freqs = np.linspace(0.0, SAMPLE_RATE // 2, MEL_N_FFT // 2 + 1)
    f_diff = f_pts[1:] - f_pts[:-1]
    slopes = f_pts[None, :] - fft_freqs[:, None]
    down = -slopes[:, :-2] / f_diff[:-1]
    up = slopes[:, 2:] / f_diff[1:]
    fb = np.maximum(0.0, np.minimum(down, up))            # (freqs, mels)
    fb *= 2.0 / (f_pts[2:MEL_N_MELS + 2] - f_pts[:MEL_N_MELS])
    return fb.T.astype(np.float64)


def _stft_window() -> np.ndarray:
    """Periodic Hann of win_length, zero-padded to n_fft and centred, as torch.stft does."""
    win = np.hanning(MEL_WIN_LENGTH + 1)[:-1]
    left = (MEL_N_FFT - MEL_WIN_LENGTH) // 2
    return np.pad(win, (left, MEL_N_FFT - MEL_WIN_LENGTH - left))


_FB = _mel_filterbank()
_WIN = _stft_window()


def log_mel(sig_5s: np.ndarray) -> np.ndarray:
    """5 s at 4 kHz -> log-mel in dB, shape (64, 501), floor at max - 60 dB (the model's input scale)."""
    x = np.asarray(sig_5s, dtype=np.float64)
    padded = np.pad(x, MEL_N_FFT // 2, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, MEL_N_FFT)[::MEL_HOP_LENGTH]
    power = np.abs(np.fft.rfft(frames * _WIN, axis=1)) ** 2          # (frames, bins)
    mel = _FB @ power.T                                                # (mels, frames)
    if mel.shape[1] > TARGET_FRAMES:
        mel = mel[:, :TARGET_FRAMES]
    elif mel.shape[1] < TARGET_FRAMES:
        mel = np.pad(mel, ((0, 0), (0, TARGET_FRAMES - mel.shape[1])), mode="edge")
    db = 10.0 * np.log10(np.maximum(mel, 1e-10))
    db = np.maximum(db, db.max() - MEL_TOP_DB)
    return db.astype(np.float32)


# ---------- the whole pipeline ----------
class Unusable(ValueError):
    """The recording cannot be turned into a model input (silent, destroyed by clipping, too short)."""


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def to_float(audio) -> np.ndarray:
    audio = np.asarray(audio)
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32)


def stage0(audio, sr: int) -> np.ndarray:
    """Device audio at any rate -> 4 kHz, centre 5 s, band-passed, quiet recordings raised to TARGET_RMS."""
    x = to_float(audio)
    if sr != SAMPLE_RATE:
        g = gcd(int(sr), SAMPLE_RATE)
        x = resample_poly(x, SAMPLE_RATE // g, int(sr) // g).astype(np.float32)
    if len(x) > TARGET_LEN:                      # e.g. 6 s -> drop 0.5 s at each end: button and handling noise
        start = (len(x) - TARGET_LEN) // 2
        x = x[start:start + TARGET_LEN]
    x = apply_highpass(x, SAMPLE_RATE)           # 50-1800 Hz: rumble out before measuring the level
    rms = _rms(x)
    if MIN_RMS_SILENCE <= rms < CALIBRATE_BELOW_RMS:
        gain = min(TARGET_RMS / rms, PEAK_LIMIT / (float(np.max(np.abs(x))) + 1e-9))
        x = (x * gain).astype(np.float32)
    return x


def clean(audio, sr: int) -> np.ndarray:
    """Stage 0 + the V3 repairs of training (same order as run_mel_cleaning_pipeline) -> exactly 5 s."""
    sig = stage0(audio, sr)
    if len(sig) < MIN_VALID_SAMPLES or _rms(sig) < MIN_RMS_SILENCE:
        raise Unusable("silent or too short")
    sig = repair_dc_latch(sig, SAMPLE_RATE)
    if len(sig) < MIN_VALID_SAMPLES or _rms(sig) < MIN_RMS_SILENCE:
        raise Unusable("nothing left after DC-latch repair")
    clip_mask, clipped = get_clipped_sample_mask(sig)
    if clipped / float(len(sig)) > CLIP_DELETE_THRESHOLD:
        raise Unusable("severe clipping")
    if clipped:
        sig = repair_moderate_clipping(sig, clip_mask, SAMPLE_RATE)
    sig = apply_highpass(sig, SAMPLE_RATE, cutoff_hz=MEL_F_MIN, high_hz=MEL_F_MAX)
    sig, _ = despike_dualband(sig, SAMPLE_RATE)
    sig = trim_dead_edges(sig, SAMPLE_RATE)
    if len(sig) < MIN_VALID_SAMPLES or _rms(sig) < MIN_RMS_SILENCE:
        raise Unusable("nothing left after repairs")
    sig = suppress_horizontal_lines(sig, SAMPLE_RATE)
    sig = standardize_to_5s(sig, SAMPLE_RATE)
    if not np.all(np.isfinite(sig)) or _rms(sig) < MIN_RMS_SILENCE:
        raise Unusable("silent after repairs")
    return sig


def recording_to_input(audio, sr: int) -> np.ndarray:
    """Whole recording -> model input [1, 1, 64, 501], float32 dB."""
    return log_mel(clean(audio, sr))[None, None, :, :]
