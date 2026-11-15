// Host test for dsp.h: the worst inputs there are, to prove the conversion can only flatten at the limit, never
// wrap around. No Arduino needed:
//     g++ -std=c++17 -O2 -o dsp_test firmware/respirai/tests/dsp_test.cpp && ./dsp_test
#include "../dsp.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

static int failures = 0;
static void check(const char* what, bool ok) {
  printf("%s %s\n", ok ? "ok   " : "FAIL ", what);
  if (!ok) failures++;
}

// A 24-bit sample as the I2S driver delivers it: in the top of a 32-bit word, low byte anything.
static int32_t word(int32_t s24, uint8_t low = 0) { return (int32_t)(((uint32_t)s24 << 8) | low); }

struct Result { std::vector<int16_t> out; uint32_t clipped = 0; };
static Result run(const std::vector<int32_t>& raw, float gain) {
  Downsampler d;
  d.begin(16000);
  Result r;
  r.out.resize(raw.size() / 2);
  for (size_t at = 0; at + 160 <= raw.size(); at += 160) d.process(raw.data() + at, 160, r.out.data() + at / 2, gain, r.clipped);
  return r;
}

// Wrap-around shows as a jump between neighbours that is bigger than the real signal could make. With the true
// (unlimited) value known, the test is exact instead: every output must equal the limited true value.
static bool matchesLimitedTruth(const std::vector<int32_t>& raw, float gain, const Result& r) {
  Downsampler d;
  d.begin(16000);
  for (size_t i = 0, k = 0; i < raw.size(); i++) {
    const float x = (float)(raw[i] >> 8) / 256.0f, y = x - d.dcPrevIn + 0.995f * d.dcPrevOut;
    d.dcPrevIn = x; d.dcPrevOut = y;
    d.history[d.head] = y; d.head = (d.head + 1) % Downsampler::TAPS;
    if (i & 1) {
      double acc = 0;
      for (int t = 0; t < Downsampler::TAPS; t++) acc += (double)d.taps[t] * d.history[(d.head + t) % Downsampler::TAPS];
      const double v = acc * gain, limited = v > 32767 ? 32767 : v < -32768 ? -32768 : v;
      if (k >= r.out.size()) break;
      if (std::abs(r.out[k] - limited) > 1.5) { printf("      sample %zu: got %d, true value %.1f\n", k, r.out[k], v); return false; }
      k++;
    }
  }
  return true;
}

int main() {
  const int N = 16000 * 4;   // 4 s at 16 kHz
  const int32_t MAX24 = 8388607, MIN24 = -8388608;
  const double pi = 3.14159265358979;

  // 1. Extreme inputs at several gains: the output is always the true value, limited.
  struct Case { const char* name; std::vector<int32_t> raw; };
  std::vector<Case> cases;
  { Case c{"full-scale square wave at 100 Hz", {}}; for (int i = 0; i < N; i++) c.raw.push_back(word((i / 80) % 2 ? MAX24 : MIN24)); cases.push_back(c); }
  { Case c{"full-scale alternating every sample (8 kHz)", {}}; for (int i = 0; i < N; i++) c.raw.push_back(word(i % 2 ? MAX24 : MIN24)); cases.push_back(c); }
  { Case c{"full-scale 3 kHz sine", {}}; for (int i = 0; i < N; i++) c.raw.push_back(word((int32_t)(8388607 * sin(2 * pi * 3000 * i / 16000.0)))); cases.push_back(c); }
  { Case c{"full-scale 150 Hz sine + low byte noise", {}}; for (int i = 0; i < N; i++) c.raw.push_back(word((int32_t)(8388607 * sin(2 * pi * 150 * i / 16000.0)), (uint8_t)rand())); cases.push_back(c); }
  { Case c{"full-scale random noise", {}}; for (int i = 0; i < N; i++) c.raw.push_back((int32_t)(((uint32_t)rand() << 17) ^ ((uint32_t)rand() << 2))); cases.push_back(c); }
  { Case c{"stuck at most negative, then most positive", {}}; for (int i = 0; i < N; i++) c.raw.push_back(i < N / 2 ? INT32_MIN : INT32_MAX); cases.push_back(c); }
  for (const float gain : {1.0f, 4.0f, 64.0f}) {
    for (const Case& c : cases) {
      const Result r = run(c.raw, gain);
      char what[160];
      snprintf(what, sizeof(what), "gain %2.0f, %s: limited, never wrapped (%u at the limit)", gain, c.name, (unsigned)r.clipped);
      check(what, matchesLimitedTruth(c.raw, gain, r));
    }
  }

  // 2. Scaling: a full-scale 24-bit sine comes out as a full-scale 16-bit sine at gain 1 (no hidden gain or shift).
  {
    std::vector<int32_t> raw;
    for (int i = 0; i < N; i++) raw.push_back(word((int32_t)(8388607 * 0.5 * sin(2 * pi * 400 * i / 16000.0))));
    const Result r = run(raw, 1.0f);
    int peak = 0;
    for (size_t i = 800; i < r.out.size(); i++) peak = std::max(peak, std::abs((int)r.out[i]));
    printf("      half-scale 400 Hz in -> peak %d out (half scale = 16384)\n", peak);
    check("gain 1: half scale in = half scale out (within 2 %)", std::abs(peak - 16384) < 330 && r.clipped == 0);
  }

  // 3. What gain 4 does to a signal at 50 % of scale with high-frequency content: jumps from one limit to the
  //    other between neighbouring samples, WITHOUT any wrap-around. It only flattens; the jumps are the signal's own.
  {
    std::vector<int32_t> raw;
    //    (Broadband noise at half scale, like rubbing or knocks on the chest piece.)
    srand(7);
    for (int i = 0; i < N; i++) raw.push_back(word((int32_t)(8388607 * 0.5 * (2.0 * rand() / RAND_MAX - 1.0))));
    for (const float gain : {4.0f, 1.0f}) {
      const Result r = run(raw, gain);
      int railToRail = 0;
      for (size_t i = 801; i < r.out.size(); i++)
        if ((r.out[i] == 32767 && r.out[i - 1] == -32768) || (r.out[i] == -32768 && r.out[i - 1] == 32767)) railToRail++;
      printf("      gain %.0f: %.1f %% of samples at the limit, %d jumps from one limit straight to the other in %.0f s\n",
             gain, 100.0 * r.clipped / r.out.size(), railToRail, r.out.size() / 8000.0);
      if (gain == 4.0f) check("gain 4 on a loud signal: many samples at the limit, still not wrapped", r.clipped > 0 && matchesLimitedTruth(raw, gain, r));
      else check("gain 1 on the same signal: nothing at the limit", r.clipped == 0);
    }
  }

  printf("\n%s\n", failures ? "FAILED" : "ALL GOOD");
  return failures ? 1 : 0;
}
