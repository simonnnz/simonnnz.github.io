"""
STL -> feature-edge extractor.

Keeps two kinds of edge:

  1. HARD edges     - the two faces meeting there diverge by more than the
                      angle threshold. Corners, steps, holes.

  2. TANGENT edges  - the boundary where a flat face meets a rounded blend.
                      These are nearly smooth, so an angle threshold either
                      misses them entirely or drags in every tessellation line
                      across the fillet with them.

The second one is what makes CAD look like CAD, and no angle threshold can
find it -- the seam is nearly smooth, so any cutoff low enough to catch it also
catches every tessellation line inside the fillet.

Instead each face is classified planar or curved, judged by the largest smooth
dihedral on its OTHER edges (the edge being tested is excluded, or it would
prop up its own verdict). An edge is kept when exactly one side is planar.
Being binary, this doesn't care how finely the fillet is tessellated -- a
coarse blend and a fine one are both simply "not flat".

Creases are excluded from that judgement too. Without that, a flat triangle
touching a 90 deg corner scores as curved and a phantom line appears alongside
every real edge.

Output is a flat little-endian float32 blob of line-segment endpoints:

    [x1,y1,z1, x2,y2,z2,  x1,y1,z1, x2,y2,z2,  ...]

normalised so the model is centred and its largest dimension is 1.0.

Pure standard library. Uses numpy if present, but does not need it.

    python extract_edges.py "in.stl" out.bin [--angle 26] [--minlen 0.005]
                                             [--curve 3.5] [--ref other.stl]
"""

import struct
import sys
import math
import os

try:
    import numpy as np
except ImportError:
    np = None


def read_binary_stl(path):
    """Return (count, [9 floats per triangle])."""
    with open(path, "rb") as fh:
        blob = fh.read()

    if len(blob) < 84:
        raise ValueError("file too short to be a binary STL")

    count = struct.unpack_from("<I", blob, 80)[0]
    expected = 84 + count * 50
    if len(blob) != expected:
        raise ValueError(
            "not a binary STL (size %d, expected %d for %d triangles) "
            "- ASCII STL is not supported" % (len(blob), expected, count)
        )

    if np is not None:
        dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        arr = np.frombuffer(blob, dtype=dt, count=count, offset=84)
        return count, arr["v"].reshape(count, 9).tolist()

    tris = []
    off = 84
    for _ in range(count):
        tris.append(list(struct.unpack_from("<9f", blob, off + 12)))
        off += 50
    return count, tris


def bounds_of(path):
    """Bounding box of an STL, as (lo, hi). Used to normalise several files
    into one shared coordinate frame so split parts still line up."""
    _, tris = read_binary_stl(path)
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for t in tris:
        for c in range(3):
            for a in range(3):
                v = t[c * 3 + a]
                if v < lo[a]:
                    lo[a] = v
                if v > hi[a]:
                    hi[a] = v
    return lo, hi


def _douglas_peucker(pts, tol):
    """Drop points that sit within `tol` of the straight line they lie on.
    Iterative so a long chain can't blow the recursion limit."""
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    tol2 = tol * tol

    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay, az = pts[i]
        bx, by, bz = pts[j]
        dx, dy, dz = bx - ax, by - ay, bz - az
        seg2 = dx * dx + dy * dy + dz * dz
        best = -1.0
        bi = -1
        for m in range(i + 1, j):
            px, py, pz = pts[m]
            if seg2 > 1e-24:
                t = ((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / seg2
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                cx, cy, cz = ax + dx * t, ay + dy * t, az + dz * t
            else:
                cx, cy, cz = ax, ay, az
            ex, ey, ez = px - cx, py - cy, pz - cz
            d = ex * ex + ey * ey + ez * ez
            if d > best:
                best, bi = d, m
        if best > tol2:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))

    return [pts[i] for i in range(n) if keep[i]]


def _simplify(kept, tol):
    """kept: list of (keyA, keyB, posA, posB).

    Tangent boundaries come out as long chains of tiny segments following a
    curve. Stitching each chain back together and simplifying it is where the
    real size saving is -- a filleted corner needs a handful of segments, not
    the twenty the tessellation used."""
    adj = {}
    pos = {}
    for (ka, kb, pa, pb) in kept:
        adj.setdefault(ka, []).append(kb)
        adj.setdefault(kb, []).append(ka)
        pos[ka] = pa
        pos[kb] = pb

    seen = set()

    def ek(a, b):
        return (a, b) if a < b else (b, a)

    def walk(start, first):
        chain = [start]
        prev, cur = start, first
        while True:
            e = ek(prev, cur)
            if e in seen:
                break
            seen.add(e)
            chain.append(cur)
            nb = adj[cur]
            if len(nb) != 2:
                break
            nxt = nb[0] if nb[1] == prev else nb[1]
            prev, cur = cur, nxt
        return chain

    chains = []
    # junctions and free ends first, so chains break at corners rather than
    # smoothing straight through them
    for k in adj:
        if len(adj[k]) != 2:
            for nb in adj[k]:
                if ek(k, nb) not in seen:
                    chains.append(walk(k, nb))
    # whatever's left is a closed loop
    for k in adj:
        for nb in adj[k]:
            if ek(k, nb) not in seen:
                chains.append(walk(k, nb))

    out = []
    for ch in chains:
        pts = [pos[k] for k in ch]
        # Break where the chain turns hard before simplifying. Without this,
        # Douglas-Peucker happily draws one straight line across a chain that
        # doubles back on itself -- which is exactly the long spurious strokes
        # spanning the whole model.
        for run in _split_at_corners(pts, 35.0):
            simp = _douglas_peucker(run, tol)
            for i in range(len(simp) - 1):
                out.append((simp[i], simp[i + 1]))
    return out


def _split_at_corners(pts, max_turn_deg):
    """Cut a point chain wherever it turns by more than max_turn_deg."""
    if len(pts) < 3:
        return [pts]
    limit = math.cos(math.radians(max_turn_deg))
    runs = []
    start = 0
    for i in range(1, len(pts) - 1):
        ax = pts[i][0] - pts[i - 1][0]
        ay = pts[i][1] - pts[i - 1][1]
        az = pts[i][2] - pts[i - 1][2]
        bx = pts[i + 1][0] - pts[i][0]
        by = pts[i + 1][1] - pts[i][1]
        bz = pts[i + 1][2] - pts[i][2]
        la = math.sqrt(ax * ax + ay * ay + az * az)
        lb = math.sqrt(bx * bx + by * by + bz * bz)
        if la < 1e-12 or lb < 1e-12:
            continue
        c = (ax * bx + ay * by + az * bz) / (la * lb)
        if c < limit:
            runs.append(pts[start:i + 1])
            start = i
    runs.append(pts[start:])
    return [r for r in runs if len(r) > 1]


def extract(path, out_path, angle_deg=26.0, min_len=0.0, ref=None,
            curve_deg=1.5, simplify=0.004, frame=None, tangents=True):
    """frame: optional (centre, extent) to normalise against, so several parts
    of one assembly share a coordinate system. Overrides ref. An extent of 1.0
    with a zero centre writes raw model units."""
    count, tris = read_binary_stl(path)
    print("  %s triangles" % format(count, ","))

    # ---- bounds ----
    if frame:
        centre, extent = list(frame[0]), float(frame[1])
        lo = [centre[a] - extent / 2.0 for a in range(3)]
        hi = [centre[a] + extent / 2.0 for a in range(3)]
    elif ref:
        lo, hi = bounds_of(ref)
        print("  normalising against %s" % os.path.basename(ref))
    else:
        lo = [float("inf")] * 3
        hi = [float("-inf")] * 3
        for t in tris:
            for c in range(3):
                for a in range(3):
                    v = t[c * 3 + a]
                    if v < lo[a]:
                        lo[a] = v
                    if v > hi[a]:
                        hi[a] = v

    if not frame:
        size = [hi[a] - lo[a] for a in range(3)]
        extent = max(size) or 1.0
        centre = [(hi[a] + lo[a]) / 2.0 for a in range(3)]

    quant = extent * 1e-5
    inv_quant = 1.0 / quant

    def key(x, y, z):
        return (int(round(x * inv_quant)),
                int(round(y * inv_quant)),
                int(round(z * inv_quant)))

    # ---- pass 1: face normals, and edge -> the two faces sharing it ----
    normals = [None] * count
    edges = {}
    degenerate = 0

    for fi, t in enumerate(tris):
        ax, ay, az = t[0], t[1], t[2]
        bx, by, bz = t[3], t[4], t[5]
        cx, cy, cz = t[6], t[7], t[8]

        ux, uy, uz = bx - ax, by - ay, bz - az
        wx, wy, wz = cx - ax, cy - ay, cz - az
        nx = uy * wz - uz * wy
        ny = uz * wx - ux * wz
        nz = ux * wy - uy * wx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-20:
            degenerate += 1
            continue
        normals[fi] = (nx / ln, ny / ln, nz / ln)

        corners = ((key(ax, ay, az), (ax, ay, az)),
                   (key(bx, by, bz), (bx, by, bz)),
                   (key(cx, cy, cz), (cx, cy, cz)))

        for i in range(3):
            k1, p1 = corners[i]
            k2, p2 = corners[(i + 1) % 3]
            if k1 == k2:
                continue
            ek = (k1, k2) if k1 < k2 else (k2, k1)
            slot = edges.get(ek)
            if slot is None:
                edges[ek] = [(p1, p2), fi, -1]
            elif slot[2] < 0:
                slot[2] = fi

    if degenerate:
        print("  skipped %d degenerate triangles" % degenerate)

    # ---- pass 2: dihedral per edge, and per-face "how bent is it here" ----
    # A flat face scores ~0. A facet inside a fillet scores the per-facet angle.
    # Per face, the two largest smooth dihedrals on its own edges. Two are
    # needed so that when testing edge e we can ask "how bent is this face
    # ignoring e" -- otherwise every edge props up its own faces' scores and
    # nothing ever disagrees.
    top1 = [0.0] * count
    top2 = [0.0] * count
    thetas = {}

    def note(f, th):
        if th > top1[f]:
            top2[f] = top1[f]; top1[f] = th
        elif th > top2[f]:
            top2[f] = th

    def bend_excluding(f, th):
        return top2[f] if th >= top1[f] - 1e-9 else top1[f]

    for ek, rec in edges.items():
        f1, f2 = rec[1], rec[2]
        if f2 < 0 or normals[f1] is None or normals[f2] is None:
            thetas[ek] = None                    # naked edge
            continue
        n1, n2 = normals[f1], normals[f2]
        d = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
        if d > 1.0:
            d = 1.0
        elif d < -1.0:
            d = -1.0
        th = math.degrees(math.acos(d))
        thetas[ek] = th
        # Creases must NOT count toward roughness. A flat triangle touching a
        # 90 deg corner would otherwise score ~30, disagree wildly with the
        # flat triangle next to it, and produce a phantom line beside every
        # real edge. Roughness is about smooth bending only.
        if th <= angle_deg:
            note(f1, th)
            note(f2, th)

    # ---- pass 3: decide ----
    kept = []
    n_hard = n_tangent = n_naked = 0
    dropped_short = 0
    min_len_abs = min_len * extent
    # Tangent boundaries trace curves, so their segments are short by nature --
    # a 3 mm fillet on a 500 mm board tessellates into sub-millimetre pieces.
    # The length filter exists to kill thread and hole noise, which is all
    # hard-edged, so curves are exempt from it entirely. Chain simplification
    # is what controls their count instead.
    min_len_tan = 0.0

    for ek, rec in edges.items():
        th = thetas[ek]
        keep = False
        tangent = False

        if th is None:
            keep = True
            n_naked += 1
        elif th > angle_deg:
            keep = True
            n_hard += 1
        elif tangents:
            # Is this the seam where a flat face meets a rounded blend?
            # Judge each side by how bent it is ignoring this edge, then keep
            # only when exactly one side is planar. Binary, so it doesn't care
            # how finely the fillet happens to be tessellated.
            flat1 = bend_excluding(rec[1], th) < curve_deg
            flat2 = bend_excluding(rec[2], th) < curve_deg
            if flat1 != flat2:
                keep = True
                tangent = True
                n_tangent += 1

        if not keep:
            continue

        limit = min_len_tan if tangent else min_len_abs
        if limit > 0.0:
            p1, p2 = rec[0]
            dx, dy, dz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
            if (dx * dx + dy * dy + dz * dz) < (limit * limit):
                dropped_short += 1
                if tangent:
                    n_tangent -= 1
                elif th is None:
                    n_naked -= 1
                else:
                    n_hard -= 1
                continue

        p1, p2 = rec[0]
        kept.append((ek[0], ek[1], p1, p2))

    raw = len(kept)

    # ---- pass 4: stitch chains and simplify ----
    if simplify > 0.0:
        pairs = _simplify(kept, simplify * extent)
    else:
        pairs = [(k[2], k[3]) for k in kept]

    out = []
    for (p1, p2) in pairs:
        for p in (p1, p2):
            out.append((p[0] - centre[0]) / extent)
            out.append((p[1] - centre[1]) / extent)
            out.append((p[2] - centre[2]) / extent)

    segments = len(out) // 6
    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<%df" % len(out), *out))

    src_kb = os.path.getsize(path) / 1024.0
    dst_kb = os.path.getsize(out_path) / 1024.0
    if dropped_short:
        print("  dropped %s edges below the length filter" % format(dropped_short, ","))
    print("  found %s edges: %s hard (>%.0f deg), %s tangent, %s open"
          % (format(raw, ","), format(n_hard, ","), angle_deg,
             format(n_tangent, ","), format(n_naked, ",")))
    if simplify > 0.0:
        print("  simplified to %s segments (%.0f%% fewer)"
              % (format(segments, ","), 100.0 * (1.0 - float(segments) / max(raw, 1))))
    print("  %.0f KB -> %.0f KB  (%.1f%% of original)"
          % (src_kb, dst_kb, 100.0 * dst_kb / src_kb))
    return segments


SIL_POS = 32000.0     # int16 position scale: viewer units * SIL_POS
SIL_NRM = 127.0       # int8 normal scale


def extract_silhouettes(path, out_path, frame, max_deg=32.0, min_deg=1.0,
                        min_len=0.0, y_up=False):
    """Smooth edges that can become OUTLINES, depending on the view.

    A hard-edge wireframe draws a cylinder as two floating circles: its side is
    smooth, so no edge on it is "hard". What the eye expects is the cylinder's
    silhouette, and that depends on where you look from. So instead of picking
    lines here, keep every edge on a curved surface together with the normals
    of its two faces; the page's shader draws an edge only when one face points
    toward the camera and the other away.

    Record per edge, little-endian, 18 bytes:
        p1 int16 x3, p2 int16 x3   position * SIL_POS (normalised like extract)
        n1 int8  x3, n2 int8  x3   unit face normals * SIL_NRM

    frame: (centre, extent) as in extract. min_len is in model units (mm).
    y_up: rotate CAD Z-up into the viewer's Y-up, (x, y, z) -> (x, z, -y).
    Needs numpy.
    """
    if np is None:
        raise RuntimeError("extract_silhouettes needs numpy")
    with open(path, "rb") as fh:
        blob = fh.read()
    count = struct.unpack_from("<I", blob, 80)[0]
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    V = np.frombuffer(blob, dtype=dt, count=count, offset=84)["v"].astype(np.float64)

    N = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    L = np.linalg.norm(N, axis=1)
    ok = L > 1e-12
    V, N = V[ok], N[ok] / L[ok, None]

    # shared vertices -> ids, then each edge -> the two faces that use it
    q = np.round(V.reshape(-1, 3) / (np.ptp(V.reshape(-1, 3), axis=0).max() * 1e-6)).astype(np.int64)
    _, ids = np.unique(q, axis=0, return_inverse=True)
    ids = ids.reshape(-1, 3)
    a = ids
    b = np.roll(ids, -1, axis=1)
    lo, hi = np.minimum(a, b).ravel(), np.maximum(a, b).ravel()
    face = np.repeat(np.arange(len(ids)), 3)
    corner = np.tile([0, 1, 2], len(ids))
    order = np.lexsort((hi, lo))
    lo, hi, face, corner = lo[order], hi[order], face[order], corner[order]
    pair = np.nonzero((lo[1:] == lo[:-1]) & (hi[1:] == hi[:-1]))[0]

    f1, f2, c = face[pair], face[pair + 1], corner[pair]
    th = np.degrees(np.arccos(np.clip((N[f1] * N[f2]).sum(1), -1.0, 1.0)))
    p1 = V[f1, c]
    p2 = V[f1, (c + 1) % 3]
    keep = (th > min_deg) & (th <= max_deg) & (np.linalg.norm(p2 - p1, axis=1) >= min_len)
    p1, p2, n1, n2 = p1[keep], p2[keep], N[f1[keep]], N[f2[keep]]

    centre, extent = np.array(frame[0], float), float(frame[1])
    p1 = (p1 - centre) / extent
    p2 = (p2 - centre) / extent
    if y_up:
        swap = lambda m: np.c_[m[:, 0], m[:, 2], -m[:, 1]]
        p1, p2, n1, n2 = swap(p1), swap(p2), swap(n1), swap(n2)

    rec = np.zeros(len(p1), dtype=[("p", "<i2", 6), ("n", "i1", 6)])
    rec["p"] = np.clip(np.round(np.c_[p1, p2] * SIL_POS), -32767, 32767)
    rec["n"] = np.clip(np.round(np.c_[n1, n2] * SIL_NRM), -127, 127)
    rec.tofile(out_path)
    print("  %s outline candidates, %.0f KB" % (format(len(rec), ","), os.path.getsize(out_path) / 1024.0))
    return len(rec)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    angle = 26.0
    minlen = 0.0
    curve = 1.5
    simp = 0.0016
    ref = None
    if "--angle" in sys.argv:
        angle = float(sys.argv[sys.argv.index("--angle") + 1])
    if "--minlen" in sys.argv:
        minlen = float(sys.argv[sys.argv.index("--minlen") + 1])
    if "--curve" in sys.argv:
        curve = float(sys.argv[sys.argv.index("--curve") + 1])
    if "--simplify" in sys.argv:
        simp = float(sys.argv[sys.argv.index("--simplify") + 1])
    if "--ref" in sys.argv:
        ref = sys.argv[sys.argv.index("--ref") + 1]
    print(os.path.basename(sys.argv[1]))
    extract(sys.argv[1], sys.argv[2], angle, minlen, ref, curve, simp)
