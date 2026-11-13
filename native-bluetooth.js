// Web Bluetooth, the part device.js and app.js use, on top of the phone app's own Bluetooth
// (BleClient from @capacitor-community/bluetooth-le, see native.js). Android's WebView has no Web Bluetooth,
// so in the phone app device.js talks to this instead and stays exactly the same.
// Tested with a stand-in BleClient in tests/native.html.
const error = (name, message) => new DOMException(message, name);
const REMEMBER = "respirai-ble";   // set once Bluetooth was allowed, so later starts can check it without asking
const HIGH_PRIORITY = 1;           // ConnectionPriority.CONNECTION_PRIORITY_HIGH: steady audio streaming

export function nativeBluetooth(ble, storage = globalThis.localStorage) {
  const bt = new EventTarget();
  let ready = null;

  // Asks for the "Nearby devices" permission the first time (Android 12+; location on older phones).
  const init = () => (ready ||= ble.initialize({ androidNeverForLocation: true }).then(async () => {
    try { storage.setItem(REMEMBER, "1"); } catch (e) { /* not essential */ }
    await ble.startEnabledNotifications((on) => bt.dispatchEvent(Object.assign(new Event("availabilitychanged"), { value: on })))
      .catch((e) => console.warn("Bluetooth on/off events:", e.message));
  }).catch((e) => {
    ready = null;   // asked again on the next tap
    throw /denied/i.test(e.message) ? error("NotAllowedError", e.message) : e;
  }));

  // Whether Bluetooth is on. Before the permission was ever given: "yes", so the app doesn't ask at start-up.
  bt.getAvailability = async () => {
    let allowed = false;
    try { allowed = storage.getItem(REMEMBER) === "1"; } catch (e) { /* unknown */ }
    if (!allowed) return true;
    try {
      await init();
      return await ble.isEnabled();
    } catch (e) {
      return true;   // can't tell: let Connect explain
    }
  };

  // The phone's device list, filtered to our service (the firmware advertises it with its name).
  bt.requestDevice = async ({ filters = [] } = {}) => {
    await init();
    if (!(await ble.isEnabled())) {
      await ble.requestEnable().catch(() => {});   // Android's own "Turn on Bluetooth?" prompt
      if (!(await ble.isEnabled())) throw new Error("Bluetooth adapter is off");
    }
    const services = filters.flatMap((f) => f.services || []);
    const name = filters.find((f) => f.name)?.name;
    try {
      return makeDevice(ble, await ble.requestDevice(services.length ? { services } : { name }));
    } catch (e) {
      throw /cancel|no device/i.test(e.message) ? error("NotFoundError", e.message) : e;   // picker closed: say nothing
    }
  };

  return bt;
}

function makeDevice(ble, { deviceId, name }) {
  const device = Object.assign(new EventTarget(), { id: deviceId, name });
  const characteristics = new Map();   // one object per characteristic, so device.js can remove its listeners
  let connected = false;
  const lost = () => {
    if (!connected) return;
    connected = false;
    device.dispatchEvent(new Event("gattserverdisconnected"));
  };

  function characteristic(service, uuid) {
    const key = `${service}/${uuid}`;
    if (!characteristics.has(key)) {
      const c = new EventTarget();
      c.startNotifications = () => ble.startNotifications(deviceId, service, uuid, (value) => {
        c.value = value;
        c.dispatchEvent(new Event("characteristicvaluechanged"));
      });
      c.writeValueWithResponse = (data) => {
        const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
        return ble.write(deviceId, service, uuid, new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength));
      };
      characteristics.set(key, c);
    }
    return characteristics.get(key);
  }

  const server = {
    async getPrimaryService(uuid) {
      const found = (await ble.getServices(deviceId)).find((s) => s.uuid.toLowerCase() === uuid);
      if (!found) throw error("NotFoundError", `No service ${uuid}`);
      return {
        async getCharacteristic(c) {
          if (!found.characteristics.some((x) => x.uuid.toLowerCase() === c)) throw error("NotFoundError", `No characteristic ${c}`);
          return characteristic(uuid, c);
        },
      };
    },
  };

  device.gatt = {
    get connected() { return connected; },
    async connect() {   // also asks for the largest packets the device allows (the plugin requests MTU 512)
      try {
        await ble.connect(deviceId, lost);
      } catch (e) {   // some Android phones need a clean disconnect after an earlier connection (the plugin's README)
        await ble.disconnect(deviceId).catch(() => {});
        await ble.connect(deviceId, lost);
      }
      connected = true;
      ble.requestConnectionPriority?.(deviceId, HIGH_PRIORITY).catch(() => {});
      return server;
    },
    disconnect() {
      ble.disconnect(deviceId).catch(() => {});
      lost();   // Web Bluetooth also reports a disconnect the app asked for
    },
  };
  return device;
}
