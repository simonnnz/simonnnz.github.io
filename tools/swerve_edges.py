r"""
Builds the CRC swerve module wireframes.

    python tools\swerve_edges.py

Reads the four STLs in "CRC Swerve Drive Model\" and writes edges\swerve-*.bin.

Unlike build.py, these parts are animated against each other, so they can't
each be centred on themselves. Everything goes into ONE shared frame instead:

    origin   the steering axis, at the height of the module's top plate
    axes     CAD is Z-up; the viewer is Y-up.  viewer (x, y, z) = (X, Z, -Y)
    scale    200 mm = 1 viewer unit

The fastener is the exception: it is written in its own part coordinates
(origin on the axis, at the underside of the head) because the page draws it
four times, placed at each finger's hole.

The numbers below were measured from the STLs, not typed from memory:
the axis is the centre of the module's bolt circle (eight insert holes on
r = 45.0 mm, mirrored about y = -184.91), and the finger's top face is z = 137.
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
from extract_edges import extract, extract_silhouettes

SRC = os.path.join(HERE, "CRC Swerve Drive Model")
OUT = os.path.join(HERE, "edges")

AXIS = (0.0, -184.91, 120.0)    # mm, CAD coordinates
SCALE = 200.0                   # mm per viewer unit

PARTS = [
    # out name          STL                    angle  min len  frame
    # (a length filter breaks edge chains apart, and simplifying the broken
    #  chains draws long stray lines across the model -- keep it at 0 here)
    ("swerve-outer",   "Outer Chassie.stl",    32,    0.0,     AXIS),
    ("swerve-module",  "Swerve Chassie.stl",   32,    0.0,     AXIS),
    ("swerve-finger",  "Bearing Finger.stl",   32,    0.0,     AXIS),
    ("swerve-screw",   "Finger Fastener.stl",  40,    0.0,     (0.0, 0.0, 0.0)),
]


# outline candidates shorter than this (mm) are fillet and thread facets,
# too small to read as an outline; legs and shafts are all far longer
SIL_MIN_LEN = {"swerve-outer": 2.0, "swerve-module": 2.0, "swerve-screw": 0.8}


def to_viewer(path):
    """Rewrite a CAD-frame .bin as Y-up viewer coordinates, in place."""
    with open(path, "rb") as fh:
        blob = fh.read()
    n = len(blob) // 4
    v = struct.unpack("<%df" % n, blob)
    out = []
    for i in range(0, n, 3):
        x, y, z = v[i], v[i + 1], v[i + 2]
        out += (x, z, -y)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<%df" % n, *out))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, stl, angle, minlen, origin in PARTS:
        print(name)
        dst = os.path.join(OUT, name + ".bin")
        extract(os.path.join(SRC, stl), dst, angle_deg=angle, min_len=minlen,
                frame=(origin, SCALE), simplify=0.0015, tangents=False)
        to_viewer(dst)
        # hard edges alone draw a cylinder as two loose circles; these are the
        # smooth edges the page turns into live outlines (see extract_silhouettes)
        extract_silhouettes(os.path.join(SRC, stl), os.path.join(OUT, name + ".sil.bin"),
                            (origin, SCALE), max_deg=angle,
                            min_len=SIL_MIN_LEN.get(name, 0.0), y_up=True)
        print()


if __name__ == "__main__":
    main()
