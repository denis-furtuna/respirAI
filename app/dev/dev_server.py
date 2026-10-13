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
import wave
from array import array
from email import policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP, DEMO_CLIPS = ROOT / "app", ROOT / "ai" / "demo_clips"
POINTS = ["Tc", "Al", "Ar", "Pl", "Pr", "Ll", "Lr"]
CASES = ["normal", "crackles", "wheezes", "both"]

try:
    sys.path.insert(0, str(ROOT / "ai"))
    import service as ai   # the real thing, if it's here
except Exception as e:     # not in this checkout, or its packages are missing
    ai = None
    AI_PROBLEM = str(e)


class FakeAI:
    """Same shapes as the real server, obviously fake findings."""
    version = "dev-fake (no AI)"
    sessions = {}

    class Error(Exception):
        def __init__(self, status, message):
            self.status, self.message = status, message

    def health(self):
        return {"status": "ok", "model_version": self.version, "dummy": True, "demo_clips": 0}

    def analyze(self, point, session_id, audio_bytes=None, demo=False, demo_case=None):
        if point not in POINTS:
            raise self.Error(400, f"Unknown point '{point}'.")
        if demo:
            if demo_case not in CASES:
                raise self.Error(400, f"Demo mode needs demo_case, one of {', '.join(CASES)}.")
            finding, quality = demo_case, 0.95
        else:
            if not audio_bytes:
                raise self.Error(400, "Send the recording in the 'audio' field, or set demo=true.")
            try:
                with wave.open(io.BytesIO(audio_bytes)) as w:
                    samples = array("h", w.readframes(w.getnframes()))
            except Exception:
                raise self.Error(400, "The audio file is not a readable WAV.")
            rms = (sum(s * s for s in samples) / max(1, len(samples))) ** 0.5
            finding, quality = ("unusable", 0.1) if rms < 30 else ("normal", 0.9)
        result = {"point": point, "finding": finding, "confidence": 0.5, "quality": quality,
                  "model_version": self.version, "latency_ms": 1, **({"demo": True} if demo else {})}
        self.sessions.setdefault(session_id, {})[point] = result
        return result

    def summary(self, session_id):
        points = self.sessions.get(session_id)
        if not points:
            raise self.Error(404, f"No recordings for session '{session_id}'.")
        return {"session_id": session_id, "points_recorded": len(points), "overall": "normal", "confidence": 0.5,
                "per_point": [{"point": p, **{k: r[k] for k in ("finding", "confidence")}} for p, r in points.items()],
                "disclaimer": "Screening aid only. Not a diagnosis. Consult a doctor."}


backend = ai or FakeAI()
Error = ai.ServiceError if ai else FakeAI.Error


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css",
                      ".ogg": "audio/ogg", ".wav": "audio/wav", ".json": "application/json"}

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/demo_clips/"):
            return str(DEMO_CLIPS / path[len("/demo_clips/"):])
        return str(APP / path.lstrip("/"))

    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            if self.path == "/health":
                return self.send_json(200, backend.health())
            if self.path.startswith("/session/") and self.path.endswith("/summary"):
                return self.send_json(200, backend.summary(self.path.split("/")[2]))
        except Error as e:
            return self.send_json(e.status, {"error": e.message})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/analyze":
            return self.send_json(404, {"error": "Not found."})
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        form = email.message_from_bytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body,
                                        policy=policy.HTTP)
        fields, audio = {}, None
        for part in form.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name == "audio":
                audio = part.get_payload(decode=True)
            else:
                fields[name] = part.get_content().strip()
        try:
            result = backend.analyze(fields.get("point"), fields.get("session_id"), audio,
                                     fields.get("demo") == "true", fields.get("demo_case"))
            self.send_json(200, result)
        except Error as e:
            self.send_json(e.status, {"error": e.message})

    def log_message(self, fmt, *args):
        if "/analyze" in self.requestline or "/health" in self.requestline:
            print(self.requestline.split(" HTTP")[0], args[1] if len(args) > 1 else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 lets a phone on the same network connect")
    args = parser.parse_args()
    print(f"AI: {'the real AI code in ai/' if ai else 'FAKE answers (' + AI_PROBLEM + ')'}")
    print(f"App: http://localhost:{args.port}/   fake device: http://localhost:{args.port}/?fakebt&wav=crackles.wav")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
