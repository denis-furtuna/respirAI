// The recorded voice for the spoken instructions (an ElevenLabs voice), with the phone's own voice behind it.
//
// Everything the app says is fixed text, so each sentence is recorded once per language by app/dev/make_voice.mjs
// and shipped with the app as voice/<language>/<clip>.mp3. The phone never talks to ElevenLabs: no key in the app,
// no internet needed, and nothing leaves the phone.
//
// voice/manifest.json holds the exact text each clip was recorded from. A clip is played only while that is still
// the text on the screen; a changed text, a clip not recorded yet or a file that can't be loaded all mean "not
// played", and app.js then says it with the phone's own voice, as before.

// clip → the texts (i18n keys) it says, one after another. Shared with make_voice.mjs: keep it free of imports.
export const CLIPS = Object.fromEntries([
  ["voiceOn", ["ready.voiceOn"]],
  ...["Tc", "Al", "Ar", "Pl", "Pr", "Ll", "Lr"].map((code) => [`point.${code}`, [`point.${code}.title`, `point.${code}.where`]]),
  ["breathe", ["point.sayBreathe"]],
  ["breatheNext", ["point.sayBreatheNext"]],
  ...["warn", "pending", "retry", "unclear", "ok"].map((key) => [`overall.${key}`, [`overall.${key}.title`, `overall.${key}.text`]]),
]);
export const spokenText = (id, t) => CLIPS[id].map((key) => t(key)).join(". ");

let recorded = null;        // promise of { language: { clip: text } }, from voice/manifest.json
const loaded = new Map();   // clip address → promise of an object URL (null: could not be loaded)
let audio = null, finish = null, turn = 0;

function manifest() {
  recorded = recorded || fetch("voice/manifest.json")
    .then((res) => (res.ok ? res.json() : {}))   // no manifest: nothing has been recorded
    .then((m) => m.clips || {})
    .catch(() => { recorded = null; return {}; });   // offline just now: ask again next time
  return recorded;
}

function load(lang, id) {
  const url = `voice/${lang}/${id}.mp3`;
  if (!loaded.has(url)) {
    loaded.set(url, fetch(url)
      .then((res) => { if (!res.ok) throw new Error(res.status); return res.blob(); })
      .then((blob) => URL.createObjectURL(blob))
      .catch(() => { loaded.delete(url); return null; }));
  }
  return loaded.get(url);
}

// Fetches this language's clips ahead of time (when spoken instructions are switched on), so the first sentence
// doesn't wait for a download and the service worker has them for offline use.
export function preloadVoice(lang) {
  manifest().then((all) => { for (const id of Object.keys(all[lang] || {})) if (id in CLIPS) load(lang, id); });
}

// Plays the recorded clip for this text. Resolves true when it has been said (or was cut by stopClip or by the
// next sentence), false when there is no usable clip: the caller then speaks the text itself.
export async function playClip(lang, id, text) {
  stopClip();
  const mine = turn;
  const all = await manifest();
  if (mine !== turn) return true;
  if (all[lang]?.[id] !== text) return false;
  const src = await load(lang, id);
  if (mine !== turn) return true;
  if (!src) return false;
  audio = audio || new Audio();
  audio.src = src;
  const said = new Promise((resolve) => {
    finish = resolve;
    audio.onended = () => resolve(true);
    audio.onerror = () => resolve(false);
  });
  try {
    await audio.play();
  } catch (e) {   // cut before it started, or the browser refused to play
    return mine !== turn;
  }
  return said;
}

export function stopClip() {
  turn++;
  if (audio) {
    audio.onended = audio.onerror = null;
    audio.pause();
  }
  finish?.(true);
  finish = null;
}
