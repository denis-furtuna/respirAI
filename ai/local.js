// The app's side of the AI on the phone (worker.js does the work). Same answers as the AI server's
// POST /analyze and GET /health, so app.js treats both the same way.
let worker = null, nextId = 0;
const waiting = new Map();   // id -> { resolve, reject }

function call(message, transfer = []) {
  if (!worker) {
    worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
    worker.onmessage = ({ data }) => {
      const w = waiting.get(data.id);
      waiting.delete(data.id);
      if (data.error) w?.reject(Object.assign(new Error(data.error.message), { status: data.error.status }));
      else w?.resolve(data.result);
    };
    worker.onerror = (e) => {   // the worker itself failed to start: fail everything waiting, start a new one next time
      console.warn("On-phone AI worker:", e.message);
      for (const w of waiting.values()) w.reject(Object.assign(new Error(e.message || "worker failed"), { status: 500 }));
      waiting.clear();
      worker = null;
    };
  }
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    waiting.set(id, { resolve, reject });
    worker.postMessage({ id, ...message }, transfer);
  });
}

// One place: samples are 8 kHz int16. Rejects with .status 400/404 (the recording can't be used) or 500 (a fault).
export function analyzeHere({ point, samples, demo = false, demoCase = null }) {
  const copy = samples ? Int16Array.from(samples) : new Int16Array(0);   // the app keeps its own copy for Listen / Share
  return call({ type: "analyze", point, samples: copy, demo, demoCase }, [copy.buffer]);
}

export const healthHere = () => call({ type: "health" });
