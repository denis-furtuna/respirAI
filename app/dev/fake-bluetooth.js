// A fake Web Bluetooth device, for testing the real Bluetooth code (device.js BleDevice) without hardware.
// Loaded only when the page is opened with ?fakebt. It behaves like the firmware and checks
// the app follows contract 1, the way Chrome would complain.
//
// Options in the URL:
//   ?fakebt                   a respirAI device with a full 162-byte packet size
//   &mtu=23                   a phone that negotiates a small MTU (smaller packets)
//   &drop=0.02                lose 2 % of packets
//   &disconnectAfter=30       drop the connection after 30 s of streaming
//   &battery=64               battery level to report (default 255 = unknown)
// From the console: fakeBt.disconnect()

const params = new URLSearchParams(location.search);
const MTU = Number(params.get("mtu") || 185);
const DROP = Number(params.get("drop") || 0);
const DISCONNECT_AFTER = Number(params.get("disconnectAfter") || 0);
const BATTERY = Number(params.get("battery") || 255);

const uuid = (n) => `7b8c9d00-000${n}-4b5e-8f00-1a2b3c4d5e6f`;
const SERVICE = uuid(1), AUDIO = uuid(2), CONTROL = uuid(3), STATUS = uuid(4);
const fail = (name, message) => Promise.reject(new DOMException(message, name));

class Characteristic extends EventTarget {
  constructor(id, device, props) {
    super();
    Object.assign(this, { uuid: id, device, props, notifying: false, value: null });
  }
  startNotifications() {
    if (!this.props.includes("notify")) return fail("NotSupportedError", `${this.uuid} does not notify`);
    this.notifying = true;
    return Promise.resolve(this);
  }
  writeValueWithResponse(data) {
    if (!this.props.includes("write")) return fail("NotSupportedError", `${this.uuid} is not writable`);
    if (!this.device.gatt.connected) return fail("NetworkError", "GATT Server is disconnected.");
    this.device.command(new Uint8Array(data.buffer || data));
    return Promise.resolve();
  }
  writeValue(data) { return this.writeValueWithResponse(data); }
  notify(bytes) {
    if (!this.notifying) return;
    this.value = new DataView(bytes.buffer);
    this.dispatchEvent(new Event("characteristicvaluechanged"));
  }
}

class Device extends EventTarget {
  constructor(allowedServices) {
    super();
    this.name = "respirAI";
    this.allowed = allowedServices.map((s) => s.toLowerCase());
    this.chars = {
      [AUDIO]: new Characteristic(AUDIO, this, ["notify"]),
      [CONTROL]: new Characteristic(CONTROL, this, ["write"]),
      [STATUS]: new Characteristic(STATUS, this, ["notify", "read"]),
    };
    const device = this;
    this.gatt = {
      connected: false,
      device,
      connect() { this.connected = true; return Promise.resolve(this); },
      disconnect() { device.drop(); },
      getPrimaryService(id) {
        if (!this.connected) return fail("NetworkError", "GATT Server is disconnected.");
        if (!device.allowed.includes(id.toLowerCase())) return fail("SecurityError", `Service ${id} is not in optionalServices.`);
        if (id !== SERVICE) return fail("NotFoundError", `No service ${id}.`);
        return Promise.resolve({
          uuid: SERVICE,
          getCharacteristic: (c) => (device.chars[c] ? Promise.resolve(device.chars[c]) : fail("NotFoundError", `No characteristic ${c}.`)),
        });
      },
    };
    this.seq = 0;
    this.t = 0;
    this.samplesPerPacket = Math.min(80, ((MTU - 5) >> 1) & ~1);
  }

  command(bytes) {
    console.log("[fakebt] command", [...bytes].map((b) => b.toString(16).padStart(2, "0")).join(" "));
    if (bytes[0] === 0x01 && !this.timer) {
      this.timer = setInterval(() => this.tick(), 10);
      this.statusTimer = setInterval(() => this.status(), 2000);
      this.streamingSince = performance.now();
    }
    if (bytes[0] === 0x02) this.stop();
    if (bytes[0] === 0x20) this.status();
  }

  tick() {   // 10 ms of breath-like noise, split into packets as the firmware would
    if (DISCONNECT_AFTER && performance.now() - this.streamingSince > DISCONNECT_AFTER * 1000) return this.drop();
    const samples = new Int16Array(80);
    for (let i = 0; i < 80; i++, this.t++) {
      const breath = 0.15 + 0.85 * Math.max(0, Math.sin((2 * Math.PI * this.t) / 64000));
      samples[i] = (Math.random() * 2 - 1) * 4000 * breath;
    }
    this.pending = this.pending ? Int16Array.from([...this.pending, ...samples]) : samples;
    while (this.pending.length >= this.samplesPerPacket) {
      const n = this.samplesPerPacket;
      const view = new DataView(new ArrayBuffer(2 + 2 * n));
      view.setUint16(0, this.seq, true);
      for (let i = 0; i < n; i++) view.setInt16(2 + 2 * i, this.pending[i], true);
      this.seq = (this.seq + 1) & 0xffff;
      this.pending = this.pending.slice(n);
      if (Math.random() >= DROP) this.chars[AUDIO].notify(new Uint8Array(view.buffer));
    }
  }

  status() {
    this.chars[STATUS].notify(new Uint8Array([BATTERY, this.timer ? 1 : 0, 0, 0]));
  }

  stop() {
    clearInterval(this.timer);
    clearInterval(this.statusTimer);
    this.timer = null;
  }

  drop() {
    this.stop();
    if (!this.gatt.connected) return;
    this.gatt.connected = false;
    console.log("[fakebt] disconnected");
    this.dispatchEvent(new Event("gattserverdisconnected"));
  }
}

let current = null;
const fakeBluetooth = {
  requestDevice(options = {}) {
    const filters = options.filters || [];
    const matches = filters.some((f) => f.name === "respirAI" || (f.services || []).includes(SERVICE));
    if (!matches) return fail("NotFoundError", "No device matched the filters (fake respirAI device).");
    if (current) current.drop();
    current = new Device([...(options.optionalServices || []), ...filters.flatMap((f) => f.services || [])]);
    return Promise.resolve(current);
  },
};
// Chrome's navigator.bluetooth is read-only, so shadow it rather than assign it.
Object.defineProperty(navigator, "bluetooth", { value: fakeBluetooth, configurable: true });
window.fakeBt = { disconnect: () => current && current.drop() };
console.log(`[fakebt] fake Bluetooth device ready: MTU ${MTU} -> ${2 + 2 * Math.min(80, ((MTU - 5) >> 1) & ~1)}-byte packets, drop ${DROP}`);
