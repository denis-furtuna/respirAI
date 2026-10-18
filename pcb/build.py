"""Rebuilds the carrier board from scratch: place, route, check, then the files for JLCPCB.

    python pcb/build.py

Needs KiCad 10 (default D:/KiCad, or set KICAD), Freerouting 2.x (set FREEROUTING_JAR) and a Java it runs on
(set JAVA; Freerouting 2.4 needs Java 25). Stops at the first step that fails; a board that fails DRC or check.py
never reaches fab/.
"""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KICAD = Path(os.environ.get("KICAD", "D:/KiCad"))
PY, CLI = KICAD / "bin" / "python.exe", KICAD / "bin" / "kicad-cli.exe"
PCB, BUILD, FAB = HERE / "respirai-carrier.kicad_pcb", HERE / "build", HERE / "fab"


def run(*args):
    print(">", " ".join(str(a) for a in args[:4]), "...")
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout[-3000:] + r.stderr[-3000:])
    return r.stdout


def main():
    java, jar = os.environ.get("JAVA", "java"), os.environ.get("FREEROUTING_JAR")
    if not jar:
        sys.exit("Set FREEROUTING_JAR to the Freerouting 2.x jar (github.com/freerouting/freerouting/releases).")
    BUILD.mkdir(exist_ok=True)
    FAB.mkdir(exist_ok=True)
    print(run(PY, HERE / "generate.py").strip())
    print(run(PY, HERE / "route.py", java, jar).strip().splitlines()[-1])
    print(run(PY, HERE / "check.py").strip().splitlines()[-1])

    run(CLI, "pcb", "drc", "--format", "json", "--severity-all", "--units", "mm", "-o", BUILD / "drc.json", PCB)
    report = json.loads((BUILD / "drc.json").read_text(encoding="utf-8"))
    issues = report["violations"] + report["unconnected_items"]
    if issues:
        sys.exit("DRC: " + "; ".join(f"{i['type']}: {i['description']}" for i in issues[:10]))
    print("DRC: 0 violations, 0 unconnected")

    gerbers = BUILD / "gerbers"
    for f in gerbers.glob("*"):
        f.unlink()
    run(CLI, "pcb", "export", "gerbers", "-l", "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts",
        "--no-x2", "--use-drill-file-origin", "-o", f"{gerbers}/", PCB)
    run(CLI, "pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm", "--excellon-separate-th",
        "-o", f"{gerbers}/", PCB)
    with zipfile.ZipFile(FAB / "respirai-carrier-jlcpcb.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gerbers.iterdir()):
            z.write(f, f.name)
    run(CLI, "pcb", "export", "pdf", "-l", "F.Cu,F.Silkscreen,Edge.Cuts", "--mode-single", "--include-border-title",
        "-o", FAB / "respirai-carrier-1to1-top.pdf", PCB)
    run(CLI, "pcb", "export", "pdf", "-l", "B.Cu,B.Silkscreen,Edge.Cuts", "--mirror", "--mode-single",
        "--include-border-title", "-o", FAB / "respirai-carrier-1to1-bottom.pdf", PCB)
    for side in ("top", "bottom"):
        run(CLI, "pcb", "render", "--side", side, "--width", "1600", "--height", "1400", "--quality", "basic",
            "--background", "opaque", "--zoom", "1.1", "-o", FAB / f"render-{side}.png", PCB)
    print(f"fab/: Gerbers zip, 1:1 PDFs, renders")


if __name__ == "__main__":
    main()
