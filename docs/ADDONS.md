# respirAI — Add-ons

respirAI is a **breathing-analysis device**. ECG and pulse oximetry are **extensions to the same platform**, not missing features. The platform already has the sensor bus, the power and the app pipeline; each add-on is a module on top.

Present them that way in the pitch and in this repo.

| Add-on | Sensor | Priority | Status |
|---|---|---|---|
| ECG | AD8232 single-lead ECG kit | P2 — built only if the core is finished | owned, not started |
| Pulse / SpO2 | MAX30102 | P2 — lowest priority | owned, not started |

**Go / no-go:** decided by the **end of week 3** ([`PLAN.md` §9](PLAN.md#9-open-decisions)).

**Freeze rule:** if an add-on isn't working on the day the case is designed, it gets no hole and doesn't go in the device. An empty rectangular hole looks unfinished; a blank finger recess looks intentional.

---

## ECG add-on — AD8232

### Wiring

| Signal | XIAO pin | GPIO | Notes |
|---|---|---|---|
| ECG output | one of D0–D3 | 1–4 | must be an **ADC1** pin; D4/D5 are reserved for I²C |
| LO+ / LO− (lead-off) | two free digital pins | — | needed for the lead-off flag; not yet in the PLAN §3 wiring table |

### Work involved

| Area | Task | Plan ref |
|---|---|---|
| Electronics | Wire the AD8232 | E11 |
| Firmware | Add the ECG channel to the stream | F11 |
| AI | ECG model — AFib detection, trained on PhysioNet/CinC 2017 | D12 |
| CAD | Jack cutout + board mounting, only if working before the freeze | C8 |

### Enclosure changes

From [`ENCLOSURE.md` §8](ENCLOSURE.md#8-add-ons-future-extensions):

- a **Ø6.5 mm hole in the right wall** for the 3.5 mm electrode jack
- **two M3 standoffs** for the board — the jack needs mechanical support, or plug force will rip it off

---

## Pulse / SpO2 add-on — MAX30102

### Wiring

| Signal | XIAO pin | GPIO |
|---|---|---|
| SDA | D4 | 5 |
| SCL | D5 | 6 |

### Work involved

| Area | Task | Plan ref |
|---|---|---|
| Electronics | Wire the MAX30102 | E11 |
| Firmware | Read the MAX30102's raw red/IR samples and run the HR/SpO2 algorithm on the ESP32 — the sensor doesn't compute them itself | F12 |
| CAD | Finger-recess window, only if working before the freeze | C8 |

### Enclosure changes

From [`ENCLOSURE.md` §8](ENCLOSURE.md#8-add-ons-future-extensions):

- a **12 × 8 mm window in the centre of the finger recess** on the right wall
- the sensor face must sit **flush** with the surface — a recessed sensor reads badly

---

## Pin budget

The core build uses 4 GPIO: D8, D9, D10 (mic) and D6 (LED matrix). The add-ons take a further 3–5 from what's left:

- ECG: one ADC1 pin from D0–D3 for the signal, plus two pins for LO+ / LO− if the lead-off flag is used
- MAX30102: the I²C pair D4/D5

With everything fitted, 2 of the 11 GPIO remain free.

## CAD

Keep each add-on as a **separate lid/base variant** in `cad/`, so the breath-only version stays clean.

## Data over BLE

Each add-on has its own characteristic, so the audio stream is untouched. Full formats in [`ARCHITECTURE.md` → Add-on characteristics](ARCHITECTURE.md#add-on-characteristics).

| Add-on | UUID suffix | Summary |
|---|---|---|
| ECG | `…0005…` | 250 Hz int16, 34-byte packets (sequence + 16 samples), ~15.6 packets/s |
| Pulse | `…0006…` | 4 bytes at 1 Hz: HR, SpO2, quality, flags |

Still open:

- where the ECG lead-off flag sits in the status packet (see [`ARCHITECTURE.md` → Open questions](ARCHITECTURE.md#open-questions--not-yet-part-of-any-contract))
- control commands to start/stop the add-on streams, if they shouldn't just run whenever the phone subscribes
- for the ECG model: whether it's a new endpoint alongside `POST /analyze`. Its training set (PhysioNet/CinC 2017) is 300 Hz, so our 250 Hz stream gets resampled.
