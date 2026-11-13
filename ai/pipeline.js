// The AI's sound processing, in JavaScript, so the phone gives the same answers as the Python server.
// A line-by-line port of ai/preprocess.py (4 kHz, band-pass, 4 s windows, log-mel), ai/quality.py and
// combine() / softmax() from ai/inference.py. Change those and this together: app/tests/ai.html runs both
// on the same recordings (on GitHub, see .github/workflows/web-app.yml) and fails if they disagree.
// No DOM here: it runs in the analysis worker (worker.js) and in the tests.

// ---------- preprocess.py ----------
export const DEVICE_SR = 8000;
export const TARGET_SR = 4000;
export const BAND_HZ = [100, 1800];
export const WINDOW_S = 4.0;
export const HOP_S = 2.0;
export const N_FFT = 256;
export const HOP_LENGTH = 64;
export const N_MELS = 64;
export const WINDOW_SAMPLES = WINDOW_S * TARGET_SR;
export const HOP_SAMPLES = HOP_S * TARGET_SR;
export const N_FRAMES = Math.floor(WINDOW_SAMPLES / HOP_LENGTH) + 1;
export const CLASSES = ["normal", "crackles", "wheezes", "both"];   // ai/icbhi.py

// The settings a trained model depends on, as saved next to its weights (preprocess.params()).
export const params = () => ({ TARGET_SR, BAND_HZ: [...BAND_HZ], WINDOW_S, N_FFT, HOP_LENGTH, N_MELS });

const f32 = Math.fround;

// int16 PCM -> float32 in [-1, 1]; float audio stays as it is.
export function toFloat(audio) {
  return audio instanceof Int16Array ? Float32Array.from(audio, (v) => v / 32768) : Float32Array.from(audio);
}

const gcd = (a, b) => (b ? gcd(b, a % b) : a);

export function resample(audio, srIn, srOut) {
  if (srIn === srOut) return Float32Array.from(audio);
  const g = gcd(srIn, srOut);
  return resamplePoly(audio, srOut / g, srIn / g);
}

// scipy.signal.resample_poly(x, up, down) with its defaults: a Kaiser (beta 5) windowed low-pass FIR,
// zero padding at the ends, output aligned the way SciPy aligns it.
function resamplePoly(x, up, down) {
  const nIn = x.length;
  const nOut = Math.ceil((nIn * up) / down);
  const maxRate = Math.max(up, down), halfLen = 10 * maxRate;
  const h = firwin(2 * halfLen + 1, 1 / maxRate).map((v) => f32(f32(v) * up));   // SciPy casts the filter to float32
  const nPrePad = down - (halfLen % down);
  const nPreRemove = Math.floor((halfLen + nPrePad) / down);
  const outputLen = (lenH) => Math.floor(((nIn - 1) * up + lenH - 1) / down) + 1;
  let nPostPad = 0;
  while (outputLen(h.length + nPrePad + nPostPad) < nOut + nPreRemove) nPostPad++;
  const hp = [...new Array(nPrePad).fill(0), ...h, ...new Array(nPostPad).fill(0)];
  const out = new Float32Array(nOut);
  for (let i = 0; i < nOut; i++) {   // upfirdn: upsample, filter, keep every down-th sample
    const k = (i + nPreRemove) * down;
    let acc = 0;
    for (let j = 0; j < hp.length && j <= k; j++) {
      const n = k - j;
      if (n % up) continue;
      const m = n / up;
      if (m < nIn) acc += hp[j] * x[m];
    }
    out[i] = acc;
  }
  return out;
}

// scipy.signal.firwin(numtaps, cutoff, window=("kaiser", 5.0)): low-pass, scaled to a gain of 1 at 0 Hz.
function firwin(numtaps, cutoff, beta = 5.0) {
  const alpha = 0.5 * (numtaps - 1);
  const sinc = (v) => (v === 0 ? 1 : Math.sin(Math.PI * v) / (Math.PI * v));
  const h = Array.from({ length: numtaps }, (_, n) => {
    const m = n - alpha;
    const w = besselI0(beta * Math.sqrt(1 - ((n - alpha) / alpha) ** 2)) / besselI0(beta);
    return cutoff * sinc(cutoff * m) * w;
  });
  const sum = h.reduce((a, b) => a + b, 0);
  return h.map((v) => v / sum);
}

function besselI0(x) {   // power series; converges fast for the small arguments used here
  let sum = 1, term = 1;
  for (let k = 1; k < 50; k++) {
    term *= (x / (2 * k)) ** 2;
    sum += term;
    if (term < sum * 1e-17) break;
  }
  return sum;
}

// butter(5, BAND_HZ, "bandpass", fs=TARGET_SR, output="sos"), worked out the way SciPy does
// (analogue prototype -> band-pass -> bilinear transform). The sections are grouped differently from
// SciPy's zpk2sos, but they make the same filter, and sosfiltfilt below gives the same output.
function butterBandpassSos(order, [lo, hi], fs) {
  const c = (re, im = 0) => ({ re, im });
  const add = (a, b) => c(a.re + b.re, a.im + b.im), sub = (a, b) => c(a.re - b.re, a.im - b.im);
  const mul = (a, b) => c(a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re);
  const div = (a, b) => { const d = b.re * b.re + b.im * b.im; return c((a.re * b.re + a.im * b.im) / d, (a.im * b.re - a.re * b.im) / d); };
  const sqrt = (a) => {   // principal square root, as NumPy
    const r = Math.hypot(a.re, a.im);
    const re = Math.sqrt((r + a.re) / 2), im = Math.sqrt(Math.max(0, (r - a.re) / 2));
    return c(re, a.im < 0 ? -im : im);
  };
  const warp = (f) => 2 * 2 * Math.tan((Math.PI * ((2 * f) / fs)) / 2);   // fs normalised to 2, as iirfilter does
  const w1 = warp(lo), w2 = warp(hi), bw = w2 - w1, wo2 = w1 * w2;
  const proto = Array.from({ length: order }, (_, i) => {   // buttap: -exp(j*pi*m/(2N)), m = -N+1, -N+3, ... N-1
    const m = -order + 1 + 2 * i;
    return c(-Math.cos((Math.PI * m) / (2 * order)), -Math.sin((Math.PI * m) / (2 * order)));
  });
  const poles = [];
  for (const p of proto) {   // lp2bp_zpk: every pole becomes two
    const pl = mul(p, c(bw / 2)), root = sqrt(sub(mul(pl, pl), c(wo2)));
    poles.push(add(pl, root), sub(pl, root));
  }
  // lp2bp gain bw^N; bilinear (fs2 = 4): zeros at +1 (from the N zeros at 0) and -1 (N), poles (4 + p) / (4 - p)
  let k = c(bw ** order);
  for (let i = 0; i < order; i++) k = div(mul(k, c(4)), c(1));   // prod(fs2 - z) over the N zeros at 0
  const zPoles = poles.map((p) => { k = div(k, sub(c(4), p)); return div(add(c(4), p), sub(c(4), p)); });
  const gain = k.re;
  // one zero at +1 and one at -1 per section; poles: conjugate pairs, then the real ones two by two
  const pairs = [];
  const complex = zPoles.filter((p) => p.im > 1e-12), real = zPoles.filter((p) => Math.abs(p.im) <= 1e-12).map((p) => p.re);
  for (const p of complex) pairs.push([1, -2 * p.re, p.re * p.re + p.im * p.im]);
  for (let i = 0; i + 1 < real.length; i += 2) pairs.push([1, -(real[i] + real[i + 1]), real[i] * real[i + 1]]);
  return pairs.map((a, i) => [...(i === 0 ? [gain, 0, -gain] : [1, 0, -1]), ...a]);
}

const SOS = butterBandpassSos(5, BAND_HZ, TARGET_SR);
const PADLEN = 3 * (2 * SOS.length + 1);   // sosfiltfilt's default: no section has a zero b2 or a2

// sosfilt_zi: each section's steady state for a constant input of 1.
const SOS_ZI = (() => {
  let scale = 1;
  return SOS.map(([b0, b1, b2, , a1, a2]) => {
    const B0 = b1 - a1 * b0, B1 = b2 - a2 * b0;   // lfilter_zi for one biquad
    const z0 = (B0 + B1) / (1 + a1 + a2), z1 = B1 - a2 * z0;
    const zi = [scale * z0, scale * z1];
    scale *= (b0 + b1 + b2) / (1 + a1 + a2);
    return zi;
  });
})();

function sosfilt(x, x0) {   // direct form II transposed, starting from the steady state for x0
  const y = new Float64Array(x.length);
  const z = SOS_ZI.map(([a, b]) => [a * x0, b * x0]);
  for (let n = 0; n < x.length; n++) {
    let v = x[n];
    for (let s = 0; s < SOS.length; s++) {
      const [b0, b1, b2, , a1, a2] = SOS[s], zs = z[s];
      const out = b0 * v + zs[0];
      zs[0] = b1 * v - a1 * out + zs[1];
      zs[1] = b2 * v - a2 * out;
      v = out;
    }
    y[n] = v;
  }
  return y;
}

// scipy.signal.sosfiltfilt with its defaults: odd extension at both ends, forwards then backwards.
function sosfiltfilt(x) {
  const n = x.length, edge = PADLEN;
  if (n <= edge) throw new Error(`sosfiltfilt needs more than ${edge} samples`);
  const ext = new Float64Array(n + 2 * edge);
  for (let i = 0; i < edge; i++) ext[i] = f32(2 * x[0] - x[edge - i]);                // float32, like NumPy's odd_ext
  ext.set(x, edge);
  for (let i = 0; i < edge; i++) ext[edge + n + i] = f32(2 * x[n - 1] - x[n - 2 - i]);
  const forward = sosfilt(ext, ext[0]).reverse();
  const back = sosfilt(forward, forward[0]).reverse();
  return Float32Array.from(back.subarray(edge, edge + n));
}

// Raw audio at any rate -> band-passed float32 audio at TARGET_SR.
export function clean(audio, sr) {
  const x = resample(toFloat(audio), sr, TARGET_SR);
  return x.length > 30 ? sosfiltfilt(x) : x;
}

// Clean audio -> 4 s windows with a 2 s hop, and their start times in seconds.
// Shorter than one window: zero-padded to a single window. The tail is never dropped.
export function windows(audio) {
  if (audio.length <= WINDOW_SAMPLES) {
    const w = new Float32Array(WINDOW_SAMPLES);
    w.set(audio);
    return { windows: [w], starts: [0] };
  }
  const starts = [];
  for (let s = 0; s <= audio.length - WINDOW_SAMPLES; s += HOP_SAMPLES) starts.push(s);
  if (starts[starts.length - 1] + WINDOW_SAMPLES < audio.length) starts.push(audio.length - WINDOW_SAMPLES);
  return { windows: starts.map((s) => audio.slice(s, s + WINDOW_SAMPLES)), starts: starts.map((s) => s / TARGET_SR) };
}

// Slaney mel scale (linear below 1 kHz, logarithmic above), as librosa's default.
const hzToMel = (f) => (f >= 1000 ? 15 + Math.log(Math.max(f, 1e-9) / 1000) / (Math.log(6.4) / 27) : f / (200 / 3));
const melToHz = (m) => (m >= 15 ? 1000 * Math.exp((Math.log(6.4) / 27) * (m - 15)) : m * (200 / 3));
const linspace = (a, b, n) => Array.from({ length: n }, (_, i) => (i === n - 1 ? b : a + i * ((b - a) / (n - 1))));

// (N_MELS, N_FFT/2 + 1) triangular filters between BAND_HZ, area-normalised, float32.
const MEL_FB = (() => {
  const bins = N_FFT / 2 + 1;
  const fftHz = linspace(0, TARGET_SR / 2, bins);
  const edges = linspace(hzToMel(BAND_HZ[0]), hzToMel(BAND_HZ[1]), N_MELS + 2).map(melToHz);
  return Array.from({ length: N_MELS }, (_, m) => {
    const norm = 2 / (edges[m + 2] - edges[m]);
    return Float32Array.from(fftHz, (f) => {
      const lower = (f - edges[m]) / (edges[m + 1] - edges[m]);
      const upper = (edges[m + 2] - f) / (edges[m + 2] - edges[m + 1]);
      return Math.max(0, Math.min(lower, upper)) * norm;
    });
  });
})();

// Periodic Hann window, float32 (get_window("hann", N_FFT, fftbins=True)).
const HANN = Float32Array.from({ length: N_FFT }, (_, n) => 0.5 + 0.5 * Math.cos(-Math.PI + n * ((2 * Math.PI) / N_FFT)));

// Power spectrum of one real frame (radix-2 FFT), bins 0..N/2.
const BITS = Math.log2(N_FFT);
const REV = Uint16Array.from({ length: N_FFT }, (_, i) => parseInt(i.toString(2).padStart(BITS, "0").split("").reverse().join(""), 2));
const COS = Float64Array.from({ length: N_FFT / 2 }, (_, i) => Math.cos((-2 * Math.PI * i) / N_FFT));
const SIN = Float64Array.from({ length: N_FFT / 2 }, (_, i) => Math.sin((-2 * Math.PI * i) / N_FFT));
function powerSpectrum(frame, out) {
  const re = new Float64Array(N_FFT), im = new Float64Array(N_FFT);
  for (let i = 0; i < N_FFT; i++) re[REV[i]] = frame[i];
  for (let size = 2; size <= N_FFT; size *= 2) {
    const half = size / 2, step = N_FFT / size;
    for (let start = 0; start < N_FFT; start += size) {
      for (let j = 0; j < half; j++) {
        const a = start + j, b = a + half, wr = COS[j * step], wi = SIN[j * step];
        const tr = re[b] * wr - im[b] * wi, ti = re[b] * wi + im[b] * wr;
        re[b] = re[a] - tr; im[b] = im[a] - ti;
        re[a] += tr; im[a] += ti;
      }
    }
  }
  for (let k = 0; k <= N_FFT / 2; k++) out[k] = re[k] * re[k] + im[k] * im[k];
}

// One clean window -> standardised log-mel spectrogram, N_MELS x N_FRAMES, row by row (mel-major), float32.
export function logMel(window) {
  const padded = new Float32Array(WINDOW_SAMPLES + N_FFT);   // centre each frame on its time step
  padded.set(window.subarray(0, WINDOW_SAMPLES), N_FFT / 2);
  const db = new Float64Array(N_MELS * N_FRAMES);
  const frame = new Float32Array(N_FFT), power = new Float64Array(N_FFT / 2 + 1);
  for (let t = 0; t < N_FRAMES; t++) {
    for (let i = 0; i < N_FFT; i++) frame[i] = padded[t * HOP_LENGTH + i] * HANN[i];   // float32 product, as NumPy
    powerSpectrum(frame, power);
    for (let m = 0; m < N_MELS; m++) {
      const fb = MEL_FB[m];
      let e = 0;
      for (let k = 0; k < power.length; k++) e += fb[k] * power[k];
      db[m * N_FRAMES + t] = 10 * Math.log10(Math.max(e, 1e-10));
    }
  }
  let mean = 0;
  for (const v of db) mean += v;
  mean /= db.length;
  let variance = 0;
  for (const v of db) variance += (v - mean) ** 2;
  const std = Math.sqrt(variance / db.length);
  return Float32Array.from(db, (v) => (v - mean) / (std + 1e-6));
}

// Whole recording -> one spectrogram per window, ready for the model: [n, 1, N_MELS, N_FRAMES] flattened.
export function recordingToSpecs(audio, sr) {
  const { windows: wins, starts } = windows(clean(audio, sr));
  const specs = new Float32Array(wins.length * N_MELS * N_FRAMES);
  wins.forEach((w, i) => specs.set(logMel(w), i * N_MELS * N_FRAMES));
  return { specs, count: wins.length, starts };
}

// ---------- inference.py ----------
const TOP_K = 2;   // how many of the most abnormal windows decide the recording

export function softmax(logits, classes = CLASSES.length) {
  const out = new Float64Array(logits.length);
  for (let r = 0; r < logits.length / classes; r++) {
    const row = Array.from(logits.subarray(r * classes, (r + 1) * classes));
    const max = Math.max(...row), e = row.map((v) => Math.exp(v - max)), sum = e.reduce((a, b) => a + b, 0);
    e.forEach((v, c) => { out[r * classes + c] = v / sum; });
  }
  return out;
}

// (n windows x 4) probabilities -> one probability per class for the whole recording.
export function combine(probs, classes = CLASSES.length) {
  const n = probs.length / classes;
  const crackle = [], wheeze = [];
  for (let r = 0; r < n; r++) {
    const p = (c) => probs[r * classes + c];
    crackle.push(p(1) + p(3));
    wheeze.push(p(2) + p(3));
  }
  const k = Math.min(TOP_K, n);
  const top = (list) => list.sort((a, b) => a - b).slice(-k).reduce((a, b) => a + b, 0) / k;
  const c = top(crackle), w = top(wheeze);
  return { normal: (1 - c) * (1 - w), crackles: c * (1 - w), wheezes: (1 - c) * w, both: c * w };
}

export const round = (v, digits) => Math.round(v * 10 ** digits) / 10 ** digits;

// Probabilities -> the answer, as Analyzer.analyze shapes it.
export function finding(probs) {
  const best = Object.keys(probs).reduce((a, b) => (probs[b] > probs[a] ? b : a));
  return { finding: best, confidence: round(probs[best], 2),
    probabilities: Object.fromEntries(Object.entries(probs).map(([k, v]) => [k, round(v, 3)])) };
}

// ---------- quality.py ----------
const SILENCE_DBFS = [-70.0, -55.0];   // below the first: silent; above the second: fine
const CLIP_LEVEL = 0.98;
const CLIP_FRAC_MAX = 0.01;            // 1 % clipped samples -> score 0
const GAP_MS = 10;                     // a run of exact zeros this long is a dropped BLE packet
const GAP_FRAC_MAX = 0.20;             // 20 % of the recording missing -> score 0
const FRAME_MS = 50;
const SPIKE_RATIO = 6.0;               // a frame this much louder than usual is a bump or rub
const SPIKE_FRAC_MAX = 0.25;
const MIN_SECONDS = 5.0;

const ramp = (x, lo, hi) => Math.min(1, Math.max(0, (x - lo) / (hi - lo)));

// -> { score 0-1, checks }
export function quality(audio, sr) {
  const x = toFloat(audio);
  if (!x.length) return { score: 0, checks: { empty: 0 } };
  const checks = {};

  let sumSq = 0;
  for (const v of x) sumSq += v * v;
  const rms = Math.sqrt(sumSq / x.length) + 1e-12;
  checks.level = ramp(20 * Math.log10(rms), ...SILENCE_DBFS);

  let clipped = 0;
  for (const v of x) if (Math.abs(v) >= CLIP_LEVEL) clipped++;
  checks.clipping = 1 - ramp(clipped / x.length, 0, CLIP_FRAC_MAX);

  // Dropped packets arrive as exact zeros (the app fills gaps with silence).
  let gapSamples = 0, run = 0;
  const minRun = (sr * GAP_MS) / 1000;
  for (let i = 0; i <= x.length; i++) {
    if (i < x.length && x[i] === 0) { run++; continue; }
    if (run >= minRun) gapSamples += run;
    run = 0;
  }
  checks.dropouts = 1 - ramp(gapSamples / x.length, 0, GAP_FRAC_MAX);

  const frame = Math.max(1, Math.floor((sr * FRAME_MS) / 1000));
  const n = Math.floor(x.length / frame);
  if (n >= 4) {
    const frameRms = Array.from({ length: n }, (_, f) => {
      let s = 0;
      for (let i = f * frame; i < (f + 1) * frame; i++) s += x[i] * x[i];
      return Math.sqrt(s / frame);
    });
    const sorted = [...frameRms].sort((a, b) => a - b);
    const median = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
    const spikes = frameRms.filter((v) => v > SPIKE_RATIO * (median + 1e-9)).length / n;
    checks.handling_noise = 1 - ramp(spikes, 0, SPIKE_FRAC_MAX);
  }

  checks.length = ramp(x.length / sr, 0, MIN_SECONDS);

  const score = Object.values(checks).reduce((a, b) => a * b, 1);
  return { score: round(score, 2), checks: Object.fromEntries(Object.entries(checks).map(([k, v]) => [k, round(v, 2)])) };
}
