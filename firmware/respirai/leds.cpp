#include "leds.h"
#include "config.h"
#include <atomic>

// What the LEDs do:
//   lungs (trachea + lobes)  only the breathing guide. Inhale: the trachea rises first, then the lobes fill.
//                            Exhale: the lobes empty first, then the trachea. When the guide stops: a 300 ms fade.
//   "AI" of the wordmark     not connected: smooth blink (fades on and off every 2 s). Connected: always on.
//                            Only when something is wrong: double blink every 4 s on low battery, fast blink on
//                            error (no mic).
// The breathing curve is the raised cosine the app's circle uses; gamma goes on the LEDs only (duty = max * level^2.2),
// so both look in step. The app owns the timer: the device loops the breath until it is told to stop.

static std::atomic<int> requested{-1};   // set from the Bluetooth task, applied on the loop task
static LedMode mode = LED_WAITING;
static uint32_t modeSince = 0, lastFrame = 0;
static volatile bool deviceError = false;
static volatile uint8_t battery = 255;
static float trachea = 0, lobes = 0;       // shown now, 0-1 before gamma
static float fadeTrachea = 0, fadeLobes = 0;
static uint16_t gammaTable[256];

static float clamp01(float x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
static float ease(float k) { return (1 - cosf(PI * k)) / 2; }   // app/app.js uses the same curve

static void show(int pin, float level) {   // perceived brightness 0-1 -> PWM duty
  ledcWrite(pin, gammaTable[(int)(clamp01(level) * 255 + 0.5f)]);
}

void ledsBegin() {
  const float maxDuty = (1 << LED_PWM_BITS) - 1;
  for (int i = 0; i < 256; i++) gammaTable[i] = (uint16_t)(maxDuty * powf(i / 255.0f, 2.2f) + 0.5f);
  for (int pin : {PIN_LED_TRACHEA, PIN_LED_LOBES, PIN_LED_AI}) {
    if (!ledcAttach(pin, LED_PWM_HZ, LED_PWM_BITS)) Serial.printf("ERROR: no PWM on GPIO %d\n", pin);
    ledcWrite(pin, 0);
  }
}

void ledsSet(LedMode m) { requested = m; }

void ledsStatus(bool error, uint8_t percent) {
  deviceError = error;
  battery = percent;
}

static void enter(LedMode m, uint32_t now) {
  fadeTrachea = trachea;   // whatever comes next fades out from where the lungs are now
  fadeLobes = lobes;
  mode = m;
  modeSince = now;
}

static void breathe(uint32_t t) {
  const uint32_t phase = t % (BREATH_IN_MS + BREATH_OUT_MS);
  const float span = 1 - TRACHEA_LEAD;
  if (phase < BREATH_IN_MS) {
    const float p = phase / (float)BREATH_IN_MS;
    trachea = ease(clamp01(p / span));
    lobes = ease(clamp01((p - TRACHEA_LEAD) / span));
  } else {
    const float q = (phase - BREATH_IN_MS) / (float)BREATH_OUT_MS;
    lobes = 1 - ease(clamp01(q / span));
    trachea = 1 - ease(clamp01((q - TRACHEA_LEAD) / span));
  }
}

static float statusLight(uint32_t now) {
  if (deviceError) return (now / 125) % 2 ? 1.0f : 0.0f;              // fast blink, 4 per second
  if (battery <= BATTERY_LOW) {                                        // never true while unknown (255)
    const uint32_t c = now % 4000;
    if (c < 120 || (c >= 300 && c < 420)) return 1.0f;                 // double blink every 4 s
  }
  if (mode == LED_WAITING) {                                           // not connected: smooth blink, 2 s
    const uint32_t c = now % 2000;
    return AI_ON * (c < 1000 ? ease(c / 1000.0f) : 1 - ease((c - 1000) / 1000.0f));
  }
  return AI_ON;                                                        // connected: always on
}

void ledsUpdate() {
  const uint32_t now = millis();
  if (now - lastFrame < 20) return;
  lastFrame = now;
  const int r = requested.exchange(-1);
  if (r >= 0) enter((LedMode)r, now);
  if (mode == LED_GUIDE && now - modeSince > GUIDE_MAX_MS) enter(LED_IDLE, now);   // the app's stop got lost
  if (mode == LED_DONE && now - modeSince > 900) enter(LED_IDLE, now);
  const uint32_t t = now - modeSince;

  if (mode == LED_GUIDE) {
    breathe(t);
  } else {   // stopped: fade out, never cut
    const float k = 1 - clamp01(t / (float)LED_FADE_MS);
    trachea = fadeTrachea * k;
    lobes = fadeLobes * k;
  }
  show(PIN_LED_TRACHEA, trachea * LED_LEVEL);
  show(PIN_LED_LOBES, lobes * LED_LEVEL);
  show(PIN_LED_AI, statusLight(now));
}
