"""A fake respirAI device over real Bluetooth, running on a Windows laptop.

It serves contract 1 (docs/ARCHITECTURE.md) like the firmware: the phone's Chrome connects to it
for real, so the whole Bluetooth path is tested before the hardware exists.

    pip install winrt-Windows.Devices.Bluetooth winrt-Windows.Devices.Bluetooth.GenericAttributeProfile \
                winrt-Windows.Storage.Streams winrt-Windows.Foundation winrt-Windows.Foundation.Collections
    python fake_device.py              # breath-like noise
    python fake_device.py --crackles   # with crackle-like clicks while breathing in
    python fake_device.py --file recordings/crackles.wav   # a real recording, looped
                                       # 8 kHz 16-bit WAVs need nothing extra; other files: pip install numpy scipy soundfile

Then in the app press "Connect the device". Windows advertises under the computer's own
Bluetooth name, not "respirAI"; the app finds it by the service ID. A phone can't connect
to this from the same laptop's browser: use the phone, or another computer.
"""
import argparse
import asyncio
import math
import random
import struct
import uuid

from winrt.windows.devices.bluetooth import BluetoothAdapter
from winrt.windows.devices.bluetooth.genericattributeprofile import (
    GattCharacteristicProperties as Props,
    GattLocalCharacteristicParameters,
    GattProtectionLevel,
    GattServiceProvider,
    GattServiceProviderAdvertisingParameters,
    GattWriteOption,
)
from winrt.windows.storage.streams import DataReader, DataWriter

UUID = lambda n: uuid.UUID(f"7b8c9d00-000{n}-4b5e-8f00-1a2b3c4d5e6f")
SERVICE, AUDIO, CONTROL, STATUS = UUID(1), UUID(2), UUID(3), UUID(4)
POINTS = ["Tc", "Al", "Ar", "Pl", "Pr", "Ll", "Lr"]


def to_buffer(data: bytes):
    writer = DataWriter()
    writer.write_bytes(data)
    return writer.detach_buffer()


def from_buffer(buffer) -> bytes:
    reader = DataReader.from_buffer(buffer)
    return bytes(reader.read_byte() for _ in range(reader.unconsumed_buffer_length))


class FakeDevice:
    def __init__(self, crackles: bool, battery: int, recording=None):
        self.crackles, self.battery, self.recording = crackles, battery, recording
        self.streaming = False
        self.seq = 0
        self.t = 0
        self.sent = 0

    async def characteristic(self, provider, uid, props, name):
        params = GattLocalCharacteristicParameters()
        params.characteristic_properties = props
        params.read_protection_level = GattProtectionLevel.PLAIN
        params.write_protection_level = GattProtectionLevel.PLAIN
        params.user_description = name
        result = await provider.service.create_characteristic_async(uid, params)
        if result.error:
            raise RuntimeError(f"Could not create the {name} characteristic: error {result.error}")
        return result.characteristic

    async def start(self):
        self.loop = asyncio.get_running_loop()
        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None or not adapter.is_peripheral_role_supported:
            raise SystemExit("This computer's Bluetooth can't act as a device (no peripheral role).")
        created = await GattServiceProvider.create_async(SERVICE)
        if created.error:
            raise SystemExit(f"Could not create the service: error {created.error}. Is Bluetooth switched on?")
        self.provider = created.service_provider
        self.audio = await self.characteristic(self.provider, AUDIO, Props.NOTIFY, "Audio")
        control = await self.characteristic(self.provider, CONTROL, Props.WRITE | Props.WRITE_WITHOUT_RESPONSE, "Control")
        self.status_chr = await self.characteristic(self.provider, STATUS, Props.NOTIFY | Props.READ, "Status")
        control.add_write_requested(lambda sender, args: asyncio.run_coroutine_threadsafe(self.on_write(args), self.loop))
        self.audio.add_subscribed_clients_changed(lambda sender, args: self.loop.call_soon_threadsafe(self.on_subscribers))

        adv = GattServiceProviderAdvertisingParameters()
        adv.is_connectable = True
        adv.is_discoverable = True
        self.provider.start_advertising_with_parameters(adv)
        for _ in range(50):
            if self.provider.advertisement_status.name.lower() == "started":
                break
            await asyncio.sleep(0.1)
        print(f"Advertising the respirAI service ({self.provider.advertisement_status.name}). "
              "In the app, press 'Connect the device' and pick this computer.")
        asyncio.create_task(self.stream())
        asyncio.create_task(self.status_every_2s())

    def packet_samples(self):
        clients = list(self.audio.subscribed_clients)
        if not clients:
            return 80
        mtu = min(c.session.max_pdu_size for c in clients)
        return min(80, ((mtu - 5) // 2) & ~1)

    def on_subscribers(self):
        n = len(list(self.audio.subscribed_clients))
        print(f"Audio subscribers: {n}" + (f", {2 + 2 * self.packet_samples()}-byte packets" if n else ""))
        if not n:
            self.streaming = False

    async def on_write(self, args):
        deferral = args.get_deferral()
        try:
            request = await args.get_request_async()
            data = from_buffer(request.value)
            if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                request.respond()
        finally:
            deferral.complete()
        if not data:
            return
        cmd = data[0]
        if cmd == 0x01:
            self.streaming = True
            print("Command: start streaming")
        elif cmd == 0x02:
            self.streaming = False
            print("Command: stop streaming")
        elif cmd == 0x10:
            point = POINTS[data[1]] if len(data) > 1 and data[1] < 7 else "?"
            print(f"LEDs: breathing guide ({point})")
        elif cmd == 0x11:
            print("LEDs: point done (green)")
        elif cmd == 0x12:
            print("LEDs: idle")
        elif cmd == 0x20:
            await self.send_status()
        else:
            print(f"Unknown command 0x{cmd:02x}")

    def block(self):
        """10 ms of audio at 8 kHz as int16: the recording, or breath-like noise."""
        if self.recording:
            out = [self.recording[(self.t + i) % len(self.recording)] for i in range(80)]
            self.t += 80
            return out
        out = []
        for _ in range(80):
            phase = math.sin(2 * math.pi * self.t / 64000)          # ~8 s breathing cycle
            breath = 0.15 + 0.85 * max(0.0, phase)
            x = (random.random() * 2 - 1) * 4000 * breath
            if self.crackles and phase > 0.3 and random.random() < 0.0004:
                self.click = 1.0
            if getattr(self, "click", 0) > 0.01:                    # short decaying click
                x += 20000 * self.click * math.sin(self.t * 0.6)
                self.click *= 0.85
            out.append(max(-32768, min(32767, int(x))))
            self.t += 1
        return out

    async def stream(self):
        pending = []
        next_at = self.loop.time()
        while True:
            next_at += 0.01
            await asyncio.sleep(max(0, next_at - self.loop.time()))
            if not self.streaming:
                pending = []
                continue
            pending += self.block()
            n = self.packet_samples()
            while len(pending) >= n:
                payload = struct.pack(f"<H{n}h", self.seq, *pending[:n])
                pending = pending[n:]
                self.seq = (self.seq + 1) & 0xFFFF
                self.sent += 1
                try:
                    await self.audio.notify_value_async(to_buffer(payload))
                except OSError as e:
                    print("Notify failed:", e)

    async def send_status(self):
        packets, self.sent = self.sent, 0
        await self.status_chr.notify_value_async(
            to_buffer(bytes([self.battery, 1 if self.streaming else 0]) + struct.pack("<H", packets & 0xFFFF)))

    async def status_every_2s(self):
        while True:
            await asyncio.sleep(2)
            if list(self.status_chr.subscribed_clients):
                await self.send_status()


def load_recording(path):
    """Audio file -> 8 kHz int16 samples. 8 kHz 16-bit mono WAVs need only the standard library."""
    import wave
    try:
        with wave.open(path) as w:
            if (w.getframerate(), w.getsampwidth(), w.getnchannels()) == (8000, 2, 1):
                samples = list(struct.unpack(f"<{w.getnframes()}h", w.readframes(w.getnframes())))
                print(f"Streaming {path}: {len(samples) / 8000:.1f} s, looped")
                return samples
    except wave.Error:
        pass   # not a plain WAV: decode it below

    from math import gcd

    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    g = gcd(int(sr), 8000)
    x = resample_poly(x, 8000 // g, int(sr) // g)
    x = x / max(1e-9, float(np.abs(x).max())) * 0.5
    print(f"Streaming {path}: {len(x) / 8000:.1f} s, looped")
    return (x * 32767).astype(np.int16).tolist()


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--crackles", action="store_true", help="add crackle-like clicks while breathing in")
    parser.add_argument("--battery", type=int, default=87, help="battery %% to report (255 = unknown)")
    parser.add_argument("--file", help="stream this audio file (looped) instead of generated breathing")
    args = parser.parse_args()
    recording = load_recording(args.file) if args.file else None
    await FakeDevice(args.crackles, args.battery, recording).start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
