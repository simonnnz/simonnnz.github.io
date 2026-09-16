r"""
Builds the wheel-leg biped wireframe for the hero, from its MuJoCo model.

    python tools\biped_edges.py <path to rl folder>

The biped has no CAD in this repo -- it exists as primitives in biped.mjcf
(box chassis, capsule legs, cylinder wheels). This walks the model at its
rest pose, turns each geom into line segments in world space, then centres
and scales the result the same way the CAD extractions are normalised, so
index.html can load edges\biped.bin like any other model.
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "edges", "biped.bin")
TAU = math.pi * 2


def circle(out, c, u, w, r, n):
    for i in range(n):
        a, b = TAU * i / n, TAU * (i + 1) / n
        p = c + r * (math.cos(a) * u + math.sin(a) * w)
        q = c + r * (math.cos(b) * u + math.sin(b) * w)
        out.append((p, q))


def geom_lines(out, kind, size, pos, R):
    """One geom, already placed in the world by pos and R (columns x, y, z)."""
    ex, ey, ez = R[:, 0], R[:, 1], R[:, 2]
    if kind == "box":
        hx, hy, hz = size[:3]
        corners = {}
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    corners[(sx, sy, sz)] = pos + sx * hx * ex + sy * hy * ey + sz * hz * ez
        for a, b in [((-1,-1,-1),(1,-1,-1)), ((1,-1,-1),(1,1,-1)), ((1,1,-1),(-1,1,-1)),
                     ((-1,1,-1),(-1,-1,-1)), ((-1,-1,1),(1,-1,1)), ((1,-1,1),(1,1,1)),
                     ((1,1,1),(-1,1,1)), ((-1,1,1),(-1,-1,1)), ((-1,-1,-1),(-1,-1,1)),
                     ((1,-1,-1),(1,-1,1)), ((1,1,-1),(1,1,1)), ((-1,1,-1),(-1,1,1))]:
            out.append((corners[a], corners[b]))
    elif kind == "capsule":
        r, h = size[0], size[1]
        for s in (-1, 1):
            circle(out, pos + s * h * ez, ex, ey, r, 10)
        for i in range(4):
            a = TAU * i / 4
            d = r * (math.cos(a) * ex + math.sin(a) * ey)
            out.append((pos - h * ez + d, pos + h * ez + d))
        for s in (-1, 1):                      # the rounded ends
            for axis in (ex, ey):
                for i in range(6):
                    a, b = math.pi / 2 * i / 6, math.pi / 2 * (i + 1) / 6
                    for sd in (-1, 1):
                        p = pos + s * (h + r * math.sin(a)) * ez + sd * r * math.cos(a) * axis
                        q = pos + s * (h + r * math.sin(b)) * ez + sd * r * math.cos(b) * axis
                        out.append((p, q))
    elif kind == "cylinder":
        r, h = size[0], size[1]
        for s in (-1, 1):
            circle(out, pos + s * h * ez, ex, ey, r, 24)
            circle(out, pos + s * h * ez, ex, ey, r * 0.24, 8)
        circle(out, pos + h * ez, ex, ey, r * 0.6, 16)
        for i in range(6):                      # spokes, so the wheel reads as a wheel
            a = TAU * i / 6
            d = math.cos(a) * ex + math.sin(a) * ey
            out.append((pos + h * ez + r * 0.24 * d, pos + h * ez + r * 0.6 * d))
            out.append((pos - h * ez + r * 0.24 * d, pos - h * ez + r * d))
        for i in range(12):                     # tread
            a = TAU * i / 12
            d = r * (math.cos(a) * ex + math.sin(a) * ey)
            out.append((pos - h * ez + d, pos + h * ez + d))


def main():
    rl = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.expanduser("~"), "projects", "biped", "rl")
    import mujoco
    m = mujoco.MjModel.from_xml_path(os.path.join(rl, "biped.mjcf"))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)                     # rest pose: legs as authored

    KINDS = {2: "sphere", 3: "capsule", 5: "cylinder", 6: "box"}
    segs = []
    for g in range(m.ngeom):
        kind = KINDS.get(int(m.geom_type[g]))
        if kind is None or kind == "sphere":    # skips the floor and the terrain
            continue
        geom_lines(segs, kind, m.geom_size[g], d.geom_xpos[g].copy(),
                   d.geom_xmat[g].reshape(3, 3))
    a = np.array([[p, q] for p, q in segs], dtype=np.float64)
    print("%d segments from %d geoms" % (len(a), m.ngeom))

    # same frame as the CAD extractions: centred, longest side 1, CAD z-up -> viewer y-up
    flat = a.reshape(-1, 3)
    c = (flat.min(0) + flat.max(0)) / 2
    ext = (flat.max(0) - flat.min(0)).max()
    a = (a - c) / ext
    a = a[:, :, [0, 2, 1]] * [1, 1, -1]
    a.astype("<f4").tofile(OUT)
    print("wrote %s  %.1f KB" % (os.path.relpath(OUT, HERE), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
