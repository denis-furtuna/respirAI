"""respirAI enclosure: the parametric model.

A hand-held "bar of soap" body in two halves that close sideways around the
stethoscope chest piece. Everything is driven by the numbers in the PARAMETERS
block; change one, run `python generate.py`, and `python check.py` says whether
the parts still fit.

Frame (mm)
    x  along the metal stem; the chest piece axis is x = 0, the stem points to +x
    y  across the body; the two halves meet on the plane y = 0
    z  depth behind the diaphragm: z = 0 is the face that touches the chest,
       the body lies at z > 0 (so the diaphragm looks toward -z)

Half A is the y > 0 side (XIAO and its USB-C port), half B the y < 0 side
(switch, screw heads). Each half prints lying on its outer side wall, with the
open side up, and needs no supports.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, Manifold, OpType
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient

# =============================================================== PARAMETERS ==
# --- measured with calipers: read from components.csv, never typed here ------
with open(Path(__file__).parent / "components.csv", newline="", encoding="utf-8") as _f:
    _M = {r["part"]: (float(r["w_mm"]), float(r["l_mm"]), float(r["h_mm"])) for r in csv.DictReader(_f)}

HEAD_BIG_D, _, HEAD_BIG_T = _M["chest_big_head"]        # diaphragm side, stays outside the body
HEAD_MID_D, _, HEAD_MID_T = _M["chest_waist"]           # the waist the body closes around
HEAD_SMALL_D, _, HEAD_SMALL_T = _M["chest_small_head"]  # bell side, inside the body
STEM_D, _, STEM_L = _M["chest_stem"]                    # metal stem; length from the waist surface to the tip
MIC_D, _, MIC_T = _M["mic_inmp441"]                     # round board
XIAO_W, XIAO_L, XIAO_STACK = _M["xiao_esp32s3"]         # stack: top of the USB socket to the bend of the Dupont wires
BAT_W, BAT_L, BAT_T = _M["lipo_2500"]
STEM_BORE = 3.0         # estimated by eye

# --- assumed, not measured yet: confirm before printing ----------------------
STEM_OFFSET = HEAD_MID_T / 2   # stem axis sits mid-way through the waist
XIAO_PCB_T = 1.6               # board thickness (slot is cut for up to this)
USB_W, USB_H = 8.94, 3.2       # USB-C socket shell
USB_OVERHANG = 1.4             # how far the socket sticks out past the board edge
USB_SHELL_L = 7.35
HEADER_PLASTIC = 2.5           # black spacer of a pin header
DUPONT_L = 14.0                # one Dupont housing
DUPONT_W = 2.6
MIC_PIN_ROWS = 10.0            # distance between the mic's two rows of three pins
MIC_ROW_L = 7.8                # length of one row of three Dupont housings
SWITCH_L, SWITCH_W, SWITCH_T = 8.6, 4.3, 4.0   # SIS-86434-G body
SWITCH_SLOT = (6.0, 3.0)       # opening for the slider
SCREW_D = 3.0                  # M3 x 12, pan or cap head
SCREW_LEN = 12.0
SCREW_HEAD_D = 5.6

# --- design choices ----------------------------------------------------------
WALL = 2.0
HEAD_GAP = 0.2          # between the back of the big head and the body
FIT = 0.25              # general clearance around a held part
STEM_CH_R = 4.2         # stem channel radius (room for the ribs at the tip)
MIC_GASKET = 0.5        # soft ring between the stem tip and the mic board
MIC_PAD = 1.0           # foam behind the mic board that presses it on the stem
EDGE_R_FRONT = 2.5      # rounding of the long edges, chest side
EDGE_R_BACK = 9.0       # ... palm side
EDGE_R_END = 6.0        # ... the two ends
SEGS = 24               # segments per quarter circle

# ------------------------------------------------------------------ derived --
Z_MID0 = HEAD_BIG_T                      # waist starts
Z_SMALL0 = Z_MID0 + HEAD_MID_T           # small head starts
Z_SMALL1 = Z_SMALL0 + HEAD_SMALL_T       # deepest point of the chest piece
Z_STEM = Z_MID0 + STEM_OFFSET            # stem axis depth
X_STEM_TIP = HEAD_MID_D / 2 + STEM_L

Z_FRONT = HEAD_BIG_T + HEAD_GAP          # outer face on the chest side
Z_FRONT_IN = Z_FRONT + WALL
Z_USB_TOP = Z_FRONT_IN + 0.4             # top of the USB shell
Z_XIAO = Z_USB_TOP + USB_H               # top face of the XIAO board
Z_BACK_IN = Z_USB_TOP + XIAO_STACK + 0.2
Z_BACK = Z_BACK_IN + WALL

X_MIN = -(HEAD_SMALL_D / 2 + 1.0 + WALL)
X_MIN_IN = X_MIN + WALL

# screw 1 sits between the head-end wall and the battery
SCREW_COL_R_A = 3.2     # column around a pilot hole
SCREW_COL_R_B = 4.2     # column around a head well
SCREW_WELL_R = 3.2
SCREW_PILOT_R = 1.35    # 2.7 mm: an M3 machine screw cuts its own thread in PLA
SCREW_CLEAR_R = 1.7
SCREW_SEAT_Y = -5.5     # where the screw head stops (half B)
S1 = (-12.5, 27.5)

BAT_X0 = S1[0] + SCREW_COL_R_B + 0.45
BAT_X1 = BAT_X0 + BAT_L
BAT_Z1 = Z_BACK_IN - 0.6                 # room to swell
BAT_Z0 = BAT_Z1 - BAT_T
BAT_STOP_X0 = BAT_X1 + 0.3
BAT_STOP_X1 = BAT_STOP_X0 + 1.6
LIP_Z0, LIP_Z1 = BAT_Z0 - 2.2, BAT_Z0 - 0.3

# mic block: a bulkhead across the body right at the stem tip
MIC_X0 = X_STEM_TIP + MIC_GASKET         # front (port) face of the board
MIC_POCKET_X0 = X_STEM_TIP - 0.2
MIC_POCKET_X1 = MIC_X0 + MIC_T + MIC_PAD + 0.2
MIC_POCKET_R = MIC_D / 2 + FIT
BULK_X0 = MIC_POCKET_X0 - 1.85
BULK_X1 = MIC_POCKET_X1 + 1.5
BULK_Z1 = Z_STEM + MIC_POCKET_R + 1.6
MIC_NOSE_R = MIC_POCKET_R + 1.6
S3 = (BULK_X0 + 3.1, BULK_Z1 + 3.5)

# XIAO: flat, top to the chest, USB through the side wall of half A
XIAO_X0 = BAT_STOP_X1 + 1.25             # board edge
XIAO_XC = XIAO_X0 + XIAO_W / 2
XIAO_X1 = XIAO_X0 + XIAO_W
X_MAX_IN = XIAO_X1 + FIT
X_MAX = X_MAX_IN + WALL

MIC_DUPONT_HALF_Y = MIC_PIN_ROWS / 2 + DUPONT_W / 2     # 6.3
XIAO_Y0 = MIC_DUPONT_HALF_Y + 1.0        # inner end of the board
XIAO_Y1 = XIAO_Y0 + XIAO_L               # USB end of the board
W_A = XIAO_Y1 + 1.05                     # 1 mm of wall left behind the board edge
W_B = BAT_W / 2 + 2.0 + WALL
Y_FLOOR_A = W_A - WALL
Y_FLOOR_B = -(W_B - WALL)
USB_MOUTH_Y = XIAO_Y1 + USB_OVERHANG     # ends a little proud of the wall

S4 = (XIAO_XC, Z_BACK_IN - 4.3)

SWITCH_C = (XIAO_XC, 21.5)

SIN45 = math.sin(math.radians(45))
EDGE_SIN = math.sin(math.radians(42))    # rounded edges start this steep on the bed
SHOULDER = math.radians(43)              # steepest lean of a surface printed over air


# ================================================================ geometry ==
def _contours(poly):
    polys = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    out = []
    for p in polys:
        p = orient(p, 1.0)
        out.append(np.asarray(p.exterior.coords)[:-1])
        out.extend(np.asarray(r.coords)[:-1] for r in p.interiors)
    return out


def xs(poly) -> CrossSection:
    return CrossSection(_contours(poly))


def prism_z(poly_xy, z0, z1) -> Manifold:
    return Manifold.extrude(xs(poly_xy), z1 - z0).translate([0, 0, z0])


def prism_y(poly_xz, y0, y1) -> Manifold:
    """Extrude a profile drawn in (x, z) along y."""
    m = Manifold.extrude(xs(poly_xz), y1 - y0)
    m = m.transform(np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0]], float))
    return m.translate([0, y1, 0])


def prism_x(poly_yz, x0, x1) -> Manifold:
    """Extrude a profile drawn in (y, z) along x."""
    m = Manifold.extrude(xs(poly_yz), x1 - x0)
    m = m.transform(np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0]], float))
    return m.translate([x0, 0, 0])


def disc(cx, cy, r):
    return Point(cx, cy).buffer(r, quad_segs=SEGS)


def cyl_x(r, x0, x1, y=0.0, z=0.0):
    return prism_x(disc(y, z, r), x0, x1)


def cyl_y(r, y0, y1, x=0.0, z=0.0):
    return prism_y(disc(x, z, r), y0, y1)


def cyl_z(r, z0, z1, x=0.0, y=0.0):
    return prism_z(disc(x, y, r), z0, z1)


def cube(x0, x1, y0, y1, z0, z1) -> Manifold:
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def union(parts) -> Manifold:
    parts = [p for p in parts if not p.is_empty()]
    return Manifold.batch_boolean(parts, OpType.Add) if parts else Manifold()


def hull(*parts) -> Manifold:
    return Manifold.batch_hull(list(parts))


def keep_y(m: Manifold, sign: int) -> Manifold:
    """The part of m on the y >= 0 (sign = +1) or y <= 0 (sign = -1) side."""
    return m.trim_by_plane([0, sign, 0], 0.0)


def rounded_rect(x0, x1, z0, z1, r_x0z0, r_x1z0, r_x1z1, r_x0z1):
    pts = []
    for cx, cz, r, a0 in (
        (x0 + r_x0z0, z0 + r_x0z0, r_x0z0, 180),
        (x1 - r_x1z0, z0 + r_x1z0, r_x1z0, 270),
        (x1 - r_x1z1, z1 - r_x1z1, r_x1z1, 0),
        (x0 + r_x0z1, z1 - r_x0z1, r_x0z1, 90),
    ):
        for a in np.linspace(a0, a0 + 90, SEGS + 1):
            pts.append((cx + r * math.cos(math.radians(a)), cz + r * math.sin(math.radians(a))))
    return Polygon(pts)


# The side view of the body. Both halves are this outline pulled sideways.
SILHOUETTE = rounded_rect(X_MIN, X_MAX, Z_FRONT, Z_BACK, 3.0, 3.0, 8.0, 9.0)
SILHOUETTE_IN = SILHOUETTE.buffer(-WALL, quad_segs=SEGS)


def edge_out(r, h):
    """How far the outline steps in, h mm above the print bed.

    The long edges are rounded, but the round starts at 45 degrees so the
    first layers never overhang more than a printer can bridge.
    """
    hc = r * EDGE_SIN
    return 0.0 if h >= hc else r - math.sqrt(r * r - (hc - h) ** 2)


def edge_in(r, h):
    """Same for the inside of the wall (h >= WALL), keeping WALL of plastic."""
    hc = r * EDGE_SIN
    if r <= WALL or h >= hc:
        return WALL
    return r - math.sqrt((r - WALL) ** 2 - (hc - h) ** 2)


def _ring(sign, width, h, inner):
    f = edge_in if inner else edge_out
    e_f, e_b, e_e = f(EDGE_R_FRONT, h), f(EDGE_R_BACK, h), f(EDGE_R_END, h)
    base = SILHOUETTE_IN if inner else SILHOUETTE
    poly = base.intersection(box(X_MIN + e_e, Z_FRONT + e_f, X_MAX - e_e, Z_BACK - e_b))
    xz = np.asarray(poly.exterior.coords)[:-1]
    y = np.full(len(xz), sign * (width - h))
    return np.column_stack([xz[:, 0], y, xz[:, 1]])


def half_shell(sign, width):
    """Outer solid and cavity of one half (sign +1 = A, -1 = B)."""
    hmax = EDGE_R_BACK * EDGE_SIN
    hs_out = list(np.linspace(0, hmax, 18)) + [width]
    hs_in = list(np.linspace(WALL, hmax, 16)) + [width + 2.0]
    outer = Manifold.hull_points(np.vstack([_ring(sign, width, h, False) for h in hs_out]))
    cavity = Manifold.hull_points(np.vstack([_ring(sign, width, h, True) for h in hs_in]))
    return outer, cavity


# ------------------------------------------------------------------ nose ----
def _nose_profiles():
    def shouldered(r):
        # a circle around the stem axis, with shoulders down to the wall so that
        # no part of it has to be printed over air
        yb = (r - math.cos(SHOULDER) * (Z_STEM - Z_FRONT_IN)) / math.sin(SHOULDER)
        return disc(0, Z_STEM, r).union(Polygon([(-yb, Z_FRONT_IN), (yb, Z_FRONT_IN), (0, Z_STEM)])).convex_hull

    stem = shouldered(STEM_CH_R + 1.6)
    mic = shouldered(MIC_NOSE_R)
    # cover over the Dupont housings behind the mic
    top = Z_STEM - MIC_ROW_L / 2 - 0.45 - 1.6
    half = MIC_DUPONT_HALF_Y + 0.5 + 1.6
    cover = Polygon([(-half, top), (half, top),
                     (half + Z_FRONT_IN - top, Z_FRONT_IN), (-half - (Z_FRONT_IN - top), Z_FRONT_IN)])
    return stem, mic, cover


def mic_dupont_cavity_profile():
    top = Z_STEM - MIC_ROW_L / 2 - 0.45
    half = MIC_DUPONT_HALF_Y + 0.5
    return Polygon([(-half, top), (half, top),
                    (half + Z_FRONT_IN - top, Z_FRONT_IN), (half + Z_FRONT_IN - top, Z_FRONT_IN + 0.2),
                    (-half - (Z_FRONT_IN - top), Z_FRONT_IN + 0.2), (-half - (Z_FRONT_IN - top), Z_FRONT_IN)])


MIC_DUPONT_X1 = MIC_X0 + MIC_T + HEADER_PLASTIC + DUPONT_L + 2.0
NOSE_X0 = HEAD_BIG_D / 2 + 0.5


def nose_outer() -> Manifold:
    """The ridge on the chest side that covers the stem, the mic and its plugs."""
    stem, mic, cover = _nose_profiles()
    t = 0.05
    parts = [
        prism_x(stem, NOSE_X0, BULK_X0 - 4.0),
        hull(prism_x(stem, BULK_X0 - 5.5, BULK_X0 - 5.5 + t), prism_x(mic, BULK_X0, BULK_X0 + t)),
        prism_x(mic, BULK_X0, BULK_X1),
        hull(prism_x(mic, BULK_X1 - t, BULK_X1), prism_x(cover, BULK_X1 + 4.5, BULK_X1 + 4.5 + t)),
        prism_x(cover, BULK_X1 + 4.5, MIC_DUPONT_X1 + 0.5),
        hull(prism_x(cover, MIC_DUPONT_X1 + 0.5 - t, MIC_DUPONT_X1 + 0.5),
             prism_x(box(-8, Z_FRONT_IN - t, 8, Z_FRONT_IN), MIC_DUPONT_X1 + 4.5, MIC_DUPONT_X1 + 4.5 + t)),
    ]
    # only the part outside the body and through its wall; inside, the bulkhead takes over
    return union(parts).trim_by_plane([0, 0, -1], -Z_FRONT_IN)


def nose_cuts() -> Manifold:
    win_y = MIC_DUPONT_HALF_Y + 0.3
    win_z = MIC_ROW_L / 2 + 0.4
    return union([
        cyl_x(STEM_CH_R, HEAD_MID_D / 2 - 2.0, MIC_POCKET_X0 + 0.01, 0, Z_STEM),      # stem channel
        cyl_x(MIC_POCKET_R, MIC_POCKET_X0, MIC_POCKET_X1, 0, Z_STEM),                  # mic pocket
        cube(MIC_X0 + MIC_T - 0.3, BULK_X1 + 0.01, -win_y, win_y, Z_STEM - win_z, Z_STEM + win_z),  # pins
        # under the big head the stem lies in a plain slot through the wall and the collar
        cube(HEAD_MID_D / 2 - 2.0, NOSE_X0 + 0.01, -STEM_CH_R, STEM_CH_R, Z_FRONT - 1.0, Z_SMALL0 + 0.01),
        prism_x(mic_dupont_cavity_profile(), BULK_X1, MIC_DUPONT_X1),
    ])


# --------------------------------------------------------------- features ---
def _common_features(sign, y_floor):
    """Ribs and bosses that both halves have (mirrored)."""
    def span(poly, y_in):  # from the half's floor to y_in, a little into the floor
        a, b = sorted((sign * y_in, y_floor + sign * 0.6))
        return prism_y(poly, a, b)

    f = []
    # collar around the waist of the chest piece; teardrop so it prints without support
    r_o = HEAD_MID_D / 2 + 0.35 + 3.0
    tear = disc(0, 0, r_o).union(Polygon([(-r_o * SIN45, sign * r_o * SIN45), (r_o * SIN45, sign * r_o * SIN45),
                                          (0, sign * r_o * math.sqrt(2))]))
    tear = tear.intersection(box(-r_o, -1.2 * r_o, r_o, 1.2 * r_o))     # blunt tip
    f.append(prism_z(tear, Z_FRONT_IN - 0.1, Z_SMALL0 - 0.3))
    # mic bulkhead
    f.append(span(box(BULK_X0, Z_FRONT_IN - 0.1, BULK_X1, BULK_Z1), 0.0))
    # screw columns 1 and 3
    r = SCREW_COL_R_A if sign > 0 else SCREW_COL_R_B
    for cx, cz in (S1, S3):
        f.append(span(disc(cx, cz, r), 0.0))
    # ... each tied to the nearest wall, so no hairline slit is left beside it
    f.append(span(box(X_MIN_IN - 0.3, S1[1] - r, S1[0], S1[1] + r), 0.0))
    f.append(span(box(S3[0] - r, BULK_Z1 - 0.1, S3[0] + r, S3[1]), 0.0))
    f.append(span(box(S3[0] - r, S3[1], S3[0] + r, LIP_Z1), 9.0))
    # battery: lips in front of it, a stop at the tail end; open in the middle for its wires
    f.append(span(box(S1[0] + 1.5, LIP_Z0, BAT_X0 + 6.0, LIP_Z1), 9.0))
    f.append(span(box(BAT_X1 - 6.5, LIP_Z0, BAT_STOP_X1, LIP_Z1), 9.0))
    f.append(span(box(BAT_STOP_X0, LIP_Z0, BAT_STOP_X1, Z_BACK_IN + 0.3), 9.0))
    # pads that centre the battery sideways
    for x in (BAT_X0 + 16, BAT_X1 - 19):
        f.append(span(box(x, BAT_Z0 + 1.0, x + 3.0, Z_BACK_IN + 0.3), BAT_W / 2 + 0.3))
    return f


def usb_shell_profile():
    """Outline of the USB-C socket shell, seen along the plug direction, in (x, z)."""
    r = 1.2
    return box(XIAO_XC - USB_W / 2 + r, Z_USB_TOP + r, XIAO_XC + USB_W / 2 - r, Z_XIAO - r).buffer(r, quad_segs=8)


def build():
    """Return (parts, references): printable halves and the things they hold."""
    out_a, cav_a = half_shell(+1, W_A)
    out_b, cav_b = half_shell(-1, W_B)
    nose = nose_outer()
    cuts = nose_cuts()
    collar_hole = cyl_z(HEAD_MID_D / 2 + 0.35, Z_FRONT - 2.0, Z_SMALL0, 0, 0)

    # ---------------------------------------------------------- half A -----
    fa = _common_features(+1, Y_FLOOR_A)
    # XIAO channel: two walls with a 0.6 mm step the board's top face rests on
    y_in = XIAO_Y0 + 1.6            # leaves room for the stop rib of half B
    ch_z1 = Z_XIAO + XIAO_PCB_T + HEADER_PLASTIC + 0.4
    step_z1 = Z_XIAO - 0.1
    fa.append(prism_y(box(XIAO_X0 - FIT - 1.5, Z_FRONT_IN - 0.1, XIAO_X0 - FIT, ch_z1), y_in, Y_FLOOR_A + 0.6))
    fa.append(prism_y(box(XIAO_X0 - FIT - 0.1, Z_FRONT_IN - 0.1, XIAO_X0 + 0.6, step_z1), y_in, Y_FLOOR_A + 0.6))
    fa.append(prism_y(box(XIAO_X1 - 0.6, Z_FRONT_IN - 0.1, X_MAX_IN + 0.3, step_z1), y_in, Y_FLOOR_A + 0.6))
    # screw 4: a corbel on the back wall, between the XIAO's two pin rows
    corbel_z0 = S4[1] - 3.5
    corbel = Polygon([(0, corbel_z0), (10, corbel_z0), (10 + Z_BACK_IN + 0.3 - corbel_z0, Z_BACK_IN + 0.3),
                      (0, Z_BACK_IN + 0.3)])
    fa.append(prism_x(corbel, S4[0] - 3.4, S4[0] + 3.4))

    a = (out_a - cav_a) + (union(fa) ^ out_a) + keep_y(nose, +1)
    a = keep_y(a, +1)
    # tongue that keys into half B along the seam
    seam_gap = box(X_MIN_IN - 1.0 + 3.4, 0, X_MAX_IN - 3.0, Z_FRONT_IN + 1.4)
    tongue = SILHOUETTE.buffer(-1.15, quad_segs=SEGS).difference(SILHOUETTE.buffer(-WALL, quad_segs=SEGS))
    a += prism_y(tongue.difference(seam_gap.buffer(0.5)), -1.6, 0.0)

    cut_a = [cuts, collar_hole]
    for cx, cz in (S1, S3, S4):
        cut_a.append(cyl_y(SCREW_PILOT_R, -2.0, SCREW_SEAT_Y + SCREW_LEN + 2.0, cx, cz))
    # the board's USB edge sits in a shallow slot in the side wall
    # (it starts a little above the floor to clear the rounded inside corner)
    cut_a.append(cube(XIAO_X0 - FIT, XIAO_X1 + FIT, Y_FLOOR_A - 2.0, XIAO_Y1 + 0.05,
                      Z_XIAO - 0.2, Z_XIAO + XIAO_PCB_T + 0.3))
    cut_a.append(prism_y(usb_shell_profile().buffer(0.3, quad_segs=8), Y_FLOOR_A - 0.01, W_A + 1.0))
    a -= union(cut_a)

    # ---------------------------------------------------------- half B -----
    fb = _common_features(-1, Y_FLOOR_B)
    fb.append(prism_y(disc(S4[0], S4[1], SCREW_COL_R_B), Y_FLOOR_B - 0.6, 0.0))
    fb.append(prism_y(box(S4[0] - SCREW_COL_R_B, S4[1], S4[0] + SCREW_COL_R_B, Z_BACK_IN + 0.3), Y_FLOOR_B - 0.6, 0.0))
    # switch pocket on the side wall
    sx, sz = SWITCH_C
    pocket_out = box(sx - SWITCH_L / 2 - 1.35, sz - SWITCH_W / 2 - 1.35, sx + SWITCH_L / 2 + 1.35, sz + SWITCH_W / 2 + 1.35)
    pocket_in = box(sx - SWITCH_L / 2 - 0.15, sz - SWITCH_W / 2 - 0.15, sx + SWITCH_L / 2 + 0.15, sz + SWITCH_W / 2 + 0.15)
    fb.append(prism_y(pocket_out.difference(pocket_in), Y_FLOOR_B - 0.6, Y_FLOOR_B + 3.5))

    b = (out_b - cav_b) + (union(fb) ^ out_b) + keep_y(nose, -1)
    b = keep_y(b, -1)
    # stop rib: reaches across the seam and holds the inner end of the XIAO board,
    # so pushing a USB plug in cannot slide the board
    rib_x0, rib_x1 = XIAO_X1 - 3.55, X_MAX_IN - 0.2
    z_a, z_b = Z_XIAO - 0.25, Z_XIAO + XIAO_PCB_T + 0.25
    b += cube(rib_x0, X_MAX_IN + 0.3, Y_FLOOR_B - 0.6, 0.0, z_a - 1.35, z_b + 2.75) ^ out_b
    b += cube(rib_x0, rib_x1, -0.01, XIAO_Y0 - FIT, z_a - 1.35, z_b + 2.75)
    # a finger under the board end (the pin side); the top side stays free for the antenna socket
    b += cube(rib_x0, rib_x1, XIAO_Y0 - FIT - 0.01, XIAO_Y0 + 1.3, z_b, z_b + 1.55)

    cut_b = [cuts, collar_hole]
    for cx, cz in (S1, S3, S4):
        cut_b.append(cyl_y(SCREW_CLEAR_R, SCREW_SEAT_Y - 0.01, 1.0, cx, cz))
        cut_b.append(cyl_y(SCREW_WELL_R, -W_B - 1.0, SCREW_SEAT_Y - 1.5, cx, cz))
        # conical seat instead of a flat ceiling: prints clean with the well facing down
        cut_b.append(hull(cyl_y(SCREW_WELL_R, SCREW_SEAT_Y - 1.55, SCREW_SEAT_Y - 1.5, cx, cz),
                          cyl_y(SCREW_CLEAR_R, SCREW_SEAT_Y - 0.05, SCREW_SEAT_Y, cx, cz)))
    cut_b.append(prism_y(box(sx - SWITCH_SLOT[0] / 2, sz - SWITCH_SLOT[1] / 2, sx + SWITCH_SLOT[0] / 2, sz + SWITCH_SLOT[1] / 2),
                         -W_B - 1.0, Y_FLOOR_B + 0.01))
    # groove for the tongue of half A
    groove = SILHOUETTE.buffer(-1.0, quad_segs=SEGS).difference(SILHOUETTE.buffer(-WALL - 0.01, quad_segs=SEGS))
    cut_b.append(prism_y(groove.difference(seam_gap), -1.8, 0.01))
    b -= union(cut_b)

    parts = {"half_a": a, "half_b": b}
    return parts, references()


def references():
    """Simplified solids of everything the body holds, in its final place."""
    chest = union([
        cyl_z(HEAD_BIG_D / 2, 0, Z_MID0),
        cyl_z(HEAD_MID_D / 2, Z_MID0 - 0.01, Z_SMALL0 + 0.01),
        cyl_z(HEAD_SMALL_D / 2, Z_SMALL0, Z_SMALL1),
        cyl_x(STEM_D / 2, 0, X_STEM_TIP, 0, Z_STEM),
    ])
    mic_pcb = cyl_x(MIC_D / 2, MIC_X0, MIC_X0 + MIC_T, 0, Z_STEM)
    mx = MIC_X0 + MIC_T
    pr, hw = MIC_PIN_ROWS / 2, DUPONT_W / 2
    mic_plugs = union([
        cube(mx, mx + HEADER_PLASTIC + DUPONT_L, s * pr - hw, s * pr + hw, Z_STEM - MIC_ROW_L / 2, Z_STEM + MIC_ROW_L / 2)
        for s in (-1, 1)
    ])
    xiao = union([
        cube(XIAO_X0, XIAO_X1, XIAO_Y0, XIAO_Y1, Z_XIAO, Z_XIAO + XIAO_PCB_T),
        prism_y(usb_shell_profile(), USB_MOUTH_Y - USB_SHELL_L, USB_MOUTH_Y),
    ])
    zp = Z_XIAO + XIAO_PCB_T
    xiao_plugs = union([
        cube(XIAO_XC + s * 7.62 - 1.3, XIAO_XC + s * 7.62 + 1.3, XIAO_Y0 + 1.76, XIAO_Y1 - 1.76,
             zp - 0.01, zp + HEADER_PLASTIC + DUPONT_L)
        for s in (-1, 1)
    ])
    battery = cube(BAT_X0, BAT_X1, -BAT_W / 2, BAT_W / 2, BAT_Z0, BAT_Z1)
    sx, sz = SWITCH_C
    switch = cube(sx - SWITCH_L / 2, sx + SWITCH_L / 2, Y_FLOOR_B, Y_FLOOR_B + SWITCH_T, sz - SWITCH_W / 2, sz + SWITCH_W / 2)
    screws = union([
        cyl_y(SCREW_HEAD_D / 2, SCREW_SEAT_Y - 4.5, SCREW_SEAT_Y - 1.4, cx, cz)
        + cyl_y(SCREW_D / 2, SCREW_SEAT_Y - 1.5, SCREW_SEAT_Y + SCREW_LEN, cx, cz)
        for cx, cz in (S1, S3, S4)
    ])
    return {
        "chest_piece": chest, "mic": mic_pcb, "mic_plugs": mic_plugs, "xiao": xiao,
        "xiao_plugs": xiao_plugs, "battery": battery, "switch": switch, "screws": screws,
    }


def print_pose(name: str, m: Manifold) -> Manifold:
    """Turn a half so its outer side wall lies on the bed (z = 0), open side up."""
    m = m.rotate([-90, 0, 0]) if name == "half_a" else m.rotate([90, 0, 0])
    x0, y0, z0, *_ = m.bounding_box()
    return m.translate([-x0, -y0, -z0])


if __name__ == "__main__":
    parts, refs = build()
    for k, v in {**parts, **refs}.items():
        bb = [round(c, 2) for c in v.bounding_box()]
        print(f"{k:12s} status={v.status().name} bodies={len(v.decompose())} vol={v.volume() / 1000:.2f} cm3 bbox={bb}")
    print(f"body: {X_MAX - X_MIN:.1f} x {W_A + W_B:.1f} x {Z_BACK - Z_FRONT:.1f} mm")
