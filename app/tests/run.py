"""Runs the app's browser tests in headless Chrome. Plain Python, nothing to install.

    python app/tests/run.py                    all suites, each against a fresh stub AI server
    python app/tests/run.py flow languages     only these suites
    python app/tests/run.py --real http://localhost:8000
                                               a whole check against a real AI server (ai/server.py or
                                               app/dev/dev_server.py), which must serve the app at that address

Each suite is a page in this folder that drives the real app in an iframe and writes PASS/FAIL lines.
The `ai` suite needs files made on GitHub (see make_golden.py and .github/workflows/web-app.yml); without them it is skipped.
Chrome is found automatically, or set CHROME to its path. Exits with 1 if anything failed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html import unescape
from pathlib import Path

import stub_server

HERE = Path(__file__).resolve().parent
SUITES = ["flow", "bluetooth", "no-audio", "languages", "on-phone", "native", "ai"]   # against the stub; real-server.html needs --real
# ai.html needs files made on GitHub (make_golden.py needs NumPy, SciPy, ONNX; ONNX Runtime Web comes from npm):
AI_FILES = [HERE / "golden" / "golden.json", HERE.parent / "vendor" / "onnxruntime-web" / "ort.wasm.min.mjs"]
CHROMES = [
    os.environ.get("CHROME"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
]


def chrome():
    for path in CHROMES:
        if path and Path(path).exists():
            return path
    sys.exit("Chrome not found. Set CHROME to its path.")


def run_page(url):
    """Opens the page headless; virtual time lets a 7-place check finish in seconds. Returns its PASS/FAIL lines."""
    with tempfile.TemporaryDirectory() as profile:
        ci = ["--no-sandbox"] if os.environ.get("CI") else []   # GitHub's Ubuntu VMs can't give Chrome its sandbox; never on a real machine
        out = subprocess.run([chrome(), *ci, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                              "--autoplay-policy=no-user-gesture-required", "--virtual-time-budget=400000", "--dump-dom", url],
                             capture_output=True, text=True, encoding="utf-8", timeout=600).stdout
    found = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    text = unescape(found.group(1)) if found else "FAIL the page did not load"
    return text if "DONE" in text else text + "\nFAIL the page stopped before the end (a script error?)"


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # check names have arrows; a Windows console would refuse them
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("suites", nargs="*", default=SUITES, help=f"any of: {', '.join(SUITES)}")
    parser.add_argument("--real", metavar="URL", help="test a real AI server that serves the app at URL")
    args = parser.parse_args()

    runs = [("real-server", f"{args.real.rstrip('/')}/tests/real-server.html")] if args.real else []
    failed = 0
    for name in [] if args.real else args.suites:
        if name == "ai" and not all(f.exists() for f in AI_FILES):
            if os.environ.get("CI"):   # on GitHub the workflow makes them: missing is a failure, not a skip
                failed += 1
                print("ai: FAILED, missing " + ", ".join(str(f) for f in AI_FILES if not f.exists()))
            else:
                print("ai: skipped (its files are made on GitHub; see make_golden.py)")
            continue
        stub = stub_server.start()
        runs.append((name, f"http://127.0.0.1:{stub.server_port}/tests/{name}.html"))

    for name, url in runs:
        run_page_lines = run_page(url).splitlines()
        lines = [l for l in run_page_lines if l.startswith(("PASS", "FAIL"))]
        bad = [l for l in lines if l.startswith("FAIL")]
        failed += len(bad)
        print(f"{name}: {len(lines) - len(bad)} passed, {len(bad)} failed")
        for line in bad + [l for l in run_page_lines if l.startswith("INFO")]:
            print("   ", line)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
