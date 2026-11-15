# respirAI — Enclosure Blueprint (v3, breath-only, lung panel)

**Purpose:** mechanical design manual for the 3D-printed housing.
**Scope:** breathing analysis only. No ECG, no pulse oximeter. See §8 for what changes if they come back.

> The layout drawing below still shows the v2 LED matrix; it gets redrawn with the re-layout.
>
> All dimensions below are **design intent**. Nothing gets modelled until every component has been measured with calipers and written into `cad/components.csv`.

---

## 1. Form and ergonomics

A rounded "puck" held in the left hand. The base rests in the palm, the index finger settles into a concave recess on the right side, and the luminous top face points at the patient's eyes. The right hand holds the stethoscope bell, which connects to the base by the rubber tube.

**Target outer size: ~95 × 70 × 22–24 mm**, corner radius 8 mm (was 100 × 85 × 24 with the LED matrix).

The 64 × 64 mm LED matrix is gone (four small LEDs behind a printed panel replace it), so the battery (60 × 50 × 8 mm) is now the only part that sets the size. Reaching ~95 × 70 means moving the parts in the §2 table about 10 mm toward the front (the battery and the screw bosses now reach Y 72–77), so it is a small CAD re-layout, not just a smaller box. A full rethink could reach ~80 × 65 mm (open decision in PLAN §9).

**The height does not shrink.** Even light through the panel needs 8–12 mm of air between the LEDs and the panel, more than the matrix's 3 mm. Don't add height for it: put the LEDs on standoffs above the battery, pointing up, and use the case's existing interior as the light chamber.

---

## 2. Internal layout

![Enclosure layout](enclosure-layout.svg)

Positions in mm, measured from the bottom-left corner of the base as seen from above:

| Component | X | Y | Notes |
|---|---|---|---|
| Acoustic chamber + mic pocket | 6 – 32 | 14 – 40 | barb exits the base directly beneath |
| XIAO ESP32-S3 | 4 – 25 | 46 – 64 | USB-C faces the left wall |
| LiPo 2500 mAh | 30 – 90 | 22 – 72 | walled compartment, no boards beneath |
| Screw bosses (4×) | 8 / 92 | 8 / 77 | Ø6 mm outer, M3 |
| Switch slot | 40 – 49 | front wall | actuator opening 6 × 3 mm |
| LEDs (4×) on standoffs | above the battery | under their zones | trachea, left lobe, right lobe, "AI"; pointing up |
| Light chambers (in lid) | under the panel | — | white walls around each of the four zones |

**Vertical stack:** base 2 mm → acoustic chamber 12 mm (its own column) → battery 8 mm → LEDs on standoffs → 8–12 mm air gap (the light chamber) → top panel 1.2–1.5 mm. Total ~22–24 mm. The chamber sits beside the battery, not under it, so it does not add to the total height.

---

## 3. External features

### 3.1 Top face
- **One printed panel** carries the lung artwork and the wordmark, and replaces both the old diffuser and the branding recess. White or natural PLA, one material, no filament swap.
- **Variable thickness is the whole trick:** thin PLA lets light through, thick PLA doesn't. Lungs and wordmark letters 0.4 mm; everything around them 1.2–1.5 mm.
- **Wordmark strip ~50 × 12 mm** (was 40 × 8: 8 mm is too small for letters lit from behind). Print the whole "respirAI" thin, then paint over "respir" from the outside with opaque paint, so light escapes only through "AI".

### 3.2 Base
- **Acoustic connection:** the barb for the stethoscope tube, centred under the acoustic chamber. See §4.1 — this part needs special attention.
- **Sticker recess:** 0.2 mm deep, 40 × 40 mm, for the printed lung decal. The recess protects it from rubbing against surfaces.
- **Four rubber feet pads** (optional): 1 mm recesses at the corners, so the device doesn't slide on a table.

### 3.3 Sides
- **Left wall:** USB-C cutout aligned with the XIAO. Nominal opening **9 × 3.5 mm**, plus 0.4 mm tolerance all round. Add a 1 mm chamfer so a chunky cable housing still seats.
- **Front wall:** slide-switch slot. The switch body is 8.6 × 4.3 × 4 mm; the visible slot is 6 × 3 mm with the body held internally.
- **Right wall:** concave finger recess, depth 4 mm, radius ~40 mm. **No hole** — it's purely ergonomic in this version.
- **Rear wall:** blank. Keep it clean.

---

## 4. Internal structures

### 4.1 Acoustic chamber (the critical part)

A funnel from the barb narrowing to the microphone port. Two rules:

1. **Keep the air volume small.** A short, narrow path preserves the high frequencies where crackles and wheezes live. Target an internal path of 15 mm or less from base to mic face.
2. **The mic gets a sealed pocket, not just a gasket.** A flat bed sized to the INMP441 board, with walls on all four sides and a closed back. If the mic's rear is open to the case interior, it will pick up wire rattle and every finger tap on the housing. Seal the front with a silicone O-ring or a hot-glue bead; pack the back with foam.

**The barb will break if printed naively.** A barb printed standing up on the base has layer lines running perpendicular to the direction the tube gets pulled, which is the weakest possible orientation. Choose one:

- **Preferred:** model a plain Ø8 mm hole and glue in a real pneumatic push-in fitting (a few lei at any hardware shop). Strongest, most airtight, looks professional.
- **Alternative:** print the barb as a separate part lying on its side, with a 3 mm fillet at the flange, and screw or glue it to the base.
- **Avoid:** printing it integral and vertical.

Add a **strain-relief clamp** just inside the base — a small bridge the tube passes under — so the pull goes into the housing, never into the barb or the mic seal.

### 4.2 Mounting

| Item | Method |
|---|---|
| XIAO | Two guide rails plus a retaining clip, so USB-C insertion force goes into the housing. Do not rely on the case lid pressing it down. |
| Battery | Walled compartment, 1.5 mm walls, 0.5 mm clearance on each side, with a foam pad underneath. Keeps it away from sharp header pins. |
| LEDs | Short standoffs (or a small perfboard) above the battery, LEDs pointing up into their chambers. Never glue anything to the battery. |
| Light chambers | White walls from the panel down to just above the LEDs, one per zone: trachea, left lobe, right lobe, and a separate walled chamber for the wordmark strip, so each zone lights on its own instead of bleeding into one blob. |
| Lid | **Four M3 screws** into the base bosses. Use M3 heat-set brass inserts if you have a soldering iron with a spare tip; otherwise self-tapping into a Ø2.5 mm pilot hole. |

**Why screws, not snap-fits:** snap-fits need two or three test prints to tune the interference, and you have neither the time nor the print budget for that. Screws work on the first print.

### 4.3 Cable management
- A routing channel along the rear wall for the mic's five wires, keeping them clear of the battery.
- Two small cable posts to loop the battery leads around, so a tug never reaches the solder joints on the XIAO's BAT pads.
- The LED wires carry a few mA each; run them along the walls, clear of the battery.

---

## 5. Print settings

| Setting | Value |
|---|---|
| Material | **PLA** |
| Layer height | 0.2 mm |
| Perimeters | 3 (≈1.2 mm) |
| Infill | 20 % |
| Supports | Only under the USB-C and switch openings |
| Orientation | Base printed open-side up; lid printed outer-face down on a smooth sheet |

**PLA, not PETG.** PETG is the right pick when you need flexible snap-fits. With screws you don't, and PLA holds finer detail and is more forgiving for a print service to get right first time.

**Top panel:** white or natural PLA, 1.2–1.5 mm with 0.4 mm thin regions for the lungs and the wordmark (thickness chosen from the week-1 test tile), 100 % infill, no supports, outer face down on a smooth build sheet. Then paint over "respir". Print three — they're a few grams each, and you will want to compare.

---

## 6. Print plan and budget

At roughly 0.50 lei/gram locally, the whole case is 30–40 lei per round.

1. **Week 1 — test print:** the acoustic chamber section alone, a few grams. Tests the seal and the tube fit before anything else is committed. **Beside it, a test tile:** the wordmark strip and one lung lobe at 0.3, 0.4 and 0.6 mm thin-region thickness, with one LED behind each. Backlit letters are the fussiest part of this case: find out in week 1, not week 3.
2. **Week 3 — v1:** full base + lid + three panels.
3. **Week 4 — v2:** fixes only. Budget for this; every first enclosure has something wrong.

Order v1 **at least 10 days before the demo.**

---

## 7. Pre-print checklist

- [ ] Every component measured with calipers, written into `cad/components.csv`
- [ ] XIAO's USB-C position measured **as mounted**, not from the datasheet
- [ ] Battery measured including its wires and heat-shrink, not just the cell
- [ ] Acoustic seal tested on the week-1 test print
- [ ] Panel thin-region thickness and LED shade (blue or teal) chosen from the week-1 test tile
- [ ] Tube outer diameter measured — the bore of a cheap stethoscope tube varies
- [ ] Screw bosses checked against the actual M3 screws you own
- [ ] The breadboard version still works and stays assembled as backup

---

## 8. Add-ons (future extensions)

ECG and pulse oximetry are **extensions**, not part of this version. The core product is breathing analysis; these are modules that plug into the same platform later.

Do **not** cut holes for an add-on that isn't built yet — an empty rectangular hole looks unfinished, while a blank finger recess looks intentional.

If an extension is working before the case is frozen:

- **ECG add-on (AD8232):** a Ø6.5 mm hole in the right wall for the 3.5 mm jack, plus two M3 standoffs for the board. The jack needs mechanical support; plug force will otherwise rip it off.
- **Pulse add-on (MAX30102):** a 12 × 8 mm window in the centre of the finger recess, with the sensor face flush to the surface — a recessed sensor reads badly.

Keep each as a separate lid/base variant in CAD so the breath-only version stays clean.
