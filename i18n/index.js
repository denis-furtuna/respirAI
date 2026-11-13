// Translations. English is built in and fills in anything a language is missing; other languages load on demand.
// To add a language: copy en.js to xx.js, translate the values (keep the {names} and <b>), add it to LANGUAGES.
// Plural texts are objects keyed by Intl.PluralRules categories (one, few, many, other); "other" is required.
import en from "./en.js";

export const LANGUAGES = [   // code, name in its own language, locale for dates, numbers and speech
  { code: "en", name: "English", locale: "en-GB" },
  { code: "ro", name: "Română", locale: "ro-RO" },
  { code: "es", name: "Español", locale: "es-ES" },
  { code: "fr", name: "Français", locale: "fr-FR" },
  { code: "de", name: "Deutsch", locale: "de-DE" },
];

let strings = en, language = LANGUAGES[0], plural = new Intl.PluralRules(language.locale);
export const current = () => language;

// The first of the phone's languages that the app has, else English.
export function detect() {
  for (const tag of navigator.languages || [navigator.language || "en"]) {
    const found = LANGUAGES.find((l) => l.code === tag.slice(0, 2).toLowerCase());
    if (found) return found.code;
  }
  return "en";
}

export async function setLanguage(code) {
  const next = LANGUAGES.find((l) => l.code === code) || LANGUAGES[0];
  try {
    strings = next.code === "en" ? en : (await import(`./${next.code}.js`)).default;
    language = next;
  } catch (e) {   // offline before this language was ever loaded: stay in the current one
    console.warn(`Could not load ${next.code}:`, e.message);
  }
  plural = new Intl.PluralRules(language.locale);
  document.documentElement.lang = language.code;
  translatePage();
}

// t("ready.continue", { n: 3 }): the text for the current language, in the right plural form for n, with {names} filled in.
export function t(key, vars = {}) {
  let text = strings[key] ?? en[key];
  if (text === undefined) {
    console.warn(`No text for "${key}"`);
    return key;
  }
  if (typeof text === "object") text = text[plural.select(vars.n ?? 0)] ?? text.other;
  return text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? vars[name] : m));
}

export const percent = (x) => new Intl.NumberFormat(language.locale, { style: "percent" }).format(x);
export const dateTime = (ms) => new Date(ms).toLocaleString(language.locale, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

// The fixed text in index.html: data-t="key" (plain text), data-t-html="key" (text with <b>), data-t-label="key" (aria-label).
export function translatePage(root = document) {
  root.querySelectorAll("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  root.querySelectorAll("[data-t-html]").forEach((el) => { el.innerHTML = t(el.dataset.tHtml); });
  root.querySelectorAll("[data-t-label]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.tLabel)));
  document.querySelector('meta[name="description"]')?.setAttribute("content", t("app.description"));
}
