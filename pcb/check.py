"""Checks the routed board against what the firmware expects, independently of how generate.py named the nets.

    D:/KiCad/bin/python.exe pcb/check.py

DRC proves the copper matches the board's own netlist; this proves the netlist is the right circuit: every XIAO pin
reaches the part the firmware (firmware/respirai/config.h) and docs/ADDONS.md say it drives. Exits 1 on any mismatch.
"""
import re
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
board = pcbnew.LoadBoard(str(HERE / "respirai-carrier.kicad_pcb"))
problems = []


def pads_on(netname):
    return {(p.GetParentFootprint().GetReference(), p.GetNumber()) for p in board.GetPads() if p.GetNetname() == netname}


def net_of(ref, pad):
    p = board.FindFootprintByReference(ref).FindPadByNumber(pad)
    return p.GetNetname()


def expect(what, ok):
    print(("ok    " if ok else "WRONG ") + what)
    if not ok:
        problems.append(what)


# XIAO pin numbers -> D-names (Seeed's XIAO-ESP32-S3 symbol) and D-name -> GPIO (the XIAO ESP32-S3 pinout)
XIAO_PIN = {f"D{i}": str(i + 1) for i in range(11)} | {"3V3": "12", "GND": "13"}
GPIO = {"D0": 1, "D1": 2, "D2": 3, "D3": 4, "D4": 5, "D5": 6, "D6": 43, "D7": 44, "D8": 7, "D9": 8, "D10": 9}

# What the firmware drives, read from config.h itself (so a pin change there shows up here)
cfg = (ROOT / "firmware" / "respirai" / "config.h").read_text(encoding="utf-8") if (ROOT / "firmware").exists() else ""
fw = {k: int(v) for k, v in re.findall(r"constexpr int (PIN_\w+)\s*=\s*(-?\d+)", cfg)}
by_gpio = {g: d for d, g in GPIO.items()}
if fw:
    for name, gpio in fw.items():
        if gpio >= 0:
            print(f"      config.h {name} = GPIO {gpio} = {by_gpio.get(gpio, '?')}")

# The circuit, as (XIAO D-pin, the other end it must reach)
want = [
    ("D8", ("J2", "5"), "mic SCK"), ("D9", ("J2", "4"), "mic WS"), ("D10", ("J2", "3"), "mic SD"),
    ("D3", ("R1", "1"), "AI LED resistor"), ("D6", ("R2", "1"), "trachea LED resistor"),
    ("D7", ("R3", "1"), "left lobe resistor"), ("D7", ("R4", "1"), "right lobe resistor"),
    ("D1", ("R5", "2"), "battery divider"), ("D0", ("J5", "3"), "ECG OUT"), ("D2", ("J5", "5"), "ECG LO+"),
    ("D4", ("J4", "3"), "pulse SDA"), ("D5", ("J4", "4"), "pulse SCL"),
]
for d, (ref, pad), what in want:
    expect(f"{d} -> {ref}.{pad} ({what})", (ref, pad) in pads_on(net_of("U1", XIAO_PIN[d])))

# The firmware's own pins land where this board puts them
if fw:
    for key, d in [("PIN_MIC_SCK", "D8"), ("PIN_MIC_WS", "D9"), ("PIN_MIC_SD", "D10"), ("PIN_LED_AI", "D3"),
                   ("PIN_LED_TRACHEA", "D6"), ("PIN_LED_LOBES", "D7")]:
        expect(f"config.h {key} is {d} (GPIO {GPIO[d]})", fw.get(key) == GPIO[d])

# Each resistor feeds the right LED's anode (pad 2 = anode); every LED cathode and the mic's L/R go to ground
for r, led in [("R1", "D1"), ("R2", "D2"), ("R3", "D3"), ("R4", "D4")]:
    expect(f"{r} -> {led} anode", (led, "2") in pads_on(net_of(r, "2")))
    expect(f"{led} cathode on GND", net_of(led, "1") == "GND")
gnd = pads_on("GND")
for ref, pad, what in [("J2", "1", "mic GND"), ("J2", "6", "mic L/R"), ("U1", "13", "XIAO GND"), ("TP2", "1", "BAT-"),
                       ("J1", "2", "battery -"), ("J4", "2", "pulse GND"), ("J5", "1", "ECG GND"), ("R6", "2", "divider"),
                       ("C1", "2", "divider cap")]:
    expect(f"{ref}.{pad} on GND ({what})", (ref, pad) in gnd)
v33 = pads_on(net_of("U1", "12"))
for ref, pad, what in [("J2", "2", "mic VDD"), ("J4", "1", "pulse VIN"), ("J5", "2", "ECG 3V3"), ("J5", "6", "ECG SDN high")]:
    expect(f"{ref}.{pad} on 3V3 ({what})", (ref, pad) in v33)

# Power path: battery + -> switch -> BAT+ pad and divider top; 5V pin unused
expect("battery + -> switch", ("J3", "1") in pads_on(net_of("J1", "1")))
expect("switch -> BAT+ pad", ("TP1", "1") in pads_on(net_of("J3", "2")))
expect("switch -> divider top", ("R5", "1") in pads_on(net_of("J3", "2")))
expect("battery never reaches 3V3 or a GPIO directly", net_of("J1", "1") not in {net_of("U1", str(i)) for i in range(1, 13)})
expect("XIAO 5V pin left unconnected", net_of("U1", "14") == "")

# Every net with a name reaches at least two pads, and the copper really connects them
conn = board.GetConnectivity()
conn.RecalculateRatsnest()
expect("no unrouted connections", conn.GetUnconnectedCount(True) == 0)
for n in {p.GetNetname() for p in board.GetPads() if p.GetNetname()}:
    expect(f"net {n} has 2+ pads", len(pads_on(n)) >= 2) if len(pads_on(n)) < 2 else None

print(f"\n{'ALL GOOD' if not problems else f'{len(problems)} PROBLEMS'}")
sys.exit(1 if problems else 0)
