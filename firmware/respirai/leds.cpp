#include "leds.h"
#include "config.h"
#include <Adafruit_NeoPixel.h>

static Adafruit_NeoPixel strip(LED_COUNT, PIN_LEDS, NEO_GRB + NEO_KHZ800);
static volatile LedMode mode = LED_WAITING;
static volatile uint32_t modeSince = 0;
static uint32_t lastFrame = 0;

void ledsBegin() {
  strip.begin();
  strip.setBrightness(LED_BRIGHTNESS);
  strip.clear();
  strip.show();
}

void ledsSet(LedMode m) {
  mode = m;
  modeSince = millis();
}

static float ease(float k) { return (1 - cosf(PI * k)) / 2; }

// A soft disc around the centre with the given radius (in pixels) and colour.
// Every drawing is symmetric, so it looks the same whether the matrix is wired row by row or zig-zag.
static void disc(float radius, uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < LED_COUNT; i++) {
    const float dx = (i % 8) - 3.5f, dy = (i / 8) - 3.5f;
    const float k = constrain(radius - sqrtf(dx * dx + dy * dy) + 0.5f, 0.0f, 1.0f);
    strip.setPixelColor(i, r * k, g * k, b * k);
  }
}

void ledsUpdate() {
  const uint32_t now = millis();
  if (now - lastFrame < 25) return;
  lastFrame = now;
  const uint32_t t = now - modeSince;

  switch (mode) {
    case LED_WAITING: {   // not connected: a slow blue blink in the middle
      const float k = (t % 2000) < 1000 ? ease((t % 1000) / 1000.0f) : 1 - ease((t % 1000) / 1000.0f);
      disc(1.2f, 0, 40 * k, 160 * k);
      break;
    }
    case LED_IDLE: {      // connected: a dim, calm glow
      const float k = 0.5f + 0.5f * sinf(t / 1600.0f);
      disc(2.0f + k, 20, 60 + 40 * k, 120 + 60 * k);
      break;
    }
    case LED_GUIDE: {     // the disc grows while breathing in, shrinks while breathing out
      const uint32_t phase = t % (BREATH_IN_MS + BREATH_OUT_MS);
      const float k = phase < BREATH_IN_MS ? ease(phase / (float)BREATH_IN_MS)
                                           : 1 - ease((phase - BREATH_IN_MS) / (float)BREATH_OUT_MS);
      disc(0.8f + 4.4f * k, 60, 150, 255);
      break;
    }
    case LED_DONE: {      // point recorded: green that fades, then back to idle
      if (t > 900) { ledsSet(LED_IDLE); return; }
      disc(6.0f, 0, 255 * (1 - t / 900.0f), 80 * (1 - t / 900.0f));
      break;
    }
  }
  strip.show();
}
