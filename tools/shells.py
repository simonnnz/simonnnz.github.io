"""
Find disconnected shells in a binary STL.

Two triangles belong to the same shell if they share a welded vertex. A hinged
lid, a separate bracket, or any part exported as its own solid shows up here as
its own shell -- which means it can be split out and animated independently
without anyone re-exporting anything.

    python shells.py "model.stl"              # report only
    python shells.py "model.stl" --dump out/  # also write shell_NN.stl
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_edges import read_binary_stl


def find_shells(path):
    count, tris = read_binary_stl(path)

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for t in tris:
        for c in range(3):
            for a in range(3):
                v = t[c * 3 + a]
                if v < lo[a]: lo[a] = v
                if v > hi[a]: hi[a] = v
    extent = max(hi[a] - lo[a] for a in range(3)) or 1.0
    inv = 1.0 / (extent * 1e-5)

    def key(x, y, z):
        return (int(round(x * inv)), int(round(y * inv)), int(round(z * inv)))

    # union-find over welded vertices
    parent = {}

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:          # path compression
            parent[a], a = root, parent[a]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    tri_keys = []
    for t in tris:
        ks = (key(t[0], t[1], t[2]), key(t[3], t[4], t[5]), key(t[6], t[7], t[8]))
        tri_keys.append(ks)
        for k in ks:
            if k not in parent:
                parent[k] = k
        union(ks[0], ks[1])
        union(ks[1], ks[2])

    groups = {}
    for i, ks in enumerate(tri_keys):
        groups.setdefault(find(ks[0]), []).append(i)

    shells = []
    for idx in groups.values():
        s_lo = [float("inf")] * 3
        s_hi = [float("-inf")] * 3
        for i in idx:
            t = tris[i]
            for c in range(3):
                for a in range(3):
                    v = t[c * 3 + a]
                    if v < s_lo[a]: s_lo[a] = v
                    if v > s_hi[a]: s_hi[a] = v
        shells.append({
            "tris": idx,
            "n": len(idx),
            "lo": s_lo,
            "hi": s_hi,
            "size": [s_hi[a] - s_lo[a] for a in range(3)],
            "centre": [(s_hi[a] + s_lo[a]) / 2.0 for a in range(3)],
        })

    shells.sort(key=lambda s: -s["n"])
    return count, tris, shells, (lo, hi)


def write_stl(path, tris, idx):
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", len(idx)))
        for i in idx:
            t = tris[i]
            fh.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            fh.write(struct.pack("<9f", *t))
            fh.write(struct.pack("<H", 0))


if __name__ == "__main__":
    src = sys.argv[1]
    print(os.path.basename(src))
    count, tris, shells, bounds = find_shells(src)
    print("  %s triangles, %d disconnected shell(s)" % (format(count, ","), len(shells)))
    print()
    print("   #   triangles     size (x, y, z)              centre (x, y, z)")
    for i, s in enumerate(shells[:25]):
        print("  %2d  %10s   %7.1f %7.1f %7.1f     %7.1f %7.1f %7.1f"
              % (i, format(s["n"], ","),
                 s["size"][0], s["size"][1], s["size"][2],
                 s["centre"][0], s["centre"][1], s["centre"][2]))
    if len(shells) > 25:
        print("  ... and %d more" % (len(shells) - 25))

    if "--split" in sys.argv:
        n = int(sys.argv[sys.argv.index("--split") + 1])
        out = sys.argv[sys.argv.index("--split") + 2]
        if not os.path.isdir(out):
            os.makedirs(out)

        part = shells[n]["tris"]
        rest = []
        for i, s in enumerate(shells):
            if i != n:
                rest.extend(s["tris"])

        write_stl(os.path.join(out, "part.stl"), tris, part)
        write_stl(os.path.join(out, "rest.stl"), tris, rest)
        print("\n  shell %d -> part.stl  (%s triangles)" % (n, format(len(part), ",")))
        print("  everything else -> rest.stl  (%s triangles)" % format(len(rest), ","))

        s = shells[n]
        print("\n  hinge candidates for shell %d (model units):" % n)
        print("    bounds  x %.1f .. %.1f" % (s["lo"][0], s["hi"][0]))
        print("            y %.1f .. %.1f" % (s["lo"][1], s["hi"][1]))
        print("            z %.1f .. %.1f" % (s["lo"][2], s["hi"][2]))
        # normalised into the same unit box the viewer uses
        full_lo, full_hi = bounds
        extent = max(full_hi[a] - full_lo[a] for a in range(3))
        centre = [(full_hi[a] + full_lo[a]) / 2.0 for a in range(3)]
        print("\n  same bounds in viewer space (unit box, model centred):")
        for a, ax in enumerate("xyz"):
            print("    %s %+.4f .. %+.4f"
                  % (ax, (s["lo"][a] - centre[a]) / extent,
                         (s["hi"][a] - centre[a]) / extent))

    if "--dump" in sys.argv:
        out = sys.argv[sys.argv.index("--dump") + 1]
        if not os.path.isdir(out):
            os.makedirs(out)
        for i, s in enumerate(shells[:25]):
            p = os.path.join(out, "shell_%02d.stl" % i)
            write_stl(p, tris, s["tris"])
        print("\n  wrote %d shell STLs to %s" % (min(25, len(shells)), out))
