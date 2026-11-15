# Google Play Console: texts and answers

For the internal testing track (see [README.md](README.md#google-play-internal-testing)). Every answer below describes what the code does today. If the app changes (for example, it starts sending anything off the phone), these answers must change too.

> [!IMPORTANT]
> Keep the wording of a screening aid, never of a diagnosis: "not a medical device", "see a doctor". An app that diagnoses is regulated as a medical device in the EU (MDR), and Google Play then asks for proof of certification. A **public** release would need that question answered properly first; internal testing for the team and the jury doesn't.

## Store listing

**App name** (30 max): `respirAI`

**Short description** (80 max, this one is 76):
```
Guided lung sound check with the respirAI stethoscope. Not a medical device.
```

**Full description:**
```
respirAI guides you through listening to your lungs with the respirAI digital stethoscope, a small Bluetooth device.

• The phone shows where to place the stethoscope: seven places on the chest, sides and back.
• A breathing circle on the screen and the lights on the device pace your breathing.
• Each recording is checked for quality and listened to by an AI that looks for crackles and wheezes.
• You see a simple result for each place, can listen to the recordings, and can send them to a doctor.

Private by design: the AI runs on the phone. Recordings and results stay on it; nothing is uploaded, and there are no accounts, ads or tracking.

In English, Romanian, Spanish, French and German, with large text, dark mode and spoken instructions.

No device yet? Tap "No device? Try a practice run" to see the whole check.

respirAI is a student project and NOT a medical device. It does not diagnose. If you are unwell, see a doctor. In an emergency, call 112.
```

**Graphics:** `icon-512.png` and `feature-graphic-1024x500.png` from the build's artifact; phone screenshots taken on a phone (at least 2).

**Category:** Medical. **Contact email:** an address you choose (it is shown on the listing). **Privacy policy:** `https://denis-furtuna.github.io/respirAI/privacy.html` (live once GitHub Pages is switched on; see `.github/workflows/pages.yml`).

## App content

| Item | Answer |
|---|---|
| Privacy policy | `https://denis-furtuna.github.io/respirAI/privacy.html` |
| App access | All functionality is available without special access. Note for reviewers: *The app works with the respirAI Bluetooth stethoscope. Without it, tap "No device? Try a practice run" on the first screen to go through the whole check with a simulated device.* |
| Ads | No ads |
| Content rating | Fill in the questionnaire honestly: no violence, sexual content, language, drugs, gambling, user interaction or sharing of location. Expected: rated for everyone (PEGI 3 / Everyone) |
| Target audience | 18 and over |
| News app | No |
| Data safety | See below |
| Health apps | See below |
| Government app | No |
| Financial features | None |

### Data safety

- **Does your app collect or share any of the required user data types?** No.
  - Why that is true: recordings are made by the device, analysed on the phone (`app/ai/`) and kept in memory only; the earlier checks list (date and overall result) stays in the app's storage; the Android app has no server setting (`app/app.js` hides it) and excludes its data from backups (`android_setup.py`). "Send the results to a doctor" hands files to an app the user picks, by the user's own action, which Play doesn't count as collection by this app.
- **Is all of the user data collected by your app encrypted in transit?** Not asked when nothing is collected.
- **Do you provide a way for users to request that their data is deleted?** Not asked when nothing is collected. (Settings → *Forget earlier checks*, or uninstalling, deletes everything.)

### Health apps declaration

Tick the features that describe the app, in the form's own words; today it does this:
- records lung sounds through a Bluetooth stethoscope and shows, per place, whether an AI heard possible crackles or wheezes;
- presents it as a screening aid, with "Not a diagnosis. Consult a doctor." on every result, and an emergency number;
- is not a regulated medical device and makes no treatment or dosage suggestions;
- keeps all data on the phone.

If the form asks whether the app is a regulated medical device: **No**. If it offers a disclaimer field, use: *respirAI is a student project and not a medical device. It does not diagnose. Consult a doctor.*

## Release notes for the first internal release

```
<en-GB>
First test version: the guided lung sound check with the respirAI stethoscope. The AI runs on the phone (example answers until the trained model is added).
</en-GB>
```
