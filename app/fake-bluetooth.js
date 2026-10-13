// A fake respirAI device behind a fake Web Bluetooth API, so the real Bluetooth code (BleDevice) runs
// without hardware. It behaves like the firmware and rejects what Chrome would reject.
// Used by "Try a practice run", and behind "Connect the device" when the page is opened with ?fakebt:
//   &mtu=25               a phone that negotiates a small MTU (smaller packets)
//   &drop=0.02            lose 2 % of packets
//   &disconnectAfter=30   drop the connection after 30 s of streaming
//   &battery=64           battery level to report (default 255 = unknown)
//   &wav=crackles.wav     stream a real recording on a loop instead of generated breathing:
//                         a file in dev/recordings/, or a path like demo_clips/crackles_Al.wav
// From the console: fakeBt.disconnect()
import { AUDIO, CONTROL, SERVICE, STATUS } from "./device.js";

const fail = (name, message) => Promise.reject(new DOMException(message, name));

export function fakeBluetooth({ mtu = 185, drop = 0, disconnectAfter = 0, battery = 255, wav = null } = {}) {
  const samplesPerPacket = Math.min(80, ((mtu - 5) >> 1) & ~1);
  let recording = null;   // loaded in the background; never holds up the app
  const recordingReady = wav ? loadRecording(wav).then((r) => { recording = r; }) : Promise.resolve();
  let current = null;

  function makeDevice(allowed) {
    const device = new EventTarget();
    const chr = (notifies) => Object.assign(new EventTarget(), {
      startNotifications: () => (notifies ? Promise.resolve() : fail("NotSupportedError", "does not notify")),
      writeValueWithResponse: (data) => {
        if (notifies) return fail("NotSupportedError", "not writable");
        if (!device.gatt.connected) return fail("NetworkError", "GATT Server is disconnected.");
        command(new Uint8Array(data.buffer || data));
        return Promise.resolve();
      },
    });
    const chars = { [AUDIO]: chr(true), [CONTROL]: chr(false), [STATUS]: chr(true) };
    const notify = (c, bytes) => { c.value = new DataView(bytes.buffer); c.dispatchEvent(new Event("characteristicvaluechanged")); };
    let seq = 0, t = 0, pending = new Int16Array(0), timers = [], since = 0;

    function command(bytes) {
      if (bytes[0] === 0x01 && !timers.length) {
        since = performance.now();
        timers = [setInterval(tick, 10), setInterval(status, 2000)];
      }
      if (bytes[0] === 0x02) stop();
      if (bytes[0] === 0x20) status();
    }

    function tick() {   // 10 ms of audio (the recording, or breath-like noise), split into packets like the firmware
      if (disconnectAfter && performance.now() - since > disconnectAfter * 1000) return device.gatt.disconnect();
      const block = Int16Array.from({ length: 80 }, () => recording ? recording[t++ % recording.length]
        : (Math.random() * 2 - 1) * 4000 * (0.15 + 0.85 * Math.max(0, Math.sin((2 * Math.PI * t++) / 64000))));
      pending = Int16Array.from([...pending, ...block]);
      for (; pending.length >= samplesPerPacket; pending = pending.slice(samplesPerPacket)) {
        const view = new DataView(new ArrayBuffer(2 + 2 * samplesPerPacket));
        view.setUint16(0, seq, true);
        for (let i = 0; i < samplesPerPacket; i++) view.setInt16(2 + 2 * i, pending[i], true);
        seq = (seq + 1) & 0xffff;
        if (Math.random() >= drop) notify(chars[AUDIO], new Uint8Array(view.buffer));
      }
    }

    const status = () => notify(chars[STATUS], new Uint8Array([battery, timers.length ? 1 : 0, 0, 0]));
    const stop = () => { timers.forEach(clearInterval); timers = []; };

    device.gatt = {
      connected: false,
      connect() { this.connected = true; return Promise.resolve(this); },
      disconnect() {
        stop();
        if (!this.connected) return;
        this.connected = false;
        device.dispatchEvent(new Event("gattserverdisconnected"));
      },
      getPrimaryService(id) {
        if (!this.connected) return fail("NetworkError", "GATT Server is disconnected.");
        if (!allowed.includes(id)) return fail("SecurityError", `Service ${id} is not in optionalServices.`);
        if (id !== SERVICE) return fail("NotFoundError", `No service ${id}.`);
        return Promise.resolve({ getCharacteristic: (c) => (chars[c] ? Promise.resolve(chars[c]) : fail("NotFoundError", `No characteristic ${c}.`)) });
      },
    };
    return device;
  }

  return {
    async requestDevice({ filters = [], optionalServices = [] } = {}) {
      if (!filters.some((f) => f.name === "respirAI" || (f.services || []).includes(SERVICE))) {
        return fail("NotFoundError", "No device matched the filters.");
      }
      await Promise.race([recordingReady, new Promise((r) => setTimeout(r, 5000))]);   // like the device picker taking a moment
      if (current) current.gatt.disconnect();
      return (current = makeDevice([...optionalServices, ...filters.flatMap((f) => f.services || [])]));
    },
    disconnect: () => current && current.gatt.disconnect(),
    get source() { return recording ? wav : "generated breathing"; },
  };
}

// A 16-bit WAV, or any file the browser can decode, at the device's 8 kHz and scaled to half of full range.
async function loadRecording(name) {
  try {
    const res = await fetch(name.includes("/") ? name : `dev/recordings/${name}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buf = await res.arrayBuffer();
    const x = readWav(buf) || (await new OfflineAudioContext(1, 1, 8000).decodeAudioData(buf)).getChannelData(0);
    const peak = x.reduce((m, v) => Math.max(m, Math.abs(v)), 1e-6);
    return Int16Array.from(x, (v) => Math.round((v / peak) * 0.5 * 32767));
  } catch (e) {
    console.warn(`Fake device: could not load ${name} (${e.message}); using generated breathing instead`);
    return null;
  }
}

// 16-bit PCM WAV -> first channel at 8 kHz (nearest-sample resampling, fine for testing), or null if it isn't one.
function readWav(buf) {
  const v = new DataView(buf);
  if (buf.byteLength < 44 || v.getUint32(0) !== 0x52494646 || v.getUint32(8) !== 0x57415645) return null;  // "RIFF", "WAVE"
  let at = 12, rate = 8000, channels = 1, bits = 16;
  while (at + 8 <= buf.byteLength) {
    const id = v.getUint32(at), size = v.getUint32(at + 4, true), body = at + 8;
    if (id === 0x666d7420) {   // "fmt "
      [channels, rate, bits] = [v.getUint16(body + 2, true), v.getUint32(body + 4, true), v.getUint16(body + 14, true)];
    } else if (id === 0x64617461) {   // "data"
      if (bits !== 16) return null;
      const n = Math.floor((Math.min(size, buf.byteLength - body) / (2 * channels)) * 8000 / rate);
      return Float32Array.from({ length: n }, (_, i) => v.getInt16(body + 2 * channels * Math.floor((i * rate) / 8000), true) / 32768);
    }
    at = body + size + (size & 1);
  }
  return null;
}
