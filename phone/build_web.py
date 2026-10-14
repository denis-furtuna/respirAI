"""Puts the web app together for shipping: app/ without its tests and dev tools, plus ONNX Runtime Web from npm.

    python phone/build_web.py phone/www          for the Android app (Capacitor's webDir; then the plugins bundle)
    python phone/build_web.py site --pages       for GitHub Pages (also: .nojekyll)

Run after `npm install` in phone/. The app's own files are copied as they are: nothing is rewritten.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
ORT = ROOT / "phone" / "node_modules" / "onnxruntime-web"
ORT_FILES = ["ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"]   # the plain WebAssembly build
SKIP = {"tests", "dev", "__pycache__", "vendor", "native"}   # vendor/ and native/ are made here and by esbuild


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--pages", action="store_true", help="a GitHub Pages site")
    args = parser.parse_args()
    out = args.out.resolve()
    if out == APP or APP in out.parents:
        sys.exit("The output can't be inside app/.")

    # ONNX Runtime Web: the version the worker asks for, or the build stops here.
    want = re.search(r'ORT_VERSION = "([^"]+)"', (APP / "ai" / "worker.js").read_text(encoding="utf-8")).group(1)
    have = json.loads((ORT / "package.json").read_text(encoding="utf-8"))["version"]
    if want != have:
        sys.exit(f"app/ai/worker.js wants onnxruntime-web {want}, phone/package.json installs {have}: make them the same.")

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(APP, out, ignore=lambda folder, names: [n for n in names if n in SKIP and Path(folder) == APP or n == "__pycache__"])
    vendor = out / "vendor" / "onnxruntime-web"
    vendor.mkdir(parents=True)
    for name in ORT_FILES:
        shutil.copy2(ORT / "dist" / name, vendor / name)
    for name in ["LICENSE", "ThirdPartyNotices.txt"]:   # MIT; shipped with the copy
        if (ORT / name).exists():
            shutil.copy2(ORT / name, vendor / name)
    if args.pages:
        (out / ".nojekyll").write_text("")   # serve every file as it is
    model = "model: " + ("yes" if (out / "model" / "resp_cnn.onnx").exists() else "none (dummy answers)")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) // 1024
    print(f"{out}: {size} KB, onnxruntime-web {have}, {model}")


if __name__ == "__main__":
    main()
