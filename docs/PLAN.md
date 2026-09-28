# respirAI — Project Plan

**Event:** "Medical Renaissance" hackathon, Timișoara
**Time available:** ~4 weeks to final presentation
**One-line pitch:** A low-cost digital stethoscope that guides the patient through chest positions, listens to lung sounds, and returns an AI-based preliminary respiratory assessment on the phone.

**What the device actually claims — read this before writing any pitch text.**

The question we answer is: *"do these lungs sound normal or abnormal, and should you see a doctor?"* That is honest triage value and it is what the data supports.

What we must **not** claim is flu detection. Influenza is mostly an upper-airway infection, and in an uncomplicated case chest auscultation is usually normal. The "storm" you hear when sick is largely upper-airway secretions and transmitted sounds from the throat and large airways, not lung pathology. Abnormal lung sounds appear when something else is happening — pneumonia, bronchitis, bronchiolitis, an asthma flare. A physician on the jury will know this instantly, so claiming "early flu detection" would lose credibility in one sentence.

The upside: abnormal-sound screening still catches the complications that matter, including the pneumonia that can follow a flu.

---

## 1. What we are building

A two-piece hybrid device:

1. **The puck (left hand)** — the brain. XIAO ESP32-S3, battery, LED matrix breathing guide, and later the extra sensors.
2. **The bell (right hand)** — the chest piece of a cheap mechanical stethoscope, cut off and connected to the puck by its rubber tube. The tube carries **sound**, not wires.

The mic sits inside the puck, sealed onto the end of the tube. This is the easy version and it is what we build first. Moving the mic into the bell is a possible later upgrade (better high frequencies, much harder assembly).

**Demo flow**

1. Phone connects to the device over Bluetooth.
2. Phone shows a torso diagram with a red target dot; the LED matrix shows the breathing rhythm.
3. User places the bell on the marked point and breathes; ~15 s of audio is recorded per point.
4. Repeat for the chest points.
5. Phone uploads the recordings, an "AI processing" animation runs, and the result is shown.

**Scope decision**

| Feature | Status |
|---|---|
| Lung sounds + AI result on phone | **Core — must work on stage** |
| LED breathing guide | **Core — strongly wanted** (visual wow factor) |
| ECG (AD8232) | **Add-on** — a planned extension, built only if the core is finished |
| Pulse / SpO2 (MAX30102) | **Add-on** — lowest priority extension |

The product is a breathing-analysis device. ECG and pulse are **extensions to the same platform**, not missing features — present them that way in the pitch and the repo. "The platform already has the sensor bus, the power and the app pipeline; adding ECG is a module" is a much stronger story than a half-finished feature list.

**Build order rule:** everything is built loose on a breadboard first. The case is designed only after the electronics are proven, measured and frozen.

---

## 2. Hardware inventory

### Already ordered / owned

| Item | Qty | Notes |
|---|---|---|
| XIAO ESP32-S3 (pre-soldered headers) | 1 | SE-102010634 |
| INMP441 I2S mic module | 2 | headers included, loose |
| LiPo 3.7 V 2500 mAh, JST plug | 1 | LP-785060, protection circuit included |
| JST PH 2.0 socket–socket adapter | 1 | VB2P-PH20 |
| JST PH 2.0 cable, open end, 2-pin | 1 | AK-PH20-2P |
| Slide switch ON-ON | 2 | SIS-86434-G |
| Flux gel | 1 | AGT-047 |
| WS2812B 8×8 RGB matrix | 1–2 | 13.31 lei each, bitmi |
| AD8232 ECG kit + spare electrodes | 1 | optional feature |
| MAX30102 pulse/SpO2 | 1 | optional feature |
| Jumper wires, breadboard, multimeter, soldering iron, solder, desoldering wick, heat-shrink, tweezers, electrical tape, USB-C data cable | — | confirmed owned |

### Still to buy

| Item | Where | Price |
|---|---|---|
| Stethoscope (Microlife ST-71) | Dr. Max, reserve + pharmacy pickup | 25.41 lei |
| Neutral-cure silicone sealant | Dedeman / Leroy Merlin / Brico | 15–25 lei |
| Wire cutters ("cleste sfic") | eMAG / bitmi | 15–30 lei |
| Wire stripper ("cleste dezizolat") | eMAG / bitmi | 20–35 lei |
| Calipers (borrow if possible) | — | needed for CAD measurements |

### Services

| Service | Provider | Price |
|---|---|---|
| 3D printing | OLX locals in Timișoara | ~0.50 lei/gram → 25–40 lei per case |
| 3D printing (online quote) | printeaza3d.ro, capib.ro | from 20–30 lei per small part |
| Lung sticker | any copy shop, self-adhesive vinyl | a few lei per A4 |

---

## 3. Wiring reference

All on the XIAO ESP32-S3. Pin budget: **4 of 11 GPIO** for the core + LED build (D6, D8, D9, D10). Add-ons take a further 3–5 — see ADDONS.

| Function | XIAO pin | GPIO | Notes |
|---|---|---|---|
| Mic SCK | D8 | 7 | |
| Mic WS | D9 | 8 | |
| Mic SD | D10 | 9 | |
| Mic VDD | 3V3 | — | **never 5V** |
| Mic GND + L/R | GND | — | L/R tied low = left channel |
| LED matrix data | D6 | 43 | |
| LED matrix power | battery + / GND | — | see power note |
| ECG output (optional) | D0–D3 | 1–4 | must be ADC1; D4/D5 are reserved for I2C |
| MAX30102 SDA/SCL (optional) | D4 / D5 | 5 / 6 | |
| Battery | BAT+ / BAT− pads (back) | — | switch in series on the + wire |

**Power notes**

- The XIAO's 5V pin is **only live when USB is connected**. On battery, the LED matrix must run from the LiPo (3.7–4.2 V) or from a boost converter.
- 64 WS2812B LEDs at full white draw ~3.8 A. **Cap brightness at ~20 %** or the battery protection circuit will cut out.
- If the matrix glitches on 5 V USB power, put a 1N4007 diode in series with its 5 V line to drop it to ~4.3 V and match the 3.3 V data logic.

**Battery connection chain:** battery JST plug → socket-socket adapter → open-end cable → switch on the positive wire → soldered to BAT+ / BAT−.
Check polarity with a multimeter before the first solder; mark the positive wire with tape.

---

## 4. The three contracts

These are fixed on day one so each category can work without waiting for the others. Changing one of these mid-project requires telling everyone.

### 4.1 Firmware ↔ App (BLE)

**Device name (advertised):** `respirAI`

**UUIDs**

| Role | UUID | Properties |
|---|---|---|
| Service | `7b8c9d00-0001-4b5e-8f00-1a2b3c4d5e6f` | — |
| Audio stream | `7b8c9d00-0002-4b5e-8f00-1a2b3c4d5e6f` | Notify |
| Control | `7b8c9d00-0003-4b5e-8f00-1a2b3c4d5e6f` | Write |
| Status | `7b8c9d00-0004-4b5e-8f00-1a2b3c4d5e6f` | Notify |

**Audio format:** PCM, signed 16-bit, little-endian, mono, **8000 Hz**.

**Audio packet:** 162 bytes total.

| Bytes | Content |
|---|---|
| 0–1 | sequence number, uint16 little-endian, wraps at 65535 |
| 2–161 | 80 audio samples (10 ms) |

Rate: 100 packets/s ≈ 16 KB/s. This packet size fits within the BLE limits of both Android and iPhone.
The app uses the sequence number to detect dropped packets and fills gaps with silence.

**Control commands (single byte, or byte + argument)**

| Command | Meaning |
|---|---|
| `0x01` | start audio streaming |
| `0x02` | stop audio streaming |
| `0x10 <n>` | LED: show breathing guide for chest point `n` (0–6) |
| `0x11` | LED: success / point complete animation |
| `0x12` | LED: idle animation |
| `0x20` | send status now |

**Status packet (4 bytes, sent every 2 s and on `0x20`)**

| Byte | Content |
|---|---|
| 0 | battery percent, 0–100 |
| 1 | state: 0 idle, 1 streaming, 2 error |
| 2–3 | packets sent since last status, uint16 LE |

**Chest point numbering** — used by `0x10 <n>` and matching the codes the AI side uses. This is ICBHI's own listing order, so no lookup table is needed anywhere.

| n | Code | Position |
|---|---|---|
| 0 | `Tc` | Trachea |
| 1 | `Al` | Anterior left |
| 2 | `Ar` | Anterior right |
| 3 | `Pl` | Posterior left |
| 4 | `Pr` | Posterior right |
| 5 | `Ll` | Lateral left |
| 6 | `Lr` | Lateral right |

The app may visit the points in any order; only the numbering is fixed.

**MTU — adaptive, not assumed.** BLE defaults to an MTU of 23 bytes, far below the 165 a full packet needs, and the peripheral cannot force a larger one. So the firmware reads the negotiated MTU at subscribe time and sizes the payload from it:

```
samples = min(80, floor((mtu - 5) / 2) rounded down to even)
```

80 samples (10 ms) whenever MTU ≥ 165, fewer if the central negotiates low. The stream degrades instead of breaking. The app handles variable-length packets already, since it reads the sequence number rather than assuming a fixed size.

**Add-on characteristics** — each add-on gets its own characteristic so the audio stream is untouched.

| Role | UUID | Format |
|---|---|---|
| ECG | `7b8c9d00-0005-4b5e-8f00-1a2b3c4d5e6f` | Notify. 250 Hz, int16 samples. Packet: 2-byte sequence + 16 samples = 34 bytes, ~15.6 packets/s. Lead-off flag travels in the status packet. |
| Pulse | `7b8c9d00-0006-4b5e-8f00-1a2b3c4d5e6f` | Notify at 1 Hz, 4 bytes: heart rate uint8 bpm, SpO2 uint8 %, quality uint8 0–100, flags uint8. No waveform is streamed. The MAX30102 itself only outputs raw red/IR samples, so the ESP32 runs the HR/SpO2 algorithm (e.g. Maxim's reference code) and sends the results. |

### 4.2 App ↔ AI

**Endpoint:** `POST /analyze`, `multipart/form-data`

| Field | Type | Notes |
|---|---|---|
| `audio` | file | WAV, 8000 Hz, 16-bit PCM, mono, 10–20 s |
| `point` | string | one of `Tc, Al, Ar, Pl, Pr, Ll, Lr` (ICBHI chest position codes) |
| `session_id` | string | groups the points of one patient session |
| `demo` | bool, optional | if true, the server analyses a dataset clip instead |

**Demo mode.** When `demo=true`, **no `audio` file is sent**. The request instead carries `demo_case`, one of `normal`, `crackles`, `wheezes`, `both`. The server holds one hand-picked ICBHI clip per case per chest point, selected once and committed to the repo under `ai/demo_clips/`, and runs it through the identical preprocessing and model. Deterministic, so it can be rehearsed and behaves identically on stage. The response has the normal shape plus `"demo": true`.

**Response, HTTP 200:**

```json
{
  "point": "Al",
  "finding": "crackles",
  "confidence": 0.81,
  "quality": 0.93,
  "model_version": "resp-cnn-0.3",
  "latency_ms": 420
}
```

- `finding` is one of: `normal`, `crackles`, `wheezes`, `both`, `unusable`
- `quality` (0–1) reflects signal quality; below 0.4 the app should ask the user to re-record
- Errors return HTTP 4xx with `{"error": "human readable message"}`

**Session summary:** `GET /session/{session_id}/summary`

```json
{
  "session_id": "abc123",
  "points_recorded": 6,
  "overall": "crackles",
  "confidence": 0.76,
  "per_point": [{"point": "Al", "finding": "crackles", "confidence": 0.81}],
  "disclaimer": "Screening aid only. Not a diagnosis. Consult a doctor."
}
```

**Wording rule:** the API and the UI never say "diagnosis". Use "finding", "screening", "possible abnormal sounds — see a doctor".

### 4.3 Electronics ↔ CAD

**Single source of truth:** one shared spreadsheet, `components.csv`, one row per part, filled in by Electronics using calipers and read by CAD. CAD never measures from a photo or a datasheet.

| Column | Meaning |
|---|---|
| `part` | component name |
| `w_mm`, `l_mm`, `h_mm` | measured bounding box |
| `hole_pattern` | mounting hole spacing, if any |
| `connector_face` | which face its connector must reach |
| `clearance_mm` | extra space needed for wires |

**Starting values (all to be confirmed with calipers):**

| Part | Nominal size | Connector face |
|---|---|---|
| XIAO ESP32-S3 | 21 × 17.8 × 3.5 mm | USB-C on one short edge |
| INMP441 module | ~15 × 13 mm | tube barb on base |
| WS2812B 8×8 matrix | 64 × 64 mm | top face, under diffuser |
| LiPo 2500 mAh | 60 × 50 × 8 mm | internal |
| Slide switch | 8.6 × 4.3 × 4 mm | side slot |
| AD8232 (optional) | measure | 3.5 mm jack on side |

**Rules**

- Holes for connectors: nominal + 0.4 mm.
- Internal clearance around boards: 1 mm minimum.
- Wall thickness 2 mm; LED diffuser 0.8 mm white PLA.
- The case is expected to need **two print rounds**. Order v1 at least 10 days before the demo.

---

## 5. Category plans

Priorities: **P0** = demo fails without it · **P1** = important · **P2** = nice to have

### 5.1 Firmware (owner: you)

| # | Task | Priority |
|---|---|---|
| F1 | Blink test — confirm board, cable, toolchain | P0 |
| F2 | I2S capture from INMP441 at 16 kHz, print levels over serial | P0 |
| F3 | Low-pass + downsample to 8 kHz, 16-bit | P0 |
| F4 | BLE service per **contract 4.1**, audio notify at 100 packets/s. **Log the negotiated MTU and resulting packet size; verify 10 ms packets on the actual demo phone.** | P0 |
| F5 | Control commands: start/stop streaming | P0 |
| F6 | Stability test: 10 min continuous streaming, no drops, no reboot | P0 |
| F7 | Battery operation: run from LiPo, confirm charging over USB-C | P1 |
| F8 | Status characteristic: battery %, state | P1 |
| F9 | LED matrix driver, breathing animation (inhale/exhale ramp), brightness capped | P1 |
| F10 | LED animations for point complete / idle | P2 |
| F11 | ECG channel added to the stream | P2 |
| F12 | MAX30102 reading | P2 |

### 5.2 App (owner: **unassigned — highest risk, fill this slot first**)

Web page in Chrome, using Web Bluetooth. Works on desktop Chrome and Android Chrome. **Not on iPhone** — Safari does not support Web Bluetooth.

**Demo device: Samsung S25 Ultra (Android).** Confirmed, so the web route is settled. No app store, no native toolchain.

**Hosting — the mixed-content trap.** Web Bluetooth normally requires an HTTPS page, but an HTTPS page may not call a plain `http://192.168.x.x` server. "GitHub Pages + FastAPI on the laptop" therefore does **not** work as-is. Two options:

- **Demo setup (use this on stage):** serve the page from the laptop over plain HTTP and enable `chrome://flags/#unsafely-treat-insecure-origin-as-secure` on the phone, adding the laptop's address. Web Bluetooth then works on an HTTP page and everything runs on our own hotspot with no internet at all. Configure once, rehearse with it.
- **Development setup:** GitHub Pages for the page + a free Cloudflare tunnel giving FastAPI an HTTPS address. Convenient, but depends on venue internet — never rely on it on stage.

Grant Chrome the "Nearby devices" permission during setup, not during the demo.

| # | Task | Priority |
|---|---|---|
| A1 | Connect to `respirAI` over Web Bluetooth, subscribe to the audio characteristic | P0 |
| A2 | Reassemble packets by sequence number into a PCM buffer | P0 |
| A3 | Live waveform display | P0 |
| A4 | Torso diagram with the red target dot per chest point | P0 |
| A5 | Guided recording flow: countdown → "breathe deeply" → 15 s per point → next | P0 |
| A6 | Build WAV and POST to the AI endpoint per **contract 4.2** | P0 |
| A7 | Results screen with per-point findings + disclaimer wording | P0 |
| A8 | "AI processing" animation during the request | P1 |
| A9 | Battery indicator from the status characteristic | P2 |
| A10 | Automatic breath detection (replaces the fixed 15 s timer) | P2 |
| A11 | Audio playback of a recorded point | P2 |

**Explicit decision:** v1 uses a **fixed timer**, not automatic breath detection. Breath detection is a signal-processing project of its own and is not required for the demo.

### 5.3 AI and data (can start today, needs no hardware)

| # | Task | Priority |
|---|---|---|
| D1 | Download ICBHI 2017 on Kaggle, explore labels and chest positions | P0 |
| D2 | Preprocessing module: resample to 4 kHz, band-pass 100–1800 Hz, log-mel — **one file shared by training and serving** | P0 |
| D3 | Patient-wise train/test split (never random — random splits give fake accuracy) | P0 |
| D4 | Train a CNN (ResNet18 on mel spectrograms), 4 classes: normal / crackles / wheezes / both | P0 |
| D5 | FastAPI server implementing **contract 4.2**, loading the trained model | P0 |
| D6 | Demo mode: real dataset clips pushed through the identical pipeline | P0 |
| D7 | Quality metric (`quality` field) — detect silence, clipping, handling noise | P1 |
| D8 | Session summary endpoint | P1 |
| D9 | Test on our own recordings, measure the domain gap vs dataset audio | P1 |
| D10 | **Phase 2:** add HF_Lung_V1 for volume and breath-phase labels | P2 |
| D11 | **Phase 2:** breath-phase detector (inhale/exhale) trained on HF_Lung_V1 labels → feeds app task A10 and the LED guide | P2 |
| D12 | ECG model (AFib detection, PhysioNet/CinC 2017) | P2 |
| D13 | **Phase 2:** export the model to ONNX (`torch.onnx.export`) and run it in the browser with ONNX Runtime Web | P2 |

**Dataset strategy — decided:**

**Use the sound labels, not the disease labels.** ICBHI's disease labels are badly imbalanced (~86 % COPD), so a model trained on them scores high by always guessing one class. The **cycle-level sound labels** — 6,898 respiratory cycles tagged normal / crackle / wheeze / both — are spread across all patients and are what we actually train on. ICBHI also uses the same seven chest position codes as our app, which no other dataset provides.

**Primary dataset — ICBHI 2017** (Kaggle, free GPU, 920 recordings, 126 participants). Weeks 1–2.

**Secondary dataset — HF_Lung_V1** (free on GitLab). 9,765 recordings of 15 s each from 279 adults, recorded with a Littmann 3200 electronic stethoscope. Event-level labels: 15,606 crackle, 8,457 wheeze, 4,740 rhonchi, 686 stridor. It is the largest open-access lung sound database.

Its decisive extra feature: **34,095 inhalation and 18,349 exhalation labels**. That is a ready-made training set for breath-phase detection — exactly what task A10 needs to replace the fixed timer, and what could drive the LED guide from the patient's real breathing instead of a fixed rhythm.

**Optional — SPRSound** (2,683 recordings, 292 children, event- and record-level labels) if paediatric coverage is ever needed. Out of scope for four weeks.

**Inference plan — two phases, decided:**

1. **Phase 1 (build this):** laptop runs FastAPI, phone uploads the WAV over the local hotspot. Simple, debuggable, and the pipeline is identical to training.
2. **Phase 2 (attempt only if week 2 finishes on time):** model exported to ONNX and run directly in Chrome on the phone with ONNX Runtime Web. Both are free and open source (ONNX is Linux Foundation, ONNX Runtime Web is MIT). Then the phone does everything — Bluetooth, recording, inference — with no laptop and no network to fail, and "the AI runs on the phone itself" is a much stronger pitch line.

If we attempt phase 2, train a **small** CNN rather than ResNet18 — the model has to download into the browser, so size matters. Keep the FastAPI path working as the fallback either way.

**Reality note:** ~86 % of ICBHI recordings come from COPD patients — which is exactly why we train on sound labels, not disease labels. Report per-class scores, and never claim clinical accuracy on stage.

### 5.4 Electronics and assembly

| # | Task | Priority |
|---|---|---|
| E1 | Solder headers onto both INMP441 modules | P0 |
| E2 | Breadboard the mic to the XIAO, verify audio | P0 |
| E3 | Seal the tube to the mic with hot glue; test that room noise drops when sealed | P0 |
| E4 | Multimeter polarity check on the JST cable; mark the positive wire | P0 |
| E5 | Solder battery cable + switch to BAT+ / BAT−; insulate with heat-shrink | P0 |
| E6 | Battery runtime test: how many hours of continuous streaming | P1 |
| E7 | Wire the LED matrix, verify current draw at the chosen brightness | P1 |
| E8 | Measure every component with calipers → fill `components.csv` | P1 |
| E9 | Final wiring harness cut to length for the case | P1 |
| E10 | Keep the breadboard version assembled as the backup demo | P1 |
| E11 | Wire AD8232 / MAX30102 | P2 |

### 5.5 CAD and enclosure

| # | Task | Priority |
|---|---|---|
| C1 | Print the **tube adapter alone** first (a few grams, a few lei) and test the acoustic seal | P0 |
| C2 | Wait for `components.csv` — do not model before measurements exist | P0 |
| C3 | Case v1: XIAO + battery + mic + tube barb + USB-C cutout + switch slot | P1 |
| C4 | LED window + 0.8 mm white PLA diffuser + recessed "respirAI" text | P1 |
| C5 | Order v1 print (OLX local, ~30 lei) — **at least 10 days before the demo** | P1 |
| C6 | Fit test, fix, order v2 | P1 |
| C7 | Lung sticker artwork → copy shop, self-adhesive vinyl | P2 |
| C8 | Cutouts for ECG jack / MAX30102 finger recess — **only if those features work before the case is frozen** | P2 |

**Freeze rule:** if a feature is not working by the day the case is designed, it does not get a hole and it does not go in the device.

### 5.6 Pitch and demo

| # | Task | Priority |
|---|---|---|
| P1 | Demo script: who speaks, who holds the device, exact sequence | P0 |
| P2 | Offline fallback: laptop hotspot, no dependency on venue Wi-Fi | P0 |
| P3 | Demo mode rehearsal — judges are healthy, so live results will say "normal" | P0 |
| P4 | Slides: problem, 1816 stethoscope → digital, architecture, results, cost | P1 |
| P5 | Rehearse end to end ≥ 5 times | P1 |
| P6 | Cost breakdown slide (the whole device is ~200 lei — a strong argument) | P1 |
| P7 | Answer prep: "is this a medical device?", "how accurate?", "what's next?" | P1 |
| P8 | **Wording check:** no flu-detection claims anywhere in slides or UI. The claim is abnormal-sound screening and "see a doctor". | P0 |

---

## 6. Timeline

| Week | Goal |
|---|---|
| **1** | Mic works, audio streams over BLE, live waveform on screen. Tube adapter printed and sealed. ICBHI training started on Kaggle. |
| **2** | Full loop: record → upload → AI result → shown on screen. Chest map in the app. Battery soldered and tested. |
| **3** | LED breathing guide. Then **measure, freeze, design the case, order print v1**. |
| **4** | Assembly, reprint if needed, five rehearsals. Optional features only if everything above is done. |

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **No app owner yet** | Fill this slot this week. The app *is* the demo. |
| Live demo shows "normal" for healthy judges | Demo mode with real dataset recordings, plus live features (waveform, breathing guide) that work on anyone |
| Venue Wi-Fi / Bluetooth interference | Laptop hotspot, everything local, rehearse in airplane-mode conditions |
| Case doesn't fit | Two print rounds budgeted; breadboard version kept as backup |
| Audio picks up room noise | Airtight seal, band-pass filter, quality metric that rejects bad recordings |
| Model accuracy looks bad | Report honestly, emphasise the device and pipeline, not the accuracy number |
| ~~iPhone can't run the web app~~ | **Resolved:** demo runs on a Samsung S25 Ultra (Android + Chrome) |
| HTTPS page can't reach the HTTP laptop server | Serve the page over HTTP from the laptop + Chrome insecure-origin flag on the phone; configured and rehearsed in advance |

---

## 8. Reference links

- Stethoscope: <https://www.drmax.ro/stetoscop-st-71-1-bucata-microlife>
- LED matrix: <https://www.bitmi.ro/electronica/matrice-led-5050-rgb-8x8-ws2812b-compatibila-arduino-12162.html>
- ECG kit: <https://www.bitmi.ro/module-electronice/kit-monitorizare-ekg-cu-electrozi-cablu-si-senzor-ad8232-11006.html>
- MAX30102: <https://www.bitmi.ro/senzori-electronici/senzor-ritm-cardiac-si-spo2-max30102-12117.html>
- 3D printing, instant quote: <https://printeaza3d.ro/>
- 3D printing, Timișoara 24 h: <https://capib.ro/3dprint/en/3d-printing-timisoara/>
- Local printing, ~0.50 lei/gram: OLX Timișoara, search "printare 3D"

**Datasets**

- ICBHI 2017 Respiratory Sound Database — on Kaggle (free GPU, dataset already hosted there)
- HF_Lung_V1 — <https://gitlab.com/techsupportHF/HF_Lung_V1>
- SPRSound (paediatric, optional) — SJTU open-source database

---

## 9. Open decisions

- [ ] Who owns the app?
- [x] ~~Which phone is used for the demo?~~ **Samsung S25 Ultra (Android + Chrome)**
- [x] ~~Where does inference run?~~ **Phase 1 laptop (FastAPI), phase 2 on-phone (ONNX) if time allows**
- [ ] One LED matrix (8×8) or two chained (16×8)?
- [ ] LED matrix powered from the LiPo directly, or via a boost converter?
- [ ] Do ECG and SpO2 make the cut, decided by end of week 3?