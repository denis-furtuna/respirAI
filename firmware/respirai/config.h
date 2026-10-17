// Pins, contract values and tuning knobs. Pins: docs/PLAN.md §3. Contract: docs/ARCHITECTURE.md §1.
#pragma once
#include <Arduino.h>

// ---------- wiring (XIAO ESP32-S3) ----------
constexpr int PIN_MIC_SCK = 7;    // D8
constexpr int PIN_MIC_WS  = 8;    // D9
constexpr int PIN_MIC_SD  = 9;    // D10
constexpr int PIN_LED_TRACHEA = 43;   // D6, through its own 100 ohm
constexpr int PIN_LED_LOBES   = 44;   // D7, both lobe LEDs in parallel, each with its OWN 100 ohm (never one shared)
constexpr int PIN_LED_AI      = 4;    // D3, behind the "AI" of the wordmark: power and status light
constexpr int PIN_BATTERY     = -1;   // ADC pin of a 1:2 divider on BAT+ (2 = D1). -1 = not wired: reports 255 ("unknown")

// ---------- contract 1 ----------
#define DEVICE_NAME   "respirAI"
#define FW_VERSION    "respirai-fw 0.4 (4-LED lung panel)"
#define SERVICE_UUID  "7b8c9d00-0001-4b5e-8f00-1a2b3c4d5e6f"
#define AUDIO_UUID    "7b8c9d00-0002-4b5e-8f00-1a2b3c4d5e6f"
#define CONTROL_UUID  "7b8c9d00-0003-4b5e-8f00-1a2b3c4d5e6f"
#define STATUS_UUID   "7b8c9d00-0004-4b5e-8f00-1a2b3c4d5e6f"

constexpr uint32_t CAPTURE_RATE   = 16000;   // what the mic is read at
constexpr uint32_t STREAM_RATE    = 8000;    // what the phone gets
constexpr int      BLOCK_SAMPLES  = 80;      // 10 ms at 8 kHz = one full packet
constexpr int      MAX_PACKET_SAMPLES = 80;  // fewer if the phone negotiates a small MTU

enum Command : uint8_t { CMD_START = 0x01, CMD_STOP = 0x02, CMD_GUIDE = 0x10, CMD_DONE = 0x11, CMD_IDLE = 0x12, CMD_STATUS = 0x20 };
enum State : uint8_t { STATE_IDLE = 0, STATE_STREAMING = 1, STATE_ERROR = 2 };

// ---------- tuning ----------
constexpr float    MIC_GAIN        = 4.0f;   // raise if lung sounds look tiny in the app, lower if the server reports clipping
constexpr uint32_t BREATH_IN_MS    = 4000;   // mirrored in app/app.js (BREATH_IN, BREATH_OUT): change both together,
constexpr uint32_t BREATH_OUT_MS   = 5000;   // or the LEDs and the circle on the phone drift apart
constexpr float    TRACHEA_LEAD    = 0.2f;   // the trachea leads the lobes by this share of a breath. Tune on the hardware
constexpr float    LED_LEVEL       = 1.0f;   // lungs at the top of a breath, 0-1. Set the brightness with the resistors first
constexpr float    AI_ON           = 1.0f;   // "AI" while connected (always on), and the peak of its blink. 0.4 = a softer glow
constexpr uint32_t LED_PWM_HZ      = 20000;  // far above the 100-1800 Hz the AI listens to
constexpr uint8_t  LED_PWM_BITS    = 11;     // the most the LEDC allows at 20 kHz (80 MHz / 20 kHz = 4000 steps)
constexpr uint32_t LED_FADE_MS     = 1000;   // the lungs fade out when the guide stops, so a stop never looks like a glitch
constexpr uint32_t GUIDE_MAX_MS    = 60000;  // a guide never needs longer (one practice breath + at most 20 s): stop if the app's stop got lost
constexpr uint8_t  BATTERY_LOW     = 15;     // percent: below this the "AI" double-blinks (needs PIN_BATTERY)
constexpr uint32_t STATUS_EVERY_MS = 2000;
