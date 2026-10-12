# app/

The **web app** that runs in Chrome on the phone (demo device: Samsung S25 Ultra) and on desktop Chrome. No native app, no app store, no build step. Not supported on iPhone: Safari has no Web Bluetooth.

Wording rule: the UI never says "diagnosis". Use "finding", "screening", "possible abnormal sounds, see a doctor".

## Files

| File | What it does | Tasks |
|---|---|---|
| `index.html`, `style.css` | the page. No CDNs or web fonts, so it works offline on the hotspot | — |
| `device.js` | the device over Web Bluetooth ([contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble)), plus a **mock device** with the same interface | A1, A9 |
| `audio.js` | packets → audio (sequence numbers, gap filling, packet size learned from the first packet), WAV encoding, playback | A2, A6, A11 |
| `app.js` | waveform, torso diagram, guided flow, upload to `/analyze` ([contract 2](../docs/ARCHITECTURE.md#2-app--ai-http)), results | A3–A8 |

## How a screening runs

Designed so an elderly person can follow it: one screen at a time, large text and buttons, plain words.

1. **Connect:** one button. "Try a practice run" uses the mock device instead.
2. **Before we start:** three short instructions, then *Begin*. The device streams all the time from here, so the app can tell when no sound is arriving.
3. **Each of the 7 places** (front → sides → back): the body drawing and plain words say where. There are 8 s to place the chest piece (or tap *It's in place, start now*), then 15 s of recording while a circle paces the breathing (4 s in, 5 s out, like the LED guide). The LED guide starts with `0x10 n`.
4. Each recording is uploaded as a WAV in the background while the next place is recorded.
5. **Results:** one sentence at the top, a coloured body map, and one row per place with *Listen* and *Record again*. Quality below 0.4, an error, or no sound from the device asks for a re-record.

**Settings** (the sliders icon, top right; for the team, remembered on the phone): the AI server's address, the seconds per place, and **demo mode**. Demo mode sends `demo=true` with the chosen case instead of the audio.

## Run it

**Development, on one computer:**
```bash
cd app && python -m http.server 8080          # the page:  http://localhost:8080
cd ai  && uvicorn server:app --host 0.0.0.0 --port 8000   # the AI server (dummy mode is fine)
```
`localhost` counts as secure, so Web Bluetooth works with no extra setup. Use **No device? Try a practice run** if there is no hardware.

**Demo setup, phone + laptop, no internet (task H):**
1. Phone on the laptop's hotspot. Find the laptop's address on the hotspot (e.g. `192.168.137.1`).
2. On the laptop, start both commands above.
3. On the phone, open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add `http://192.168.137.1:8080`, set it to **Enabled**, and relaunch Chrome. Without this, Chrome refuses Web Bluetooth on a plain `http://` page.
4. Open `http://192.168.137.1:8080`. The AI server address defaults to the same host on port 8000. Check it with **Settings → Test the AI server**.
5. Press **Connect device** once now, so Chrome asks for the *Nearby devices* permission during setup and not during the demo.

Don't host the page on GitHub Pages for the demo. An `https://` page can't call the laptop's `http://` server.
