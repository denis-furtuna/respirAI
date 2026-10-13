// The respirAI device over Web Bluetooth (contract 1 in docs/ARCHITECTURE.md).
// `bluetooth` is navigator.bluetooth, or a fake one from fake-bluetooth.js.

const uuid = (n) => `7b8c9d00-000${n}-4b5e-8f00-1a2b3c4d5e6f`;
export const SERVICE = uuid(1), AUDIO = uuid(2), CONTROL = uuid(3), STATUS = uuid(4);

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
  constructor(bluetooth, handlers) {
    Object.assign(this, { bluetooth, h: handlers, queue: Promise.resolve() });
  }

  async connect() {
    if (!this.bluetooth) {
      throw new Error("Web Bluetooth isn't available here. Use Chrome on Android or a computer. " +
        "If the page is served over http://, add its address to chrome://flags/#unsafely-treat-insecure-origin-as-secure.");
    }
    // By name, or by our service ID (a Windows test peripheral can't change its name).
    this.device = await this.bluetooth.requestDevice({ filters: [{ name: "respirAI" }, { services: [SERVICE] }], optionalServices: [SERVICE] });
    this.device.addEventListener("gattserverdisconnected", () => this.h.onDisconnect());
    const service = await (await this.device.gatt.connect()).getPrimaryService(SERVICE);
    this.control = await service.getCharacteristic(CONTROL);
    await this.subscribe(service, AUDIO, (v) => this.h.onPacket(v));
    try {  // status is optional until firmware task F8 is done
      await this.subscribe(service, STATUS, (v) => this.h.onStatus({ battery: v.getUint8(0), state: v.getUint8(1) }));
    } catch (e) {
      console.warn("No status characteristic yet:", e.message);
    }
  }

  async subscribe(service, uuid, onValue) {
    const c = await service.getCharacteristic(uuid);
    c.addEventListener("characteristicvaluechanged", (e) => onValue(e.target.value));
    await c.startNotifications();
  }

  // Bluetooth allows one write at a time, so writes are queued.
  send(bytes) {
    return (this.queue = this.queue.then(() => this.control.writeValueWithResponse(new Uint8Array(bytes))));
  }

  disconnect() {
    if (this.device && this.device.gatt.connected) this.device.gatt.disconnect();
  }
}
