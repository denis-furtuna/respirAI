"""Train on this computer's GPU instead of Kaggle, and measure what matters for our own device.

    python train_local.py lodo  --data <ICBHI folder>      # leave one stethoscope out: how well does it carry to a new device?
    python train_local.py split --data <ICBHI folder>      # train / val / test by patient: the usual scores
    python train_local.py final --data <ICBHI folder>      # train the model to ship, export ONNX + JSON to ai/weights/

--band-norm on|off and --band LO HI try preprocessing variants (they override preprocess.py for the run).
--noise <folder>: background recordings from OUR device (wav/aac), mixed into the training windows.
--own <folder>:   healthy people recorded with OUR device (one sub-folder per person); only used to count false alarms.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn as nn
import torch.nn.functional as F

import preprocess as pp
import icbhi
from model import build_model, export

DEV = "cuda" if torch.cuda.is_available() else "cpu"
AMP = False   # half precision overflowed in evaluation (not-a-number outputs); full precision is fast enough here
AUDIO = (".wav", ".aac", ".m4a")


# ---------- audio ----------
def read_audio(path):
    """Any wav (ICBHI has 24-bit ones) or aac/m4a -> (float32 mono, rate)."""
    path = Path(path)
    if path.suffix.lower() != ".wav":
        import av
        c = av.open(str(path))
        s = c.streams.audio[0]
        x = np.concatenate([f.to_ndarray().astype(np.float32).reshape(-1) for f in c.decode(s)])
        if np.abs(x).max() > 2:
            x = x / 32768
        return x, s.rate
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1), sr


def clean_like_device(path):
    """What preprocess.clean() gives for this file once it has gone through the device's format (8 kHz, 16-bit)."""
    x, sr = read_audio(path)
    return pp.clean(icbhi.as_device(x, sr), pp.DEVICE_SR)


def load_icbhi(data_dir):
    audio_dir = icbhi.find_audio_dir(data_dir)
    df = icbhi.load_index(audio_dir)
    cache = Path(data_dir) / f"_cache_{int(pp.BAND_HZ[0])}_{int(pp.BAND_HZ[1])}.npz"
    if cache.exists():
        z = np.load(cache)
        return df, z["x"], z["y"], z["rec"]
    xs, ys, rec = [], [], []
    t0 = time.time()
    for i, row in df.iterrows():
        audio = clean_like_device(row.path)
        cycles = icbhi.read_cycles(Path(row.path).with_suffix(".txt"))
        wins, starts = pp.windows(audio)
        for w, s in zip(wins, starts):
            lab = icbhi.window_label(cycles, s)
            if lab is None:
                continue
            xs.append(w.astype(np.float32))
            ys.append(lab)
            rec.append(i)
        if i % 100 == 0:
            print(f"  read {i}/{len(df)} recordings, {time.time() - t0:.0f} s", flush=True)
    x, y, rec = np.stack(xs), np.array(ys), np.array(rec)
    np.savez(cache, x=x, y=y, rec=rec)
    return df, x, y, rec


def load_folder(folder):
    """Every audio file under folder -> (windows, group index, group names); a group is the first sub-folder (a person)."""
    xs, groups, names = [], [], []
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix.lower() not in AUDIO:
            continue
        rel = p.relative_to(folder)
        g = rel.parts[0] if len(rel.parts) > 1 else "(top)"
        if g not in names:
            names.append(g)
        wins, _ = pp.windows(clean_like_device(p))
        xs += [w.astype(np.float32) for w in wins]
        groups += [names.index(g)] * len(wins)
    x = np.stack(xs) if xs else np.zeros((0, pp.WINDOW_SAMPLES), np.float32)
    return x, np.array(groups), names


# ---------- log-mel on the GPU: the same numbers as preprocess.log_mel ----------
class LogMel(nn.Module):
    def __init__(self, band_norm):
        super().__init__()
        self.band_norm = band_norm
        self.register_buffer("fb", torch.tensor(pp._MEL_FB))
        self.register_buffer("hann", torch.tensor(pp._HANN))

    def forward(self, x):                                   # (batch, WINDOW_SAMPLES) -> (batch, 1, N_MELS, N_FRAMES)
        x = F.pad(x, (pp.N_FFT // 2, pp.N_FFT // 2))
        frames = x.unfold(1, pp.N_FFT, pp.HOP_LENGTH)[:, :pp.N_FRAMES] * self.hann
        power = torch.fft.rfft(frames, dim=2).abs() ** 2    # (batch, frames, bins)
        db = 10 * torch.log10(torch.clamp(power @ self.fb.T, min=1e-10)).transpose(1, 2)
        if self.band_norm:
            db = db - db.mean(dim=2, keepdim=True)
        db = (db - db.mean(dim=(1, 2), keepdim=True)) / (db.std(dim=(1, 2), keepdim=True, correction=0) + 1e-6)
        return db[:, None]


def augment(x, noise):
    """Waveform augmentation on the GPU: shift in time, and our device's own background at a random level."""
    b, n_samples = x.shape
    shift = torch.randint(0, n_samples, (b,), device=x.device)
    idx = (torch.arange(n_samples, device=x.device)[None] + shift[:, None]) % n_samples
    x = torch.gather(x, 1, idx)
    if noise is not None and len(noise):
        n = noise[torch.randint(0, len(noise), (b,), device=x.device)]
        n = torch.gather(n, 1, (idx + 977) % n_samples)
        snr_db = torch.empty(b, 1, device=x.device).uniform_(0, 25)
        rms = lambda v: v.pow(2).mean(1, keepdim=True).sqrt()
        scale = rms(x) / (rms(n) + 1e-9) * 10 ** (-snr_db / 20)
        use = (torch.rand(b, 1, device=x.device) < 0.6).float()
        x = x + use * scale * n
    return x


def spec_augment(s):
    """Blank one band of frequencies and one stretch of time in each spectrogram."""
    b, _, m, t = s.shape
    for i in range(b):
        f0 = np.random.randint(0, m - 8)
        s[i, :, f0:f0 + np.random.randint(0, 9)] = 0
        t0 = np.random.randint(0, t - 30)
        s[i, :, :, t0:t0 + np.random.randint(0, 31)] = 0
    return s


# ---------- training and scores ----------
def predict(net, mel, x, bs=256):
    net.eval()
    out = []
    with torch.no_grad(), torch.autocast(DEV, enabled=AMP):
        for i in range(0, len(x), bs):
            out.append(F.softmax(net(mel(torch.tensor(x[i:i + bs], device=DEV))).float(), dim=1).cpu())
    return torch.cat(out).numpy() if out else np.zeros((0, 4), np.float32)


def auc(score, positive):
    """Area under the ROC curve: the chance that an abnormal window scores above a normal one."""
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(positive, score)) if 0 < positive.sum() < len(positive) else float("nan")


def scores(probs, y):
    pred = probs.argmax(1)
    sp = float((pred[y == 0] == 0).mean()) if (y == 0).any() else float("nan")           # normal called normal
    se = float((pred[y > 0] == y[y > 0]).mean()) if (y > 0).any() else float("nan")      # abnormal given its exact class
    return {"n": int(len(y)), "specificity": round(sp, 4), "sensitivity": round(se, 4), "icbhi_score": round((sp + se) / 2, 4),
            "auc_abnormal": round(auc(1 - probs[:, 0], y > 0), 4)}


def train(x, y, val, noise, band_norm, epochs, seed=0, log=""):
    torch.manual_seed(seed)
    np.random.seed(seed)
    mel = LogMel(band_norm).to(DEV)
    net = build_model(pretrained=True).to(DEV)
    counts = np.bincount(y, minlength=4).astype(np.float64)
    sampler_w = (1 / np.maximum(counts, 1) ** 0.5)[y]      # soften the class imbalance
    sampler_w /= sampler_w.sum()
    bs = 64
    steps = max(1, len(x) // bs)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=1e-3, total_steps=epochs * steps, pct_start=0.15)
    scaler = torch.amp.GradScaler(enabled=AMP)
    xt, yt = torch.tensor(x), torch.tensor(y)
    noise_t = torch.tensor(noise, device=DEV) if noise is not None and len(noise) else None
    best, best_state = -1, None
    for ep in range(epochs):
        net.train()
        tot = 0
        for _ in range(steps):
            idx = torch.tensor(np.random.choice(len(x), bs, p=sampler_w))
            xb, yb = xt[idx].to(DEV), yt[idx].to(DEV)
            with torch.no_grad():
                sb = spec_augment(mel(augment(xb, noise_t)))
            with torch.autocast(DEV, enabled=AMP):
                loss = F.cross_entropy(net(sb), yb, label_smoothing=0.05)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(net.parameters(), 2.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += loss.item()
        if val is not None and len(val[0]):
            s = scores(predict(net, mel, val[0]), val[1])
            key = s["icbhi_score"] + s["auc_abnormal"]
            if key > best:
                best, best_state = key, {k: v.detach().clone() for k, v in net.state_dict().items()}
            print(f"  {log}epoch {ep + 1:2d}/{epochs} loss {tot / steps:.3f} | val score {s['icbhi_score']:.3f} auc {s['auc_abnormal']:.3f}", flush=True)
    if best_state is not None:
        net.load_state_dict(best_state)
    return net, mel


def false_alarms(net, mel, own):
    """Healthy people on our device: how many windows, and how many per person, come out as not normal."""
    x, g, names = own
    if not len(x):
        return None
    p = predict(net, mel, x)
    return {"windows": int(len(x)), "p_abnormal_mean": round(float((1 - p[:, 0]).mean()), 3),
            "windows_not_normal": round(float((p.argmax(1) != 0).mean()), 3),
            "per_person": {n: round(float((p[g == i].argmax(1) != 0).mean()), 3) for i, n in enumerate(names)},
            "p_abnormal": np.round(1 - p[:, 0], 3).tolist()}


def brief(d):
    return {k: v for k, v in d.items() if k != "p_abnormal"} if d else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["lodo", "split", "final"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--noise")
    ap.add_argument("--own")
    ap.add_argument("--band", nargs=2, type=float)
    ap.add_argument("--band-norm", choices=["on", "off"])
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--tag", default="run")
    a = ap.parse_args()
    if a.band:                       # override preprocess.py for this run (the filter and the mel bands depend on it)
        pp.BAND_HZ = tuple(a.band)
        pp._SOS = pp.butter(5, pp.BAND_HZ, btype="bandpass", fs=pp.TARGET_SR, output="sos")
        pp._MEL_FB = pp._mel_filterbank()
    band_norm = (a.band_norm == "on") if a.band_norm else getattr(pp, "BAND_NORM", False)
    print(f"device {DEV}, band {pp.BAND_HZ}, per-band normalisation {band_norm}", flush=True)

    df, x, y, rec = load_icbhi(a.data)
    dev = df.device.values[rec]
    pat = df.patient.values[rec]
    per_dev = {d: int((dev == d).sum()) for d in np.unique(dev)}
    print(f"{len(df)} recordings, {len(x)} windows, classes {np.bincount(y, minlength=4).tolist()}, devices {per_dev}", flush=True)
    noise = load_folder(a.noise)[0] if a.noise else None
    own = load_folder(a.own) if a.own else None
    if noise is not None:
        print(f"{len(noise)} noise windows from our device", flush=True)
    if own is not None:
        print(f"{len(own[0])} windows of healthy people on our device: {own[2]}", flush=True)
    out = {"band": list(pp.BAND_HZ), "band_norm": band_norm, "noise": bool(a.noise), "epochs": a.epochs}
    part = icbhi.patient_split(df).loc[pat].values             # every window's patient -> train / val / test

    if a.mode == "lodo":
        for d in np.unique(dev):
            tr, va, te = (dev != d) & (part != "val"), (dev != d) & (part == "val"), dev == d
            if tr.sum() < 200 or te.sum() < 50:
                continue
            net, mel = train(x[tr], y[tr], (x[va], y[va]), noise, band_norm, a.epochs, log=f"[without {d}] ")
            out[d] = scores(predict(net, mel, x[te]), y[te])
            if own:
                out[d]["own_healthy"] = brief(false_alarms(net, mel, own))
            print(f"== left out {d}: {json.dumps(out[d])}", flush=True)
    else:
        tr, va, te = part == "train", part == "val", part == "test"
        if a.mode == "final":
            tr = tr | te             # the shipped model also learns from the test patients; honest scores come from 'split'
        net, mel = train(x[tr], y[tr], (x[va], y[va]), noise, band_norm, a.epochs)
        out["val"] = scores(predict(net, mel, x[va]), y[va])
        if a.mode == "split":
            out["test"] = scores(predict(net, mel, x[te]), y[te])
        if own:
            out["own_healthy"] = false_alarms(net, mel, own)
        print(json.dumps({k: brief(v) if k == "own_healthy" else v for k, v in out.items()}, indent=1), flush=True)
        if a.mode == "final":
            w = Path(__file__).parent / "weights"
            w.mkdir(exist_ok=True)
            export(net, w / "resp_cnn.onnx", f"respirai-{a.tag}", metrics={k: v for k, v in out.items() if k != "own_healthy"})
            torch.save(net.state_dict(), w / "resp_cnn.pt")
            print("exported", w / "resp_cnn.onnx", flush=True)
    res = Path(__file__).parent / "results"
    res.mkdir(exist_ok=True)
    (res / f"{a.mode}_{a.tag}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
