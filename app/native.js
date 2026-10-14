// The phone app (phone/, built with Capacitor) runs this same web app inside Android's WebView. A few things a
// browser does aren't there (Web Bluetooth, speech, the screen wake lock, the share sheet), so the app uses the
// phone's own instead, through Capacitor plugins. In a browser `native` is null and the web app runs as always.
import { nativeBluetooth } from "./native-bluetooth.js";

export const native = window.Capacitor?.isNativePlatform?.()
  ? await load().catch((e) => { console.error("Phone features unavailable:", e); return null; })   // the app still opens
  : null;

async function load() {
  const p = await import("./native/plugins.js");   // the plugins, bundled from phone/plugins.js by the build
  // Android's back button: back through the app's own history (a check catches it to stop the recording, as in
  // Chrome); at the start, the app goes to the background instead of closing, so nothing on screen is lost.
  p.App.addListener("backButton", ({ canGoBack }) => (canGoBack ? history.back() : p.App.minimizeApp()));
  return {
    bluetooth: nativeBluetooth(p.BleClient),
    pickerTexts: (texts) => p.BleClient.setDisplayStrings(texts).catch(() => {}),
    speak: (text, lang) => p.TextToSpeech.speak({ text, lang, rate: 0.9 }),   // resolves when it has been said
    hush: () => p.TextToSpeech.stop().catch(() => {}),
    keepAwake: (on) => (on ? p.KeepAwake.keepAwake() : p.KeepAwake.allowSleep()).catch(() => {}),
    vibrate: (ms) => p.Haptics.vibrate({ duration: ms }).catch(() => {}),
    onPause: (fn) => p.App.addListener("pause", fn),
    onResume: (fn) => p.App.addListener("resume", fn),
    bars: (theme) => p.SystemBars.setStyle({ style: theme === "dark" ? p.SystemBarsStyle.Dark : p.SystemBarsStyle.Light }).catch(() => {}),
    share: (sheet) => share(p, sheet),
  };
}

// The phone's share sheet with the recordings as files: they are written to the app's cache first, in a folder of
// their own; the previous share's folder is removed (Android may also clear the cache by itself).
let lastShare = null;
async function share(p, { title, text, files = [] }) {
  if (lastShare) await p.Filesystem.rmdir({ path: lastShare, directory: p.Directory.Cache, recursive: true }).catch(() => {});
  const folder = (lastShare = `share-${Date.now()}`);
  const uris = [];
  for (const file of files) {
    const data = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    uris.push((await p.Filesystem.writeFile({ path: `${folder}/${file.name}`, data, directory: p.Directory.Cache, recursive: true })).uri);
  }
  try {
    await p.Share.share({ title, text, dialogTitle: title, ...(uris.length ? { files: uris } : {}) });
  } catch (e) {
    throw /cancel/i.test(e.message) ? new DOMException(e.message, "AbortError") : e;
  }
}
