// respirAI LED test (tasks F-LED1 to F-LED5): the four LEDs behind the lung panel on their own, with no Bluetooth.
// Flash it, open the Serial Monitor at 115200, type a letter + Enter. It starts by lighting each LED in turn, so you
// can check the wiring. Same pins, PWM, gamma, breathing curve and fades as the firmware (respirai/config.h,
// respirai/leds.cpp), so what you see here is what the device will show. When the LEDs are right, flash
// firmware/respirai again.
#include <Arduino.h>
#include <driver/gpio.h>

// ---------- as firmware/respirai/config.h ----------
constexpr int PIN_LED_TRACHEA = 43;   // D6, through its own 100 ohm
constexpr int PIN_LED_LOBES   = 44;   // D7, both lobe LEDs in parallel, each with its OWN 100 ohm
constexpr int PIN_LED_AI      = 4;    // D3, behind the "AI" of the wordmark
constexpr uint32_t BREATH_IN_MS  = 4000;
constexpr uint32_t BREATH_OUT_MS = 5000;
constexpr float    TRACHEA_LEAD  = 0.2f;
constexpr float    AI_ON         = 1.0f;
constexpr uint32_t LED_PWM_HZ    = 20000;
constexpr uint8_t  LED_PWM_BITS  = 11;
constexpr uint32_t LED_FADE_MS   = 1000;

struct Led { const char* name; const char* pin; int gpio; };
static const Led LEDS[] = {
  {"AI", "D3", PIN_LED_AI},
  {"trachea", "D6", PIN_LED_TRACHEA},
  {"both lobes", "D7", PIN_LED_LOBES},
};
constexpr int AI = 0, TRACHEA = 1, LOBES = 2;

enum Test { OFF, IDENTIFY, BREATHE, FADE, WAITING, ERROR_BLINK, LOW_BATTERY, RAMP, STEADY };
static Test test = OFF;
static uint32_t since = 0;
static int step = -1;                  // the part of a test last announced, so each is printed once
static float level = 1.0f;             // the lungs' top brightness: LED_LEVEL in config.h
static bool lit[3] = {false, false, false};   // STEADY: which LEDs are on
static uint16_t gammaTable[256];
static bool pwmOk[3] = {false, false, false};   // ledcAttach() per LED, shown with the help

static float clamp01(float x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
static float ease(float k) { return (1 - cosf(PI * k)) / 2; }   // the curve of the app's circle

static void show(int led, float brightness) {   // perceived brightness 0-1 -> PWM duty, gamma 2.2
  ledcWrite(LEDS[led].gpio, gammaTable[(int)(clamp01(brightness) * 255 + 0.5f)]);
}

static void allOff() { for (int i = 0; i < 3; i++) show(i, 0); }

static void start(Test t) {
  test = t;
  since = millis();
  step = -1;
  allOff();
}

static bool announce(int s) {   // true once per new step
  if (s == step) return false;
  step = s;
  return true;
}

static void help() {
  Serial.println();
  Serial.println("respirAI LED test. Type a letter, then Enter:");
  Serial.println("  i  identify: each LED alone, one after another (checks the wiring)");
  Serial.println("  b  breathing guide, as the firmware: trachea first in, lobes first out; 4 s in, 5 s out");
  Serial.println("  f  fades: the 1 s fade-out when the guide stops, then each LED slowly up and down");
  Serial.println("  w  \"AI\" waiting for a phone: smooth blink every 2 s");
  Serial.println("  e  \"AI\" error (no mic): fast blink");
  Serial.println("  l  \"AI\" low battery: double blink every 4 s");
  Serial.println("  r  ramp: all LEDs from 0 to 100 % in 10 % steps, 1 s each (to choose resistors and LED_LEVEL)");
  Serial.println("  1 / 2 / 3  switch the AI / trachea / lobes LED on or off, steady");
  Serial.println("  a  all on, steady      0  all off");
  Serial.println("  + / -  lungs brightness (LED_LEVEL) up or down by 10 %");
  Serial.println("  h  this help");
  Serial.printf("Lungs brightness now: %.0f %%.\n", level * 100);
  for (int i = 0; i < 3; i++)
    if (!pwmOk[i]) Serial.printf("ERROR: no PWM on %s (%s): this LED can't be controlled.\n", LEDS[i].pin, LEDS[i].name);
  if (pwmOk[0] && pwmOk[1] && pwmOk[2]) Serial.println("PWM: OK on all three LED pins.");
  Serial.println();
}

static void handle(int c) {
  switch (c) {
    case 'i': start(IDENTIFY); break;
    case 'b': start(BREATHE); Serial.println("Breathing guide. Trachea leads in, lobes lead out. Any other letter stops it."); break;
    case 'f': start(FADE); break;
    case 'w': start(WAITING); Serial.println("\"AI\" waiting for a phone: fades on and off every 2 s, never a hard step."); break;
    case 'e': start(ERROR_BLINK); Serial.println("\"AI\" error: 4 blinks a second."); break;
    case 'l': start(LOW_BATTERY); Serial.println("\"AI\" low battery: two short blinks every 4 s."); break;
    case 'r': start(RAMP); break;
    case '1': case '2': case '3': {
      const int i = c - '1';
      if (test != STEADY) { for (bool& b : lit) b = false; start(STEADY); }
      lit[i] = !lit[i];
      Serial.printf("%s LED (%s) %s.\n", LEDS[i].name, LEDS[i].pin, lit[i] ? "on" : "off");
      break;
    }
    case 'a': start(STEADY); for (bool& b : lit) b = true; Serial.println("All on, steady. Every LED should be equally bright through the panel."); break;
    case '0': start(OFF); for (bool& b : lit) b = false; Serial.println("All off."); break;
    case '+': case '-':
      level = clamp01(level + (c == '+' ? 0.1f : -0.1f));
      if (level < 0.1f) level = 0.1f;
      Serial.printf("Lungs brightness %.0f %%: put LED_LEVEL = %.1ff in config.h to keep it.\n", level * 100, level);
      break;
    case 'h': case '?': help(); break;
    default: break;
  }
}

// The firmware's breathing guide (leds.cpp breathe()).
static void breathe(uint32_t t, float& trachea, float& lobes) {
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

static void update() {
  const uint32_t now = millis(), t = now - since;
  switch (test) {
    case OFF:
      break;

    case IDENTIFY: {   // 1.2 s each, 0.3 s dark between
      const int i = t / 1500;
      if (i >= 3) {
        allOff();
        Serial.println("Done. If a different LED lit than the one named, its wire is on the wrong pin. If one stayed dark,");
        Serial.println("turn it around (the long leg goes to the resistor side) and check its resistor and GND.");
        Serial.println("Type h + Enter for the other tests.");
        test = OFF;
        break;
      }
      if (announce(i)) Serial.printf("Now only the %s LED (%s) should be lit.\n", LEDS[i].name, LEDS[i].pin);
      allOff();
      if (t % 1500 < 1200) show(i, 1);
      break;
    }

    case BREATHE: {
      float trachea, lobes;
      breathe(t, trachea, lobes);
      if (announce(t % (BREATH_IN_MS + BREATH_OUT_MS) < BREATH_IN_MS ? 0 : 1)) Serial.println(step == 0 ? "  breathe in" : "  breathe out");
      show(TRACHEA, trachea * level);
      show(LOBES, lobes * level);
      show(AI, AI_ON);   // connected: the "AI" is on
      break;
    }

    case FADE: {   // lungs on 1 s, the stop fade, 1 s dark, then each LED 2 s up and 2 s down
      const uint32_t slow = 2000 + LED_FADE_MS;
      if (t < 1000) {
        if (announce(0)) Serial.println("Lungs on...");
        show(TRACHEA, level);
        show(LOBES, level);
      } else if (t < 1000 + LED_FADE_MS) {
        if (announce(1)) Serial.println("...and the guide stops: a 1 s fade out, never a cut.");
        const float k = 1 - (t - 1000) / (float)LED_FADE_MS;
        show(TRACHEA, level * k);
        show(LOBES, level * k);
      } else if (t < slow) {
        allOff();
      } else if (t < slow + 3 * 4000) {
        const int i = (t - slow) / 4000;
        const float k = ((t - slow) % 4000) / 2000.0f;   // 0..2
        if (announce(2 + i)) Serial.printf("Slow fade, %s LED: it should glide, with no steps or flicker near dark.\n", LEDS[i].name);
        allOff();
        show(i, (i == AI ? AI_ON : level) * ease(k < 1 ? k : 2 - k));
      } else {
        allOff();
        Serial.println("Fades done. Type f + Enter to see them again.");
        test = OFF;
      }
      break;
    }

    case WAITING: {   // leds.cpp statusLight(), not connected
      const uint32_t c = now % 2000;
      show(AI, AI_ON * (c < 1000 ? ease(c / 1000.0f) : 1 - ease((c - 1000) / 1000.0f)));
      break;
    }

    case ERROR_BLINK:
      show(AI, (now / 125) % 2 ? 1.0f : 0.0f);
      break;

    case LOW_BATTERY: {
      const uint32_t c = now % 4000;
      show(AI, c < 120 || (c >= 300 && c < 420) ? 1.0f : 0.0f);
      break;
    }

    case RAMP: {
      const int s = t / 1000;
      if (s > 10) {
        allOff();
        Serial.println("Ramp done. Choose a brightness with + and -, or swap resistors: 47 ohm brighter, 220 ohm dimmer, never below 47.");
        test = OFF;
        break;
      }
      const float k = s / 10.0f;
      if (announce(s)) Serial.printf("  %3d %%  (PWM duty %4u of %u)\n", s * 10, gammaTable[(int)(k * 255 + 0.5f)], (1u << LED_PWM_BITS) - 1);
      for (int i = 0; i < 3; i++) show(i, k);
      break;
    }

    case STEADY:
      for (int i = 0; i < 3; i++) show(i, lit[i] ? (i == AI ? AI_ON : level) : 0);
      break;
  }
}

void setup() {
  Serial.begin(115200);
  const float maxDuty = (1 << LED_PWM_BITS) - 1;
  for (int i = 0; i < 256; i++) gammaTable[i] = (uint16_t)(maxDuty * powf(i / 255.0f, 2.2f) + 0.5f);
  ledcSetClockSource(LEDC_USE_APB_CLK);   // as leds.cpp: 11 bits at 20 kHz need the 80 MHz clock, or every attach fails
  for (const Led& led : LEDS) {
    pwmOk[&led - LEDS] = ledcAttach(led.gpio, LED_PWM_HZ, LED_PWM_BITS);
    gpio_set_drive_capability((gpio_num_t)led.gpio, GPIO_DRIVE_CAP_3);   // strongest drive, as the firmware
    ledcWrite(led.gpio, 0);
  }
  const uint32_t t = millis();
  while (!Serial && millis() - t < 3000) delay(10);   // USB serial: give the Serial Monitor a moment to attach
  help();
  start(IDENTIFY);
}

void loop() {
  while (Serial.available()) {
    const int c = tolower(Serial.read());
    if (c != '\n' && c != '\r' && c != ' ') handle(c);
  }
  static uint32_t lastFrame = 0;
  if (millis() - lastFrame >= 20) {   // 50 frames a second, as the firmware
    lastFrame = millis();
    update();
  }
}
