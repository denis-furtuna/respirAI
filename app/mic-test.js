// Microphone test, for the team: the device's mic and its Bluetooth stream, live (tasks F2-F6, E3). Nothing is analysed
// or uploaded. Opened from Settings → Microphone test, or directly as mic-test.html (?fakebt and its options work as in the app).
import { BleDevice, CMD } from "./device.js";
import { PacketStream, Recording, SAMPLE_RATE, play, stopPlayback, toWav } from "./audio.js";
import { fakeBluetooth } from "./fake-bluetooth.js";
import { native } from "./native.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const bluetooth = params.has("fakebt") ? (window.fakeBt = fakeBluetooth(Object.fromEntries(params))) : native ? native.bluetooth : navigator.bluetooth;

const WINDOW = SAMPLE_RATE / 10;   // 100 ms: one level reading
const HISTORY = 100;               // readings kept: 10 s
const CLIP = 32000;                // a sample this loud counts as clipped (the firmware clamps at 32767)
const FULL_PACKET = 162;           // bytes, contract 1
const RECORD_SECONDS = 10;
const FLOOR = -60;                 // dBFS at the left end of the meter
const LOUD_BACKGROUND = -25;       // dBFS: a background this loud in a quiet room is a wiring fault, not sound
const QUIET_PEAK = -30;            // dBFS: after 10 s, a loudest sound below this means no tap or breath got through

const dB = (amp) => 20 * Math.log10(Math.max(amp, 0.5) / 32768);   // 0.5: silence reads about −96, not −∞
const fmtDb = (d) => `${Math.round(d)} dBFS`.replace("-", "−");
const pct = (x) => `${(100 * x).toFixed(x && x < 0.01 ? 2 : 1)} %`;
const meterPos = (d) => `${(100 * Math.min(1, Math.max(0, (d - FLOOR) / -FLOOR))).toFixed(1)}%`;

// ---------- state ----------
let dev = null, connected = false, leaving = false, status = null, connectedAt = 0;
let windows = [], win = newWindow(), loudest = 0;   // loudest: biggest |sample| since connecting
let rate = 0, lastReceived = 0;                     // packets in the last second
let rec = null, recLostFrom = 0, clip = null, playing = false;
const ring = new Float32Array(3 * SAMPLE_RATE);     // the last 3 s, for the waveform
let ringPos = 0;
const stream = new PacketStream(onSamples);

function newWindow() { return { n: 0, sum: 0, peak: 0, clipped: 0, min: Infinity, max: -Infinity }; }

function reset() {
  stream.reset();
  windows = []; win = newWindow(); loudest = 0; rate = 0; lastReceived = 0; status = null;
  ring.fill(0);
}

// Every sample: the waveform, the 100 ms level readings, and the clip being recorded.
function onSamples(samples) {
  for (const v of samples) {
    ring[ringPos] = v / 32768;
    ringPos = (ringPos + 1) % ring.length;
    const a = Math.abs(v);
    win.sum += v * v;
    win.peak = Math.max(win.peak, a);
    win.clipped += a >= CLIP;
    win.min = Math.min(win.min, v);
    win.max = Math.max(win.max, v);
    if (++win.n === WINDOW) {
      windows.push({ rms: Math.sqrt(win.sum / WINDOW), peak: win.peak, clipped: win.clipped, flat: win.min === win.max });
      if (windows.length > HISTORY) windows.shift();
      loudest = Math.max(loudest, win.peak);
      win = newWindow();
    }
  }
  if (rec) {
    rec.add(samples);
    if (rec.length >= rec.data.length) finishRecording();
  }
}

const recent = (n) => windows.slice(-n);
function background() {   // the quietest tenth of the last 10 s: the noise floor, ignoring taps and breaths
  if (windows.length < 20) return null;
  const sorted = windows.map((w) => w.rms).sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 10)];
}

// ---------- connecting ----------
async function connect() {
  notice();
  $("btnConnect").disabled = true;
  try {
    dev = new BleDevice(bluetooth, { onPacket: (v) => stream.push(v), onStatus: (s) => (status = s), onDisconnect: disconnected });
    await dev.connect();
    reset();
    connected = true;
    leaving = false;
    connectedAt = performance.now();
    await dev.send(CMD.start);
    dev.send(CMD.status).catch(() => {});   // the battery now, not in 2 s
  } catch (e) {
    connected = false;
    dev?.disconnect();
    dev = null;
    if (!(e.name === "NotFoundError" && /cancel/i.test(e.message))) {   // closing the device picker is not an error
      console.warn("Connect failed:", e);
      notice(e.name === "NotFoundError" ? "No respirAI device found. Is it switched on and close to the phone?" : e.message);
    }
  }
  render();
}

function disconnected() {
  if (!connected) return;
  connected = false;
  if (rec) {
    rec = null;
    $("clipText").textContent = "Recording stopped: the device disconnected.";
  }
  if (!leaving) notice("The device disconnected. Connect again when it is back in range.");
  render();
}

function disconnect() {
  const d = dev;
  leaving = true;
  d?.send(CMD.stop).catch(() => {}).finally(() => d.disconnect());
  disconnected();
  dev = null;
}

function notice(text) {
  $("notice").hidden = !text;
  $("notice").textContent = text || "";
}

// ---------- the checks: each one ok / warn / bad / info / wait, with plain advice ----------
function checks() {
  const out = [];
  const add = (state, title, text) => out.push({ state, title, text });
  if (!connected) {
    add("wait", "Bluetooth", "Not connected. Press Connect the device, then pick respirAI.");
    return out;
  }
  const seconds = (performance.now() - connectedAt) / 1000;
  add("ok", "Bluetooth", `Connected to ${dev?.device?.name || "respirAI"}`);

  const n = stream.packetSamples, expected = n ? SAMPLE_RATE / n : 100;
  if (!stream.received) {
    add(seconds < 3 ? "wait" : "bad", "Packets", seconds < 3 ? "Waiting for the first packet…"
      : "None arriving. The device connected but sends no audio: is the respirAI firmware on it? (Serial: “Audio subscribed”, then status lines.)");
  } else {
    add(rate >= 0.9 * expected ? "ok" : rate >= 0.5 * expected ? "warn" : "bad", "Packets", `${rate} per second (expected ${Math.round(expected)})`);
  }
  if (n) {
    const bytes = 2 + 2 * n;
    add(bytes === FULL_PACKET ? "ok" : "warn", "Packet size", bytes === FULL_PACKET ? `${bytes} bytes: full 10 ms packets`
      : `${bytes} bytes: this phone negotiated a small MTU (${bytes + 3}). It works, but tell the firmware owner.`);
  }
  const total = stream.received + stream.lost;
  if (total) {
    const lost = stream.lost / total;
    add(lost < 0.01 ? "ok" : lost < 0.05 ? "warn" : "bad", "Lost packets",
      `${stream.lost} of ${total} (${pct(lost)})${lost < 0.01 ? "" : ". Bring the phone closer and keep other Bluetooth devices away."}`);
  }

  const last = recent(10), silent = last.length === 10 && last.every((w) => w.flat);
  if (status?.state === 2 || silent) {
    add("bad", "Microphone", `${status?.state === 2 ? "The device reports that its microphone sends no sound." : "Every sample is the same: no sound at all."} ` +
      "Unplug USB and the battery, then check VDD on 3V3 (never 5V), SD on D10, SCK on D8, WS on D9 and L/R on GND.");
    return out;
  }
  if (!last.length) {
    add("wait", "Microphone", "Waiting for sound…");
    return out;
  }
  add("ok", "Microphone", "Sound is arriving");

  const bg = background();
  const clipped = recent(20).reduce((s, w) => s + w.clipped, 0) / (Math.min(20, windows.length) * WINDOW);
  if (clipped > 0.001) {
    add("bad", "Level", `Clipping: ${pct(clipped)} of the last 2 s is at full scale. Hold the chest piece still; if breathing alone clips, lower MIC_GAIN in firmware/respirai/config.h.`);
  } else if (bg !== null && dB(bg) > LOUD_BACKGROUND) {
    add("warn", "Level", `The background is very loud (${fmtDb(dB(bg))}). In a quiet room that is a wiring fault, not sound: check that SCK and WS are not swapped and that SD sits firmly in D10.`);
  } else if (seconds > 10 && dB(loudest) < QUIET_PEAK) {
    add("warn", "Level", `Quiet: the loudest sound so far is ${fmtDb(dB(loudest))}. Tap the chest piece: a tap should reach −20 dBFS. If it doesn't, raise MIC_GAIN in config.h.`);
  } else {
    add("ok", "Level", `Loudest so far ${fmtDb(dB(loudest))}${bg !== null ? `, background ${fmtDb(dB(bg))}` : ""}`);
  }

  if (status) {
    const b = status.battery;
    add(b === 255 ? "info" : b < 15 ? "warn" : "ok", "Battery", b === 255 ? "Not measured (the battery divider and PIN_BATTERY are optional)" : `${b} %`);
  }
  return out;
}

// ---------- the page ----------
const VERDICT = { bad: "Problem", warn: "Check", ok: "OK", wait: "Waiting…", info: "OK" };
function render() {
  $("btnConnect").hidden = connected;
  $("btnConnect").disabled = !bluetooth;
  $("btnDisconnect").hidden = !connected;
  $("btnRecord").disabled = !connected || !!rec;
  $("btnRecord").textContent = rec ? "Recording…" : `Record ${RECORD_SECONDS} s`;
  $("btnListen").disabled = !clip;
  $("btnListen").textContent = playing ? "Stop" : "Listen";
  $("btnSave").disabled = !clip;

  const n = stream.packetSamples;
  $("device").textContent = !connected ? "Not connected"
    : [dev?.device?.name || "respirAI", n ? `${2 + 2 * n} bytes per packet` : "no packets yet",
       status && status.battery !== 255 ? `battery ${status.battery} %` : null].filter(Boolean).join(" · ");

  const list = checks();
  $("checks").innerHTML = list.map((c) => `<li class="${c.state}"><b>${c.title}</b><span>${c.text}</span></li>`).join("");
  const worst = ["bad", "warn", "wait", "ok", "info"].find((s) => list.some((c) => c.state === s));
  $("verdict").className = `tag ${connected ? worst : ""}`;
  $("verdict").textContent = connected ? VERDICT[worst] : "Not connected";

  const now = recent(1)[0], two = recent(20), bg = background();
  const peak2 = two.reduce((m, w) => Math.max(m, w.peak), 0);
  $("level").textContent = now ? fmtDb(dB(now.rms)) : "–";
  $("peak").textContent = two.length ? fmtDb(dB(peak2)) : "–";
  $("background").textContent = bg !== null ? fmtDb(dB(bg)) : "–";
  $("clipped").textContent = two.length ? pct(two.reduce((s, w) => s + w.clipped, 0) / (two.length * WINDOW)) : "–";
  $("meterRms").style.width = now ? meterPos(dB(now.rms)) : "0";
  $("meterPeak").style.width = now ? meterPos(dB(now.peak)) : "0";
  $("meterHold").style.left = two.length ? meterPos(dB(peak2)) : "0";
  $("meter").setAttribute("aria-valuenow", now ? Math.round(Math.max(FLOOR, dB(now.rms))) : FLOOR);

  if (rec) $("clipText").textContent = `Recording… ${(rec.length / SAMPLE_RATE).toFixed(1)} of ${RECORD_SECONDS} s`;
}

setInterval(() => {   // once a second: the packet rate
  rate = stream.received - lastReceived;
  lastReceived = stream.received;
}, 1000);
setInterval(render, 250);

// ---------- waveform ----------
const canvas = $("wave"), ctx = canvas.getContext("2d");
let gain = 1;
(function draw() {
  requestAnimationFrame(draw);
  const w = Math.round(canvas.clientWidth * devicePixelRatio), h = Math.round(canvas.clientHeight * devicePixelRatio);
  if (!w || !h) return;
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
  const target = $("zoom").checked ? Math.min(50, 0.9 / Math.max(peak, 1e-4)) : 1;
  gain += (target - gain) * 0.1;
})();

// ---------- the test clip ----------
function finishRecording() {
  clip = rec.samples.slice();
  rec = null;
  const lost = stream.lost - recLostFrom;
  let sum = 0, peak = 0, clipped = 0;
  for (const v of clip) { sum += v * v; peak = Math.max(peak, Math.abs(v)); clipped += Math.abs(v) >= CLIP; }
  $("clipText").textContent = `${(clip.length / SAMPLE_RATE).toFixed(1)} s · level ${fmtDb(dB(Math.sqrt(sum / clip.length)))} · ` +
    `peak ${fmtDb(dB(peak))} · ${clipped} clipped samples · ${lost} packets lost`;
  render();
}

$("btnRecord").addEventListener("click", () => {
  if (!connected || rec) return;
  stopPlayback();
  playing = false;
  clip = null;
  rec = new Recording(RECORD_SECONDS);
  recLostFrom = stream.lost;
  render();
});

$("btnListen").addEventListener("click", () => {
  if (!clip) return;
  if (playing) stopPlayback();
  else play(clip, () => { playing = false; render(); });   // played louder, so quiet breath sounds can be heard
  playing = !playing;
  render();
});

$("btnSave").addEventListener("click", async () => {
  if (!clip) return;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");
  const file = new File([toWav(clip)], `respirai-mic-${stamp}.wav`, { type: "audio/wav" });
  if (native) {   // the phone app: Android's share sheet (Drive, email, Files…)
    await native.share({ title: "respirAI microphone test", text: $("clipText").textContent, files: [file] })
      .catch((e) => { if (e.name !== "AbortError") notice(`Couldn't share the clip: ${e.message}`); });
    return;
  }
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(file), download: file.name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
});

// ---------- buttons ----------
$("btnConnect").addEventListener("click", connect);
$("btnDisconnect").addEventListener("click", disconnect);
$("back").href = `./${location.search}`;   // back to the app with the same options (e.g. ?fakebt)
addEventListener("pagehide", () => {   // leaving the page: let the device go, so the app can connect to it
  leaving = true;
  dev?.disconnect();
});
if (!bluetooth) {
  notice("Web Bluetooth isn't available here. Use Chrome on Android or a computer, from https:// or localhost.");
}
render();
