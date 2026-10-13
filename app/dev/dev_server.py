"""Development server: the app plus the AI API (contract 2), on one port, with plain Python.

    python app/dev/dev_server.py            then open  http://localhost:8000/?fakebt&wav=crackles.wav

Made for laptops where FastAPI can't be installed or loaded. If the AI code is in this checkout
(ai/service.py and its packages: numpy, scipy, onnxruntime), it runs that: the real model, or the
AI's own dummy mode. Otherwise it gives clearly fake answers, so the app's whole flow can be tried.
For the demo itself, use the real server: uvicorn server:app (see ai/README.md).
"""
import argparse
import email
import io
import json
import sys
import types
import wave
from array import array
from email import policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP, DEMO_CLIPS = ROOT / "app", ROOT / "ai" / "demo_clips"


class ServiceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


# ---------- fake AI: same shapes as ai/service.py, obviously fake findings ----------
VERSION, SESSIONS = "dev-fake (no AI)", {}


def fake_health():
    return {"status": "ok", "model_version": VERSION, "dummy": True, "demo_clips": 0}


def fake_analyze(point, session_id, audio_bytes=None, demo=False, demo_case=None):
    if point not in ("Tc", "Al", "Ar", "Pl", "Pr", "Ll", "Lr"):
        raise ServiceError(400, f"Unknown point '{point}'.")
    if demo:
        if demo_case not in ("normal", "crackles", "wheezes", "both"):
            raise ServiceError(400, "Demo mode needs demo_case, one of normal, crackles, wheezes, both.")
        finding, quality = demo_case, 0.95
    else:
        if not audio_bytes:
            raise ServiceError(400, "Send the recording in the 'audio' field, or set demo=true.")
        try:
            with wave.open(io.BytesIO(audio_bytes)) as w:
                samples, rate = array("h", w.readframes(w.getnframes())), w.getframerate()
        except Exception:
            raise ServiceError(400, "The audio file is not a readable WAV.")
        seconds = len(samples) / rate
        if not 2 <= seconds <= 60:   # as ai/service.py
            raise ServiceError(400, f"Recording is {seconds:.1f} s; send between 2 and 60 s.")
        rms = (sum(s * s for s in samples) / max(1, len(samples))) ** 0.5
        finding, quality = ("unusable", 0.1) if rms < 30 else ("normal", 0.9)
    result = {"point": point, "finding": finding, "confidence": 0.5, "quality": quality,
              "model_version": VERSION, "latency_ms": 1, **({"demo": True} if demo else {})}
    SESSIONS.setdefault(session_id, {})[point] = result
    return result


def fake_summary(session_id):
    if session_id not in SESSIONS:
        raise ServiceError(404, f"No recordings for session '{session_id}'.")
    points = SESSIONS[session_id]
    return {"session_id": session_id, "points_recorded": len(points), "overall": "normal", "confidence": 0.5,
            "per_point": [{"point": p, "finding": r["finding"], "confidence": r["confidence"]} for p, r in points.items()],
            "disclaimer": "Screening aid only. Not a diagnosis. Consult a doctor."}


try:
    sys.path.insert(0, str(ROOT / "ai"))
    import service as ai   # the real thing, if it's in this checkout
except Exception as e:     # not here, or its packages are missing
    ai = types.SimpleNamespace(health=fake_health, analyze=fake_analyze, summary=fake_summary, ServiceError=ServiceError)
    AI_PROBLEM = str(e)
else:
    AI_PROBLEM = None


# ---------- HTTP ----------
class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css",
                      ".ogg": "audio/ogg", ".wav": "audio/wav", ".json": "application/json", ".webmanifest": "application/manifest+json"}

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/demo_clips/"):
            return str(DEMO_CLIPS / path[len("/demo_clips/"):])
        return str(APP / path.lstrip("/"))

    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        for k, v in {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Content-Length": str(len(data))}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def api(self, call):
        try:
            self.send_json(200, call())
        except ai.ServiceError as e:
            self.send_json(e.status, {"error": e.message})

    def do_GET(self):
        if self.path == "/health":
            return self.api(ai.health)
        if self.path.startswith("/session/") and self.path.endswith("/summary"):
            return self.api(lambda: ai.summary(self.path.split("/")[2]))
        super().do_GET()

    def do_POST(self):
        if self.path != "/analyze":
            return self.send_json(404, {"error": "Not found."})
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        form = email.message_from_bytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body,
                                        policy=policy.HTTP)
        parts = {p.get_param("name", header="content-disposition"): p for p in form.iter_parts()}
        audio = parts.pop("audio", None)
        fields = {name: part.get_content().strip() for name, part in parts.items()}
        self.api(lambda: ai.analyze(fields.get("point"), fields.get("session_id"),
                                    audio.get_payload(decode=True) if audio else None,
                                    fields.get("demo") == "true", fields.get("demo_case")))

    def log_message(self, fmt, *args):
        if "/analyze" in self.requestline or "/health" in self.requestline:
            print(self.requestline.split(" HTTP")[0], args[1] if len(args) > 1 else "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 lets a phone on the same network connect")
    args = parser.parse_args()
    print(f"AI: {'the real AI code in ai/' if not AI_PROBLEM else 'FAKE answers (' + AI_PROBLEM + ')'}")
    print(f"App: http://localhost:{args.port}/   fake device: http://localhost:{args.port}/?fakebt&wav=crackles.wav")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
