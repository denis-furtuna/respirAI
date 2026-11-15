# firmware/

Code that runs on the **Seeed XIAO ESP32-S3** inside the puck. It implements [contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble) exactly; changing anything in it means telling the app owner first.

Pin assignments are in [`docs/PLAN.md` §3](../docs/PLAN.md#3-wiring-reference). Task list: F1–F12 in [`docs/PLAN.md` §5.1](../docs/PLAN.md#51-firmware-owner-you).

## Where it stands (14 November 2026)

The device is assembled and closed in its box: XIAO, one INMP441 on the stethoscope's chest piece, a 2500 mAh LiPo and the power switch. No LEDs, no pulse or ECG sensor, no battery measurement (the app shows the battery as unknown). It runs `respirai-fw 0.5 (no LEDs, gain 1)`.

Measured with the app's microphone test, on USB and on battery:

| | Result |
|---|---|
| Bluetooth | 0 packets lost of 57 000 (USB) and of 25 000 (battery), full 162-byte packets |
| Level at `MIC_GAIN` 1 | 0 samples at the limit in two 10 s recordings (it was 7.5 % at gain 4, which sounded robotic) |
| USB against battery | the same background, −26 to −29 dBFS: the power supply adds no noise |
| Breath sounds | **not confirmed yet.** The test room was loud, and the recording on the chest looked the same as the background. To repeat in a quiet room |

## Files (`respirai/`, one Arduino sketch)

| File | What it does | Tasks |
|---|---|---|
| `config.h` | pins, UUIDs, commands, and the one knob you'll tune (`MIC_GAIN`) | — |
| `audio.cpp`, `dsp.h` | INMP441 over I²S at 16 kHz → DC removal → 3.5 kHz low-pass → every second sample = 8 kHz, 16-bit. The conversion is in `dsp.h`, with no Arduino in it: float arithmetic, limited before the cast, so it can flatten at full scale but never wrap around. `tests/dsp_test.cpp` proves it on a computer with the worst inputs there are | F2, F3 |
| `respirai.ino` | Bluetooth service (audio notify, control, status), packet sizing from the negotiated MTU, start/stop, status every 2 s | F4, F5, F8 |
| — | **No LEDs.** The app still sends its LED commands (`0x10`, `0x11`, `0x12`); the firmware accepts and ignores them. `led_test/` is an old sketch for a build with LEDs, not used now | — |

Audio runs in its own task on core 1, so Bluetooth can't make it miss samples.

## Module tests: one sketch per part

Each part is tested on its own first, before the full firmware and the app are involved. Each test is a separate sketch with the firmware's own pins and settings: flash it, open the serial monitor at 115200, and it says what to look for. When a part works, flash `respirai/` again.

| Sketch | Tests | Tasks |
|---|---|---|
| `mic_test/` | the INMP441: wiring check, live level, the audio on the computer over the USB cable | F2, E2, E3 |

Upload a test the same way as the firmware (see *Build and flash*), with its folder instead of `firmware/respirai`.

### Microphone test (`mic_test/`)

`mic_test/mic_test.ino` checks the INMP441 on its own, before Bluetooth or the app are involved (F2). Same pins and I²S setup as the firmware; it needs no library. Flash it, open the serial monitor at 115200:

1. **Wiring check** at start (keep quiet for 2 s). It names the fault instead of just failing: only zeros on SD (power, SD, SCK or WS), SD stuck at one value, the mic answering on the right slot (L/R not on GND), or a background too loud for a quiet room (SCK and WS swapped).
2. **Live report**, one line every 0.5 s: level, a meter from −90 to 0 dBFS, the peak, and how loud that peak would be **in the app** at the firmware's `MIC_GAIN`. A tap shows `<- sound`; `CLIPPING` and `would clip in the app: lower MIC_GAIN` say when to tune.
3. Type **`p`** + Enter for the **Serial Plotter** view (level, peak and background as curves), **`r`** to check the wiring again.
4. **Hear it on the computer, over the cable:** close the serial monitor, then
   ```bash
   pip install pyserial sounddevice
   python firmware/mic_test/listen.py          # finds the board, plays live, Ctrl+C saves mic-<date>-<time>.wav
   ```
   It plays exactly what the phone would get (8 kHz, the firmware's filter and `MIC_GAIN`) and shows a level meter. Use headphones; `--gain 8` plays louder, `--seconds 20` stops by itself.

When the mic is right, flash `respirai/` again. The app has a matching test for the whole chain (mic → Bluetooth → phone): *Settings → Microphone test* (`app/mic-test.html`, on the `phone-app` branch).


## Build and flash

**Arduino IDE 2:**
1. *File → Preferences → Additional boards manager URLs:* `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. *Boards Manager:* install **esp32 by Espressif** (3.x).
3. *Library Manager:* install **NimBLE-Arduino** (2.x).
4. *Tools → Board:* **XIAO_ESP32S3**. *Tools → USB Mode:* **Hardware CDC and JTAG**. *Tools → USB CDC On Boot:* **Enabled** (so the serial monitor works over USB).
5. Open `firmware/respirai/respirai.ino`, upload, open the serial monitor at 115200.

**Or from the command line:**

Careful: on the XIAO the option `CDCOnBoot=cdc` means **Disabled** (on most ESP32 boards it means Enabled). With it, `Serial` goes to D6/D7 instead of USB and the serial monitor stays empty. Use `CDCOnBoot=default`, as below.
```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default firmware/respirai
arduino-cli upload  --fqbn esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default -p COM5 firmware/respirai
```

The box is closed, so the B and R buttons can't be reached. The upload works without them; the port was `COM16` on the last upload.

## Test it, step by step

| Step | How | Good when |
|---|---|---|
| Boots | Serial monitor | "respirai-fw 0.5 (no LEDs, gain 1)", then "Advertising as respirAI" |
| Mic (F2) | Before the full firmware: flash `mic_test/` (see above). With the firmware: if it prints "ERROR: I2S microphone did not start", check the wiring | "OK: the microphone answers…", and a tap jumps the level |
| Bluetooth (F4) | **nRF Connect** app on the S25: scan, connect to *respirAI* | serial prints the MTU |
| Streaming (F5) | In nRF Connect, enable notifications on `…0002…`, write `01` to `…0003…` | serial status shows ~200 packets per 2 s |
| Full packets | Serial line "Audio subscribed: MTU …" | **162 bytes** per packet. Smaller still works, but tell the app owner |
| Level | Serial monitor while recording, chest piece on the chest | the status line ends in **0 samples at the limit**. More than a few means the sound is too loud for the gain: it comes out flattened, which sounds harsh and robotic |
| Stability (F6) | Stream 10 minutes from the web app | "lost" stays near 0, no reboot |
| Mic in the app | App → *Settings → Microphone test* → connect | every check green; a tap reaches −20 dBFS or more |
| Real audio | Web app → practice the full flow with the real device | lung sounds visible in the small waveform |

## Things to tune on the real hardware

- **`MIC_GAIN`** in `config.h` is **1.0**: the microphone's own level. At 4.0 a sealed chest piece was far too loud: 7.5 % of a recording sat at the limit and it sounded robotic. Limiting alone does that: broadband sound at half scale, times 4, gives hundreds of jumps from one limit straight to the other, with no wrap-around (`tests/dsp_test.cpp` shows it). Raise the gain only if breathing is tiny in the app **and** the serial status shows 0 samples at the limit. A quiet recording loses nothing: the app's waveform and *Listen* amplify by themselves.
- **Battery level (F8)** needs a 1:2 resistor divider (two equal resistors, e.g. 2 × 100 kΩ) from BAT+ to a free analog pin; set `PIN_BATTERY` to that GPIO. Until then the device reports 255 ("unknown") and the app hides the battery.

Not done yet: the ECG and pulse add-ons (F11, F12, see [`docs/ADDONS.md`](../docs/ADDONS.md)).
