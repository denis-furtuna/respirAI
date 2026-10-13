# firmware/

Code that runs on the **Seeed XIAO ESP32-S3** inside the puck. It implements [contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble) exactly; changing anything in it means telling the app owner first.

Pin assignments are in [`docs/PLAN.md` §3](../docs/PLAN.md#3-wiring-reference). Task list: F1–F12 in [`docs/PLAN.md` §5.1](../docs/PLAN.md#51-firmware-owner-you).

## Files (`respirai/`, one Arduino sketch)

| File | What it does | Tasks |
|---|---|---|
| `config.h` | pins, UUIDs, commands, and the knobs you'll tune (mic gain, LED brightness, breathing rhythm) | — |
| `audio.cpp` | INMP441 over I²S at 16 kHz → DC removal → 3.5 kHz low-pass → every second sample = 8 kHz, 16-bit | F2, F3 |
| `respirai.ino` | Bluetooth service (audio notify, control, status), packet sizing from the negotiated MTU, start/stop, status every 2 s | F4, F5, F8 |
| `leds.cpp` | 8×8 matrix: waiting (blue blink), idle (dim glow), breathing guide (disc grows 4 s, shrinks 5 s), done (green fade) | F9, F10 |

Audio runs in its own task on core 1, so Bluetooth and the LEDs can't make it miss samples.

## Build and flash

**Arduino IDE 2:**
1. *File → Preferences → Additional boards manager URLs:* `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. *Boards Manager:* install **esp32 by Espressif** (3.x).
3. *Library Manager:* install **NimBLE-Arduino** (2.x) and **Adafruit NeoPixel**.
4. *Tools → Board:* **XIAO_ESP32S3**. *Tools → USB CDC On Boot:* **Enabled** (so the serial monitor works).
5. Open `firmware/respirai/respirai.ino`, upload, open the serial monitor at 115200.

**Or from the command line:**
```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:CDCOnBoot=cdc firmware/respirai
arduino-cli upload  --fqbn esp32:esp32:XIAO_ESP32S3:CDCOnBoot=cdc -p COM5 firmware/respirai
```

## Test it, step by step

| Step | How | Good when |
|---|---|---|
| Boots | Serial monitor | "Advertising as respirAI"; LEDs blink blue in the middle |
| Mic (F2) | If it prints "ERROR: I2S microphone did not start", check the wiring | no error |
| Bluetooth (F4) | **nRF Connect** app on the S25: scan, connect to *respirAI* | serial prints the MTU; LEDs change to a dim glow |
| Streaming (F5) | In nRF Connect, enable notifications on `…0002…`, write `01` to `…0003…` | serial status shows ~200 packets per 2 s |
| Full packets | Serial line "Audio subscribed: MTU …" | **162 bytes** per packet. Smaller still works, but tell the app owner |
| LEDs (F9, F10) | Write `1000`, then `11`, then `12` to `…0003…` | breathing disc, green fade, dim glow |
| Stability (F6) | Stream 10 minutes from the web app | "lost" stays near 0, no reboot |
| Real audio | Web app → practice the full flow with the real device | lung sounds visible in the small waveform |

## Things to tune on the real hardware

- **`MIC_GAIN`** in `config.h`: raise it if breathing barely moves the waveform; lower it if the AI server reports clipping (quality drops).
- **`LED_BRIGHTNESS`**: keep at or below 51 (20 %) on battery.
- **Battery level (F8)** needs a 1:2 resistor divider (two equal resistors, e.g. 2 × 100 kΩ) from BAT+ to a free analog pin; set `PIN_BATTERY` to that GPIO. Until then the device reports 255 ("unknown") and the app hides the battery.

Not done yet: the ECG and pulse add-ons (F11, F12, see [`docs/ADDONS.md`](../docs/ADDONS.md)).
