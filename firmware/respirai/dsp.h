// The sample conversion on its own, with no Arduino in it, so it can be tested on a computer:
// raw I2S words (24-bit sample in the top of a 32-bit slot, 16 kHz) -> DC removal -> 3.5 kHz low-pass ->
// every second sample (8 kHz) -> gain -> int16. All the arithmetic is in float and the result is limited
// BEFORE the cast, so no input can wrap around: the worst case is a flat top at +-full scale.
#pragma once
#include <math.h>
#include <stdint.h>

struct Downsampler {
  static constexpr int TAPS = 31;   // windowed-sinc low-pass: removes what would alias when every second sample is kept
  float taps[TAPS];
  float history[TAPS];
  int head = 0;
  float dcPrevIn = 0, dcPrevOut = 0;   // DC blocker: the INMP441 output sits on an offset

  void begin(float captureRate) {
    const float pi = 3.14159265358979f, fc = 3500.0f / captureRate;
    float sum = 0;
    for (int n = 0; n < TAPS; n++) {
      const float m = n - (TAPS - 1) / 2.0f;
      const float sinc = m == 0 ? 2 * fc : sinf(2 * pi * fc * m) / (pi * m);
      taps[n] = sinc * (0.54f - 0.46f * cosf(2 * pi * n / (TAPS - 1)));   // Hamming window
      sum += taps[n];
    }
    for (float& t : taps) t /= sum;   // unity gain at DC
    for (float& h : history) h = 0;
    head = 0;
    dcPrevIn = dcPrevOut = 0;
  }

  // Float -> int16, limited first. A NaN (never expected) becomes silence instead of an undefined cast.
  static int16_t toInt16(float v, uint32_t& clipped) {
    if (!(v == v)) return 0;
    if (v > 32767.0f) { clipped++; return 32767; }
    if (v < -32768.0f) { clipped++; return -32768; }
    return (int16_t)lrintf(v);
  }

  // count raw words in (an even number), count / 2 samples out. Adds the samples that hit the limit to `clipped`.
  int process(const int32_t* raw, int count, int16_t* out, float gain, uint32_t& clipped) {
    int k = 0;
    for (int i = 0; i < count; i++) {
      // The 24-bit sample sits in bits 31..8. The shift keeps its sign (arithmetic shift of a signed value),
      // so x is within +-8388608, and x / 256 is the 16-bit scale: +-32768.
      const float x = (float)(raw[i] >> 8) / 256.0f;
      const float y = x - dcPrevIn + 0.995f * dcPrevOut;
      dcPrevIn = x;
      dcPrevOut = y;
      history[head] = y;
      head = (head + 1) % TAPS;
      if (i & 1) {   // keep every second sample
        float acc = 0;
        for (int t = 0; t < TAPS; t++) acc += taps[t] * history[(head + t) % TAPS];
        out[k++] = toInt16(acc * gain, clipped);
      }
    }
    return k;
  }
};
