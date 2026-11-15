"""Builds the enclosure and writes the files for the printer to out/.

    python generate.py

  respirai-half-a.stl, respirai-half-b.stl   the two parts to print, already lying
                                             the way they should be printed
  respirai-assembly.stl                      both halves closed with every component
                                             in place, for looking at only
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

import case

OUT = Path(__file__).parent / "out"


def to_trimesh(m) -> trimesh.Trimesh:
    """Mesh for export. STL stores no connectivity, so vertices that share a
    position are merged here and the triangles that collapse to a line because
    of it are dropped; otherwise a slicer would see them as holes."""
    mesh = m.to_mesh()
    t = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3].astype(np.float32).astype(float),
                        faces=np.asarray(mesh.tri_verts), process=False)
    t.merge_vertices(digits_vertex=5)
    f = t.faces
    t.update_faces((f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2]))
    t.remove_unreferenced_vertices()
    return t


def main():
    OUT.mkdir(exist_ok=True)
    parts, refs = case.build()
    for name, m in parts.items():
        path = OUT / f"respirai-{name.replace('_', '-')}.stl"
        to_trimesh(case.print_pose(name, m)).export(path)
        x0, y0, z0, x1, y1, z1 = case.print_pose(name, m).bounding_box()
        print(f"{path.name}: {x1:.1f} x {y1:.1f} x {z1:.1f} mm, {m.volume() / 1000:.1f} cm3")
    assembly = trimesh.util.concatenate([to_trimesh(m) for m in list(parts.values()) + list(refs.values())])
    assembly.export(OUT / "respirai-assembly.stl")
    print("respirai-assembly.stl: preview only, not for printing")


if __name__ == "__main__":
    main()
