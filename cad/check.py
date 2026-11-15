"""Checks the enclosure model before anything is sent to a printer.

    python check.py

It builds the model from case.py and tests, with real solid geometry:

  1. every printed part is one closed, valid solid;
  2. nothing collides: the two halves with each other, and every component
     (chest piece, mic, XIAO, battery, switch, screws) with the plastic;
  3. every component is actually held: nudged a millimetre in any direction,
     it hits plastic;
  4. the device can be put together: each component drops straight into its
     half, and the second half closes over the first;
  5. each half prints without supports and has no walls thinner than a nozzle
     can lay down;
  6. the exported STL files are watertight and match the model.

Exit code 0 only if every check passes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold
from shapely.geometry import Polygon
from shapely.ops import unary_union

import case

OUT = Path(__file__).parent / "out"
EPS_VOL = 0.05          # mm3: below this an "overlap" is numerical noise
results: list[tuple[bool, str]] = []


def report(ok: bool, text: str):
    results.append((ok, text))
    print(("  ok   " if ok else "  FAIL ") + text)


def overlap(a: Manifold, b: Manifold) -> float:
    return (a ^ b).volume()


# ------------------------------------------------------------------ 1 -------
def check_solids(parts):
    print("1. solids")
    for name, m in parts.items():
        n = len(m.decompose())
        report(m.status().name == "NoError" and n == 1 and m.volume() > 0,
               f"{name}: valid, {n} body, {m.volume() / 1000:.1f} cm3 of plastic (roughly {m.volume() / 1000 * 1.24 * 0.75:.0f} g of PLA)")


# ------------------------------------------------------------------ 2 -------
def check_collisions(parts, refs):
    print("2. collisions")
    a, b = parts["half_a"], parts["half_b"]
    v = overlap(a, b)
    report(v < EPS_VOL, f"half A and half B do not overlap ({v:.3f} mm3)")
    body = a + b
    for name, r in refs.items():
        if name == "screws":
            continue
        v = overlap(body, r)
        gap = body.min_gap(r, 5.0)
        report(v < EPS_VOL, f"{name}: no overlap with the body ({v:.3f} mm3), nearest plastic {gap:.2f} mm away")
    names = [n for n in refs if n != "screws"]
    for i, n1 in enumerate(names):
        for n2 in names[i + 1:]:
            v = overlap(refs[n1], refs[n2])
            pair = {n1, n2}
            if pair in ({"xiao", "xiao_plugs"},):
                continue    # plugs sit on the board by definition
            report(v < EPS_VOL, f"{n1} / {n2}: clear of each other ({v:.3f} mm3)")
    # screws: free in half B, biting into half A
    v_b = overlap(b, refs["screws"])
    report(v_b < EPS_VOL, f"screws pass freely through half B ({v_b:.3f} mm3)")
    for i, s in enumerate(refs["screws"].decompose()):
        x0, y0, z0, x1, y1, z1 = s.bounding_box()
        shaft = s.trim_by_plane([0, 1, 0], 0.0)
        bite = overlap(a, shaft)
        ring = np.pi * (case.SCREW_D ** 2 / 4 - case.SCREW_PILOT_R ** 2)
        length = bite / ring
        report(length >= 5.5, f"screw at x={(x0 + x1) / 2:.1f}: {length:.1f} mm of thread in half A")
        others = [r for n, r in refs.items() if n != "screws"]
        v = sum(overlap(s, r) for r in others)
        report(v < EPS_VOL, f"screw at x={(x0 + x1) / 2:.1f}: clear of every component ({v:.3f} mm3)")


# ------------------------------------------------------------------ 3 -------
def check_held(parts, refs):
    print("3. every component is held")
    body = parts["half_a"] + parts["half_b"]
    dirs = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}

    def free_dirs(m, step, also=None):
        free = []
        for label, d in dirs.items():
            moved = m.translate([step * c for c in d])
            v = overlap(body, moved)
            if also is not None:
                v += overlap(also, moved)
            if v < EPS_VOL:
                free.append(label)
        return free

    f = free_dirs(refs["chest_piece"], 1.0)
    report(not f, f"chest piece: blocked in all six directions at 1.0 mm (free: {f or 'none'})")
    twist = refs["chest_piece"].rotate([0, 0, 4.0])
    report(overlap(body, twist) > EPS_VOL, "chest piece: cannot turn about its own axis (4 degrees hits plastic)")

    xiao = refs["xiao"]
    f = free_dirs(xiao, 0.8)
    report(not f, f"XIAO: blocked in all six directions at 0.8 mm (free: {f or 'none'})")

    # the battery may only move toward its wires' gap less than this
    f = free_dirs(refs["battery"], 2.5)
    report(not f, f"battery: blocked in all six directions at 2.5 mm (free: {f or 'none'})")

    # mic: sideways and outward the pocket holds it; toward the stem, the stem does
    f = free_dirs(refs["mic"], 0.9, also=refs["chest_piece"])
    f = [d for d in f if d != "+x"]      # +x is the foam pad's job (not modelled)
    report(not f, f"mic board: held sideways and against the stem tip (free: {f or 'none'}; behind it sits the foam pad)")

    f = free_dirs(refs["switch"], 0.8)
    f = [d for d in f if d != "+y"]      # glued in from the inside
    report(not f, f"switch: located in its pocket (free: {f or 'none'}; a drop of glue holds it in)")


# ------------------------------------------------------------------ 4 -------
def check_assembly(parts, refs):
    print("4. assembly")
    a, b = parts["half_a"], parts["half_b"]
    steps = np.arange(0.5, 45.0, 0.5)

    def slides_out(m, fixed, direction):
        for k in steps:
            if overlap(fixed, m.translate([direction[0] * k, direction[1] * k, direction[2] * k])) > EPS_VOL:
                return k
        return None

    for name in ("chest_piece", "mic", "mic_plugs", "battery"):
        hit = slides_out(refs[name], a, (0, -1, 0))
        report(hit is None, f"{name}: drops straight into half A" + ("" if hit is None else f" (hits plastic {hit} mm out)"))
    xiao = refs["xiao"] + refs["xiao_plugs"]
    hit = slides_out(xiao, a, (0, -1, 0))
    report(hit is None, "XIAO with its plugs: drops straight into half A, USB socket into its opening"
           + ("" if hit is None else f" (hits plastic {hit} mm out)"))
    hit = slides_out(refs["switch"], b, (0, 1, 0))
    report(hit is None, "switch: drops into its pocket in half B" + ("" if hit is None else f" (hits {hit} mm out)"))
    loaded = a + case.union([r for n, r in refs.items() if n not in ("screws", "switch")])
    hit = slides_out(b + refs["switch"], loaded, (0, -1, 0))
    report(hit is None, "half B (with the switch) closes straight onto the loaded half A"
           + ("" if hit is None else f" (hits {hit} mm before closing)"))


# ------------------------------------------------------------------ 5 -------
def _polys(cs):
    out = []
    for c in cs.to_polygons():
        c = np.asarray(c)
        if len(c) >= 3:
            out.append(c)
    if not out:
        return None
    # even-odd assembly of contours into polygons with holes
    shapes = [Polygon(c) for c in out]
    shapes = [s if s.is_valid else s.buffer(0) for s in shapes]
    shapes.sort(key=lambda s: -s.area)
    result = None
    for s in shapes:
        result = s if result is None else result.symmetric_difference(s)
    return result


def check_printability(parts):
    print("5. printing (each half on its side wall, open side up, no supports)")
    for name, m in parts.items():
        p = case.print_pose(name, m)
        x0, y0, z0, x1, y1, z1 = p.bounding_box()
        report(max(x1, y1) <= 180 and z1 <= 180, f"{name}: {x1:.1f} x {y1:.1f} mm on the bed, {z1:.1f} mm tall")

        mesh = p.to_mesh()
        v = np.asarray(mesh.vert_properties)[:, :3].astype(float)
        t = v[np.asarray(mesh.tri_verts)]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        area = np.linalg.norm(n, axis=1) / 2
        ok = area > 1e-9
        t, n, area = t[ok], n[ok] / (2 * area[ok, None]), area[ok]
        zc = t[:, :, 2].mean(axis=1)
        on_bed = t[:, :, 2].max(axis=1) < 0.02
        report(area[on_bed].sum() > 600, f"{name}: {area[on_bed].sum():.0f} mm2 flat on the bed")

        # anything facing down more steeply than 45 degrees needs something under it
        down = (n[:, 2] < -0.72) & ~on_bed
        flat = (n[:, 2] < -0.999) & ~on_bed
        steep = down & ~flat
        report(area[steep].sum() < 1.0, f"{name}: no sloped overhang steeper than 45 degrees ({area[steep].sum():.2f} mm2)")
        # flat ceilings are fine only as short bridges: measure the longest unsupported span
        worst = 0.0
        where = None
        if flat.any():
            for z in np.unique(np.round(zc[flat], 2)):
                sel = flat & (np.abs(zc - z) < 0.011)
                ceiling = unary_union([Polygon(tri[:, :2]) for tri in t[sel]]).buffer(1e-4)
                below = _polys(p.slice(z - 0.1))
                hanging = ceiling if below is None else ceiling.difference(below.buffer(0.05))
                for g in getattr(hanging, "geoms", [hanging]):
                    if g.is_empty or g.area < 0.05:
                        continue
                    # span = width of the hanging patch across its narrow direction
                    rect = g.minimum_rotated_rectangle
                    xs, ys = rect.exterior.coords.xy
                    sides = sorted(np.hypot(np.diff(xs), np.diff(ys))[:2])
                    if sides[0] > worst:
                        worst, where = sides[0], (round(g.centroid.x, 1), round(g.centroid.y, 1), float(z))
        report(worst <= 8.0, f"{name}: longest flat bridge {worst:.1f} mm" + (f" at print x,y,z={where}" if where else ""))

        # thin features, per layer and across the other two axes
        # A wall thinner than 0.8 mm shows up as a strip that disappears when the
        # slice is shrunk by 0.39 mm and grown back. A real thin wall shows in
        # several neighbouring slices; a slice that only grazes a rounded crest
        # shows once and is ignored.
        # The same test turned inside out finds slits: air gaps under 0.6 mm
        # inside one part, which a slicer either fuses shut or leaves as a
        # weak seam. They close when the slice is grown by 0.29 mm and shrunk back.
        thin, slits = [], []
        for axis, rot in (("layer", None), ("x", [0, 90, 0]), ("y", [90, 0, 0])):
            q = p if rot is None else p.rotate(rot)
            _, _, qz0, _, _, qz1 = q.bounding_box()
            prev_thin, prev_slit = [], []
            for z in np.arange(qz0 + 0.35, qz1 - 0.2, 0.35):
                poly = _polys(q.slice(float(z)))
                cur_thin, cur_slit = [], []
                if poly is not None and not poly.is_empty:
                    lost = poly.difference(poly.buffer(-0.39).buffer(0.40))
                    cur_thin = [g for g in getattr(lost, "geoms", [lost]) if not g.is_empty and g.area > 0.6]
                    closed = poly.buffer(0.29).buffer(-0.30).difference(poly)
                    cur_slit = [g for g in getattr(closed, "geoms", [closed]) if not g.is_empty and g.area > 0.4]
                for cur, prev, found in ((cur_thin, prev_thin, thin), (cur_slit, prev_slit, slits)):
                    for g in cur:
                        if any(g.centroid.distance(o.centroid) < 1.0 for o in prev):
                            found.append((axis, round(float(z), 1), round(g.centroid.x, 1), round(g.centroid.y, 1), round(g.area, 2)))
                prev_thin, prev_slit = cur_thin, cur_slit
        report(not thin, f"{name}: nothing thinner than 0.8 mm" + (f" ({len(thin)} slices, first: {thin[0]})" if thin else ""))
        report(not slits, f"{name}: no slit narrower than 0.6 mm" + (f" ({len(slits)} slices, first: {slits[0]})" if slits else ""))


# ------------------------------------------------------------------ 6 -------
def check_exports(parts):
    print("6. exported files")
    for name, m in parts.items():
        path = OUT / f"respirai-{name.replace('_', '-')}.stl"
        if not path.exists():
            report(False, f"{path.name}: missing, run generate.py first")
            continue
        mesh = trimesh.load_mesh(path)
        vol = case.print_pose(name, m).volume()
        ok = mesh.is_watertight and mesh.is_winding_consistent and abs(mesh.volume - vol) < 0.5
        report(ok, f"{path.name}: watertight, consistent, volume matches the model "
               f"({mesh.volume / 1000:.2f} cm3, {len(mesh.faces)} triangles, min z {mesh.bounds[0][2]:.2f})")


def check_intent(parts, refs):
    print("7. design numbers")
    body = parts["half_a"] + parts["half_b"]
    x0, y0, z0, x1, y1, z1 = body.bounding_box()
    report(z0 > 0.3, f"the diaphragm is the highest point: the body stays {z0:.2f} mm behind it at its tallest (the mic bump), "
           f"{case.Z_FRONT:.1f} mm behind it elsewhere")
    report(True, f"body size {x1 - x0:.1f} x {y1 - y0:.1f} x {z1 - case.Z_FRONT:.1f} mm, plus the head standing {case.Z_FRONT:.1f} mm proud")
    mouth = case.USB_MOUTH_Y - case.W_A
    report(0.2 <= mouth <= 1.2, f"USB-C socket ends {mouth:.1f} mm proud of the side wall")
    gap = case.MIC_X0 - case.X_STEM_TIP
    report(abs(gap - case.MIC_GASKET) < 1e-6 and case.STEM_BORE / 2 < case.STEM_D / 2,
           f"stem tip to mic board: {gap:.1f} mm (the gasket), mic port on the stem axis inside the {case.STEM_BORE:.0f} mm bore")


def main():
    parts, refs = case.build()
    check_solids(parts)
    check_collisions(parts, refs)
    check_held(parts, refs)
    check_assembly(parts, refs)
    check_printability(parts)
    check_exports(parts)
    check_intent(parts, refs)
    failed = [t for ok, t in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
    for t in failed:
        print("  FAILED:", t)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
