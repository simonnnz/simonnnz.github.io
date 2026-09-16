r"""
Builds the whole-robot wireframe for the CRC overview.

    python tools\robot_edges.py                        overview, crc-robot.bin
    python tools\robot_edges.py 22 2.5 crc-robot-mid   zoom levels for the viewer
    python tools\robot_edges.py 14 0.6 crc-robot-hi

The full robot STL is ~2.5 million triangles, too big for the pure-Python
extractor build.py uses, so this one does the same job with numpy:

  1. weld vertices (STL stores every triangle's corners separately)
  2. find each edge's two faces and the angle between them
  3. keep edges sharper than ANGLE, drop ones shorter than MIN_LEN
  4. centre, scale so the largest side is 1, turn CAD Z-up into viewer Y-up

Writes edges\crc-robot.bin, same float32 line-segment format as the others.
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "CRC Swerve Drive Model", "CRC 2026 v35.stl")
ANGLE = float(sys.argv[1]) if len(sys.argv) > 1 else 35.0     # degrees
MIN_LEN = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0    # mm
NAME = sys.argv[3] if len(sys.argv) > 3 else "crc-robot"
OUT = os.path.join(HERE, "edges", NAME + ".bin")
WELD = 0.01                                                   # mm


def main():
    n = int(np.fromfile(SRC, dtype="<u4", count=1, offset=80)[0])
    tri = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    v = np.fromfile(SRC, dtype=tri, count=n, offset=84)["v"]          # (n, 3, 3)
    print("%d triangles" % n)

    # 1. weld: one integer key per quantised position
    q = np.round(v.reshape(-1, 3) / WELD).astype(np.int64)
    q -= q.min(0)
    span = q.max(0) + 1
    key = (q[:, 0] * span[1] + q[:, 1]) * span[2] + q[:, 2]
    uniq, idx = np.unique(key, return_inverse=True)
    del q, key
    idx = idx.reshape(-1, 3)
    pos = np.zeros((len(uniq), 3), np.float64)
    pos[idx.ravel()] = v.reshape(-1, 3)
    print("%d welded vertices" % len(uniq))

    fn = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]).astype(np.float64)
    ln = np.linalg.norm(fn, axis=1)
    good = ln > 1e-12
    fn[good] /= ln[good][:, None]
    del v

    # 2. edges -> faces
    a = idx[:, [0, 1, 2]].ravel()
    b = idx[:, [1, 2, 0]].ravel()
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    face = np.repeat(np.arange(n), 3)
    ek = lo.astype(np.int64) * len(uniq) + hi
    order = np.argsort(ek, kind="stable")
    ek, lo, hi, face = ek[order], lo[order], hi[order], face[order]
    first = np.r_[True, ek[1:] != ek[:-1]]
    starts = np.flatnonzero(first)
    counts = np.diff(np.r_[starts, len(ek)])

    keep = np.zeros(len(starts), bool)
    # boundary edges (open meshes, cut faces) are always outlines
    keep[counts == 1] = True
    two = counts == 2
    s2 = starts[two]
    cosang = (fn[face[s2]] * fn[face[s2 + 1]]).sum(1)
    keep[np.flatnonzero(two)] = cosang < np.cos(np.radians(ANGLE))
    # non-manifold edges: keep (usually where two bodies touch)
    keep[counts > 2] = True

    s = starts[keep]
    p1, p2 = pos[lo[s]], pos[hi[s]]
    L = np.linalg.norm(p2 - p1, axis=1)
    m = L >= MIN_LEN
    p1, p2 = p1[m], p2[m]
    print("%d edges kept (angle %.0f deg, min %.1f mm)" % (len(p1), ANGLE, MIN_LEN))

    # 4. frame, from the whole model rather than the kept edges, so every
    #    detail level lands in exactly the same place and they can cross-fade
    c = (pos.min(0) + pos.max(0)) / 2
    ext = (pos.max(0) - pos.min(0)).max()
    seg = np.stack([p1, p2], 1) - c
    seg /= ext
    seg = seg[:, :, [0, 2, 1]] * [1, 1, -1]        # (x, y, z) -> (x, z, -y)
    seg.astype("<f4").tofile(OUT)
    print("wrote %s  %.0f KB" % (os.path.relpath(OUT, HERE), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
