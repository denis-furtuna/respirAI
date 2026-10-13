# respirAI — Demo day

The script, the setup, the fallbacks and the answers for the 5-minute presentation (PLAN tasks P1, P2, P3, P7, P8). A first draft: rehearse it and change what doesn't work.

Roles below are **A** (speaker), **B** (holds the device and the phone) and **C** (laptop, fallbacks). Fill in names.

---

## 1. Setup (P2): everything local, no internet

**The day before**
- [ ] Device charged; breadboard backup packed (E10).
- [ ] Laptop: the repo with `ai/` and `app/` together, the trained model in `ai/weights/`, the demo clips in `ai/demo_clips/`.
- [ ] Phone (S25 Ultra): Chrome flag set for the laptop's address, *Nearby devices* permission already granted (see `app/README.md`).
- [ ] Full run with Wi-Fi and mobile data **off** on both phone and laptop.

**30 minutes before**
1. Laptop: turn on the hotspot, connect the phone to it.
2. Laptop, in `ai/`: `uvicorn server:app --host 0.0.0.0 --port 8000`. This one command serves the app and the AI.
3. Phone: open `http://<laptop-address>:8000`. Settings icon → **Test the AI server** shows the model version and "28 demo clips".
4. Settings → **Seconds per place: 5**, so a full check takes about a minute on stage.
5. Switch the device on, press **Connect the device**, check "Sound is coming through". Then leave it connected.
6. Phone: screen brightness up, auto-rotate off, notifications muted (Do Not Disturb).

---

## 2. The 5 minutes (P1)

| Time | Who | Says | Does / on screen |
|---|---|---|---|
| 0:00 | A | "The stethoscope was invented in 1816. Two hundred years later, it still only works if a trained ear is listening." | Slide: Laennec's stethoscope next to ours |
| 0:30 | A | "Most people who need their lungs checked don't have that ear nearby. respirAI lets anyone record their lungs and get a first screening: normal, or see a doctor." | Slide: the problem |
| 1:00 | B | "This is it. A cheap stethoscope chest piece, a microphone, and a small board. About 200 lei in parts." | Holds up puck and bell; LEDs glowing |
| 1:20 | B | "Can one of you help us? Just sit upright." | Volunteer judge. Phone: *Begin* |
| 1:30 | B | (quiet; let the app guide) "The phone shows where to place it, and the light paces the breathing." | 7 places, ~6 s each, *It's in place, start now* to keep the pace |
| 2:30 | A | "And the result: no unusual sounds. Good news for our judge." | Results: green |
| 2:40 | A | "Healthy lungs sound normal, so here's what the AI hears in a real patient, from the ICBHI clinical dataset." | C or B: Settings → Demo mode *crackles* → *Record again* on one place |
| 3:10 | A | "Crackles, picked up at that spot. The app doesn't diagnose. It says: show this to a doctor." | Results: amber, body map |
| 3:30 | A | "Under the hood: the device streams 8 kHz audio over Bluetooth, a neural network trained on 6,898 breathing cycles screens each place." | Slide: architecture |
| 4:00 | A | "On patients it never saw, it scores [numbers from `ai/results/results.json`]. Honest numbers, per class." | Slide: per-class scores |
| 4:30 | A | "Next: ECG and pulse modules on the same device, and running the AI on the phone itself." | Slide: what's next + cost |
| 4:50 | A | "respirAI. Listen early." | Logo |

**Demo mode is part of the story, not an excuse (P3).** Say it the same way every time: *healthy lungs sound normal, so here's what a real patient's recording sounds like.* Practise the switch until it takes under 10 seconds.

---

## 3. If something fails

| What goes wrong | What to do |
|---|---|
| Device won't connect | Switch it off and on, *Connect the device* again. Still nothing within 20 s: *No device? Try a practice run* and continue with demo mode. Say "we'll show you the recordings from the session this morning". |
| "No sound" on screen | Check the tube is pushed onto the mic. Then as above. |
| AI server unreachable | C restarts the command on the laptop. Meanwhile A talks through the architecture slide. |
| Phone dies or Chrome crashes | C opens `http://localhost:8000` in Chrome on the laptop. Web Bluetooth works there too. |
| Case breaks | The breadboard version (E10). |

---

## 4. Questions we'll get (P7)

**Is this a medical device?**
No. It's a screening aid built at a student hackathon. It doesn't diagnose; it says whether the lungs sound normal and when to see a doctor. A real product would need clinical validation and certification.

**How accurate is it?**
Give the per-class scores on the test patients (from `ai/results/results.json`), and say plainly where it's weak. Never round up or say "clinically accurate". Add: the training data came from clinical stethoscopes, so our next step is testing on our own device's recordings (D9).

**Can it detect the flu / COVID / pneumonia?**
It doesn't detect diseases. It detects abnormal lung *sounds*: crackles and wheezes. Those show up with problems like pneumonia, bronchitis or an asthma flare, including complications after the flu. An ordinary flu usually sounds normal in the lungs.

**Why train on sounds, not diseases?**
86 % of the dataset's patients have COPD. A model trained on diagnoses learns to always say "COPD". Sound labels are spread across all patients and match what we actually report.

**Where does the data go?**
Nowhere. The audio goes from the device to the phone to a laptop on a local hotspot. No cloud, no internet.

**Why not just buy a digital stethoscope?**
Commercial ones cost many times more and still need a trained ear or a subscription. Ours costs about 200 lei and guides someone with no training.

**What would you do with more time?**
Test on our own recordings and retrain; ECG and pulse modules (the hardware is already planned); run the model on the phone so no laptop is needed.

---

## 5. Wording check (P8)

Search the slides, the app and anything printed for these before the final rehearsal.

| Never say | Say instead |
|---|---|
| diagnosis, diagnose | screening, finding |
| detects flu / COVID / pneumonia | detects abnormal lung sounds |
| accurate, clinically proven | per-class scores on test patients |
| replaces a doctor | helps you know when to see a doctor |

The only allowed use of "diagnosis" is the disclaimer: *Screening aid only. Not a diagnosis. Consult a doctor.*

---

## 6. Rehearsals (P5)

Five full runs with the real device, timed, at least one with Wi-Fi and data switched off and one where C deliberately triggers a fallback. Note the time of each run here:

| # | Date | Time | What went wrong |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
