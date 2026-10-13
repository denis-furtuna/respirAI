// The respirAI device over Web Bluetooth (contract 1 in docs/ARCHITECTURE.md),
// and a mock with the same interface so the app works without hardware.

const uuid = (n) => `7b8c9d00-000${n}-4b5e-8f00-1a2b3c4d5e6f`;
const SERVICE = uuid(1), AUDIO = uuid(2), CONTROL = uuid(3), STATUS = uuid(4);

export const CMD = {
  start: [0x01],
  stop: [0x02],
  guide: (n) => [0x10, n],   // LED breathing guide for chest point n
  done: [0x11],
  idle: [0x12],
  status: [0x20],
};

// handlers: { onPacket(DataView), onStatus({battery, state}), onDisconnect() }
export class BleDevice {
  constructor(handlers) {
    this.h = handlers;
    this.name = "respirAI";
    this.queue = Promise.resolve();
  }

  async connect() {
    if (!navigator.bluetooth) {
      throw new Error("Web Bluetooth isn't available here. Use Chrome on Android or a computer. " +
        "If the page is served over http://, add its address to chrome://flags/#unsafely-treat-insecure-origin-as-secure.");
    }
    // By name, or by our service ID (a Windows test peripheral can't change its name).
    this.device = await navigator.bluetooth.requestDevice({
      filters: [{ name: "respirAI" }, { services: [SERVICE] }],
      optionalServices: [SERVICE],
    });
    this.device.addEventListener("gattserverdisconnected", () => this.h.onDisconnect());
    const service = await (await this.device.gatt.connect()).getPrimaryService(SERVICE);
    this.control = await service.getCharacteristic(CONTROL);

    const audio = await service.getCharacteristic(AUDIO);
    audio.addEventListener("characteristicvaluechanged", (e) => this.h.onPacket(e.target.value));
    await audio.startNotifications();

    try {  // status is optional until firmware task F8 is done
      const status = await service.getCharacteristic(STATUS);
      status.addEventListener("characteristicvaluechanged", (e) =>
        this.h.onStatus({ battery: e.target.value.getUint8(0), state: e.target.value.getUint8(1) }));
      await status.startNotifications();
    } catch (e) {
      console.warn("No status characteristic yet:", e.message);
    }
  }

  // Bluetooth allows one write at a time, so writes are queued.
  send(bytes) {
    this.queue = this.queue.then(() => this.control.writeValueWithResponse(new Uint8Array(bytes)));
    return this.queue;
  }

  disconnect() {
    if (this.device && this.device.gatt.connected) this.device.gatt.disconnect();
  }
}

// Breath-like noise (about 4 s in, 4 s out) at 100 packets/s, dropping 1 packet in 200
// so the gap filling gets exercised too.
export class MockDevice {
  constructor(handlers) {
    this.h = handlers;
    this.name = "mock device";
    this.seq = 0;
    this.t = 0;
  }

  async connect() {}

  send(bytes) {
    if (bytes[0] === CMD.start[0] && !this.timer) this.timer = setInterval(() => this.tick(), 10);
    if (bytes[0] === CMD.stop[0]) this.stopTimer();
    if (bytes[0] === CMD.status[0]) setTimeout(() => this.h.onStatus({ battery: 87, state: this.timer ? 1 : 0 }), 50);
    return Promise.resolve();
  }

  tick() {
    const view = new DataView(new ArrayBuffer(162));
    view.setUint16(0, this.seq, true);
    for (let i = 0; i < 80; i++, this.t++) {
      const breath = 0.15 + 0.85 * Math.max(0, Math.sin((2 * Math.PI * this.t) / 64000));
      view.setInt16(2 + 2 * i, (Math.random() * 2 - 1) * 4000 * breath, true);
    }
    this.seq = (this.seq + 1) & 0xffff;
    if (Math.random() > 0.005) this.h.onPacket(view);
  }

  stopTimer() {
    clearInterval(this.timer);
    this.timer = null;
  }

  disconnect() {
    this.stopTimer();
    this.h.onDisconnect();
  }
}
