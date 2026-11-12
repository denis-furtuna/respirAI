"""Pictures of the enclosure: shaded views and cross-sections, written to out/.

No GPU or window needed: a small z-buffer renderer in numpy, and matplotlib
for the sections. Run after changing case.py to look at the result.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from PIL import Image

import case

OUT = Path(__file__).parent / "out"

COLORS = {
    "half_a": (0.93, 0.94, 0.96), "half_b": (0.70, 0.80, 0.90),
    "chest_piece": (0.72, 0.74, 0.78), "mic": (0.45, 0.25, 0.60), "mic_plugs": (0.15, 0.15, 0.17),
    "xiao": (0.10, 0.45, 0.35), "xiao_plugs": (0.15, 0.15, 0.17), "battery": (0.85, 0.70, 0.25),
    "switch": (0.80, 0.30, 0.25), "screws": (0.35, 0.37, 0.40),
}


def _view(az, el):
    """Rotation whose rows are the screen x, screen y and view depth axes."""
    az, el = math.radians(az), math.radians(el)
    fwd = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])  # toward the eye
    up = np.array([0, 0, 1.0]) if abs(fwd[2]) < 0.99 else np.array([0, 1.0, 0])
    right = np.cross(up, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    return np.vstack([right, up, fwd])


def shade(bodies, az, el, path, px_per_mm=9, flip_z=True):
    """bodies: {name: Manifold}. flip_z shows the model with the chest side up."""
    rot = _view(az, el)
    tris, cols = [], []
    for name, m in bodies.items():
        mesh = m.to_mesh()
        v = np.asarray(mesh.vert_properties)[:, :3].astype(float)
        if flip_z:
            v = v * np.array([1, -1, -1])   # turn over (a rotation, not a mirror)
        t = v[np.asarray(mesh.tri_verts)] @ rot.T
        tris.append(t)
        cols.append(np.tile(COLORS.get(name, (0.8, 0.8, 0.8)), (len(t), 1)))
    tris, cols = np.vstack(tris), np.vstack(cols)
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    pad = 4
    w = int((hi[0] - lo[0] + 2 * pad) * px_per_mm)
    h = int((hi[1] - lo[1] + 2 * pad) * px_per_mm)
    sx = (tris[:, :, 0] - lo[0] + pad) * px_per_mm
    sy = (hi[1] - tris[:, :, 1] + pad) * px_per_mm
    sz = tris[:, :, 2]
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = (ln > 1e-12) & (n[:, 2] > 0)          # front faces only
    n = n[keep] / ln[keep, None]
    sx, sy, sz, cols = sx[keep], sy[keep], sz[keep], cols[keep]
    light = np.array([-0.35, 0.55, 0.76])
    light /= np.linalg.norm(light)
    lum = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
    rgb = cols * lum[:, None]

    img = np.ones((h, w, 3))
    zbuf = np.full((h, w), -np.inf)
    for i in range(len(sx)):
        x0, x1 = max(int(sx[i].min()), 0), min(int(sx[i].max()) + 1, w - 1)
        y0, y1 = max(int(sy[i].min()), 0), min(int(sy[i].max()) + 1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        ax, ay, bx, by, cx, cy = sx[i][0], sy[i][0], sx[i][1], sy[i][1], sx[i][2], sy[i][2]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        z = l1 * sz[i][0] + l2 * sz[i][1] + l3 * sz[i][2]
        zb = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z > zb)
        zb[upd] = z[upd]
        img[y0:y1 + 1, x0:x1 + 1][upd] = rgb[i]
    # darken depth discontinuities a little so edges read
    dz = np.abs(np.diff(np.where(np.isinf(zbuf), -50, zbuf), axis=0, prepend=0)) + \
        np.abs(np.diff(np.where(np.isinf(zbuf), -50, zbuf), axis=1, prepend=0))
    img[dz > 0.9] *= 0.55
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)


def _section_polys(m, axis, at):
    """Outline of m cut by the plane axis = at, as (u, v) contours."""
    if axis == "z":
        r = m
    elif axis == "y":      # look along y: (x, z) plane
        r = m.transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0]], float))
        at = -at
    else:                  # look along x: (y, z) plane
        r = m.transform(np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0]], float))
    return r.slice(at).to_polygons()


def section(bodies, axis, at, path, title):
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=110)
    for name, m in bodies.items():
        polys = _section_polys(m, axis, at)
        if not polys:
            continue
        verts, codes = [], []
        for p in polys:
            p = np.asarray(p)
            verts += list(p) + [p[0]]
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(p) - 1) + [MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=COLORS.get(name, (0.8, 0.8, 0.8)),
                               edgecolor="black", linewidth=0.5, label=name))
    ax.set_aspect("equal")
    ax.autoscale()
    ax.invert_yaxis()                  # chest side on top
    labels = {"y": ("x (mm)", "z depth (mm)"), "x": ("y (mm)", "z depth (mm)"), "z": ("x (mm)", "y (mm)")}[axis]
    ax.set_xlabel(labels[0]); ax.set_ylabel(labels[1])
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.set_title(title)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _as_printed(name, half, m):
    """m moved the same way print_pose moves the half it belongs to."""
    r = [-90, 0, 0] if name == "half_a" else [90, 0, 0]
    x0, y0, z0, *_ = half.rotate(r).bounding_box()
    return m.rotate(r).translate([-x0, -y0, -z0])


def main():
    OUT.mkdir(exist_ok=True)
    parts, refs = case.build()
    everything = {**parts, **refs}
    only = set(sys.argv[1:])

    def want(tag):
        return not only or tag in only

    if want("views"):
        shade(everything, 235, 28, OUT / "view-chest-side.png")
        shade(everything, 55, -30, OUT / "view-palm-side.png")
        # each half as it lies on the printer, looking into the open side
        for name in ("half_a", "half_b"):
            tag = name.replace("_", "-")
            shade({name: case.print_pose(name, parts[name])}, 250, 50, OUT / f"view-{tag}-print.png", flip_z=False)
            shade({name: case.print_pose(name, parts[name])}, 70, 55, OUT / f"view-{tag}-print-2.png", flip_z=False)
            held = {k: v for k, v in refs.items() if k != "screws" and (k == "switch") == (name == "half_b")}
            if name == "half_a":
                loaded = {name: parts[name], **held}
                shade({k: _as_printed(name, parts[name], v) for k, v in loaded.items()}, 250, 50,
                      OUT / f"view-{tag}-loaded.png", flip_z=False)
    if want("sections"):
        section(everything, "y", 0.3, OUT / "section-y0-seam.png", "side view cut just inside half A (y = 0.3)")
        section(everything, "y", 6.0, OUT / "section-y6.png", "y = 6: mic plugs, corbel")
        section(everything, "y", 18.0, OUT / "section-y18-xiao.png", "y = 18: through the XIAO")
        section(everything, "y", -12.0, OUT / "section-y-12.png", "y = -12: half B")
        section(everything, "x", 0.0, OUT / "section-x0-head.png", "x = 0: through the chest piece axis")
        section(everything, "x", case.MIC_X0 + 0.5, OUT / "section-x-mic.png", "through the mic board")
        section(everything, "x", case.XIAO_XC, OUT / "section-x-xiao.png", "through the XIAO centre (USB port, switch, screw 4)")
        section(everything, "x", case.S1[0], OUT / "section-x-screw1.png", "through screw 1")
        section(everything, "z", case.Z_STEM, OUT / "section-z-stem.png", "plan cut at the stem axis depth")
        section(everything, "z", case.Z_XIAO + 0.8, OUT / "section-z-xiao.png", "plan cut through the XIAO board")
        section(everything, "z", case.BAT_Z0 + 3, OUT / "section-z-battery.png", "plan cut through the battery")
    print("pictures in", OUT)


if __name__ == "__main__":
    main()
