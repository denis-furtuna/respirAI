// Turning Bluetooth packets back into audio, and audio into a WAV (tasks A2, A6, A11).

export const SAMPLE_RATE = 8000;
const MAX_GAP = 50;  // packets (0.5 s). A bigger jump is a restart, not a few lost packets.

// Packet = uint16 sequence number + int16 samples, all little-endian.
// The packet size is fixed per connection but can be below 162 bytes on a low MTU,
// so it is learned from the first packet (contract 1).
export class PacketStream {
  constructor(onSamples) {
    this.onSamples = onSamples;
    this.reset();
  }

  reset() {
    this.lastSeq = null;
    this.packetSamples = null;
    this.received = 0;
    this.lost = 0;
  }

  push(view) {
    const seq = view.getUint16(0, true);
    const n = (view.byteLength - 2) >> 1;
    if (this.packetSamples === null) this.packetSamples = n;
    if (this.lastSeq !== null) {
      const gap = (seq - this.lastSeq - 1) & 0xffff;
      if (gap > 0x8000) return;  // a late or repeated packet: its slot is already filled
      if (gap > 0 && gap <= MAX_GAP) {
        this.lost += gap;
        this.onSamples(new Int16Array(gap * this.packetSamples));  // silence for what was lost
      }
    }
    this.lastSeq = seq;
    this.received++;
    const samples = new Int16Array(n);
    for (let i = 0; i < n; i++) samples[i] = view.getInt16(2 + 2 * i, true);
    this.onSamples(samples);
  }
}

// One chest point's recording, at most `seconds` long.
export class Recording {
  constructor(seconds) {
    this.data = new Int16Array(Math.round(seconds * SAMPLE_RATE));
    this.length = 0;
  }

  add(samples) {
    const n = Math.min(samples.length, this.data.length - this.length);
    this.data.set(samples.subarray(0, n), this.length);
    this.length += n;
  }

  get samples() {
    return this.data.subarray(0, this.length);
  }
}

// 16-bit mono PCM WAV, as contract 2 expects.
export function toWav(samples) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (offset, s) => [...s].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);              // fmt chunk size
  view.setUint16(20, 1, true);               // PCM
  view.setUint16(22, 1, true);               // mono
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true); // bytes per second
  view.setUint16(32, 2, true);               // bytes per sample
  view.setUint16(34, 16, true);              // bits per sample
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, s, true));
  return new Blob([view], { type: "audio/wav" });
}

let audioCtx = null;

export function play(samples) {
  audioCtx = audioCtx || new AudioContext();
  const buffer = audioCtx.createBuffer(1, samples.length, SAMPLE_RATE);
  const channel = buffer.getChannelData(0);
  samples.forEach((s, i) => { channel[i] = s / 32768; });
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);
  source.start();
}
