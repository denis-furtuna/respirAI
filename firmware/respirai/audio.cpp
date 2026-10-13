#include "audio.h"
#include "config.h"
#include <ESP_I2S.h>

static I2SClass i2s;

// 31-tap windowed-sinc low-pass at 3.5 kHz: removes everything that would alias
// when we keep every second sample (16 kHz -> 8 kHz).
constexpr int TAPS = 31;
static float taps[TAPS];
static float history[TAPS];
static int head = 0;

// DC blocker: the INMP441 output sits on an offset.
static float dcPrevIn = 0, dcPrevOut = 0;

bool audioBegin() {
  const float fc = 3500.0f / CAPTURE_RATE;
  float sum = 0;
  for (int n = 0; n < TAPS; n++) {
    const float m = n - (TAPS - 1) / 2.0f;
    const float sinc = m == 0 ? 2 * fc : sinf(2 * PI * fc * m) / (PI * m);
    const float hamming = 0.54f - 0.46f * cosf(2 * PI * n / (TAPS - 1));
    taps[n] = sinc * hamming;
    sum += taps[n];
  }
  for (float& t : taps) t /= sum;  // unity gain at DC

  i2s.setPins(PIN_MIC_SCK, PIN_MIC_WS, -1, PIN_MIC_SD);
  // The INMP441 sends 24-bit samples in 32-bit slots; L/R tied to GND = left slot.
  return i2s.begin(I2S_MODE_STD, CAPTURE_RATE, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT);
}

void audioRead(int16_t* out) {
  static int32_t raw[BLOCK_SAMPLES * 2];  // 10 ms at 16 kHz
  size_t want = sizeof(raw), got = 0;
  while (got < want) got += i2s.readBytes(reinterpret_cast<char*>(raw) + got, want - got);

  for (int i = 0, k = 0; i < BLOCK_SAMPLES * 2; i++) {
    const float x = (raw[i] >> 8) / 256.0f;        // 24-bit -> 16-bit scale
    const float y = x - dcPrevIn + 0.995f * dcPrevOut;
    dcPrevIn = x;
    dcPrevOut = y;
    history[head] = y;
    head = (head + 1) % TAPS;
    if (i & 1) {                                    // keep every second sample
      float acc = 0;
      for (int t = 0; t < TAPS; t++) acc += taps[t] * history[(head + t) % TAPS];
      out[k++] = (int16_t)constrain(acc * MIC_GAIN, -32768.0f, 32767.0f);
    }
  }
}
