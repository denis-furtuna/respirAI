#include "audio.h"
#include "config.h"
#include "dsp.h"
#include <ESP_I2S.h>
#include <atomic>

static I2SClass i2s;
static Downsampler dsp;                       // the conversion itself: dsp.h
static std::atomic<uint32_t> clippedCount{0};  // samples that hit the int16 limit since audioClipped() was last asked

// A working INMP441 never sends identical samples for long: even in silence its noise floor moves the low bits.
static volatile int flatBlocks = 0;
constexpr int FLAT_LIMIT = CAPTURE_RATE / (BLOCK_SAMPLES * 2);   // blocks in 1 s

bool audioBegin() {
  dsp.begin(CAPTURE_RATE);
  i2s.setPins(PIN_MIC_SCK, PIN_MIC_WS, -1, PIN_MIC_SD);
  // The INMP441 sends 24-bit samples, MSB first, in 32-bit slots (standard I2S); L/R tied to GND = left slot.
  return i2s.begin(I2S_MODE_STD, CAPTURE_RATE, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT);
}

bool audioSilent() { return flatBlocks >= FLAT_LIMIT; }

uint32_t audioClipped() { return clippedCount.exchange(0); }

void audioRead(int16_t* out) {
  static int32_t raw[BLOCK_SAMPLES * 2];  // 10 ms at 16 kHz
  size_t want = sizeof(raw), got = 0;
  while (got < want) got += i2s.readBytes(reinterpret_cast<char*>(raw) + got, want - got);

  bool flat = true;
  for (int i = 1; i < BLOCK_SAMPLES * 2 && flat; i++) flat = raw[i] == raw[0];
  flatBlocks = flat ? min(flatBlocks + 1, FLAT_LIMIT) : 0;

  uint32_t clipped = 0;
  dsp.process(raw, BLOCK_SAMPLES * 2, out, MIC_GAIN, clipped);
  if (clipped) clippedCount += clipped;
}
