// Pins, contract values and tuning knobs. Pins: docs/PLAN.md §3. Contract: docs/ARCHITECTURE.md §1.
#pragma once
#include <Arduino.h>

// ---------- wiring (XIAO ESP32-S3) ----------
constexpr int PIN_MIC_SCK = 7;    // D8
constexpr int PIN_MIC_WS  = 8;    // D9
constexpr int PIN_MIC_SD  = 9;    // D10
constexpr int PIN_BATTERY     = -1;   // ADC pin of a 1:2 divider on BAT+ (2 = D1). -1 = not wired: reports 255 ("unknown")

// ---------- contract 1 ----------
#define DEVICE_NAME   "respirAI"
#define FW_VERSION    "respirai-fw 0.5 (no LEDs, gain 1)"
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
constexpr float    MIC_GAIN        = 1.0f;   // 1 = the microphone's own level. Raise it only if breathing is tiny in the app AND the
                                             // serial status shows 0 samples at the limit (the app's playback and waveform amplify by themselves)
constexpr uint32_t STATUS_EVERY_MS = 2000;
