"""Builds the respirAI carrier board: places every part, names every net, draws the outline and the ground fills.

    D:/KiCad/bin/python.exe pcb/generate.py            -> pcb/respirai-carrier.kicad_pcb (unrouted) and .dsn for the router

Run with KiCad's own Python (it has the pcbnew module). Routing is a separate step (route.py). Positions are in mm, in
KiCad's frame: x to the right, y towards the FRONT of the puck (the front wall, with the switch, is y = 85). The board
sits right under the lid on the case's four corner posts: the LEDs are on top, everything else hangs underneath.
Pins: firmware/respirai/config.h and docs/ADDONS.md. The XIAO's pin numbers: Seeed's XIAO-ESP32-S3-DIP footprint.
"""
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
KICAD_FP = Path("D:/KiCad/share/kicad/footprints")
OUT = HERE / "respirai-carrier.kicad_pcb"
mm = pcbnew.FromMM

# ---------- board ----------
BOARD = (2.5, 2.5, 97.5, 82.5)        # inside the 100 x 85 mm case, 2 mm walls, 0.5 mm clearance
CORNER = 6.0
HOLES = [(8, 8), (92, 8), (8, 77), (92, 77)]   # the case's M3 posts (docs/ENCLOSURE.md): the lid screws go through

# ---------- nets: the whole circuit ----------
# XIAO pin -> net. 1-7 = D0-D6, 8-11 = D7-D10, 12 = 3V3, 13 = GND, 14 = 5V (unused: the board runs from the LiPo).
XIAO_NETS = {
    "1": "ECG_OUT", "2": "BAT_SENSE", "3": "ECG_LO+", "4": "LED_AI", "5": "I2C_SDA", "6": "I2C_SCL", "7": "LED_TRACHEA",
    "8": "LED_LOBES", "9": "MIC_SCK", "10": "MIC_WS", "11": "MIC_SD", "12": "3V3", "13": "GND",
}

# ref, library, footprint, value, (x, y), rotation, side, {pad: net}, label
PARTS = [
    ("U1", None, "XIAO_ESP32S3_THT", "XIAO ESP32-S3", (15.0, 30.0), 0, "bottom", XIAO_NETS, None),

    # LEDs, on top under the lung panel. Pad 1 = cathode (short leg, flat side), pad 2 = anode (long leg).
    ("D1", "LED_THT", "LED_D3.0mm", "AI", (64.73, 78.0), 0, "top", {"1": "GND", "2": "AI_A"}, "AI"),
    ("D2", "LED_THT", "LED_D3.0mm", "trachea", (48.73, 27.0), 0, "top", {"1": "GND", "2": "TRACHEA_A"}, "trachea"),
    ("D3", "LED_THT", "LED_D3.0mm", "lobe L", (36.73, 45.0), 0, "top", {"1": "GND", "2": "LOBE_L_A"}, "lobe"),
    ("D4", "LED_THT", "LED_D3.0mm", "lobe R", (60.73, 45.0), 0, "top", {"1": "GND", "2": "LOBE_R_A"}, "lobe"),

    # Resistors underneath, along the rear edge (no battery under there). 47-100 ohm for the LEDs: one each.
    ("R1", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "100", (21.0, 6.5), 0, "bottom", {"1": "LED_AI", "2": "AI_A"}, "AI"),
    ("R2", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "100", (31.0, 6.5), 0, "bottom", {"1": "LED_TRACHEA", "2": "TRACHEA_A"}, "trachea"),
    ("R3", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "100", (41.0, 6.5), 0, "bottom", {"1": "LED_LOBES", "2": "LOBE_L_A"}, "lobe L"),
    ("R4", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "100", (51.0, 6.5), 0, "bottom", {"1": "LED_LOBES", "2": "LOBE_R_A"}, "lobe R"),
    # Battery level: BAT+ (after the switch) / 2 into D1, steadied by C1.
    ("R5", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "100k", (61.0, 6.5), 0, "bottom", {"1": "VBAT", "2": "BAT_SENSE"}, "100k"),
    ("R6", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "100k", (71.0, 6.5), 0, "bottom", {"1": "BAT_SENSE", "2": "GND"}, "100k"),
    ("C1", "Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", "100n", (78.0, 6.5), 0, "bottom", {"1": "BAT_SENSE", "2": "GND"}, "100n"),

    # Plugs (JST PH, 2.0 mm), underneath. The mic hangs down into its pocket; the others go to the walls.
    ("J2", "Connector_JST", "JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical", "MIC", (9.0, 44.0), 180, "bottom",
     {"1": "GND", "2": "3V3", "3": "MIC_SD", "4": "MIC_WS", "5": "MIC_SCK", "6": "GND"}, "MIC"),
    ("J1", "Connector_JST", "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", "BATTERY", (30.0, 78.5), 0, "bottom", {"1": "VBAT_IN", "2": "GND"}, "BATTERY"),
    ("J3", "Connector_JST", "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", "SWITCH", (44.0, 78.5), 0, "bottom", {"1": "VBAT_IN", "2": "VBAT"}, "SWITCH"),
    ("J4", "Connector_JST", "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical", "PULSE", (93.5, 22.0), 90, "bottom",
     {"1": "3V3", "2": "GND", "3": "I2C_SDA", "4": "I2C_SCL"}, "PULSE MAX30102"),
    ("J5", "Connector_JST", "JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical", "ECG", (93.5, 40.0), 90, "bottom",
     {"1": "GND", "2": "3V3", "3": "ECG_OUT", "4": "", "5": "ECG_LO+", "6": "3V3"}, "ECG AD8232"),

    # Two pads for the XIAO's BAT+ and BAT- (on its underside, facing this board): short wires, soldered before mounting.
    ("TP1", "TestPoint", "TestPoint_THTPad_D2.0mm_Drill1.0mm", "BAT+", (28.6, 26.5), 0, "bottom", {"1": "VBAT"}, "BAT+"),
    ("TP2", "TestPoint", "TestPoint_THTPad_D2.0mm_Drill1.0mm", "BAT-", (28.6, 33.5), 0, "bottom", {"1": "GND"}, "BAT-"),
]
for i, (x, y) in enumerate(HOLES, 1):
    PARTS.append((f"H{i}", "MountingHole", "MountingHole_3.2mm_M3", "M3", (x, y), 0, "top", {}, None))

POWER_NETS = {"GND", "3V3", "VBAT", "VBAT_IN"}


def load(lib, name):
    path = HERE / "respirai.pretty" if lib is None else KICAD_FP / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {lib}:{name}")
    return fp


def text(board, s, x, y, layer, size=1.0, angle=0, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetTextAngleDegrees(angle)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def outline(board):
    x0, y0, x1, y1 = BOARD
    r = CORNER

    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(start, mid, end):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(*(pcbnew.VECTOR2I(mm(p[0]), mm(p[1])) for p in (start, mid, end)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    k = r * (1 - 0.7071067811865476)
    seg((x0 + r, y0), (x1 - r, y0)); arc((x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r))
    seg((x1, y0 + r), (x1, y1 - r)); arc((x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1))
    seg((x1 - r, y1), (x0 + r, y1)); arc((x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r))
    seg((x0, y1 - r), (x0, y0 + r)); arc((x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0))


def ground_fill(board, gnd, layer):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(gnd)
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.4))
    z.SetThermalReliefSpokeWidth(mm(0.5))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # no floating copper scraps
    z.SetIsFilled(False)
    o = z.Outline()
    o.NewOutline()
    x0, y0, x1, y1 = BOARD
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        o.Append(mm(x), mm(y))
    board.Add(z)


def build():
    board = pcbnew.CreateEmptyBoard()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    # JLCPCB's standard 2-layer process allows much less; these leave room for hand soldering and DIY repairs.
    ds.m_TrackMinWidth = mm(0.2)
    ds.m_ViasMinSize = mm(0.6)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.4)
    ds.m_MinClearance = mm(0.2)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(0.25))
    nc.SetTrackWidth(mm(0.3))
    nc.SetViaDiameter(mm(0.7))
    nc.SetViaDrill(mm(0.35))

    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    for ref, lib, name, value, (x, y), rot, side, padnets, label in PARTS:
        fp = load(lib, name)
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.Reference().SetVisible(ref.startswith(("U", "D")))   # the others get a label that says what they are
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        if side == "bottom":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for pad in fp.Pads():
            n = padnets.get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
            if n == "GND" and ref.startswith(("J", "TP")):
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # plugs get pulled: solid to the ground plane

    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        ground_fill(board, net("GND"), layer)
    outline(board)

    # Silkscreen: what goes where, on both sides.
    text(board, "respirAI", 50.0, 64.0, pcbnew.F_SilkS, 2.5, bold=True)
    text(board, "LEDs on this side, under the lung panel", 50.0, 68.0, pcbnew.F_SilkS, 1.0)
    text(board, "respirAI carrier v1 - bottom", 62.0, 70.0, pcbnew.B_SilkS, 1.5, bold=True)
    text(board, "measure battery polarity before plugging in", 62.0, 73.0, pcbnew.B_SilkS, 0.9)
    for ref, lib, name, value, (x, y), rot, side, padnets, label in PARTS:
        if not label or ref.startswith(("U", "D")):
            continue
        if ref.startswith("J") and rot == 90:
            text(board, f"{ref} {label}", x - 8.4, y - 3.0 if ref == "J4" else y - 5.0, pcbnew.B_SilkS, 0.9, angle=90)
        elif ref.startswith("J"):
            text(board, f"{ref} {label}", x + 5.0 if ref == "J2" else x - 1.0, y + 7.6 if ref == "J2" else y - 4.6, pcbnew.B_SilkS, 0.9)
        elif ref.startswith("TP"):
            text(board, label, x + 3.0, y, pcbnew.B_SilkS, 0.9)
        else:
            text(board, f"{ref} {label}", x - 3.8, y - 2.6, pcbnew.B_SilkS, 0.8)
    text(board, "XIAO: USB-C to this edge", 15.0, 18.0, pcbnew.B_SilkS, 0.9)
    # One name per plug pin, so a cable can be wired without the manual.
    for ref, names, dx, dy, angle in [("J2", ["GND", "3V3", "SD", "WS", "SCK", "L/R"], 0.0, 4.2, 90),
                                      ("J4", ["3V3", "GND", "SDA", "SCL"], -5.6, 0.0, 0),
                                      ("J5", ["GND", "3V3", "OUT", "LO-", "LO+", "SDN"], -5.6, 0.0, 0),
                                      ("J1", ["+", "-"], 0.0, -2.9, 0)]:
        fp = board.FindFootprintByReference(ref)
        for pad in fp.Pads():
            pos = pad.GetPosition()
            text(board, names[int(pad.GetNumber()) - 1], pcbnew.ToMM(pos.x) + dx, pcbnew.ToMM(pos.y) + dy, pcbnew.B_SilkS, 0.8, angle=angle)
    return board, nets


if __name__ == "__main__":
    board, nets = build()
    board.SetFileName(str(OUT))
    pcbnew.SaveBoard(str(OUT), board)
    print(f"{OUT.name}: {len(list(board.GetFootprints()))} parts, {len(nets)} nets")
