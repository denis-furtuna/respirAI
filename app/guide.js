// The voice guide: an ElevenLabs conversational agent that talks the person through the check and answers questions
// like "where exactly do I put it?". It is a layer over the app's own flow, never a replacement: the timer, the
// breathing circle and the device's lights stay in app.js, and every step still works by screen and button.
//
//   - app.js tells the agent what is happening (the place, the recording about to start, the result) with tell();
//     the agent says it in its own words, in the person's language.
//   - The agent can press two of the app's buttons: its client tools start_recording ("it's in place") and stop_check.
//   - While the stethoscope records, hold(true): the phone's microphone is off and the agent is silent, or the
//     stethoscope would pick the voices up.
//   - No connection, no microphone, the agent gone mid-check: connected turns false and app.js goes back to the
//     spoken instructions (voice.js), so the check never waits for the internet.
//
// Needs internet, unlike the rest of the app. What goes to ElevenLabs: what the person says while the guide listens,
// and the on-screen texts the agent is told (place, result). Stethoscope recordings never do.
import { AGENT_ID } from "./guide-config.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SDK = "./guide-sdk/elevenlabs-client.mjs";   // @elevenlabs/client, loaded only when a guided check starts

function agentId() {
  try {
    const given = new URLSearchParams(location.search).get("agent");
    if (given !== null) given ? localStorage.setItem("respirai-agent", given) : localStorage.removeItem("respirai-agent");
    return localStorage.getItem("respirai-agent") || AGENT_ID;
  } catch (e) {
    return AGENT_ID;
  }
}

let conversation = null, opening = null, run = 0;
let mode = "listening", held = false, micOff = false;
let language = "";            // the person's language, by its English name: every message to the agent names it
let spokeAt = 0, saidAt = 0;  // when the agent last began to speak, and when its last reply arrived
let onState = () => {};

// "off" | "connecting" | "listening" | "speaking" | "micOff" | "held"
const state = () => (!conversation ? (opening ? "connecting" : "off") : held ? "held" : mode === "speaking" ? "speaking" : micOff ? "micOff" : "listening");
const changed = () => onState(state());

function applyAudio() {
  if (!conversation) return;
  try {
    conversation.setMicMuted(held || micOff);
    conversation.setVolume({ volume: held ? 0 : 1 });
  } catch (e) { /* the session is closing */ }
}

async function open(mine, lang, tools, withLanguage) {
  const sdk = window.respiraiGuideSdk || await import(SDK);   // the tests bring a stand-in
  let openedAt = 0, session = null;
  session = await sdk.Conversation.startSession({
    agentId: agentId(),
    clientTools: tools,
    ...(withLanguage ? { overrides: { agent: { language: lang } } } : {}),
    onModeChange: ({ mode: m }) => {
      if (mine !== run) return;
      if (m === "speaking" && mode !== "speaking") spokeAt = performance.now();
      mode = m;
      changed();
    },
    onMessage: ({ source }) => { if (mine === run && source === "ai") saidAt = performance.now(); },
    onDisconnect: () => {
      if (mine !== run || !session || conversation !== session) return;   // stopped by the app, or never opened
      conversation = null;
      // Closed right after opening: most likely the agent doesn't allow the language to be set. Once more, without.
      if (withLanguage && performance.now() - openedAt < 4000) opening = connect(mine, lang, tools, false);
      changed();
    },
    onError: (message) => console.warn("voice guide:", message),
  });
  openedAt = performance.now();
  return session;
}

async function connect(mine, lang, tools, withLanguage) {
  let session = null;
  try {
    session = await open(mine, lang, tools, withLanguage);
  } catch (e) {
    if (withLanguage && mine === run && e?.name !== "NotAllowedError") {
      try { session = await open(mine, lang, tools, false); } catch (e2) { console.warn("voice guide:", e2); }
    } else console.warn("voice guide:", e);
  }
  if (mine !== run) {   // stopped while it was connecting
    session?.endSession().catch(() => {});
    return false;
  }
  opening = null;
  conversation = session;
  mode = "listening";
  applyAudio();
  changed();
  return !!session;
}

export const guide = {
  // Is there a guide to offer at all? (An agent is set up, and this browser has a microphone to give it.)
  get available() { return !!agentId() && !!navigator.mediaDevices?.getUserMedia; },
  get connected() { return !!conversation; },
  get state() { return state(); },

  // Asks for the microphone, from a tap. Throws when the person (or the phone) says no.
  async allow() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
  },

  // Starts connecting; doesn't wait and never throws. tools: what the agent may do in the app, by name.
  start({ lang, name, tools, onChange }) {
    this.stop();
    onState = onChange || (() => {});
    held = micOff = false;
    language = name || lang;
    opening = connect(++run, lang, tools, true);
    changed();
  },

  // Tells the agent something from the app; it answers aloud. Waits a little for a guide still connecting.
  // false: there is no guide (now), say it another way.
  async tell(message, wait = 6000) {
    if (opening) await Promise.race([opening, sleep(wait)]);
    if (!conversation) return false;
    try {
      conversation.sendUserMessage(`[APP] (Speak ${language}, and only ${language}.) ${message}`);
      return true;
    } catch (e) {
      return false;
    }
  },

  // Resolves when the agent has said what it was asked to at `since` (a tell(), or a tool's answer):
  //   1. its answer has begun: it started speaking after `since`, or a reply arrived after `since` and is being
  //      spoken. Whatever it was already saying before (a "Great!" ahead of its tool call) doesn't count.
  //      Gives up after `start` ms: an agent that says nothing must not hold the check up.
  //   2. and it is over: nothing audible for a full second (a pause between two sentences is shorter), or `end` ms.
  async spoken(since = performance.now(), start = 6000, end = 25000) {
    const mine = run;
    const live = () => mine === run && conversation;
    const audible = () => {
      if (mode === "speaking") return true;
      try { return conversation.getOutputVolume() > 0.02; } catch (e) { return false; }
    };
    for (let t0 = performance.now(); live() && !(spokeAt >= since || (saidAt >= since && audible())) && performance.now() - t0 < start;) await sleep(80);
    for (let t0 = performance.now(), quiet = 0; live() && performance.now() - t0 < end; await sleep(80)) {
      if (audible()) quiet = 0;
      else if (!quiet) quiet = performance.now();
      else if (performance.now() - quiet >= 1000) break;
    }
  },

  // The last thing to say (the result): tells it, lets the agent finish, then ends the conversation.
  async finish(message) {
    const mine = run;
    if (!(await this.tell(message))) return false;
    this.spoken(performance.now(), 8000, 45000).then(() => { if (mine === run) this.stop(); });
    return true;
  },

  // true while the stethoscope records: microphone off, agent inaudible.
  hold(on) {
    if (held === on) return;
    held = on;
    applyAudio();
    changed();
  },

  // The person's own switch for the microphone (a noisy room). Returns whether it is now off.
  toggleMic() {
    micOff = !micOff;
    applyAudio();
    changed();
    return micOff;
  },

  stop() {
    run++;
    const session = conversation, was = state();
    conversation = opening = null;
    held = false;
    session?.endSession().catch(() => {});
    if (was !== "off") changed();
  },
};
