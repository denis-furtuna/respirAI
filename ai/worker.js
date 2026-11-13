// The AI on the phone: what ai/service.py does on the server, in a worker so the screen never stutters.
// Same answers and the same shapes as POST /analyze (contract 2):
//   no model in app/model/   -> dummy mode, like the server without weights: fixed answers, real quality check
//   app/model/resp_cnn.onnx  -> the trained model, run with ONNX Runtime Web (+ resp_cnn.json, from the Kaggle export)
//   app/model/demo_clips/    -> demo mode with a model: the example recordings (manifest.json, like ai/demo_clips/)
// Messages in: { id, type: "analyze", point, samples: Int16Array (8 kHz), demo, demoCase } or { id, type: "health" }.
// Messages out: { id, result } or { id, error: { status, message } } (status as the server's HTTP status).
import { CLASSES, DEVICE_SR, combine, finding, params, quality, recordingToSpecs, softmax, N_FRAMES, N_MELS } from "./pipeline.js";

const MODEL = new URL(new URL(self.location.href).searchParams.get("model") || "../model/", import.meta.url);   // ?model=: tests/ai.html
const ORT_VERSION = "1.30.0";   // the copy in vendor/ is put there by the build (see .github/workflows); same version
const ORT_LOCAL = new URL("../vendor/onnxruntime-web/", import.meta.url);
// Only for development on a laptop (the plain-http dev servers), which has no local copy. The phone app and the
// website (https) never load code from anywhere else: they ship their own copy, and without it the AI says so.
const ORT_CDN = self.location.protocol === "http:" ? `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/` : null;
const UNUSABLE_BELOW = 0.4;   // contract: below this the app asks for a re-record
const MIN_S = 2.0, MAX_S = 60.0;

class ServiceError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

// Loads once, on the first request: the model's description, then (only if there is a model) ONNX Runtime and the weights.
let loaded = null;
const load = () => (loaded ||= (async () => {
  const meta = await fetchJson(new URL("resp_cnn.json", MODEL));
  const demo = (await fetchJson(new URL("demo_clips/manifest.json", MODEL))) || {};
  if (!meta) return { session: null, modelVersion: "dummy-0.0", demo };
  if (JSON.stringify(meta.classes) !== JSON.stringify(CLASSES)) throw new Error(`Model classes ${meta.classes} differ from ${CLASSES}.`);
  const want = params(), got = meta.preprocess || {};
  if (Object.keys(want).some((k) => JSON.stringify(got[k]) !== JSON.stringify(want[k]))) {
    throw new Error(`Model was trained with preprocessing ${JSON.stringify(got)}, but pipeline.js has ${JSON.stringify(want)}.`);
  }
  const ort = await loadOrt();
  const session = await ort.InferenceSession.create(new URL("resp_cnn.onnx", MODEL).href, { executionProviders: ["wasm"] });
  return { ort, session, input: session.inputNames[0], output: session.outputNames[0], modelVersion: meta.model_version, demo };
})().catch((e) => { loaded = null; throw e; }));   // a failure is retried on the next request

async function fetchJson(url) {   // null when the file isn't there
  const res = await fetch(url, { cache: "no-cache" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${url.pathname}: HTTP ${res.status}`);
  const text = await res.text();
  return text.trim() ? JSON.parse(text) : null;
}

async function loadOrt() {
  for (const base of [ORT_LOCAL.href, ORT_CDN].filter(Boolean)) {
    try {
      const ort = await import(`${base}ort.wasm.min.mjs`);
      Object.assign(ort.env.wasm, { wasmPaths: base, numThreads: 1, proxy: false });   // already in a worker; no threads without cross-origin isolation
      return ort;
    } catch (e) {
      console.warn(`ONNX Runtime not at ${base}:`, e.message);
    }
  }
  throw new Error("ONNX Runtime Web could not be loaded.");
}

// Analyzer.analyze: every 4 s window through the model at once, then the windows combined.
async function analyzeAudio(m, audio, sr) {
  const { specs, count } = recordingToSpecs(audio, sr);
  const tensor = new m.ort.Tensor("float32", specs, [count, 1, N_MELS, N_FRAMES]);
  const logits = (await m.session.run({ [m.input]: tensor }))[m.output].data;
  return finding(combine(softmax(logits)));
}

// A demo clip: 16-bit mono PCM WAV, as the notebook writes them (ai/icbhi.py as_device) -> { samples, sr }
async function readClip(name) {
  const res = await fetch(new URL(`demo_clips/${name}`, MODEL));
  if (!res.ok) throw new ServiceError(404, `Demo clip ${name} is missing.`);
  const view = new DataView(await res.arrayBuffer());
  let pos = 12, sr = 0;
  while (pos + 8 <= view.byteLength) {   // walk the chunks: fmt for the format, data for the samples
    const id = String.fromCharCode(...new Uint8Array(view.buffer, pos, 4)), size = view.getUint32(pos + 4, true);
    if (id === "fmt ") {
      const [format, channels, bits] = [view.getUint16(pos + 8, true), view.getUint16(pos + 10, true), view.getUint16(pos + 22, true)];
      if (format !== 1 || channels !== 1 || bits !== 16) throw new ServiceError(400, `${name} is not 16-bit mono PCM.`);
      sr = view.getUint32(pos + 12, true);
    }
    if (id === "data" && sr) {
      const n = Math.floor(Math.min(size, view.byteLength - pos - 8) / 2), samples = new Int16Array(n);
      for (let i = 0; i < n; i++) samples[i] = view.getInt16(pos + 8 + 2 * i, true);
      return { samples, sr };
    }
    pos += 8 + size + (size & 1);
  }
  throw new ServiceError(400, `${name} has no audio.`);
}

// service.analyze, minus the session bookkeeping (the app keeps its own).
async function analyze({ point, samples, demo, demoCase }) {
  const t0 = performance.now();
  const m = await load();
  let q, result;
  if (demo) {
    if (!CLASSES.includes(demoCase)) throw new ServiceError(400, `Demo mode needs demo_case, one of ${CLASSES.join(", ")}.`);
    if (!m.session) {
      [q, result] = [0.95, { finding: demoCase, confidence: 0.9 }];
    } else {
      const name = m.demo[`${demoCase}/${point}`];
      if (!name) throw new ServiceError(404, `No demo clip for ${demoCase} at ${point}.`);
      const clip = await readClip(name);
      q = quality(clip.samples, clip.sr).score;
      result = await analyzeAudio(m, clip.samples, clip.sr);
    }
  } else {
    const seconds = samples.length / DEVICE_SR;
    if (!(seconds >= MIN_S && seconds <= MAX_S)) throw new ServiceError(400, `Recording is ${seconds.toFixed(1)} s; send between ${MIN_S} and ${MAX_S} s.`);
    q = quality(samples, DEVICE_SR).score;
    if (q < UNUSABLE_BELOW) result = { finding: "unusable", confidence: 0.0 };
    else if (!m.session) result = { finding: "normal", confidence: 0.5 };
    else result = await analyzeAudio(m, samples, DEVICE_SR);
  }
  return { point, finding: result.finding, confidence: result.confidence, quality: q, model_version: m.modelVersion,
    latency_ms: Math.round(performance.now() - t0), ...(demo ? { demo: true } : {}) };
}

async function health() {
  const m = await load();
  return { status: "ok", model_version: m.modelVersion, dummy: !m.session, demo_clips: Object.keys(m.demo).length };
}

self.onmessage = async ({ data }) => {
  try {
    self.postMessage({ id: data.id, result: data.type === "health" ? await health() : await analyze(data) });
  } catch (e) {
    console.warn("On-phone AI:", e);
    self.postMessage({ id: data.id, error: { status: e.status || 500, message: e.message } });
  }
};
