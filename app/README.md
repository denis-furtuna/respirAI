# app/

The **web app** that runs in Chrome on the phone (demo device: Samsung S25 Ultra) and on desktop Chrome. No native app, no app store, no build step. Not supported on iPhone: Safari has no Web Bluetooth.

Wording rule: the UI never says "diagnosis". Use "finding", "screening", "possible abnormal sounds, see a doctor".

## Files

| File | What it does | Tasks |
|---|---|---|
| `index.html`, `style.css` | the page. No CDNs or web fonts, so it works offline on the hotspot | — |
| `img/`, `manifest.webmanifest`, `sw.js` | the logo (made from `docs/brand/`) and icons; the app can be added to the home screen and opens without a connection once loaded | — |
| `device.js` | the device over Web Bluetooth ([contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble)) | A1, A9 |
| `fake-bluetooth.js` | a fake device behind a fake Web Bluetooth API, so the real Bluetooth code runs without hardware (practice run, `?fakebt`) | — |
| `audio.js` | packets → audio (sequence numbers, gap filling, packet size learned from the first packet), WAV encoding, playback | A2, A6, A11 |
| `app.js` | waveform, torso diagram, guided flow, upload to `/analyze` ([contract 2](../docs/ARCHITECTURE.md#2-app--ai-http)), results | A3–A8 |

## How a screening runs

Designed so an elderly person can follow it: one screen at a time, large text and buttons, plain words.

1. **Connect:** one button. "Try a practice run" connects to the fake device instead.
2. **Before we start:** three short instructions, a switch to **read the instructions aloud** (spoken only before each recording, never during it, so the stethoscope doesn't pick it up), then *Begin*. The device streams all the time from here, so the app can tell when no sound is arriving.
3. **Each of the 7 places** (front → sides → back): the body drawing and plain words say where. There are 8 s to place the chest piece (or tap *It's in place, start now*), then 15 s of recording while a circle paces the breathing (4 s in, 5 s out, like the LED guide). The LED guide starts with `0x10 n`.
4. Each recording is uploaded as a WAV in the background while the next place is recorded. A short *Done* (and a buzz) marks the end of each place.
5. **Results:** one sentence at the top with the date, a coloured body map, and one row per place with its waveform, *Listen* (tap again to stop; one at a time; the waveform shows how far it has played) and *Record again*. Quality below 0.4, a rejected recording, or no sound from the device asks for a re-record. If the AI server couldn't be reached or failed (timeout, 5xx), the row offers *Try again*, which sends the same recording again.

**Share with a doctor** sends a short summary and the recordings (WAV) through the phone's share sheet (email, WhatsApp…); on a computer without sharing it opens print / save as PDF. **Earlier checks** on this phone (date and overall answer only, never audio) are listed under the results.

During recording the signal line also warns when the sound is clipping ("Too loud. Hold the chest piece still"). If the Bluetooth connection drops, the app reconnects by itself for about 10 s before asking the user.

The check can be paused and continued without losing anything: *Stop*, the phone's back button, leaving the app, or the device disconnecting all keep the finished places, and *Continue* records only what is left. The page asks before closing if there are results. "Start a new check" needs two separate taps.

**Settings** (the sliders icon, top right; remembered on the phone): **text size** for the user; for the team: the AI server's address, the seconds per place, and **demo mode**. Demo mode sends `demo=true` with the chosen case instead of the audio.

## Testing without the hardware

Three fakes, from quickest to most realistic:

| Fake | How | What it tests |
|---|---|---|
| Practice run | the *No device? Try a practice run* button | the screens, recording, upload and results, through the real Bluetooth code with a fake device. |
| Fake Web Bluetooth | open the page with **`?fakebt`**, then *Connect the device* | the real Bluetooth code (`BleDevice`): UUIDs, subscribing, commands, packet sizes, disconnects. **`&wav=crackles.wav`** or **`&wav=wheeze.wav`** streams a real lung recording (from [`dev/recordings/`](dev/recordings/CREDITS.md)) instead of generated breathing. Other options: `&mtu=25` (small packets), `&drop=0.02` (lost packets), `&disconnectAfter=30`, `&battery=64`. In the browser console: `fakeBt.disconnect()`. |
| Fake device over real Bluetooth | on a Windows laptop with Bluetooth: `python dev/fake_device.py --file dev/recordings/crackles.wav` (or no `--file` for generated breathing). Install its packages first; the list is at the top of the file. | everything, over the air: the phone's Chrome connects to the laptop as if it were the device. Windows advertises under the computer's name, so pick that name in the device list. The laptop can't connect to itself, so use the phone. |

## Run it

**Development, on one computer, one command, plain Python (works where FastAPI is blocked):**
```bash
python app/dev/dev_server.py      # then open http://localhost:8000/?fakebt&wav=crackles.wav
```
It serves the app and answers the AI's API. If the AI code (`ai/`) is in the same checkout it runs it (the real model, or the AI's dummy mode); otherwise it gives clearly fake answers ("dev-fake"), so every result says *Clear*. `localhost` counts as secure, so Web Bluetooth works with no extra setup.

**With the real AI server:** `cd ai && uvicorn server:app --host 0.0.0.0 --port 8000`. Once `ai/` and `app/` are in the same checkout it serves the app too.

**Demo setup, phone + laptop, no internet (task H):**
1. Phone on the laptop's hotspot. Find the laptop's address on the hotspot (e.g. `192.168.137.1`).
2. On the laptop, start both commands above.
3. On the phone, open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add `http://192.168.137.1:8080`, set it to **Enabled**, and relaunch Chrome. Without this, Chrome refuses Web Bluetooth on a plain `http://` page.
4. Open `http://192.168.137.1:8080`. The AI server address defaults to the same host on port 8000. Check it with the settings icon → **Test the AI server**.
5. Press **Connect the device** once now, so Chrome asks for the *Nearby devices* permission during setup and not during the demo.

Don't host the page on GitHub Pages for the demo. An `https://` page can't call the laptop's `http://` server.
