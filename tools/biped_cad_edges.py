r"""
Builds the biped wireframe from the SolidWorks export.

    python tools\biped_cad_edges.py <folder of part STLs> [angle] [min mm]

solidworks_export.py writes one STL per component. Each is in ASSEMBLY
coordinates, so the robot is rebuilt by concatenating them, then the same
feature-edge extraction the CRC robot uses runs over the result: weld
vertices, keep edges where the two faces meet sharply enough, drop the short
ones, then centre and scale into the viewer's frame.

Writes edges\biped.bin, replacing the version built from the MuJoCo model.
"""

import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "edges", "biped.bin")
WELD = 0.02          # mm


def load_stl(path):
    n = int(np.fromfile(path, dtype="<u4", count=1, offset=80)[0])
    if n == 0 or os.path.getsize(path) != 84 + n * 50:
        return np.zeros((0, 3, 3), np.float32)          # ascii or empty
    tri = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.fromfile(path, dtype=tri, count=n, offset=84)["v"]


def newest_per_part(folder):
    """SolidWorks writes 'name.STL' and 'name-1.STL' when a file already
    exists, so keep only the newest file per component."""
    best = {}
    for f in os.listdir(folder):
        if not f.lower().endswith(".stl"):
            continue
        p = os.path.join(folder, f)
        key = re.sub(r"-\d+\.stl$", "", f, flags=re.I).lower()
        if key not in best or os.path.getmtime(p) > os.path.getmtime(best[key]):
            best[key] = p
    return sorted(best.values())


def main():
    src = sys.argv[1]
    angle = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    min_len = float(sys.argv[3]) if len(sys.argv) > 3 else 1.2
    # degrees about the viewer's x axis, applied last. The leg is modelled
    # lying down (motors at one end, wheel at the other); 90 stands it up with
    # both hip motors on top and the wheel hanging below.
    roll = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0

    # one assembly STL (what solidworks_export.py writes with the right
    # preferences), or a folder of per-component files
    files = [src] if os.path.isfile(src) else newest_per_part(src)
    parts = [load_stl(p) for p in files]
    tris = np.concatenate([p for p in parts if len(p)], 0).astype(np.float64)
    print("%d components, %d triangles" % (len(files), len(tris)))
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    print("bounding box (mm): %s -> %s  size %s" % (np.round(lo, 1), np.round(hi, 1),
                                                    np.round(hi - lo, 1)))

    q = np.round(tris.reshape(-1, 3) / WELD).astype(np.int64)
    q -= q.min(0)
    span = q.max(0) + 1
    key = (q[:, 0] * span[1] + q[:, 1]) * span[2] + q[:, 2]
    uniq, idx = np.unique(key, return_inverse=True)
    idx = idx.reshape(-1, 3)
    pos = np.zeros((len(uniq), 3))
    pos[idx.ravel()] = tris.reshape(-1, 3)
    print("%d welded vertices" % len(uniq))

    fn = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(fn, axis=1)
    good = ln > 1e-12
    fn[good] /= ln[good][:, None]

    a = idx[:, [0, 1, 2]].ravel()
    b = idx[:, [1, 2, 0]].ravel()
    lo_i, hi_i = np.minimum(a, b), np.maximum(a, b)
    face = np.repeat(np.arange(len(tris)), 3)
    ek = lo_i.astype(np.int64) * len(uniq) + hi_i
    order = np.argsort(ek, kind="stable")
    ek, lo_i, hi_i, face = ek[order], lo_i[order], hi_i[order], face[order]
    starts = np.flatnonzero(np.r_[True, ek[1:] != ek[:-1]])
    counts = np.diff(np.r_[starts, len(ek)])

    keep = np.zeros(len(starts), bool)
    keep[counts == 1] = True                       # open boundaries are outlines
    two = counts == 2
    s2 = starts[two]
    cos = (fn[face[s2]] * fn[face[s2 + 1]]).sum(1)
    keep[np.flatnonzero(two)] = cos < np.cos(np.radians(angle))
    keep[counts > 2] = True                        # where two bodies touch

    s = starts[keep]
    p1, p2 = pos[lo_i[s]], pos[hi_i[s]]
    L = np.linalg.norm(p2 - p1, axis=1)
    m = L >= min_len
    p1, p2 = p1[m], p2[m]
    print("%d edges kept (angle %.0f deg, min %.1f mm)" % (len(p1), angle, min_len))

    allp = np.vstack([p1, p2])
    c = (allp.min(0) + allp.max(0)) / 2
    ext = (allp.max(0) - allp.min(0)).max()
    seg = (np.stack([p1, p2], 1) - c) / ext
    seg = seg[:, :, [0, 2, 1]] * [1, 1, -1]        # CAD z-up -> viewer y-up
    if roll:
        r = np.radians(roll)
        y, z = seg[..., 1].copy(), seg[..., 2].copy()
        seg[..., 1] = y * np.cos(r) - z * np.sin(r)
        seg[..., 2] = y * np.sin(r) + z * np.cos(r)
    seg.astype("<f4").tofile(OUT)
    print("wrote %s  %.0f KB" % (os.path.relpath(OUT, HERE), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
