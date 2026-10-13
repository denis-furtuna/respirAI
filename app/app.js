// respirAI web app: one screen at a time. Connect → before we start → each place → analysing → results.
import { BleDevice, CMD, MockDevice } from "./device.js";
import { PacketStream, Recording, SAMPLE_RATE, play, toWav } from "./audio.js";

// n is the contract number (0-6). x/y place the dot on the front or back drawing.
// Left/right are the patient's: on the front view their left is on the viewer's right.
const POINTS = {
  Tc: { n: 0, view: "front", x: 80, y: 56, title: "Base of the neck", where: "In the middle, just above the breastbone." },
  Al: { n: 1, view: "front", x: 101, y: 76, title: "Upper chest, left", where: "Just below your left collarbone." },
  Ar: { n: 2, view: "front", x: 59, y: 76, title: "Upper chest, right", where: "Just below your right collarbone." },
  Pl: { n: 3, view: "back", x: 64, y: 88, title: "Upper back, left", where: "Left of the spine, at shoulder-blade height. Ask someone to help you." },
  Pr: { n: 4, view: "back", x: 96, y: 88, title: "Upper back, right", where: "Right of the spine, at shoulder-blade height. Ask someone to help you." },
  Ll: { n: 5, view: "front", x: 112, y: 110, title: "Left side", where: "On your left side, a hand's width below the armpit." },
  Lr: { n: 6, view: "front", x: 48, y: 110, title: "Right side", where: "On your right side, a hand's width below the armpit." },
};
const ORDER = ["Tc", "Al", "Ar", "Ll", "Lr", "Pl", "Pr"];  // front, sides, back
const PLACE_SECONDS = 8;
const BREATH_IN = 4, BREATH_OUT = 5;   // seconds; matches the device's LED guide
const MIN_QUALITY = 0.4;               // contract 2: below this, ask for a re-record
const RING = 2 * Math.PI * 92;         // circumference of the dial's progress ring
const ABNORMAL = { crackles: "Possible crackles", wheezes: "Possible wheezes", both: "Possible crackles and wheezes" };
const ICONS = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  alert: '<path d="M12 7v6m0 3.5v.5"/>',
  retry: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v3.7h3.7"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- settings (remembered on this phone; for the team, behind the icon) ----------
const settings = { server: `http://${location.hostname || "localhost"}:8000`, seconds: 15, demo: "" };
try { Object.assign(settings, JSON.parse(localStorage.getItem("respirai") || "{}")); } catch (e) { /* private mode */ }

function bindSetting(id, parse) {
  $(id).value = settings[id];
  $(id).addEventListener("change", () => {
    settings[id] = parse($(id).value);
    try { localStorage.setItem("respirai", JSON.stringify(settings)); } catch (e) { /* not essential */ }
    if (!$("sReady").hidden) showReady();
  });
}
bindSetting("server", (v) => v.trim().replace(/\/+$/, ""));
bindSetting("seconds", (v) => Math.min(20, Math.max(5, Number(v) || 15)));
bindSetting("demo", (v) => v);

// ---------- device + audio ----------
let device = null;
let recording = null;
let lastAudioAt = 0;
const ring = new Float32Array(SAMPLE_RATE);  // last second, for the small waveform
let ringPos = 0;

const stream = new PacketStream((samples) => {
  for (const s of samples) {
    ring[ringPos] = s / 32768;
    ringPos = (ringPos + 1) % ring.length;
  }
  lastAudioAt = performance.now();
  if (recording) recording.add(samples);
});

async function connect(Kind) {
  hideNotice();
  const old = device;
  device = null;
  if (old) old.disconnect();
  const d = new Kind({
    onPacket: (view) => stream.push(view),
    onStatus: showDeviceStatus,
    onDisconnect: () => { if (d === device) lostDevice(); },
  });
  $("btnConnect").disabled = $("btnPractice").disabled = true;
  try {
    await d.connect();
    stream.reset();
    device = d;
    await d.send(CMD.start);   // stream all the time, so the signal is live while placing the chest piece
    afterConnect();
  } catch (e) {
    if (e.name !== "NotFoundError") showNotice(e.message);  // NotFoundError: the device picker was closed
  } finally {
    $("btnConnect").disabled = $("btnPractice").disabled = false;
  }
}

function lostDevice() {
  device = null;
  $("battery").hidden = true;
  showNotice("The device disconnected. Switch it on and connect again. Your recordings so far are kept.");
  if (running) cancel = true;
  else if (!$("sReady").hidden) show("sConnect");   // results stay on screen if they are showing
}

// After connecting: carry on where the user was.
function afterConnect() {
  if (session && !remaining().length) showResults();
  else showReady();
}

function needDevice() {
  if (device) return false;
  showNotice("Connect the device first.");
  show("sConnect");
  return true;
}

function send(bytes) {
  if (device) device.send(bytes).catch((e) => console.warn("Command failed:", e.message));
}

function showDeviceStatus({ battery, state }) {
  $("battery").hidden = battery > 100;   // 255 = the device can't measure it (no battery sense wired)
  $("battery").textContent = `Battery ${battery}%`;
  if (state === 2) showNotice("The device reported a problem. Switch it off and on again.");
}

// ---------- session ----------
let session = null;   // { id, results: {code: response}, audio: {code: Int16Array}, pending: [] }
let current = null;
let running = false, cancel = false, skip = false;

const remaining = () => (session ? ORDER.filter((c) => !session.results[c]) : ORDER);

function newSession() {
  session = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), results: {}, audio: {}, pending: [] };
}

async function runSession(codes) {
  running = true;
  cancel = false;
  hideNotice();
  show("sPoint");
  let lock = null;   // keep the screen on; never wait for it, so a slow answer can't hold up the session
  navigator.wakeLock?.request("screen").then((l) => { lock = l; }).catch(() => {});
  try {
    for (const code of codes) {
      await recordPoint(code);
      if (cancel) break;
    }
    if (!cancel) await finish();
  } finally {
    running = false;
    current = null;
    recording = null;
    if (lock) lock.release();
    send(CMD.idle);
    if (cancel) {
      if (!device) show("sConnect");
      else if (remaining().length) showReady();
      else showResults();
    }
  }
}

async function recordPoint(code) {
  const p = POINTS[code];
  current = code;
  $("pointStep").textContent = `Place ${ORDER.indexOf(code) + 1} of ${ORDER.length}`;
  $("pointTitle").textContent = p.title;
  $("pointWhere").textContent = p.where;
  drawProgress();
  drawBody($("body"), p.view, (c) => (c === code ? "here" : ""));

  // 1. Time to place the chest piece (or tap "start now").
  $("btnNow").hidden = false;
  $("breath").style.transform = "scale(0.62)";
  const placed = await countdown(PLACE_SECONDS, (t, total) => dial(Math.ceil(total - t), "Recording starts in", t / total), true);
  $("btnNow").hidden = true;
  if (!placed) return;

  // 2. Record while the circle paces the breathing.
  recording = new Recording(settings.seconds);
  send(CMD.guide(p.n));   // the device's LEDs start breathing now, in step with the circle on screen
  const finished = await countdown(settings.seconds, (t, total) => {
    const phase = t % (BREATH_IN + BREATH_OUT);
    const inhale = phase < BREATH_IN;
    const k = inhale ? phase / BREATH_IN : 1 - (phase - BREATH_IN) / BREATH_OUT;
    $("breath").style.transform = `scale(${0.62 + 0.38 * (1 - Math.cos(Math.PI * k)) / 2})`;
    dial(inhale ? "Breathe in" : "Breathe out", `${Math.ceil(total - t)} seconds left`, t / total);
  });
  const samples = recording.samples.slice();
  recording = null;
  if (!finished) return;
  send(CMD.done);

  if (!settings.demo && samples.length < 2 * SAMPLE_RATE) {   // demo mode sends no audio, so it needs none
    session.results[code] = { finding: "error", error: "No sound arrived from the device. Check it is switched on, then record again." };
    return;
  }
  session.pending.push(analyze(code, samples));
}

// Runs onTick about 20 times a second; resolves false if the session was stopped.
async function countdown(seconds, onTick, skippable = false) {
  const start = performance.now();
  skip = false;
  for (;;) {
    const t = (performance.now() - start) / 1000;
    if (cancel || t >= seconds || (skippable && skip)) break;
    onTick(t, seconds);
    updateSignal();
    await sleep(50);
  }
  return !cancel;
}

function dial(main, sub, progress) {
  $("dialMain").textContent = main;
  $("dialMain").classList.toggle("word", typeof main === "string");
  $("dialSub").textContent = sub;
  $("ringBar").style.strokeDashoffset = RING * (1 - progress);
}

async function analyze(code, samples) {
  session.audio[code] = samples;
  session.results[code] = { finding: "pending" };
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
}

function describeFetchError(e) {
  if (e.name === "TimeoutError") return "The AI server took too long to answer.";
  if (e instanceof TypeError) return `Can't reach the AI server at ${settings.server}. Check the address in Settings.`;
  return e.message;
}

async function finish() {
  current = null;
  show("sBusy");
  await Promise.all([Promise.all(session.pending), sleep(1500)]);  // a short, calm pause even when the server is fast
  showResults();
}

// ---------- screens ----------
function show(id) {
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.id !== id; });
  window.scrollTo(0, 0);
}

function showReady() {
  const left = remaining().length;
  const partial = session && left > 0 && left < ORDER.length;
  $("readyTitle").textContent = partial ? "Ready to continue" : "Before we start";
  $("btnBegin").textContent = partial ? `Continue (${left} ${left === 1 ? "place" : "places"} left)` : "Begin";
  $("readyNote").hidden = !settings.demo;
  $("readyNote").textContent = `Demo mode is on: the results will show a ${settings.demo} example.`;
  show("sReady");
}

function verdict(r) {
  if (!r) return { cls: "todo", chip: "Not recorded" };
  if (r.finding === "pending") return { cls: "todo", chip: "Still analysing" };
  if (r.finding === "error") return { cls: "unclear", chip: "Please record again", detail: r.error };
  if (r.finding === "unusable" || r.quality < MIN_QUALITY) return { cls: "unclear", chip: "Please record again", detail: "The sound was not clear enough." };
  const detail = `${Math.round(r.confidence * 100)}% confidence${r.demo ? " · example recording" : ""}`;
  if (r.finding === "normal") return { cls: "ok", chip: "Clear", detail };
  return { cls: "warn", chip: ABNORMAL[r.finding] || r.finding, detail };
}

function showResults() {
  const classes = ORDER.map((c) => verdict(session.results[c]).cls);
  const [cls, mark, title, text] =
    classes.includes("warn") ? ["warn", "alert", "Some unusual sounds were heard", "Please show these results to a doctor."] :
    classes.includes("unclear") || classes.includes("todo") ? ["unclear", "retry", "Some places need another recording", "Tap “Record again” next to them below."] :
    ["ok", "check", "No unusual sounds were heard", "If you feel unwell, see a doctor anyway."];
  $("overall").className = `overall ${cls}`;
  $("overallIcon").innerHTML = icon(mark);
  $("overallTitle").textContent = title;
  $("overallText").textContent = text;

  const stateOf = (c) => verdict(session.results[c]).cls;
  drawBody($("mapFront"), "front", stateOf);
  drawBody($("mapBack"), "back", stateOf);

  $("resultList").replaceChildren(...ORDER.map((code) => {
    const v = verdict(session.results[code]);
    const li = document.createElement("li");
    li.className = v.cls;
    li.innerHTML = `<span class="mark">${icon(v.cls === "ok" ? "check" : v.cls === "warn" ? "alert" : "retry")}</span>
      <div class="what"><b></b><span class="chip"></span><small></small></div><div class="acts"></div>`;
    li.querySelector("b").textContent = POINTS[code].title;
    li.querySelector(".chip").textContent = v.chip;
    li.querySelector("small").textContent = v.detail || "";
    const acts = li.querySelector(".acts");
    if (session.audio[code] && session.audio[code].length) {
      acts.append(button(`${icon("play")} Listen`, () => play(session.audio[code])));
    }
    acts.append(button(`${icon("retry")} Record again`, () => { if (!needDevice()) runSession([code]); }));
    return li;
  }));
  show("sResults");
}

function button(html, onClick) {
  const b = document.createElement("button");
  b.className = "btn secondary small";
  b.innerHTML = html;
  b.addEventListener("click", onClick);
  return b;
}

function drawProgress() {
  $("progress").innerHTML = ORDER.map((c) =>
    `<i class="${c === current ? "now" : session.results[c] ? "done" : ""}"></i>`).join("");
}

// Front or back outline with its points; stateOf(code) gives each dot's class.
function drawBody(svg, view, stateOf) {
  const [leftLabel, rightLabel] = view === "front" ? ["Right", "Left"] : ["Left", "Right"];
  svg.innerHTML = `<use href="#silhouette" class="sil"/>
    <text x="18" y="152">${leftLabel}</text><text x="142" y="152">${rightLabel}</text>
    <text x="80" y="187" class="view">${view === "front" ? "Front" : "Back"}</text>` +
    ORDER.filter((c) => POINTS[c].view === view).map((c) => {
      const { x, y } = POINTS[c];
      const s = stateOf(c);
      return `<g class="pt ${s}"><circle class="halo" cx="${x}" cy="${y}" r="8"/><circle cx="${x}" cy="${y}" r="${s === "here" ? 8 : 6}"/></g>`;
    }).join("");
}

function showNotice(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
}

function hideNotice() {
  $("notice").hidden = true;
}

// ---------- small live waveform: shows sound is coming through ----------
const canvas = $("wave");
const ctx = canvas.getContext("2d");
let gain = 1;

function updateSignal() {
  const hearing = performance.now() - lastAudioAt < 1000;
  $("signalText").textContent = hearing ? "Sound is coming through" : "No sound. Check the device is switched on.";
  $("signalText").parentElement.classList.toggle("none", !hearing && !settings.demo);
}

function drawWave() {
  requestAnimationFrame(drawWave);
  if ($("sPoint").hidden) return;
  const w = Math.round(canvas.clientWidth * devicePixelRatio);
  const h = Math.round(canvas.clientHeight * devicePixelRatio);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = getComputedStyle(canvas).color;
  ctx.lineWidth = devicePixelRatio;
  ctx.beginPath();
  const perPixel = ring.length / w;
  let peak = 0;
  for (let x = 0; x < w; x++) {
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
    ? `Signal: ${stream.received} packets, ${stream.lost} lost, ${stream.packetSamples * 2 + 2} bytes each`
    : "Signal: no audio received yet";
}, 1000);

// ---------- buttons ----------
$("btnConnect").addEventListener("click", () => connect(BleDevice));
$("btnPractice").addEventListener("click", () => connect(MockDevice));
$("btnBegin").addEventListener("click", () => {
  if (needDevice()) return;
  if (!session || !remaining().length) newSession();
  runSession(remaining());
});
$("btnNow").addEventListener("click", () => { skip = true; });
$("btnStop").addEventListener("click", () => { cancel = true; });
$("btnRestart").addEventListener("click", () => { newSession(); showReady(); });
$("btnSettings").addEventListener("click", () => $("settings").showModal());
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
