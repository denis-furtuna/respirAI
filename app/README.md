# app/

The app. One web app, used three ways: in Chrome on the phone (demo device: Samsung S25 Ultra) or on a computer, from GitHub Pages (`https://denis-furtuna.github.io/respirAI/`, see [`pages.yml`](../.github/workflows/pages.yml)), and as the Android app built from it ([`phone/`](../phone/README.md)). The AI runs on the phone, so none of them needs a laptop or a server. No build step for the web app itself. Not on iPhone: Safari has no Web Bluetooth.

Wording rule: the UI never says "diagnosis". Use "finding", "screening", "possible abnormal sounds, see a doctor".

## Files

| File | What it does | Tasks |
|---|---|---|
| `index.html`, `style.css` | the page. No CDNs or web fonts, so it works offline on the hotspot | — |
| `img/`, `manifest.webmanifest`, `sw.js` | the logo (made from `docs/brand/`) and icons; the app can be added to the home screen and opens without a connection once loaded | — |
| `device.js` | the device over Web Bluetooth ([contract 1](../docs/ARCHITECTURE.md#1-firmware--app-ble)) | A1, A9 |
| `fake-bluetooth.js` | a fake device behind a fake Web Bluetooth API, so the real Bluetooth code runs without hardware (practice run, `?fakebt`) | — |
| `audio.js` | packets → audio (sequence numbers, gap filling, packet size learned from the first packet), WAV encoding, playback | A2, A6, A11 |
| `tests/` | browser tests and their runner, see *Automated tests* | — |
| `i18n/` | translations: English, Română, Español, Français, Deutsch (see *Languages* below) | — |
| `app.js` | waveform, torso diagram, guided flow, analysis (on the phone, or `/analyze` on an AI server: [contract 2](../docs/ARCHITECTURE.md#2-app--ai-http)), results | A3–A8 |
| `ai/` | **the AI on the phone**: `pipeline.js` is `ai/preprocess.py`, `ai/quality.py` and the window combining of `ai/inference.py` in JavaScript; `worker.js` runs it with the model (ONNX Runtime Web) off the main thread and answers like `POST /analyze`; `local.js` is the app's side | — |
| `model/` | the trained model for `ai/` (see its README); empty until trained: dummy answers, like the server without weights | — |
| `native.js`, `native-bluetooth.js` | only in the Android app: the phone's own Bluetooth (behind the Web Bluetooth calls `device.js` uses), speech, wake lock, share sheet ([`phone/`](../phone/README.md)) | — |
| `privacy.html` | the privacy policy (English, Română), for Google Play | — |

## Languages

The app opens in the phone's language when it has it (else English); the globe button on the first screens and *Settings → Language* change it, and the choice is remembered. Dates, percentages and plurals follow the language (Romanian: „15 secunde”, „20 de secunde”), and the spoken instructions use it too.

All text is in `i18n/<code>.js`, one file per language, loaded only when chosen. `en.js` is the reference: a missing text falls back to English, and the tests check every language has every text with the same `{placeholders}` and all the plural forms it needs. To add a language: copy `en.js`, translate the values, add a line to `LANGUAGES` in `i18n/index.js`. The AI server's own messages are never shown; the app shows its own words, in the user's language.

## How a screening runs

Designed so an elderly person can follow it: one screen at a time, large text and buttons, plain words.

0. **Welcome** (first time only): the language, what the app is and isn't (not a diagnosis), privacy in one line, and what to do in an emergency (112).
1. **Connect:** one button. "Try a practice run" connects to the fake device instead.
2. **Before we start:** three short instructions, a switch to **read the instructions aloud** (spoken only before each recording, never during it, so the stethoscope doesn't pick it up), then *Begin*. The device streams all the time from here, so the app can tell when no sound is arriving.
3. **Each of the 7 places** (front → sides → back): the body drawing and plain words say where. There are 8 s to place the chest piece (or tap *It's in place, start now*), then one practice breath, then 18 s of recording (two whole breaths, so it ends at the bottom of a breath) while a circle paces the breathing: 4 s in, 5 s out. The app sends `0x10 n` when the practice breath starts and the device's lungs light up in the same rhythm and curve ([contract 1, breathing sync](../docs/ARCHITECTURE.md)). The circle is drawn every frame from that curve, never with CSS easing, and only the recording itself is uploaded.
4. Each recording is analysed in the background while the next place is recorded: on the phone, or uploaded as a WAV when an AI server is set. A short *Done* (and a buzz) marks the end of each place.
5. **Results:** one sentence at the top with the date, a coloured body map, and one row per place with its waveform, *Listen* (tap again to stop; one at a time; the waveform shows how far it has played) and *Record again*. Quality below 0.4, a rejected recording, or no sound from the device asks for a re-record. If the analysis failed (on the phone, or the AI server couldn't be reached: timeout, 5xx), the row offers *Try again*, which analyses the same recording again.

**Share with a doctor** sends a short summary and the recordings (WAV) through the phone's share sheet (email, WhatsApp…); on a computer without sharing it opens print / save as PDF. **Earlier checks** on this phone (date and overall answer only, never audio) are listed under the results.

During recording the signal line also warns when the sound is clipping ("Too loud. Hold the chest piece still"). If the Bluetooth connection drops, the app reconnects by itself for about 10 s before asking the user.

The check can be paused and continued without losing anything: *Stop*, the phone's back button, leaving the app, or the device disconnecting all keep the finished places, and *Continue* records only what is left. The page asks before closing if there are results. "Start a new check" needs two separate taps.

**Settings** (the sliders icon, top right; remembered on the phone): **language**, **text size** and **appearance** (automatic / light / dark) for the user; for the team: an AI server's address (empty: the AI runs on the phone; not shown in the Android app), the seconds per place, and **demo mode**. Demo mode answers for the chosen case's example recording instead of the audio: on the phone from `model/demo_clips/` (a fixed example answer until there is a model), or `demo=true` to an AI server.

## Testing without the hardware

Three fakes, from quickest to most realistic:

| Fake | How | What it tests |
|---|---|---|
| Practice run | the *No device? Try a practice run* button | the screens, recording, upload and results, through the real Bluetooth code with a fake device. |
| Fake Web Bluetooth | open the page with **`?fakebt`**, then *Connect the device* | the real Bluetooth code (`BleDevice`): UUIDs, subscribing, commands, packet sizes, disconnects. **`&wav=crackles.wav`** or **`&wav=wheeze.wav`** streams a real lung recording (from [`dev/recordings/`](dev/recordings/CREDITS.md)) instead of generated breathing. Other options: `&mtu=25` (small packets), `&drop=0.02` (lost packets), `&disconnectAfter=30`, `&battery=64`. In the browser console: `fakeBt.disconnect()`. |
| Fake device over real Bluetooth | on a Windows laptop with Bluetooth: `python dev/fake_device.py --file dev/recordings/crackles.wav` (or no `--file` for generated breathing). Install its packages first; the list is at the top of the file. | everything, over the air: the phone's Chrome connects to the laptop as if it were the device. Windows advertises under the computer's name, so pick that name in the device list. The laptop can't connect to itself, so use the phone. |

## Run it

**Nothing to run:** open the GitHub Pages site in Chrome on the phone, or install the Android app ([`phone/README.md`](../phone/README.md)).

**Development, on one computer, one command, plain Python (works where FastAPI is blocked):**
```bash
python app/dev/dev_server.py      # then open http://localhost:8000/?fakebt&wav=crackles.wav
```
It serves the app, which analyses on the phone (here: in the browser). It also answers the AI's API: put its address in Settings → *AI server address* to use that instead. If the AI code (`ai/`) is in the same checkout it runs it (the real model, or the AI's dummy mode); otherwise it gives clearly fake answers ("dev-fake"), so every result says *Clear*. `localhost` counts as secure, so Web Bluetooth works with no extra setup.

**With the real AI server:** `cd ai && uvicorn server:app --host 0.0.0.0 --port 8000`. Once `ai/` and `app/` are in the same checkout it serves the app too.

Either server also answers the API. The app uses it only when its address is in Settings → *AI server address* (for example `http://10.39.40.62:8000` below); empty, the AI runs on the phone.

### On a phone

Two safe ways, both without internet and without putting anything online. Never use a public tunnel (ngrok, Cloudflare and the like): it puts the laptop's server on the internet for anyone with the address.

**A. Your own hotspot (easiest).** Only the phone and the laptop are on the network.
1. Turn on the **phone's hotspot** (with a password) and connect the laptop to it. Not the hackathon or café Wi-Fi: there, everyone on the network could reach the server.
2. On the laptop: `python app/dev/dev_server.py --host 0.0.0.0` (or `uvicorn server:app --host 0.0.0.0 --port 8000` in `ai/`). Find the laptop's address on the hotspot: `ipconfig` → *Wireless LAN adapter Wi-Fi* → *IPv4 Address*, e.g. `10.39.40.62`.
3. On the phone, once: open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, type `http://10.39.40.62:8000` (your address), set it to **Enabled**, tap **Relaunch**. This lets that one address use Bluetooth; nothing else changes. (The practice run works without it.)
4. Open `http://10.39.40.62:8000` on the phone. Check the AI with the settings icon → **Test the AI server**, and press **Connect the device** once, so Chrome asks for the *Nearby devices* permission now and not during the demo.
5. Afterwards, stop the server (Ctrl+C). Without `--host 0.0.0.0` it only listens to the laptop itself.

**B. USB cable (safest: nothing on any network).** The phone reaches the laptop through the cable, and the server never leaves the laptop.
1. On the phone, once: *Settings → About phone → Software information*, tap *Build number* 7 times; then *Settings → Developer options → USB debugging* on.
2. On the laptop: `python app/dev/dev_server.py` (no `--host`: it stays on the laptop). In Chrome open `chrome://inspect/#devices`, connect the phone by USB and accept the prompt on the phone.
3. Click **Port forwarding…**, add port `8000` → `localhost:8000`, tick *Enable port forwarding*, **Done**.
4. On the phone open `http://localhost:8000`. `localhost` counts as secure, so Bluetooth works with no Chrome flag, and the app can be added to the home screen.
5. Afterwards, turn *USB debugging* off again. Windows may need Samsung's USB driver to see the phone (a work laptop may not allow installing it); if the phone never appears in `chrome://inspect`, use A.

Both servers only ever serve files from `app/` (the dev server's file paths are checked, FastAPI does it itself).

## Automated tests

```bash
python app/tests/run.py                               # 120 checks, each suite against a fresh stand-in AI server
python app/tests/run.py --real http://localhost:8000  # a whole check against a running real AI server (15 checks)
```
Plain Python and the installed Chrome (set `CHROME` if it isn't found); nothing to install. The suites in [`tests/`](tests/) drive the real app in headless Chrome, fast-forwarding time, so a 7-place check takes seconds:
`flow` (the whole check, results, Listen, share, restart, back button, settings), `bluetooth` (small packets, lost packets, reconnect, device switched off), `no-audio`, `languages` (every language complete, a check in Romanian, dark mode), `on-phone` (the AI's sound processing behaves as designed; a whole check with no server), `native` (the Android app's Bluetooth under `device.js`, with a stand-in plugin) and `real-server` (contract 2, checked on every answer of a real server, with or without a model).

On GitHub ([`web-app.yml`](../.github/workflows/web-app.yml)) one more suite runs, `ai`: [`make_golden.py`](tests/make_golden.py) runs the Python AI on a set of recordings with a stand-in model, and the JavaScript must give the same numbers at every stage (resampled and filtered audio, spectrograms, quality, model output, the final answer). It needs NumPy, SciPy and ONNX, so it is skipped on a laptop. The Android app is also started in an emulator on every build and checked from inside ([`phone/emulator_check.py`](../phone/emulator_check.py)).
