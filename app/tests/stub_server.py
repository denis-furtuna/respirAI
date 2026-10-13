"""Test stand-in for the AI server: serves app/ (tests included) and fakes contract 2 with known answers.

    Al -> crackles, Lr -> unusable (quality 0.2), Pl -> 400 error, Ar -> 503 the first time (then normal),
    everything else -> normal; demo requests answer with their demo_case.

Every uploaded WAV is checked (header, 8 kHz mono 16-bit, sizes) and logged; GET /log returns the log.
Used by run.py; can also be started by hand:  python app/tests/stub_server.py 8001
"""
import email
import json
import struct
import sys
import threading
from email import policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".wav": "audio/wav",
                      ".webmanifest": "application/manifest+json"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"status": "ok", "model_version": "stub", "dummy": True, "demo_clips": 0})
        if self.path == "/log":
            return self.send_json(200, self.server.log)
        return super().do_GET()

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        msg = email.message_from_bytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body,
                                       policy=policy.HTTP)
        fields, wav = {}, None
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name == "audio":
                wav = part.get_payload(decode=True)
            else:
                fields[name] = part.get_content().strip()
        entry = dict(fields)
        if wav is not None:
            riff, size, wave, fmt, _, pcm, ch, sr, _, _, bits, data, dlen = struct.unpack("<4sI4s4sIHHIIHH4sI", wav[:44])
            entry.update(wav_ok=(riff, wave, fmt, data, pcm, ch, sr, bits) == (b"RIFF", b"WAVE", b"fmt ", b"data", 1, 1, 8000, 16)
                         and size == len(wav) - 8 and dlen == len(wav) - 44, seconds=round(dlen / 2 / 8000, 2))
        self.server.log.append(entry)
        point = fields["point"]
        if point == "Ar" and point not in self.server.failed_once:   # a server hiccup: the app should offer "Try again"
            self.server.failed_once.add(point)
            return self.send_json(503, {"error": "Stub overloaded"})
        if point == "Pl":   # a refused recording: the app should ask for a new one
            return self.send_json(400, {"error": "Stub error for Pl"})
        finding = fields.get("demo_case") or {"Al": "crackles", "Lr": "unusable"}.get(point, "normal")
        return self.send_json(200, {"point": point, "finding": finding, "confidence": 0.8,
                                    "quality": 0.2 if finding == "unusable" else 0.9, "model_version": "stub", "latency_ms": 5,
                                    **({"demo": True} if fields.get("demo") == "true" else {})})

    def log_message(self, *args):
        pass


def start(port=0):
    """A fresh stub (empty log) on `port` (0: any free port), in a background thread."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.log, server.failed_once = [], set()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    s = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8001)
    print(f"Stub AI server: http://127.0.0.1:{s.server_port}/tests/flow.html")
    threading.Event().wait()
