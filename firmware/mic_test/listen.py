"""Hear the respirAI microphone on this computer, over the USB cable (no Bluetooth, no phone).

Flash firmware/mic_test first and close the Arduino Serial Monitor (only one program can use the port). Then:

    pip install pyserial sounddevice
    python firmware/mic_test/listen.py                 finds the XIAO, plays the sound live, saves a WAV on Ctrl+C
    python firmware/mic_test/listen.py COM5            a given port
    python firmware/mic_test/listen.py --seconds 20    stop by itself after 20 s
    python firmware/mic_test/listen.py --gain 8        play louder (the WAV is saved as it came, without this gain)
    python firmware/mic_test/listen.py --no-play       only save the WAV (sounddevice not needed)

The audio is exactly what the phone gets: 8 kHz, 16-bit, after the firmware's filter and MIC_GAIN. Use headphones:
a speaker next to the chest piece feeds back. The WAV opens in any player, and in Audacity for a closer look.
"""
import argparse
import math
import queue
import struct
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is missing:  pip install pyserial")

RATE = 8000
SAMPLES = 80                       # per frame: 10 ms
FRAME = 4 + 2 * SAMPLES            # "RA" + uint16 sequence + samples
MAGIC = b"RA"
ESPRESSIF_VID = 0x303A             # the XIAO ESP32-S3's own USB


def find_port():
    ports = [p for p in list_ports.comports() if p.vid == ESPRESSIF_VID]
    if len(ports) == 1:
        return ports[0].device
    found = "\n".join(f"  {p.device}: {p.description}" for p in list_ports.comports()) or "  none"
    sys.exit(("Several Espressif boards are connected; name one: listen.py COMx" if ports else
              "No XIAO ESP32-S3 found on USB. Is it plugged in with a data cable?") + f"\nPorts:\n{found}")


def open_port(name):
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = name, 115200, 0.2
    port.dtr = port.rts = False    # opening with these set can reset an ESP32-S3; the sketch would still restart fine
    try:
        port.open()
    except serial.SerialException as e:
        sys.exit(f"Can't open {name}: {e}\nClose the Arduino Serial Monitor (or any other program using the port) and try again.")
    return port


class Frames:
    """Finds frames in the byte stream: text from the sketch is skipped, and a lost byte costs one frame, not the rest."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            at = self.buf.find(MAGIC)
            if at < 0:
                del self.buf[:-1]
                return out
            if len(self.buf) < at + FRAME + 2:
                del self.buf[:at]
                return out
            if self.buf[at + FRAME:at + FRAME + 2] != MAGIC:   # not a frame boundary: "RA" inside text or samples
                del self.buf[:at + 1]
                continue
            seq, = struct.unpack_from("<H", self.buf, at + 2)
            out.append((seq, struct.unpack_from(f"<{SAMPLES}h", self.buf, at + 4)))
            del self.buf[:at + FRAME]


def player(gain):
    try:
        import sounddevice
    except ImportError:
        print("(sounddevice is missing, so nothing plays: pip install sounddevice. The WAV is still saved.)")
        return None, None
    q = queue.Queue(maxsize=50)        # up to 0.5 s waiting to play
    started = False

    def callback(out, frames, _time, _status):
        nonlocal started
        if not started and q.qsize() < 10:   # wait for 0.1 s of sound first, so Windows' timing doesn't make it crackle
            out[:] = b"\0" * len(out)
            return
        started = True
        data = bytearray()
        while len(data) < len(out):
            try:
                data += q.get_nowait()
            except queue.Empty:
                data += b"\0" * (len(out) - len(data))
                started = False
        out[:] = bytes(data[:len(out)])

    stream = sounddevice.RawOutputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=SAMPLES, callback=callback)
    stream.start()

    def play(samples):
        if gain != 1:
            samples = [max(-32768, min(32767, round(s * gain))) for s in samples]
        try:
            q.put_nowait(struct.pack(f"<{SAMPLES}h", *samples))
        except queue.Full:
            pass                         # the speaker fell behind: skip 10 ms rather than drift further behind
    return play, stream


def db(x):
    return 20 * math.log10(max(x, 0.5) / 32768)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("port", nargs="?", help="e.g. COM5 (default: the connected XIAO)")
    parser.add_argument("--seconds", type=float, default=0, help="stop after this long (default: Ctrl+C)")
    parser.add_argument("--gain", type=float, default=1, help="playback gain only (default 1)")
    parser.add_argument("--no-play", action="store_true", help="don't play, only save")
    parser.add_argument("--out", type=Path, help="WAV file to save (default: mic-<date>-<time>.wav here)")
    args = parser.parse_args()

    name = args.port or find_port()
    port = open_port(name)
    play, stream = (None, None) if args.no_play else player(args.gain)
    out = args.out or Path(f"mic-{datetime.now():%Y%m%d-%H%M%S}.wav")
    recorded, frames = bytearray(), Frames()
    last_seq, lost, received = None, 0, 0
    window, peak_hold, start, asked, heard = [], 0, time.monotonic(), 0, 0

    print(f"Listening on {name}. Ctrl+C to stop and save.")
    try:
        while not args.seconds or time.monotonic() - start < args.seconds:
            now = time.monotonic()
            if now - heard > 1 and now - asked > 1:   # no audio for 1 s: ask (again). The board may be starting, or was reset
                port.write(b"a\n")
                asked = now
                if not received and now - start > 8:
                    sys.exit("No audio after 8 s. Is firmware/mic_test on the board (not firmware/respirai)? "
                             "Open the Serial Monitor once to see what it says.")
            got = frames.feed(port.read(port.in_waiting or 1))
            if got:
                heard = time.monotonic()
            for seq, samples in got:
                if last_seq is not None:
                    gap = (seq - last_seq - 1) & 0xFFFF
                    if 0 < gap <= 50:
                        lost += gap
                        recorded += b"\0" * (2 * SAMPLES * gap)   # keep the timing right
                last_seq, received = seq, received + 1
                recorded += struct.pack(f"<{SAMPLES}h", *samples)
                if play:
                    play(samples)
                window.extend(samples)
                if len(window) >= RATE // 10:                    # a meter line every 100 ms
                    rms = math.sqrt(sum(s * s for s in window) / len(window))
                    peak = max(abs(s) for s in window)
                    peak_hold = max(peak, peak_hold * 0.9)
                    bar = "#" * max(0, min(30, round((db(rms) + 60) / 2)))
                    print(f"\r{received / 100:6.1f} s  level {db(rms):4.0f} dBFS [{bar:<30}] peak {db(peak_hold):4.0f} dBFS"
                          f"{'  CLIPPING' if peak >= 32000 else '          '}  lost {lost}", end="", flush=True)
                    window = []
    except KeyboardInterrupt:
        pass
    finally:
        try:
            port.write(b"x\n")           # back to the report view, so the board isn't left streaming
            port.close()
        except serial.SerialException:
            pass
        if stream:
            stream.stop()
            stream.close()
    print()
    if not recorded:
        sys.exit("Nothing recorded.")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(recorded)
    print(f"Saved {out} ({len(recorded) // 2 / RATE:.1f} s, {lost} frames lost of {received + lost}).")


if __name__ == "__main__":
    main()
