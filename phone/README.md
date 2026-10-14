# phone/: respirAI as an Android app

The Android app is the web app in [`app/`](../app/), unchanged, packaged with [Capacitor 8](https://capacitorjs.com/). Same screens, same languages, same tests. It needs no laptop, no server and no internet: the AI runs on the phone (`app/ai/`).

Everything is built on GitHub. Nothing has to be installed on a laptop.

## What is different inside the app

Android's WebView lacks a few browser features, so the app uses the phone's own instead. [`app/native.js`](../app/native.js) chooses; in a browser none of this runs.

| In Chrome | In the app | Plugin |
|---|---|---|
| Web Bluetooth | Android's Bluetooth, behind the same calls ([`native-bluetooth.js`](../app/native-bluetooth.js)), so `device.js` is unchanged; asks for larger packets and a fast connection | `@capacitor-community/bluetooth-le` |
| Speech | Android's text-to-speech | `@capacitor-community/text-to-speech` |
| Screen wake lock | keep the screen on during a check | `@capacitor-community/keep-awake` |
| Share sheet with files | Android's share sheet, recordings as WAV files | `@capacitor/share`, `@capacitor/filesystem` |
| Vibration | Android's vibration | `@capacitor/haptics` |
| Back button | back through the app's own screens (a check stops, as in Chrome); at the start, the app goes to the background instead of closing | `@capacitor/app` |
| Status bar | light or dark icons to match the theme; the page keeps clear of the bars (`--safe-area-inset-*` in `style.css`) | Capacitor's System Bars |
| "AI server address" (team setting) | hidden: the app always analyses on the phone, so nothing it records leaves the phone | |

## Files

| File | What it does |
|---|---|
| `package.json` | the exact versions of Capacitor, its plugins, ONNX Runtime Web and esbuild |
| `capacitor.config.json` | app ID `ro.respirai.app`, name, the plugins' settings |
| `plugins.js` | the plugins, bundled by esbuild into `www/native/plugins.js` for `app/native.js` |
| `build_web.py` | `app/` without tests and dev tools, plus ONNX Runtime Web: into `www/` (or the Pages site) |
| `android_setup.py` | everything that differs from Capacitor's Android template: permissions, no backup, icons, splash, version, signing |

`www/`, `android/` and `store/` are made by each build and never committed.

## Install the test app on a phone

1. On GitHub: **Actions** → **Phone app** → the newest run with a green tick → **Artifacts** → `respirAI-android-<n>`. Download it on the phone (or on a computer, then copy it over) and unzip it.
2. Open `respirAI-test-<n>.apk`. Android asks to allow installing apps from that source (Files or Chrome): allow it for this once.
3. Open **respirAI** and tap **Connect the device**. Android asks for **Nearby devices**: allow. Then pick the respirAI device in the list.

The test APK is signed with a debug key: an update installs over it; the Play version can't (uninstall the test one first). Phones in Romania still install such APKs normally; Google's new rule that apps outside the Play Store must come from a verified developer applies in four other countries now and worldwide in 2027.

**Check on the phone** (things the automated tests can't reach): Bluetooth connects and the signal shows; spoken instructions in Romanian; the screen stays on; *Send the results to a doctor* opens the share menu with the WAV files; the back button during a recording; dark mode, with the status bar icons readable; the app paused by a phone call.

## Google Play: internal testing

Internal testing reaches up to 100 testers you choose by email, through the Play Store, without a public listing and without the 14-day closed test that a public release needs. The texts and answers for the Play Console are in [`PLAY.md`](PLAY.md).

### 1. The upload key (once)

Google keeps the key that signs the app for users (*Play App Signing*). You only need an **upload key**, to prove the uploads are yours. Make it on a GitHub Codespace (a temporary machine in the cloud), not on a laptop:

1. On GitHub: **Code** → **Codespaces** → **Create codespace on phone-app**. In its terminal:
   ```bash
   keytool -genkeypair -v -keystore upload.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000 \
     -dname "CN=respirAI, O=respirAI, C=RO"
   base64 -w0 upload.jks > upload.jks.txt
   ```
   It asks for a password twice. Use a long one and keep it in a password manager.
2. In the repository: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, four times:

   | Name | Value |
   |---|---|
   | `RESPIRAI_KEYSTORE_BASE64` | the contents of `upload.jks.txt` (open it in the Codespace's editor, copy all) |
   | `RESPIRAI_KEYSTORE_PASSWORD` | the password |
   | `RESPIRAI_KEY_ALIAS` | `upload` |
   | `RESPIRAI_KEY_PASSWORD` | the same password |
3. Download `upload.jks` from the Codespace (right-click → Download) and keep it, with the password, somewhere safe and private (a password manager). Never commit it: `.gitignore` refuses `*.jks`. Then delete the Codespace (**Code** → **Codespaces** → … → **Delete**).

If the upload key is ever lost, Play Console can register a new one (**Setup** → **App signing** → *Request upload key reset*); the app itself is safe, because Google holds its signing key.

### 2. The bundle

Run **Actions** → **Phone app** → **Run workflow** on `phone-app` (or push). With the secrets set, the artifact also has `respirAI-<n>.aab`, signed with the upload key, plus `icon-512.png` and `feature-graphic-1024x500.png` for the listing. Every build has a higher version code (the run number), as Play requires.

### 3. Play Console (once)

1. **Create app**: name *respirAI*, default language English (United Kingdom), *App*, *Free*. Accept the declarations.
2. **App content** (Dashboard → *Set up your app*): fill in each item with the answers in [`PLAY.md`](PLAY.md): privacy policy URL, app access, ads, content rating, target audience, data safety, health apps.
3. **Testing** → **Internal testing** → **Testers**: create an email list (yourself and the team, the Google accounts used on the phones). Copy the **opt-in link**.
4. **Internal testing** → **Create new release**. Choose *Use Google-generated key* (Play App Signing). Upload `respirAI-<n>.aab`. Release name and notes: see `PLAY.md`. **Next** → **Save and publish**.
5. Each tester opens the opt-in link on the phone, accepts, and installs respirAI from the Play Store. The first internal release can take a while to appear; later ones are usually quick.

The package name `ro.respirai.app` (in `capacitor.config.json`) becomes permanent with the first upload. To use another, change it before then.

### 4. Updates

Push to `phone-app` → wait for the green tick → download the new `.aab` → **Internal testing** → **Create new release** → upload → **Save and publish**. Testers get the update through the Play Store.

## Build it yourself (optional)

Only on a computer that may have the tools (Node 22+, JDK 21, Android Studio with SDK 36), never on the work laptop. From `phone/`:

```bash
npm install --ignore-scripts
python build_web.py www
npx esbuild plugins.js --bundle --format=esm --target=es2020 --outfile=www/native/plugins.js
npx cap add android
pip install pillow && python android_setup.py
npx cap sync android
npx cap open android        # Android Studio: Run on a connected phone
```
