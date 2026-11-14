// Records the app's spoken instructions with an ElevenLabs voice: app/voice/<language>/<clip>.mp3 + manifest.json.
//
//   ELEVENLABS_API_KEY=... node app/dev/make_voice.mjs --voice <name or voice id>
//
//   --voice X      the voice: a voice id, or a name / search word among the voices of your ElevenLabs account
//                  (default: the voice the clips were made with last time)
//   --list [X]     only list your account's voices (matching X) with their ids
//   --lang ro en   only these languages (default: every language in app/i18n/)
//   --model M      default eleven_multilingual_v2 (it speaks all five of the app's languages)
//   --force        record everything again, also what has not changed
//   --dry-run      show what would be recorded and how many characters it costs; needs no key
//
// Only what is new is recorded: a clip is made again when its text changed in app/i18n/, or the voice or model
// changed. Clips of sentences the app no longer says are deleted. Commit app/voice/ afterwards: the app plays the
// files and never calls ElevenLabs itself, so the key stays on your computer (never put it in the repository).
// Needs Node 18 or newer, nothing to install.
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const APP = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(APP, "voice");
const MANIFEST = join(OUT, "manifest.json");
const API = process.env.ELEVENLABS_API_URL || "https://api.elevenlabs.io";   // e.g. https://api.eu.residency.elevenlabs.io for an EU-residency account
const FORMAT = "mp3_44100_64";   // speech only: half the size of the default, no audible loss on a phone

// The app's own modules, read as text so this runs whatever Node thinks of .js files (they import nothing).
const load = (path) => import("data:text/javascript;charset=utf-8," + encodeURIComponent(readFileSync(join(APP, path), "utf8")));

function options(argv) {
  const opt = { lang: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], value = () => (argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : undefined);
    if (a === "--voice") opt.voice = value();
    else if (a === "--model") opt.model = value();
    else if (a === "--list") { opt.list = true; opt.search = value(); }
    else if (a === "--lang") { let v; while ((v = value())) opt.lang.push(v); }
    else if (a === "--force") opt.force = true;
    else if (a === "--dry-run") opt.dry = true;
    else stop(`Unknown option ${a}. The options are at the top of app/dev/make_voice.mjs.`);
  }
  return opt;
}

function stop(message) {
  console.error(message);
  process.exit(1);
}

async function api(path, init = {}) {
  const key = process.env.ELEVENLABS_API_KEY;
  if (!key) stop("Set ELEVENLABS_API_KEY first (elevenlabs.io → Developers → API keys). It is read from the environment only.");
  const res = await fetch(API + path, { ...init, headers: { "xi-api-key": key, ...init.headers } });
  if (!res.ok) {
    const body = (await res.text()).slice(0, 400);
    stop(`ElevenLabs answered ${res.status} for ${path.split("?")[0]}: ${body}` + (res.status === 401 ? "\nIs the API key right, and may it use text to speech and read voices?" : ""));
  }
  return res;
}

const describe = (v) => `${v.voice_id}  ${v.name}` + (v.labels?.use_case ? `  [${v.labels.use_case}]` : "") + (v.category ? `  (${v.category})` : "");

async function voices(search) {
  const query = new URLSearchParams({ page_size: "100", ...(search ? { search } : {}) });
  return (await (await api(`/v2/voices?${query}`)).json()).voices || [];
}

// A voice id is used as it is; anything else is looked up among the account's voices and must match exactly one.
async function findVoice(wanted) {
  if (wanted === old.voice?.id) return { voice_id: old.voice.id, name: old.voice.name };
  if (/^[A-Za-z0-9]{20}$/.test(wanted)) return { voice_id: wanted, name: wanted };
  const found = await voices(wanted);
  const exact = found.filter((v) => v.name.toLowerCase() === wanted.toLowerCase());
  const pick = exact.length === 1 ? exact : found;
  if (pick.length === 1) return pick[0];
  if (!pick.length) stop(`No voice matching "${wanted}" in your ElevenLabs account. Add it to "My Voices" first, or see: node app/dev/make_voice.mjs --list`);
  stop(`"${wanted}" matches ${pick.length} voices. Run again with the id of the one you mean:\n` + pick.map((v) => "  " + describe(v)).join("\n"));
}

const opt = options(process.argv.slice(2));
if (opt.list) {
  for (const v of await voices(opt.search)) console.log(describe(v));
  process.exit(0);
}

const { CLIPS, spokenText } = await load("voice.js");
const en = (await load("i18n/en.js")).default;
const all = readdirSync(join(APP, "i18n")).filter((f) => /^[a-z]{2}\.js$/.test(f)).map((f) => f.slice(0, 2)).sort();
for (const code of opt.lang) if (!all.includes(code)) stop(`No app/i18n/${code}.js. Languages: ${all.join(", ")}.`);
const languages = opt.lang.length ? opt.lang : all;

const old = existsSync(MANIFEST) ? JSON.parse(readFileSync(MANIFEST, "utf8")) : {};
const model = opt.model || old.model || "eleven_multilingual_v2";
const wanted = opt.voice || old.voice?.id;
if (!wanted) stop("Which voice? Pass --voice <name or voice id>. To see your account's voices: node app/dev/make_voice.mjs --list");
const same = old.model === model && (wanted === old.voice?.id || wanted.toLowerCase() === old.voice?.name?.toLowerCase());
const kept = same ? old.clips || {} : {};   // another voice or model: every clip is recorded again
if (!same && old.clips && opt.lang.length) stop("Another voice or model than the clips were made with: run without --lang, so every language is in the same voice.");

// What to say, per language (a text a language lacks is said in English, as the app shows it).
const todo = [], clips = {};
for (const lang of all) {
  const dict = (await load(`i18n/${lang}.js`)).default;
  const t = (key) => {
    const text = dict[key] ?? en[key];
    if (typeof text !== "string") stop(`"${key}" (${lang}) must be a plain text to be spoken.`);
    return text;
  };
  clips[lang] = {};
  for (const id of Object.keys(CLIPS)) {
    const text = spokenText(id, t), file = join(OUT, lang, `${id}.mp3`);
    const again = opt.force && languages.includes(lang);
    if (!again && kept[lang]?.[id] === text && existsSync(file)) clips[lang][id] = text;       // up to date
    else if (languages.includes(lang)) todo.push({ lang, id, text, file });                    // record it
    else if (old.clips?.[lang]?.[id] && existsSync(file) && same) clips[lang][id] = old.clips[lang][id];   // not asked for now: stays as it is (the app won't play it if its text changed)
  }
}

const characters = todo.reduce((n, c) => n + c.text.length, 0);
console.log(`${todo.length} clips to record (${characters} characters), ${Object.values(clips).reduce((n, c) => n + Object.keys(c).length, 0)} up to date.`);
if (opt.dry) {
  for (const c of todo) console.log(`  ${c.lang}/${c.id}: ${c.text}`);
  process.exit(0);
}

const voice = todo.length || !old.voice ? await findVoice(wanted) : { voice_id: old.voice.id, name: old.voice.name };
const save = () => {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(MANIFEST, JSON.stringify({ voice: { id: voice.voice_id, name: voice.name }, model, format: FORMAT, clips }, null, 2) + "\n");
};
if (todo.length) console.log(`Voice: ${voice.name} (${voice.voice_id}), model ${model}`);

for (const c of todo) {
  // eleven_multilingual_v2 works the language out from the text and takes no language_code; the newer models do.
  const body = { text: c.text, model_id: model, ...(model === "eleven_multilingual_v2" ? {} : { language_code: c.lang }) };
  const res = await api(`/v1/text-to-speech/${voice.voice_id}?output_format=${FORMAT}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  mkdirSync(dirname(c.file), { recursive: true });
  writeFileSync(c.file, Buffer.from(await res.arrayBuffer()));
  clips[c.lang][c.id] = c.text;
  save();   // after every clip: a run that stops halfway keeps what it made
  console.log(`  ${c.lang}/${c.id}.mp3`);
}
save();

// Clips of sentences the app no longer says, or of languages it no longer has.
if (existsSync(OUT)) {
  for (const lang of readdirSync(OUT, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name)) {
    for (const file of readdirSync(join(OUT, lang)).filter((f) => f.endsWith(".mp3"))) {
      if (!clips[lang]?.[file.slice(0, -4)]) {
        rmSync(join(OUT, lang, file));
        console.log(`  removed ${lang}/${file}`);
      }
    }
  }
}
console.log(`Done: app/voice/ has ${Object.values(clips).reduce((n, c) => n + Object.keys(c).length, 0)} clips. Listen to a few, then commit app/voice/.`);
