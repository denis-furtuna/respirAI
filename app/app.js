// respirAI web app: connect, guide the user point by point, upload, show results.
import { BleDevice, CMD, MockDevice } from "./device.js";
import { PacketStream, Recording, SAMPLE_RATE, play, toWav } from "./audio.js";

// n is the contract number (0-6); x/y place the dot on the torso drawing.
// Left/right are the patient's: on the front view their left is on the viewer's right.
const POINTS = {
  Tc: { n: 0, name: "Trachea", where: "the base of the neck, in the middle", x: 80, y: 44 },
  Al: { n: 1, name: "Front left", where: "the upper chest, left side", x: 97, y: 72 },
  Ar: { n: 2, name: "Front right", where: "the upper chest, right side", x: 63, y: 72 },
  Pl: { n: 3, name: "Back left", where: "the upper back, left side", x: 223, y: 92 },
  Pr: { n: 4, name: "Back right", where: "the upper back, right side", x: 257, y: 92 },
  Ll: { n: 5, name: "Side left", where: "the left side, below the armpit", x: 106, y: 104 },
  Lr: { n: 6, name: "Side right", where: "the right side, below the armpit", x: 54, y: 104 },
};
const ORDER = ["Tc", "Al", "Ar", "Ll", "Lr", "Pl", "Pr"];  // front, sides, back
const PLACE_SECONDS = 5;
const MIN_QUALITY = 0.4;   // contract 2: below this, ask for a re-record
const ABNORMAL = { crackles: "Possible crackles", wheezes: "Possible wheezes", both: "Possible crackles and wheezes" };

const $ = (id) => document.getElementById(id);

// ---------- settings (remembered on this phone) ----------
const settings = { server: `http://${location.hostname || "localhost"}:8000`, seconds: 15, demo: "" };
try { Object.assign(settings, JSON.parse(localStorage.getItem("respirai") || "{}")); } catch (e) { /* private mode */ }

function bindSetting(id, parse) {
  $(id).value = settings[id];
  $(id).addEventListener("change", () => {
    settings[id] = parse($(id).value);
    try { localStorage.setItem("respirai", JSON.stringify(settings)); } catch (e) { /* not essential */ }
    showIdle();
  });
}
bindSetting("server", (v) => v.trim().replace(/\/+$/, ""));
bindSetting("seconds", (v) => Math.min(20, Math.max(5, Number(v) || 15)));
bindSetting("demo", (v) => v);

// ---------- device + audio ----------
let device = null;
let recording = null;
const ring = new Float32Array(SAMPLE_RATE * 2);  // last 2 s, for the waveform
let ringPos = 0;

const stream = new PacketStream((samples) => {
  for (const s of samples) {
    ring[ringPos] = s / 32768;
    ringPos = (ringPos + 1) % ring.length;
  }
  if (recording) recording.add(samples);
});

async function connect(Kind) {
  hideError();
  const old = device;
  device = null;
  if (old) old.disconnect();
  const d = new Kind({
    onPacket: (view) => stream.push(view),
    onStatus: showDeviceStatus,
    onDisconnect: () => { if (d === device) lostDevice(); },
  });
  setBadge("Connecting…");
  try {
    await d.connect();
    stream.reset();
    device = d;
    await d.send(CMD.start);   // stream all the time, so the waveform is live while placing the chest piece
    setBadge(`Connected · ${d.name}`, "ok");
  } catch (e) {
    setBadge("Not connected", "bad");
    if (e.name !== "NotFoundError") showError(e.message);  // NotFoundError: the user closed the device picker
  }
  showIdle();
}

function lostDevice() {
  device = null;
  setBadge("Disconnected", "bad");
  if (running) {
    cancel = true;
    showError("The device disconnected. Reconnect it, then press Continue to record the remaining points.");
  }
  showIdle();
}

function send(bytes) {
  if (device) device.send(bytes).catch((e) => console.warn("Command failed:", e.message));
}

function showDeviceStatus({ battery, state }) {
  $("battery").hidden = false;
  $("battery").textContent = `Battery ${battery}%`;
  if (state === 2) showError("The device reported an error. Try switching it off and on.");
}

// ---------- the guided session ----------
let session = null;   // { id, results: {code: response}, audio: {code: Int16Array}, pending: [] }
let current = null;   // chest point being recorded now
let running = false;
let cancel = false;

function newSession() {
  session = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), results: {}, audio: {}, pending: [] };
  $("results").hidden = true;
}

async function runSession(codes) {
  running = true;
  cancel = false;
  hideError();
  showIdle();
  const lock = await navigator.wakeLock?.request("screen").catch(() => null);  // keep the screen on
  try {
    for (const code of codes) {
      await recordPoint(code);
      if (cancel) return;
    }
    await finish();
  } finally {
    running = false;
    current = null;
    recording = null;
    if (lock) lock.release();
    send(CMD.idle);
    showIdle();
  }
}

async function recordPoint(code) {
  const p = POINTS[code];
  const step = `${ORDER.indexOf(code) + 1} of ${ORDER.length} · ${p.name}`;
  current = code;
  drawTorso();
  send(CMD.guide(p.n));
  setStep(step, `Place the chest piece on ${p.where}`, "Hold it still. Recording starts after the countdown.");
  if (!(await countdown(PLACE_SECONDS))) return;

  recording = new Recording(settings.seconds);
  setStep(step, "Breathe deeply through your mouth", "Slow, deep breaths. Keep the chest piece still.");
  const finished = await countdown(settings.seconds);
  const samples = recording.samples.slice();
  recording = null;
  current = null;
  if (!finished) return;
  send(CMD.done);
  session.pending.push(analyze(code, samples));
}

// Counts down on screen; resolves false if the session was stopped.
async function countdown(seconds) {
  const end = performance.now() + seconds * 1000;
  $("clock").hidden = false;
  while (!cancel && performance.now() < end) {
    $("clock").textContent = Math.ceil((end - performance.now()) / 1000);
    await new Promise((r) => setTimeout(r, 100));
  }
  $("clock").hidden = true;
  return !cancel;
}

async function analyze(code, samples) {
  session.audio[code] = samples;
  session.results[code] = { finding: "pending" };
  drawTorso();
  const form = new FormData();
  form.append("point", code);
  form.append("session_id", session.id);
  if (settings.demo) {
    form.append("demo", "true");
    form.append("demo_case", settings.demo);
  } else {
    form.append("audio", toWav(samples), `${code}.wav`);
  }
  try {
    const res = await fetch(`${settings.server}/analyze`, { method: "POST", body: form, signal: AbortSignal.timeout(30000) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `The AI server answered with error ${res.status}.`);
    session.results[code] = body;
  } catch (e) {
    session.results[code] = { finding: "error", error: describeFetchError(e) };
  }
  drawTorso();
}

function describeFetchError(e) {
  if (e.name === "TimeoutError") return "The AI server took too long to answer.";
  if (e instanceof TypeError) return `Can't reach the AI server at ${settings.server}. Check that it is running and the address in Settings.`;
  return e.message;
}

async function finish() {
  setStep("All points recorded", "Analysing the recordings…", "This takes a few seconds.");
  $("busy").hidden = false;
  await Promise.all(session.pending);
  $("busy").hidden = true;
  showResults();
}

// ---------- what the user sees ----------
function verdict(r) {
  if (!r || r.finding === "pending") return { text: r ? "Analysing…" : "Not recorded", cls: "todo" };
  if (r.finding === "error") return { text: r.error, cls: "unclear" };
  if (r.finding === "unusable" || r.quality < MIN_QUALITY) return { text: "Recording unclear. Please record again.", cls: "unclear" };
  if (r.finding === "normal") return { text: "No abnormal sounds found", cls: "normal" };
  return { text: `${ABNORMAL[r.finding] || r.finding}. See a doctor.`, cls: "abnormal" };
}

function showResults() {
  const verdicts = ORDER.map((code) => verdict(session.results[code]).cls);
  $("overall").textContent =
    verdicts.includes("abnormal") ? "Possible abnormal sounds found. Please see a doctor." :
    verdicts.includes("unclear") ? "Some points need to be recorded again." :
    "No abnormal sounds found at the recorded points.";

  $("resultList").replaceChildren(...ORDER.map((code) => {
    const r = session.results[code];
    const v = verdict(r);
    const li = document.createElement("li");
    li.className = v.cls;
    const title = document.createElement("b");
    title.textContent = POINTS[code].name + (r && r.demo ? " (demo example)" : "");
    const detail = document.createElement("span");
    detail.className = "muted small";
    detail.textContent = v.text + (v.cls === "normal" || v.cls === "abnormal" ? ` · ${Math.round(r.confidence * 100)}% confidence` : "");
    const actions = document.createElement("div");
    actions.className = "actions";
    if (session.audio[code] && session.audio[code].length) actions.append(button("Play", () => play(session.audio[code])));
    actions.append(button(r ? "Redo" : "Record", () => runSession([code])));
    li.append(title, actions, detail);
    return li;
  }));
  $("results").hidden = false;
  drawTorso();
}

function button(label, onClick) {
  const b = document.createElement("button");
  b.textContent = label;
  b.addEventListener("click", onClick);
  b.disabled = running;
  return b;
}

function drawTorso() {
  $("dots").innerHTML = ORDER.map((code) => {
    const { x, y } = POINTS[code];
    const cls = code === current ? "now" : verdict(session && session.results[code]).cls;
    return `<g class="dot ${cls}"><circle class="ring" cx="${x}" cy="${y}" r="7"/><circle cx="${x}" cy="${y}" r="7"/></g>`;
  }).join("");
}

function setStep(eyebrow, title, text) {
  $("stepEyebrow").textContent = eyebrow;
  $("stepTitle").textContent = title;
  $("stepText").textContent = text;
}

// The step card and buttons when nothing is being recorded.
function showIdle() {
  const ready = device || settings.demo;   // demo mode sends no audio, so it works without the device
  const left = session ? ORDER.filter((c) => !session.results[c]) : ORDER;
  $("btnStart").disabled = !ready;
  $("btnStart").hidden = running;
  $("btnStart").textContent = session && left.length && left.length < ORDER.length ? "Continue" : "Start screening";
  $("btnStop").hidden = !running;
  document.querySelectorAll("#resultList button").forEach((b) => { b.disabled = running; });
  if (!running) {
    setStep(`${ORDER.length} chest points · ${settings.seconds} s each`,
      ready ? (settings.demo ? `Demo mode: ${settings.demo} examples` : "Ready when you are") : "Connect the device to begin",
      ready ? "Sit upright and breathe normally. The app tells you where to place the chest piece."
            : "Or use the mock device to try the app without hardware.");
  }
  drawTorso();
}

function setBadge(text, cls = "") {
  $("badge").textContent = text;
  $("badge").className = `badge ${cls}`;
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}

function hideError() {
  $("error").hidden = true;
}

// ---------- live waveform ----------
const canvas = $("wave");
const ctx = canvas.getContext("2d");
let gain = 1;

function drawWave() {
  requestAnimationFrame(drawWave);
  const w = Math.round(canvas.clientWidth * devicePixelRatio);
  const h = Math.round(canvas.clientHeight * devicePixelRatio);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = getComputedStyle(canvas).color;
  ctx.beginPath();
  const perPixel = ring.length / w;
  let peak = 0;
  for (let x = 0; x < w; x++) {   // min/max per pixel column: cheap and shows every click
    let lo = 0, hi = 0;
    for (let i = Math.floor(x * perPixel); i < Math.floor((x + 1) * perPixel); i++) {
      const v = ring[(ringPos + i) % ring.length];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    peak = Math.max(peak, hi, -lo);
    ctx.moveTo(x + 0.5, h / 2 - hi * gain * h / 2);
    ctx.lineTo(x + 0.5, h / 2 - lo * gain * h / 2 + 1);
  }
  ctx.stroke();
  gain += (Math.min(50, 0.9 / Math.max(peak, 1e-4)) - gain) * 0.05;  // auto-gain: quiet breath sounds stay visible
}
requestAnimationFrame(drawWave);

setInterval(() => {
  $("stats").textContent = stream.received
    ? `${stream.received} packets · ${stream.lost} lost · ${stream.packetSamples * 2 + 2} bytes each`
    : "No audio yet";
}, 500);

// ---------- buttons ----------
$("btnConnect").addEventListener("click", () => connect(BleDevice));
$("btnMock").addEventListener("click", () => connect(MockDevice));
$("btnStop").addEventListener("click", () => { cancel = true; });
$("btnStart").addEventListener("click", () => {
  if (!session || ORDER.every((c) => session.results[c])) newSession();
  runSession(ORDER.filter((c) => !session.results[c]));
});
$("btnTest").addEventListener("click", async () => {
  $("testResult").textContent = "Checking…";
  try {
    const res = await fetch(`${settings.server}/health`, { signal: AbortSignal.timeout(5000) });
    const h = await res.json();
    $("testResult").textContent = `OK · model ${h.model_version}${h.dummy ? " (dummy answers)" : ""} · ${h.demo_clips} demo clips`;
  } catch (e) {
    $("testResult").textContent = describeFetchError(e);
  }
});

showIdle();
