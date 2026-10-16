// respirAI web app: one screen at a time. Connect → before we start → each place → analysing → results.
import { BleDevice, CMD } from "./device.js";
import { PacketStream, Recording, SAMPLE_RATE, play, stopPlayback, toWav } from "./audio.js";
import { fakeBluetooth } from "./fake-bluetooth.js";
import { LANGUAGES, current, dateTime, detect, percent, setLanguage, t } from "./i18n/index.js";
import { analyzeHere, healthHere } from "./ai/local.js";
import { native } from "./native.js";   // null in a browser; the phone app's own Bluetooth, speech... (see native.js)

// n is the contract number (0-6). x/y place the dot on the front or back drawing; names are in i18n/ (point.Tc.title…).
// Left/right are the patient's: on the front view their left is on the viewer's right.
const POINTS = {
  Tc: { n: 0, view: "front", x: 80, y: 56 },
  Al: { n: 1, view: "front", x: 101, y: 76 },
  Ar: { n: 2, view: "front", x: 59, y: 76 },
  Pl: { n: 3, view: "back", x: 64, y: 88 },
  Pr: { n: 4, view: "back", x: 96, y: 88 },
  Ll: { n: 5, view: "front", x: 112, y: 110 },
  Lr: { n: 6, view: "front", x: 48, y: 110 },
};
const title = (code) => t(`point.${code}.title`);
const ORDER = ["Tc", "Al", "Ar", "Ll", "Lr", "Pl", "Pr"];  // front, sides, back
const PLACE_SECONDS = 8;
const BREATH_IN = 4, BREATH_OUT = 5;   // seconds. Mirrored in firmware/respirai/config.h (BREATH_IN_MS, BREATH_OUT_MS): change both
const BREATH = BREATH_IN + BREATH_OUT; // one breath; also the practice breath before each recording
const MIN_QUALITY = 0.4;               // contract 2: below this, ask for a re-record
const RING = 2 * Math.PI * 92;         // circumference of the dial's progress ring
const FINDINGS = ["normal", "crackles", "wheezes", "both", "unusable"];
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
const calm = matchMedia("(prefers-reduced-motion: reduce)");

// ?fakebt puts a fake device behind "Connect the device" (options in fake-bluetooth.js).
const params = new URLSearchParams(location.search);
const bluetooth = params.has("fakebt") ? (window.fakeBt = fakeBluetooth(Object.fromEntries(params))) : native ? native.bluetooth : navigator.bluetooth;

// ---------- settings (remembered on this phone, behind the icon; voice is on the "before we start" screen) ----------
// server "": the AI runs on this phone (ai/local.js), no server or internet needed. An address: that AI server
// instead (contract 2: ai/server.py, or app/dev/dev_server.py), e.g. the laptop's own address when it serves the app.
const settings = { server: "", seconds: 18, demo: "", textSize: "100", theme: "auto", voice: false, lang: "", welcomed: false };
try { Object.assign(settings, JSON.parse(localStorage.getItem("respirai") || "{}")); } catch (e) { /* private mode */ }
if (native) {   // the phone app always analyses on the phone: nothing it records ever leaves it (Google Play's data safety form)
  settings.server = "";
  $("server").closest("label").hidden = true;
}
const api = (path) => settings.server + path;

const darkSystem = matchMedia("(prefers-color-scheme: dark)");
function saveSettings() {
  try { localStorage.setItem("respirai", JSON.stringify(settings)); } catch (e) { /* not essential */ }
  document.documentElement.style.fontSize = `${settings.textSize}%`;
  const theme = settings.theme === "auto" ? (darkSystem.matches ? "dark" : "light") : settings.theme;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = theme === "dark" ? "#0b1620" : "#f3f6f9";
  native?.bars(theme);   // the phone app: light or dark status bar icons to match
  $("btnVoice").setAttribute("aria-pressed", settings.voice);
}
saveSettings();
darkSystem.addEventListener("change", saveSettings);

for (const [id, parse] of [
  ["textSize", (v) => v],
  ["theme", (v) => v],
  ["server", (v) => v.trim().replace(/\/+$/, "")],
  ["seconds", (v) => Math.min(20, Math.max(5, Number(v) || 18))],   // 18 s = two whole breaths, ends at the bottom of one
  ["demo", (v) => v],
]) {
  $(id).value = settings[id];
  $(id).addEventListener("change", () => {
    $(id).value = settings[id] = parse($(id).value);   // show the value actually used (e.g. 50 s -> 20 s)
    saveSettings();
    if (!$("sReady").hidden) showReady();
  });
}

// ---------- spoken instructions (for when the eyes are not on the screen, e.g. placing on the back) ----------
// Never while recording: the stethoscope would pick it up. The phone app speaks with Android's own voice.
function say(text) {
  if (!settings.voice) return Promise.resolve();
  if (native) return Promise.race([native.speak(text, current().locale).catch(() => {}), sleep(8000)]);
  if (!window.speechSynthesis) return Promise.resolve();
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  Object.assign(u, { lang: current().locale, rate: 0.9 });
  const spoken = new Promise((r) => { u.onend = u.onerror = r; });
  speechSynthesis.speak(u);
  return Promise.race([spoken, sleep(8000)]);
}
const hush = () => (native ? native.hush() : window.speechSynthesis?.cancel());

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

// Say up front when this phone can't connect, rather than after a tap.
let connectNoteKey = null;
function connectNote(key) {
  connectNoteKey = key;
  $("connectNote").textContent = key ? t(key) : "";
  $("connectNote").hidden = !key;
}
if (!bluetooth) {
  connectNote("connect.noBluetooth");
  $("btnConnect").disabled = true;
  console.info("Web Bluetooth needs Chrome, and https:// or localhost. For http:// on a phone, add the address to " +
    "chrome://flags/#unsafely-treat-insecure-origin-as-secure.");
} else if (bluetooth.getAvailability) {
  const off = (on) => connectNote(on ? null : "connect.bluetoothOff");
  bluetooth.getAvailability().then(off, () => {});
  bluetooth.addEventListener?.("availabilitychanged", (e) => off(e.value));
}

let latest = null;   // the last device the user connected; a reconnect gives up when they pick another
let battery = null;  // last level the device reported

function showBattery() {
  $("battery").hidden = battery === null || battery > 100;   // 255 = the device can't measure it (no battery sense wired)
  $("battery").textContent = t("device.battery", { pct: percent(battery / 100) });
  $("battery").classList.toggle("low", battery <= 15);
}

async function connect(bt, button) {
  notice();
  batteryWarned = false;
  const old = device;
  device = null;
  if (old) old.disconnect();
  const d = (latest = new BleDevice(bt, {
    onPacket: (view) => stream.push(view),
    onStatus: (status) => {
      battery = status.battery;
      showBattery();
      if (status.state === 2) notice("device.problem");   // the firmware's error: its microphone sends no sound
      else if (noticeShown[0] === "device.problem") notice();   // it hears again: the message goes away by itself
      else if (battery <= 15 && !batteryWarned) {
        batteryWarned = true;
        notice("device.lowBattery", { pct: percent(battery / 100) });
      }
    },
    onDisconnect: () => { if (d === device) lostDevice(d); },
  }));
  button.textContent = t("connect.connecting");
  $("btnConnect").disabled = $("btnPractice").disabled = true;
  try {
    await d.connect();
    await online(d);
  } catch (e) {
    if (device === d) device = null;
    d.disconnect();
    const message = connectError(e);
    if (message) notice(message);
  } finally {
    button.textContent = t(button.dataset.t);
    $("btnConnect").disabled = !bluetooth;
    $("btnPractice").disabled = false;
  }
}

// Plain words for the user (a text key); the details go to the console for the team.
function connectError(e) {
  console.warn("Could not connect:", e);
  if (/adapter/i.test(e.message)) return "error.bluetoothOff";
  if (e.name === "NotFoundError") return null;   // the device picker was closed
  if (e.name === "SecurityError" || e.name === "NotAllowedError") return native ? "error.notAllowedApp" : "error.notAllowed";
  return "error.connect";
}

async function online(d) {
  stream.reset();
  device = d;
  await d.send(CMD.start);              // stream all the time, so the signal is live while placing the chest piece
  d.send(CMD.status).catch(() => {});   // battery now, not in 2 s
  if (running) return;                  // still analysing: the results come next anyway
  if (session && !remaining().length) showResults();   // carry on where the user was
  else showReady();
}

// A dropped connection is retried for about 10 s before the user has to do anything.
async function lostDevice(d) {
  device = null;
  battery = null;
  showBattery();
  notice("device.reconnecting");
  if (running) cancel = true;
  else if (!$("sReady").hidden) show("sConnect");   // results stay on screen if they are showing
  for (const wait of [500, 1500, 3000, 5000]) {
    await sleep(wait);
    if (latest !== d || device) return;   // the user connected something themselves
    try {
      await d.open();
      if (latest !== d || device) return d.disconnect();
      notice(session && remaining().length && remaining().length < ORDER.length ? "device.backContinue" : "device.back");
      return await online(d);
    } catch (e) {
      console.warn("Reconnect failed:", e.message);
    }
  }
  if (latest === d && !device) notice("device.lost");
}

function needDevice() {
  if (device) return false;
  notice("device.first");
  show("sConnect");
  return true;
}

function send(bytes) {
  if (device) device.send(bytes).catch((e) => console.warn("Command failed:", e.message));
}

// ---------- session ----------
let session = null;   // { id, started, results: {code: response}, audio: {code: Int16Array}, pending: [] }
let running = false, cancel = false, skip = false, lock = null;

const remaining = () => (session ? ORDER.filter((c) => !session.results[c]) : ORDER);
const newSession = () => { session = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), started: Date.now(), results: {}, audio: {}, pending: [] }; };

// Keep the screen on during a session, also after switching away and back. Never waited for.
const keepAwake = () => native ? native.keepAwake(true)
  : navigator.wakeLock?.request("screen").then((l) => { if (running) lock = l; else l.release(); }).catch(() => {});

function away() {
  stopListening();
  hush();
  if (running && !$("sPoint").hidden) {   // a phone call, or the screen switched off: pause rather than record nothing
    cancel = true;
    notice("device.paused");
  }
}
document.addEventListener("visibilitychange", () => { if (document.hidden) away(); else if (running) keepAwake(); });
native?.onPause(away);   // the phone app going to the background (its WebView may not report it as hidden)
native?.onResume(() => { if (running) keepAwake(); });

// Ask before leaving the page mid-check or with results that would be lost.
addEventListener("beforeunload", (e) => {
  if (running || (session && Object.keys(session.results).length)) { e.preventDefault(); e.returnValue = ""; }
});

// Android's back button stops a recording instead of leaving the page.
addEventListener("popstate", () => { if (running) cancel = true; });
const catchBack = () => { if (history.state !== "check") history.pushState("check", ""); };

async function runSession(codes) {
  if (running) return;
  running = true;
  cancel = false;
  let finished = false;
  notice();
  catchBack();
  show("sPoint");
  keepAwake();
  try {
    for (const code of codes) if (!cancel) await recordPoint(code);
    if (!cancel) {
      finished = true;   // from here a disconnect no longer matters: everything is recorded
      show("sBusy");
      await Promise.all([...session.pending, sleep(1500)]);  // a short, calm pause even when the server is fast
      showResults();
    }
  } finally {
    running = false;
    recording = null;
    if (lock) lock.release();
    lock = null;
    native?.keepAwake(false);
    send(CMD.idle);
    hush();
    pointCode = null;
    if (!finished) !device ? show("sConnect") : remaining().length ? showReady() : showResults();
  }
}

let pointCode = null;   // the place being recorded
function pointTexts(code) {
  $("pointStep").textContent = t("point.step", { n: ORDER.indexOf(code) + 1, total: ORDER.length });
  $("pointTitle").textContent = title(code);
  $("pointWhere").textContent = t(`point.${code}.where`);
}

async function recordPoint(code) {
  const p = POINTS[code];
  pointCode = code;
  pointTexts(code);
  $("progress").innerHTML = ORDER.map((c) => `<i class="${c === code ? "now" : session.results[c] ? "done" : ""}"></i>`).join("");
  drawBody($("body"), p.view, (c) => (c === code ? "here" : ""));
  if (settled()) enter($("pointStep"), $("pointTitle"), $("pointWhere"), $("body"));   // the next place (the first comes in with the screen)
  say(`${title(code)}. ${t(`point.${code}.where`)}`);

  // 1. Time to place the chest piece (or tap "start now").
  $("btnNow").hidden = false;
  $("breath").style.transform = "scale(0.62)";
  const placed = await countdown(PLACE_SECONDS, (s, total) => dial(Math.ceil(total - s), t("point.startsIn"), s / total), true);
  $("btnNow").hidden = true;
  if (!placed) return;
  dial(t("point.getReady"), t("point.breatheSlowly"), 0);
  await say(t("point.sayBreathe"));   // finishes before the recording starts
  if (cancel) return;

  // 2. One practice breath, then record the next breaths. The device's lights start with the circle and loop on
  //    their own clock (contract 4.1), so the recording starts at the bottom of a breath, in step with them.
  send(CMD.guide(p.n));
  const started = breathe();
  const inhale = () => ((performance.now() - started) / 1000) % BREATH < BREATH_IN;
  let samples, recorded;
  try {
    const practised = await countdown(BREATH, (s, total) => dial(t(inhale() ? "point.in" : "point.out"), t("point.practice"), s / total));
    if (!practised) return;
    recording = new Recording(settings.seconds);
    recorded = await countdown(settings.seconds, (s, total) =>
      dial(t(inhale() ? "point.in" : "point.out"), t("point.secondsLeft", { n: Math.ceil(total - s) }), s / total));
    samples = recording.samples.slice();
    recording = null;
  } finally {
    breathe(false);
  }
  if (!recorded) return;
  send(CMD.done);
  if (!settings.demo && samples.length < 2 * SAMPLE_RATE) {   // demo mode sends no audio, so it needs none
    session.results[code] = { finding: "error", error: "error.noSound" };
  } else {
    analyze(code, samples);
  }

  // 3. A moment to see it worked, then the next place.
  if (native) native.vibrate(120);
  else navigator.vibrate?.(120);
  $("breath").style.transform = "scale(0.62)";
  dial(t("point.done"), t("point.wellDone"), 1);
  await countdown(1.2, () => {});
}

// The breathing circle, drawn every frame from the curve the device uses too: (1 - cos(pi k)) / 2 (contract 4.1).
// breathe() starts it and returns its start time; breathe(false) stops it. drawBreath() is also called by the
// countdown's ticks, so the circle keeps moving (in step) where the browser slows down animation frames.
let breathing = 0, breathStart = 0;
function drawBreath() {
  if (!breathStart) return;
  const phase = ((performance.now() - breathStart) / 1000) % BREATH;
  const k = phase < BREATH_IN ? phase / BREATH_IN : 1 - (phase - BREATH_IN) / BREATH_OUT;
  $("breath").style.transform = `scale(${0.62 + 0.38 * (1 - Math.cos(Math.PI * k)) / 2})`;
}
function breathe(on = true) {
  const run = ++breathing;
  breathStart = on ? performance.now() : 0;
  $("breath").style.transform = "scale(0.62)";
  const frame = () => {
    if (run !== breathing) return;
    drawBreath();
    requestAnimationFrame(frame);
  };
  if (on) requestAnimationFrame(frame);
  return breathStart;
}

// Runs onTick about 20 times a second; resolves false if the session was stopped.
async function countdown(seconds, onTick, skippable = false) {
  const start = performance.now();
  skip = false;
  for (let elapsed = 0; !cancel && elapsed < seconds && !(skippable && skip); elapsed = (performance.now() - start) / 1000) {
    onTick(elapsed, seconds);
    drawBreath();
    const hearing = performance.now() - lastAudioAt < 1000;
    const clipping = hearing && ring.reduce((n, v) => n + (Math.abs(v) > 0.97), 0) > ring.length / 100;   // rubbing or knocks
    $("signalText").textContent = t(!hearing ? "signal.none" : clipping ? "signal.loud" : "signal.ok");
    $("signalText").parentElement.classList.toggle("none", (!hearing || clipping) && !settings.demo);
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

// ---------- the AI: on this phone, or an AI server (contract 2) ----------
// Analyses one place in the background. A late answer never lands in a newer recording or a new check.
function analyze(code, samples) {
  const s = session, mine = { finding: "pending" };
  s.audio[code] = samples;
  s.results[code] = mine;
  s.pending.push(request(code, samples, s.id).then((result) => {
    if (s.results[code] !== mine) return;
    s.results[code] = result;
    if (s === session && !$("sResults").hidden) renderResults();
  }));
}

async function request(code, samples, sessionId) {
  if (!settings.server) return requestHere(code, samples);
  const form = new FormData();
  form.append("point", code);
  form.append("session_id", sessionId);
  if (settings.demo) {
    form.append("demo", "true");
    form.append("demo_case", settings.demo);
  } else {
    form.append("audio", toWav(samples), `${code}.wav`);
  }
  // retry: the recording is fine and can simply be sent again; otherwise it needs recording again.
  // error: a text key; the server's own words (English, technical) only go to the console.
  try {
    const res = await fetch(api("/analyze"), { method: "POST", body: form, signal: AbortSignal.timeout(30000) });
    const body = await res.json().catch(() => ({}));
    if (res.status >= 500) {   // the server's own words are for the team
      console.warn(`AI server error ${res.status}:`, body.error);
      return { finding: "error", error: "error.server", retry: true };
    }
    if (!res.ok) {
      console.warn(`AI server refused the recording (${res.status}):`, body.error);
      return { finding: "error", error: "error.rejected" };
    }
    if (!FINDINGS.includes(body.finding)) return { finding: "error", error: "error.badAnswer", retry: true };
    return body;
  } catch (e) {
    return { finding: "error", error: describeFetchError(e), retry: true };
  }
}

function describeFetchError(e) {
  console.warn("AI server:", e);
  return e.name === "TimeoutError" ? "error.timeout" : "error.unreachable";
}

// The same, on this phone (ai/local.js): the server's answers without a server. Its errors mean what the server's do:
// 4xx, this recording can't be used (record it again); otherwise a fault, and the same recording can be tried again.
async function requestHere(code, samples) {
  try {
    const body = await analyzeHere({ point: code, samples: settings.demo ? null : samples, demo: !!settings.demo, demoCase: settings.demo || null });
    return FINDINGS.includes(body.finding) ? body : { finding: "error", error: "error.badAnswer", retry: true };
  } catch (e) {
    console.warn("On-phone AI:", e);
    return e.status >= 400 && e.status < 500 ? { finding: "error", error: "error.rejected" } : { finding: "error", error: "error.local", retry: true };
  }
}

// ---------- screens ----------
let shownAt = 0;
const settled = () => performance.now() - shownAt > 400;   // a double-tap must not also press the next screen's button

function show(id) {
  stopListening();
  const screen = $(id);
  if (!screen.hidden) return;   // already showing: content updates in place, without jumping
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s !== screen; });
  $("btnLang").hidden = id !== "sWelcome" && id !== "sConnect";   // the language is chosen at the start (and in Settings)
  window.scrollTo(0, 0);
  enter(screen);
  screen.querySelector("h1").focus({ preventScroll: true });   // screen readers announce the new screen
  shownAt = performance.now();
}

function enter(...elements) {   // a gentle fade-up for new content
  if (calm.matches) return;
  for (const el of elements) el.animate([{ opacity: 0.35, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: "ease-out" });
}

let noticeShown = [null];
function notice(key, vars) {   // no key: hide it. Kept as a key, so it follows a change of language.
  noticeShown = [key, vars];
  $("notice").textContent = key ? t(key, vars) : "";
  $("notice").hidden = !key;
}

function showReady() {
  const left = remaining().length;
  const partial = session && left > 0 && left < ORDER.length;
  $("readyTitle").textContent = t(partial ? "ready.titleContinue" : "ready.title");
  $("btnBegin").textContent = partial ? t("ready.continue", { n: left }) : t("ready.begin");
  $("step2").innerHTML = t("ready.step2", { n: settings.seconds });
  $("readyNote").hidden = !settings.demo;
  $("readyNote").textContent = settings.demo ? t("ready.demo", { case: t(`case.${settings.demo}`) }) : "";
  show("sReady");
}

function verdict(r) {
  if (!r) return { cls: "todo", chip: t("chip.notRecorded") };
  if (r.finding === "pending") return { cls: "todo", chip: t("chip.analysing"), pending: true };
  if (r.finding === "error") return { cls: "unclear", chip: t(r.retry ? "chip.notChecked" : "chip.again"), detail: t(r.error), retry: r.retry };
  if (r.finding === "unusable" || r.quality < MIN_QUALITY) return { cls: "unclear", chip: t("chip.again"), detail: t("detail.unclear") };
  const detail = [Number.isFinite(r.confidence) && t("detail.confidence", { pct: percent(r.confidence) }), r.demo && t("detail.example")].filter(Boolean).join(" · ");
  return r.finding === "normal" ? { cls: "ok", chip: t("chip.clear"), detail } : { cls: "warn", chip: t(`finding.${r.finding}`), detail };
}

const MARK = { ok: "check", warn: "alert", unclear: "retry", todo: "retry" };
const STYLE = { warn: "warn", pending: "unclear", retry: "unclear", unclear: "unclear", ok: "ok" };   // overall answer → colour
const SHORT = { warn: "short.warn", retry: "short.unfinished", unclear: "short.unfinished", ok: "short.ok" };   // for earlier checks
const listenable = (code) => session.audio[code]?.length > 0 && !session.results[code]?.demo;   // a demo result was about an example, not this recording

function showResults() {
  resetRestart();
  show("sResults");
  renderResults();
  say(`${$("overallTitle").textContent}. ${$("overallText").textContent}`);
}

function renderResults() {
  const verdicts = Object.fromEntries(ORDER.map((c) => [c, verdict(session.results[c])]));
  const all = Object.values(verdicts);
  const any = (test) => all.some(test);
  const key = any((v) => v.cls === "warn") ? "warn" : any((v) => v.pending) ? "pending" : any((v) => v.retry) ? "retry"
    : any((v) => v.cls !== "ok") ? "unclear" : "ok";
  const cls = STYLE[key];
  $("overall").className = `overall ${cls}`;
  $("overallIcon").innerHTML = icon(MARK[cls]);
  $("overallTitle").textContent = t(`overall.${key}.title`);
  $("overallText").textContent = t(`overall.${key}.text`);
  $("checkDate").textContent = t("results.checked", { date: dateTime(session.started) });
  drawBody($("mapFront"), "front", (c) => verdicts[c].cls);
  drawBody($("mapBack"), "back", (c) => verdicts[c].cls);

  $("resultList").replaceChildren(...ORDER.map((code) => {
    const v = verdicts[code], audio = session.audio[code];
    const li = document.createElement("li");
    li.className = v.cls;
    li.innerHTML = `<span class="mark">${icon(MARK[v.cls])}</span><div class="what"><b></b><span class="chip"></span><small></small></div>` +
      (listenable(code) ? `<div class="wave" aria-hidden="true">${waveform(audio)}</div>` : "") + `<div class="acts"></div>`;
    [li.querySelector("b").textContent, li.querySelector(".chip").textContent, li.querySelector("small").textContent] = [title(code), v.chip, v.detail || ""];
    const acts = li.querySelector(".acts");
    if (listenable(code)) {
      const b = button("play", t("action.listen"), () => listen(code));
      b.dataset.listen = code;
      acts.append(b);
    }
    if (v.retry) acts.append(button("retry", t("action.retry"), () => { analyze(code, audio); renderResults(); }));
    acts.append(button("retry", t("action.record"), () => { if (!needDevice()) runSession([code]); }));
    return li;
  }));
  listenButtons();

  const earlier = pastChecks(key === "pending" ? null : { id: session.id, started: session.started, key })
    .filter((c) => c.id !== session.id && SHORT[c.key]).sort((a, b) => b.started - a.started).slice(0, 3);
  $("earlier").hidden = !earlier.length;
  $("earlierList").innerHTML = earlier.map((c) => `<li><i class="dot ${STYLE[c.key]}"></i><span>${dateTime(c.started)}</span><b>${t(SHORT[c.key])}</b></li>`).join("");
}

// A recording's outline (min/max per column), worked out once per recording.
const waves = new WeakMap();
function waveform(samples) {
  if (!waves.has(samples)) {
    const cols = 120, step = samples.length / cols, peak = samples.reduce((m, v) => Math.max(m, Math.abs(v)), 1);
    let d = "";
    for (let x = 0; x < cols; x++) {
      let lo = 0, hi = 0;
      for (let i = Math.floor(x * step); i < Math.floor((x + 1) * step); i++) { lo = Math.min(lo, samples[i]); hi = Math.max(hi, samples[i]); }
      d += `M${x + 0.5} ${(20 - (19 * hi) / peak).toFixed(1)}V${(20.5 - (19 * lo) / peak).toFixed(1)}`;
    }
    waves.set(samples, `<svg viewBox="0 0 ${cols} 40" preserveAspectRatio="none"><path d="${d}"/></svg><i class="played"></i>`);
  }
  return waves.get(samples);
}

// Earlier checks on this phone: the date and the overall answer only, never the audio.
function pastChecks(update) {
  let list = [];
  try { list = JSON.parse(localStorage.getItem("respirai-checks")) || []; } catch (e) { /* none yet */ }
  if (update) {
    list = [update, ...list.filter((c) => c.id !== update.id)].slice(0, 20);
    try { localStorage.setItem("respirai-checks", JSON.stringify(list)); } catch (e) { /* not essential */ }
  }
  return list;
}

// "Share with a doctor": a short summary and the recordings, through the phone's own share sheet
// (email, WhatsApp…). Where sharing files isn't possible, the summary alone; on a computer, print / save as PDF.
async function share() {
  const lines = ORDER.map((c) => {
    const v = verdict(session.results[c]);
    return `• ${title(c)}: ${v.chip}${v.detail && v.cls !== "unclear" ? ` (${v.detail})` : ""}`;
  });
  const text = [t("share.heading", { date: dateTime(session.started) }), `${$("overallTitle").textContent}.`, ...lines, "", t("results.disclaimer")].join("\n");
  const day = new Date(session.started).toISOString().slice(0, 10);
  const files = ORDER.filter(listenable).map((c) => new File([toWav(session.audio[c])], `respirAI ${day} ${title(c).replace(/[^\p{L}\p{N} -]+/gu, "")}.wav`, { type: "audio/wav" }));
  const sheet = { title: t("share.title"), text };
  if (native) {   // the phone app: Android's share sheet, with the recordings (else the summary alone)
    try {
      await native.share({ ...sheet, files });
    } catch (e) {
      if (e.name !== "AbortError") { console.warn("Share failed:", e); await native.share(sheet).catch(() => {}); }
    }
    return;
  }
  try {
    if (files.length && navigator.canShare?.({ files })) await navigator.share({ ...sheet, files });
    else if (navigator.share) await navigator.share(sheet);
    else print();
  } catch (e) {
    if (e.name !== "AbortError") { console.warn("Share failed:", e); print(); }   // AbortError: the share sheet was closed
  }
}

// Listen / Stop: one recording at a time, with the waveform showing how far it has played.
let playing = null;   // { code, started, seconds }

function listen(code) {
  const again = playing && playing.code === code;
  stopListening();
  if (!again) {
    const seconds = play(session.audio[code], () => { playing = null; listenButtons(); });
    playing = { code, started: performance.now(), seconds };
  }
  listenButtons();
}

function stopListening() {
  stopPlayback();
  playing = null;
  listenButtons();
}

function listenButtons() {
  document.querySelectorAll("[data-listen]").forEach((b) => {
    const on = !!playing && b.dataset.listen === playing.code;
    b.innerHTML = on ? `${icon("stop")} ${t("action.stop")}` : `${icon("play")} ${t("action.listen")}`;
    b.setAttribute("aria-pressed", on);
    b.classList.toggle("playing", on);
    const li = b.closest("li");
    li.classList.toggle("playing", on);
    if (on) {
      li.style.setProperty("--dur", `${playing.seconds}s`);
      li.style.setProperty("--delay", `${-(performance.now() - playing.started) / 1000}s`);
    }
  });
}

// "Start a new check" clears the results, so it asks for a second, separate tap.
let armedAt = -Infinity, disarm = null;
function resetRestart() {
  clearTimeout(disarm);
  armedAt = -Infinity;
  $("btnRestart").textContent = t("results.restart");
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
  const [left, right] = (view === "front" ? ["body.right", "body.left"] : ["body.left", "body.right"]).map((k) => t(k));
  svg.innerHTML = `<use href="#silhouette" class="sil"/><text x="0" y="14" class="side l">${left}</text><text x="160" y="14" class="side r">${right}</text>
    <text x="80" y="187" class="view">${t(view === "front" ? "body.front" : "body.back")}</text>` +
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

function showStats() {
  $("stats").textContent = stream.received
    ? t("settings.stats", { received: stream.received, lost: stream.lost, bytes: stream.packetSamples * 2 + 2 })
    : t("settings.noSignal");
}
setInterval(showStats, 1000);

// ---------- buttons ----------
$("btnConnect").addEventListener("click", () => connect(bluetooth, $("btnConnect")));
$("btnPractice").addEventListener("click", () => connect(fakeBluetooth({ battery: 87, drop: 0.005 }), $("btnPractice")));
$("btnBegin").addEventListener("click", () => {
  if (!settled() || needDevice()) return;
  if (!session || !remaining().length) newSession();
  runSession(remaining());
});
$("btnNow").addEventListener("click", () => { if (settled()) skip = true; });
$("btnStop").addEventListener("click", () => { if (settled()) cancel = true; });
$("btnRestart").addEventListener("click", () => {
  const since = performance.now() - armedAt;
  if (since < 400) return;   // the two taps of a double-tap count as one
  if (since > 4000) {
    armedAt = performance.now();
    $("btnRestart").textContent = t("results.restartConfirm");
    disarm = setTimeout(resetRestart, 4000);
    return;
  }
  resetRestart();
  newSession();
  showReady();
});
$("notice").addEventListener("click", () => notice());   // tap to dismiss
$("btnShare").addEventListener("click", share);
$("btnVoice").addEventListener("click", () => {
  settings.voice = !settings.voice;
  saveSettings();
  if (settings.voice) say(t("ready.voiceOn"));
  else hush();
});
$("btnForget").addEventListener("click", () => {
  try { localStorage.removeItem("respirai-checks"); } catch (e) { /* nothing stored */ }
  $("earlier").hidden = true;
});
$("btnSettings").addEventListener("click", () => $("settings").showModal());
$("micTest").href = `mic-test.html${location.search}`;   // the team's microphone test, with the same options (e.g. ?fakebt)
$("btnLang").addEventListener("click", chooseLanguage);
$("btnLangRow").addEventListener("click", chooseLanguage);
$("btnWelcome").addEventListener("click", () => {
  settings.welcomed = true;
  saveSettings();
  show("sConnect");
});
for (const d of [$("settings"), $("languages")]) d.addEventListener("click", (e) => { if (e.target === d) d.close(); });   // tap outside closes
$("btnTest").addEventListener("click", async () => {
  $("btnTest").disabled = true;
  $("testResult").textContent = t("settings.checking");
  try {   // the AI on this phone, or the server in the setting
    const h = settings.server ? await (await fetch(api("/health"), { signal: AbortSignal.timeout(5000) })).json() : await healthHere();
    $("testResult").textContent = t("settings.testOk", { model: h.model_version, dummy: h.dummy ? t("settings.dummy") : "", clips: h.demo_clips });
  } catch (e) {
    $("testResult").textContent = !settings.server ? t("error.local") : e.name === "TimeoutError" ? t("error.timeout") : t("settings.unreachable", { server: settings.server });
  } finally {
    $("btnTest").disabled = false;
  }
});

// ---------- language ----------
function chooseLanguage() {
  $("languageList").replaceChildren(...LANGUAGES.map((l) => {
    const b = document.createElement("button");
    Object.assign(b, { type: "button", className: "language", lang: l.code, textContent: l.name });
    b.setAttribute("aria-pressed", l.code === current().code);
    b.addEventListener("click", async () => {
      $("languages").close();
      settings.lang = l.code;
      saveSettings();
      await setLanguage(l.code);
      refreshTexts();
    });
    return b;
  }));
  $("languages").showModal();
}

// Everything on screen that code wrote, in the current language (setLanguage does the fixed text in index.html).
function refreshTexts() {
  $("langCode").textContent = current().code.toUpperCase();
  $("langName").textContent = current().name;
  $("server").placeholder = t("settings.onPhone");
  native?.pickerTexts({ scanning: t("picker.scanning"), cancel: t("picker.cancel"), availableDevices: t("picker.devices"), noDeviceFound: t("picker.none") });
  for (const o of $("demo").options) o.textContent = o.value ? t("settings.demo.on", { case: t(`case.${o.value}`) }) : t("settings.demo.off");
  notice(...noticeShown);
  connectNote(connectNoteKey);
  showBattery();
  showStats();
  resetRestart();
  if (!$("sReady").hidden) showReady();
  if (!$("sResults").hidden) renderResults();
  if (pointCode) pointTexts(pointCode);
}

await setLanguage(settings.lang || detect());   // the phone's language until the user picks one
refreshTexts();
if (!settings.welcomed) show("sWelcome");
document.documentElement.classList.remove("loading");

// Works without a connection once opened (the AI on the phone too), and can be installed. Not in the phone app:
// its files are on the phone already, and an old cached copy must never outlive an app update.
if ("serviceWorker" in navigator && isSecureContext && !native) navigator.serviceWorker.register("sw.js").catch((e) => console.warn("No offline mode:", e.message));
