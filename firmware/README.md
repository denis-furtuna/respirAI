# firmware/

Code that runs on the **Seeed XIAO ESP32-S3** inside the puck.

What belongs here:

- I²S capture from the INMP441 at 16 kHz
- low-pass filter + downsampling to 8 kHz, 16-bit
- the BLE service — audio notify, control, status — exactly as defined in [contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble)
- the WS2812B LED matrix driver and breathing-guide animations (brightness capped at ~20 %)
- battery level reporting
- later: the ECG and pulse add-ons (see [`docs/ADDONS.md`](../docs/ADDONS.md))

Pin assignments are in [`docs/PLAN.md` §3](../docs/PLAN.md#3-wiring-reference). Task list: F1–F12 in [`docs/PLAN.md` §5.1](../docs/PLAN.md#51-firmware-owner-you).

Changing anything in the BLE contract means telling the app owner first.
