// respirAI web app: one screen at a time. Connect → before we start → each place → analysing → results.
import { BleDevice, CMD } from "./device.js";
import { PacketStream, Recording, SAMPLE_RATE, play, stopPlayback, toWav } from "./audio.js";
import { fakeBluetooth } from "./fake-bluetooth.js";

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
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ?fakebt puts a fake device behind "Connect the device" (options in fake-bluetooth.js).
const params = new URLSearchParams(location.search);
const bluetooth = params.has("fakebt") ? (window.fakeBt = fakeBluetooth(Object.fromEntries(params))) : navigator.bluetooth;

// ---------- settings (remembered on this phone; for the team, behind the icon) ----------
const settings = { server: `http://${location.hostname || "localhost"}:8000`, seconds: 15, demo: "" };
try { Object.assign(settings, JSON.parse(localStorage.getItem("respirai") || "{}")); } catch (e) { /* private mode */ }

for (const [id, parse] of [
  ["server", (v) => v.trim().replace(/\/+$/, "")],
  ["seconds", (v) => Math.min(20, Math.max(5, Number(v) || 15))],
  ["demo", (v) => v],
]) {
  $(id).value = settings[id];
  $(id).addEventListener("change", () => {
    $(id).value = settings[id] = parse($(id).value);   // show the value actually used (e.g. 50 s -> 20 s)
    try { localStorage.setItem("respirai", JSON.stringify(settings)); } catch (e) { /* not essential */ }
    if (!$("sReady").hidden) showReady();
  });
}

// ---------- device + audio ----------
let device = null, recording = null, lastAudioAt = 0, batteryWarned = false;
const ring = new Float32Array(SAMPLE_RATE);  // last second, for the small waveform
let ringPos = 0;

const stream = new PacketStream((samples) => {
  for (const s of samples) ring[ringPos++ % ring.length] = s / 32768;
  ringPos %= ring.length;
  lastAudioAt = performance.now();
  if (recording) recording.add(samples);
});

async function connect(bt, button) {
  notice();
  batteryWarned = false;
  const old = device;
  device = null;
  if (old) old.disconnect();
  const d = new BleDevice(bt, {
    onPacket: (view) => stream.push(view),
    onStatus: ({ battery, state }) => {
      $("battery").hidden = battery > 100;   // 255 = the device can't measure it (no battery sense wired)
      $("battery").textContent = `Battery ${battery}%`;
      if (state === 2) notice("The device reported a problem. Switch it off and on again.");
      else if (battery <= 15 && !batteryWarned) {
        batteryWarned = true;
        notice(`The device battery is low (${battery}%). Charge it soon.`);
      }
    },
    onDisconnect: () => { if (d === device) lostDevice(); },
  });
  const label = button.textContent;
  button.textContent = "Connecting…";
  $("btnConnect").disabled = $("btnPractice").disabled = true;
  try {
    await d.connect();
    stream.reset();
    device = d;
    await d.send(CMD.start);              // stream all the time, so the signal is live while placing the chest piece
    d.send(CMD.status).catch(() => {});   // battery now, not in 2 s
    if (session && !remaining().length) showResults();   // carry on where the user was
    else showReady();
  } catch (e) {
    if (e.name !== "NotFoundError") notice(e.message);  // NotFoundError: the device picker was closed
  } finally {
    button.textContent = label;
    $("btnConnect").disabled = $("btnPractice").disabled = false;
  }
}

function lostDevice() {
  device = null;
  $("battery").hidden = true;
  notice("The device disconnected. Switch it on and connect again. Your recordings so far are kept.");
  if (running) cancel = true;
  else if (!$("sReady").hidden) show("sConnect");   // results stay on screen if they are showing
}

function needDevice() {
  if (device) return false;
  notice("Connect the device first.");
  show("sConnect");
  return true;
}

function send(bytes) {
  if (device) device.send(bytes).catch((e) => console.warn("Command failed:", e.message));
}

// ---------- session ----------
let session = null;   // { id, results: {code: response}, audio: {code: Int16Array}, pending: [] }
let running = false, cancel = false, skip = false, lock = null;

// Keep the screen on during a session, also after switching away and back. Never waited for.
const keepAwake = () => navigator.wakeLock?.request("screen").then((l) => { if (running) lock = l; else l.release(); }).catch(() => {});
document.addEventListener("visibilitychange", () => { if (running && !document.hidden) keepAwake(); });
addEventListener("beforeunload", (e) => { if (running) { e.preventDefault(); e.returnValue = ""; } });   // ask before leaving mid-recording

const remaining = () => (session ? ORDER.filter((c) => !session.results[c]) : ORDER);
const newSession = () => { session = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), results: {}, audio: {}, pending: [] }; };

async function runSession(codes) {
  running = true;
  cancel = false;
  notice();
  show("sPoint");
  keepAwake();
  try {
    for (const code of codes) if (!cancel) await recordPoint(code);
    if (!cancel) {
      show("sBusy");
      await Promise.all([...session.pending, sleep(1500)]);  // a short, calm pause even when the server is fast
      showResults();
    }
  } finally {
    running = false;
    recording = null;
    if (lock) lock.release();
    lock = null;
    send(CMD.idle);
    if (cancel) !device ? show("sConnect") : remaining().length ? showReady() : showResults();
  }
}

async function recordPoint(code) {
  const p = POINTS[code];
  $("pointStep").textContent = `Place ${ORDER.indexOf(code) + 1} of ${ORDER.length}`;
  $("pointTitle").textContent = p.title;
  $("pointWhere").textContent = p.where;
  $("progress").innerHTML = ORDER.map((c) => `<i class="${c === code ? "now" : session.results[c] ? "done" : ""}"></i>`).join("");
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
  } else {
    session.pending.push(analyze(code, samples));
  }
}

// Runs onTick about 20 times a second; resolves false if the session was stopped.
async function countdown(seconds, onTick, skippable = false) {
  const start = performance.now();
  skip = false;
  for (let t = 0; !cancel && t < seconds && !(skippable && skip); t = (performance.now() - start) / 1000) {
    onTick(t, seconds);
    const hearing = performance.now() - lastAudioAt < 1000;
    $("signalText").textContent = hearing ? "Sound is coming through" : "No sound. Check the device is switched on.";
    $("signalText").parentElement.classList.toggle("none", !hearing && !settings.demo);
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

// ---------- screens ----------
function show(id) {
  stopPlayback();
  playing = null;
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.id !== id; });
  window.scrollTo(0, 0);
}

function notice(message) {   // no message: hide it
  $("notice").textContent = message || "";
  $("notice").hidden = !message;
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
  return r.finding === "normal" ? { cls: "ok", chip: "Clear", detail } : { cls: "warn", chip: ABNORMAL[r.finding] || r.finding, detail };
}

const MARK = { ok: "check", warn: "alert", unclear: "retry", todo: "retry" };
const OVERALL = {
  warn: ["Some unusual sounds were heard", "Please show these results to a doctor."],
  unclear: ["Some places need another recording", "Tap “Record again” next to them below."],
  ok: ["No unusual sounds were heard", "If you feel unwell, see a doctor anyway."],
};

function showResults() {
  const cls = (c) => verdict(session.results[c]).cls;
  const all = ORDER.map(cls);
  const overall = all.includes("warn") ? "warn" : all.some((c) => c === "unclear" || c === "todo") ? "unclear" : "ok";
  $("overall").className = `overall ${overall}`;
  $("overallIcon").innerHTML = icon(MARK[overall]);
  [$("overallTitle").textContent, $("overallText").textContent] = OVERALL[overall];
  drawBody($("mapFront"), "front", cls);
  drawBody($("mapBack"), "back", cls);

  $("resultList").replaceChildren(...ORDER.map((code) => {
    const v = verdict(session.results[code]);
    const li = document.createElement("li");
    li.className = v.cls;
    li.innerHTML = `<span class="mark">${icon(MARK[v.cls])}</span><div class="what"><b></b><span class="chip"></span><small></small></div><div class="acts"></div>`;
    [li.querySelector("b").textContent, li.querySelector(".chip").textContent, li.querySelector("small").textContent] = [POINTS[code].title, v.chip, v.detail || ""];
    const audio = session.audio[code], r = session.results[code];
    if (audio && audio.length && !(r && r.demo)) {   // a demo result was about an example, not this recording
      const b = button("play", "Listen", () => listen(code));
      b.dataset.listen = code;
      li.querySelector(".acts").append(b);
    }
    li.querySelector(".acts").append(button("retry", "Record again", () => { if (!needDevice()) runSession([code]); }));
    return li;
  }));
  resetRestart();
  show("sResults");
}

// Listen / Stop: one recording at a time.
let playing = null;
function listen(code) {
  if (playing === code) {
    stopPlayback();
    playing = null;
  } else {
    play(session.audio[code], () => { playing = null; listenButtons(); });
    playing = code;
  }
  listenButtons();
}

function listenButtons() {
  document.querySelectorAll("[data-listen]").forEach((b) => {
    const on = b.dataset.listen === playing;
    b.innerHTML = on ? `${icon("stop")} Stop` : `${icon("play")} Listen`;
    b.setAttribute("aria-pressed", on);
  });
}

// "Start a new check" clears the results, so it asks for a second tap.
let restartTimer = null;
function resetRestart() {
  clearTimeout(restartTimer);
  restartTimer = null;
  $("btnRestart").textContent = "Start a new check";
}

function button(iconName, label, onClick) {
  const b = document.createElement("button");
  b.className = "btn secondary small";
  b.innerHTML = `${icon(iconName)} ${label}`;
  b.addEventListener("click", onClick);
  return b;
}

// Front or back outline with its points; stateOf(code) gives each dot's class.
function drawBody(svg, view, stateOf) {
  const [left, right] = view === "front" ? ["Right", "Left"] : ["Left", "Right"];
  svg.innerHTML = `<use href="#silhouette" class="sil"/><text x="18" y="152">${left}</text><text x="142" y="152">${right}</text>
    <text x="80" y="187" class="view">${view === "front" ? "Front" : "Back"}</text>` +
    ORDER.filter((c) => POINTS[c].view === view).map((c) => {
      const { x, y } = POINTS[c], s = stateOf(c);
      return `<g class="pt ${s}"><circle class="halo" cx="${x}" cy="${y}" r="8"/><circle cx="${x}" cy="${y}" r="${s === "here" ? 8 : 6}"/></g>`;
    }).join("");
}

// ---------- small live waveform: shows sound is coming through ----------
const canvas = $("wave"), ctx = canvas.getContext("2d");
let gain = 1;

(function drawWave() {
  requestAnimationFrame(drawWave);
  if ($("sPoint").hidden) return;
  const w = Math.round(canvas.clientWidth * devicePixelRatio), h = Math.round(canvas.clientHeight * devicePixelRatio);
  if (canvas.width !== w || canvas.height !== h) [canvas.width, canvas.height] = [w, h];
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = getComputedStyle(canvas).color;
  ctx.lineWidth = devicePixelRatio;
  ctx.beginPath();
  let peak = 0;
  for (let x = 0; x < w; x++) {   // min/max per pixel column
    let lo = 0, hi = 0;
    for (let i = Math.floor((x * ring.length) / w); i < Math.floor(((x + 1) * ring.length) / w); i++) {
      const v = ring[(ringPos + i) % ring.length];
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    peak = Math.max(peak, hi, -lo);
    ctx.moveTo(x + 0.5, h / 2 - (hi * gain * h) / 2);
    ctx.lineTo(x + 0.5, h / 2 - (lo * gain * h) / 2 + 1);
  }
  ctx.stroke();
  gain += (Math.min(50, 0.9 / Math.max(peak, 1e-4)) - gain) * 0.05;  // auto-gain: quiet breath sounds stay visible
})();

setInterval(() => {
  $("stats").textContent = stream.received
    ? `Signal: ${stream.received} packets, ${stream.lost} lost, ${stream.packetSamples * 2 + 2} bytes each`
    : "Signal: no audio received yet";
}, 1000);

// ---------- buttons ----------
$("btnConnect").addEventListener("click", () => connect(bluetooth, $("btnConnect")));
$("btnPractice").addEventListener("click", () => connect(fakeBluetooth({ battery: 87, drop: 0.005 }), $("btnPractice")));
$("btnBegin").addEventListener("click", () => {
  if (needDevice()) return;
  if (!session || !remaining().length) newSession();
  runSession(remaining());
});
$("btnNow").addEventListener("click", () => { skip = true; });
$("btnStop").addEventListener("click", () => { cancel = true; });
$("btnRestart").addEventListener("click", () => {
  if (!restartTimer) {
    $("btnRestart").textContent = "Tap again to clear these results";
    restartTimer = setTimeout(resetRestart, 4000);
    return;
  }
  resetRestart();
  newSession();
  showReady();
});
$("btnSettings").addEventListener("click", () => $("settings").showModal());
$("settings").addEventListener("click", (e) => { if (e.target === $("settings")) $("settings").close(); });   // tap outside closes
$("btnTest").addEventListener("click", async () => {
  $("btnTest").disabled = true;
  $("testResult").textContent = "Checking…";
  try {
    const h = await (await fetch(`${settings.server}/health`, { signal: AbortSignal.timeout(5000) })).json();
    $("testResult").textContent = `OK · model ${h.model_version}${h.dummy ? " (dummy answers)" : ""} · ${h.demo_clips} demo clips`;
  } catch (e) {
    $("testResult").textContent = describeFetchError(e);
  } finally {
    $("btnTest").disabled = false;
  }
});
