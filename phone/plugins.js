// What the phone app adds to the web app: the Capacitor plugins. The build bundles this file into
// www/native/plugins.js (esbuild, see .github/workflows/phone-app.yml); app/native.js loads it, only in the app.
export { BleClient } from "@capacitor-community/bluetooth-le";
export { KeepAwake } from "@capacitor-community/keep-awake";
export { TextToSpeech } from "@capacitor-community/text-to-speech";
export { App } from "@capacitor/app";
export { SystemBars, SystemBarsStyle } from "@capacitor/core";
export { Directory, Filesystem } from "@capacitor/filesystem";
export { Haptics } from "@capacitor/haptics";
export { Share } from "@capacitor/share";
