"""Runs the built app in an Android emulator (on GitHub, see phone-app.yml) and checks it from inside its WebView.

    python phone/emulator_check.py APK          needs adb, a running emulator, and pip websocket-client + Pillow

Installs the test APK, starts it, connects to the WebView through Chrome DevTools (debug builds allow it) and checks
what the browser tests can't: the app starts, its plugins load (native.js), the page keeps clear of Android's bars,
the AI worker answers on the phone, a whole practice check reaches its results, the share sheet opens with the
recordings, and nothing is logged as an error. Small screenshots go into the run's notices.
Exits with 1 if anything failed.
"""
import base64
import io
import json
import re
import subprocess
import sys
import time
import urllib.request

import websocket
from PIL import Image

PKG = "ro.respirai.app"
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name} {extra}", flush=True)
    if not ok:
        print(f"::error title={name}::{str(extra)[:900] or 'failed'}", flush=True)


def adb(*args):
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=120).stdout


def screenshot(title):   # small, in pieces: GitHub keeps 4096 characters of a notice, and 10 notices per step
    png = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=60).stdout
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = img.resize((180, int(180 * img.height / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=50)
    data = base64.b64encode(buf.getvalue()).decode()
    parts = [data[i:i + 4000] for i in range(0, len(data), 4000)]
    for i, part in enumerate(parts):
        print(f"::notice title=screenshot {title} {i + 1}/{len(parts)}::{part}", flush=True)


class Page:
    def __init__(self):
        for _ in range(90):
            sockets = re.findall(r"@(webview_devtools_remote_\d+)", adb("shell", "cat", "/proc/net/unix"))
            if sockets:
                break
            time.sleep(1)
        else:
            raise RuntimeError("The app's WebView never appeared.")
        adb("forward", "tcp:9222", f"localabstract:{sockets[0]}")
        for _ in range(30):
            try:
                pages = [p for p in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)) if p["type"] == "page"]
                if pages:
                    break
            except OSError:
                pass
            time.sleep(1)
        print("WebView page:", pages[0]["url"], flush=True)
        self.ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self.n = 0

    def js(self, expression):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": "Runtime.evaluate",
                                 "params": {"expression": expression, "awaitPromise": True, "returnByValue": True}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.n:
                result = message["result"]
                if "exceptionDetails" in result:
                    raise RuntimeError(json.dumps(result["exceptionDetails"])[:500])
                return result["result"].get("value")

    def until(self, expression, seconds, step=0.5):
        end = time.time() + seconds
        while time.time() < end:
            value = self.js(expression)
            if value:
                return value
            time.sleep(step)
        return None

    def ready(self):
        return self.until("document.readyState === 'complete' && !document.documentElement.classList.contains('loading')", 60)


def main(apk):
    print(adb("install", "-r", apk).strip())
    adb("shell", "svc", "power", "stayon", "true")
    adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    adb("shell", "wm", "dismiss-keyguard")
    adb("logcat", "-c")
    adb("shell", "am", "start", "-W", "-n", f"{PKG}/.MainActivity")
    page = Page()
    check("the app starts and its page loads", bool(page.ready()))
    check("runs as the phone app (Capacitor, native platform)", page.js("!!window.Capacitor && Capacitor.isNativePlatform()") is True)
    check("first start: the welcome screen", page.js("!document.getElementById('sWelcome').hidden") is True)
    check("phone features loaded (native.js: the team's server field is hidden)",
          page.js("document.getElementById('server').closest('label').hidden") is True)
    # Clear of the status bar: either the page pads itself (env(safe-area-inset-*), WebView 140+) or Android places
    # the WebView below the bar (older WebViews). Edge to edge with no padding would be wrong.
    view = json.loads(page.js("JSON.stringify({ pad: parseFloat(getComputedStyle(document.body).paddingTop), inner: innerHeight, "
                              "screen: screen.height, ua: navigator.userAgent })"))
    check("the page keeps clear of the status bar", view["pad"] > 0 or view["inner"] < view["screen"] - 20, json.dumps(view))
    time.sleep(1)
    screenshot("welcome")

    page.js("localStorage.setItem('respirai', JSON.stringify({ seconds: 5, welcomed: true, lang: 'en' })); location.reload(); true")
    time.sleep(2)
    page.ready()
    page.js("document.getElementById('btnTest').click(); true")
    test = page.until("(t => /Checking|^$/.test(t) ? null : t)(document.getElementById('testResult').textContent)", 30)
    check("Test: the AI on the phone answers", test == "OK · model dummy-0.0 (dummy answers) · 0 demo clips", repr(test))

    page.js("document.getElementById('btnPractice').click(); true")
    check("practice device connects -> ready screen", bool(page.until("!document.getElementById('sReady').hidden", 20)))
    time.sleep(1)
    page.js("document.getElementById('btnBegin').click(); true")
    page.until("!document.getElementById('sPoint').hidden && document.getElementById('btnNow').hidden === false", 10)
    page.js("document.getElementById('btnNow').click(); true")
    time.sleep(4)
    clicker = ("(() => { const $ = (i) => document.getElementById(i);"
               " if (!$('sPoint').hidden && !$('btnNow').hidden) $('btnNow').click();"
               " return !$('sResults').hidden && !document.querySelector('#resultList li.todo'); })()")
    check("a whole practice check reaches the results", bool(page.until(clicker, 300, step=1)))
    rows = page.js("[...document.querySelectorAll('#resultList li')].map(li => li.className + ':' + li.querySelector('.chip').textContent).join(' | ')")
    check("7 places, all analysed on the phone", rows is not None and rows.count("ok:Clear") == 7, rows)
    screenshot("results")

    page.js("document.getElementById('btnShare').click(); true")
    shared = False
    for _ in range(20):
        time.sleep(1)
        if re.search(r"ChooserActivity|ResolverActivity|intentresolver", adb("shell", "dumpsys", "activity", "activities"), re.I):
            shared = True
            break
    check("Send to a doctor: Android's share sheet opens with the recordings", shared)
    adb("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(1)

    adb("shell", "cmd", "uimode", "night", "yes")
    time.sleep(3)
    page.js("location.reload(); true")
    time.sleep(2)
    page.ready()
    check("dark mode follows the phone", page.until("document.documentElement.dataset.theme === 'dark'", 10) is True)
    screenshot("dark")
    adb("shell", "cmd", "uimode", "night", "no")

    log = adb("logcat", "-d", "-s", "Capacitor/Console:*", "Capacitor:*", "chromium:*")
    errors = [l for l in log.splitlines() if re.search(r"\bE (Capacitor|chromium)|Uncaught|TypeError|ReferenceError|SyntaxError", l)
              and "Unable to open asset URL: https://localhost/model/" not in l]   # no trained model yet: dummy mode, as intended
    check("no errors in the app's log", not errors, " | ".join(errors[:5]))
    print(f"{sum(results)} passed, {len(results) - sum(results)} failed")
    print(f"::notice title=Emulator check::{sum(results)} passed, {len(results) - sum(results)} failed", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main(sys.argv[1])
