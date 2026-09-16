"""
STEP -> exact feature edges.

STEP is a boundary representation: it stores every edge explicitly, as real
geometry (a line, a circle, a spline) rather than as a difference between
triangles. So there is nothing to infer here -- no angle threshold, no
planar/curved classification, no noise filtering, no simplification. We read
the edges the CAD kernel already knows about and sample each curve just finely
enough that it looks smooth.

That also means a fillet's tangent seam comes out for free. It's a real edge in
the file, sitting alongside the sharp ones.

Output matches extract_edges.py exactly -- a flat little-endian float32 blob of
line-segment endpoints, normalised so the model is centred and its largest
dimension is 1.0 -- so the viewer needs no changes.

    python step_edges.py model.step out.bin
    python step_edges.py model.step --list           list the solids
    python step_edges.py model.step out.bin --solid 3
    python step_edges.py model.step out.bin --ref whole.step

Needs OpenCASCADE:  pip install cadquery-ocp
"""

import struct
import sys
import os
import math

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_TangentialDeflection
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def named_parts(path):
    """[(full assembly path, shape)] via XCAF, which keeps the CAD's own names.
    Lets us split on what the model actually is rather than on which lumps of
    triangles happen to touch."""
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_LabelSequence, TDF_Label
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopAbs import TopAbs_SOLID

    doc = TDocStd_Document(TCollection_ExtendedString("step"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if not reader.ReadFile(path):
        raise RuntimeError("could not read %s" % path)
    reader.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name_of(label):
        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            return attr.Get().ToExtString()
        return ""

    out = []

    def walk(label, prefix=""):
        nm = name_of(label) or "(unnamed)"
        full = (prefix + " / " + nm) if prefix else nm
        if tool.IsAssembly_s(label):
            kids = TDF_LabelSequence()
            tool.GetComponents_s(label, kids)
            for i in range(1, kids.Length() + 1):
                kid = kids.Value(i)
                ref = TDF_Label()
                walk(ref if tool.GetReferredShape_s(kid, ref) else kid, full)
            return
        try:
            sh = tool.GetShape_s(label)
        except Exception:
            return
        if sh is None or sh.IsNull():
            return
        sm = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(sh, TopAbs_SOLID, sm)
        if sm.Extent():
            out.append((full, sh))

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i))
    return out


def compound(shapes):
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for s in shapes:
        b.Add(comp, s)
    return comp


def read_step(path):
    reader = STEPControl_Reader()
    status = reader.ReadFile(path)
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError("could not read %s (status %s)" % (path, status))
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError("%s produced an empty shape" % path)
    return shape


def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    lo, hi = box.CornerMin(), box.CornerMax()
    return ([lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()])


def solids(shape):
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_SOLID, m)
    return [TopoDS.Solid_s(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def edges_of(shape):
    """Every distinct edge. Mapping rather than exploring means an edge shared
    by two faces is returned once, not twice."""
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, m)
    return [TopoDS.Edge_s(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def sample(edge, ang_defl, curv_defl):
    """Points along one edge, spaced by how much the curve is actually
    bending. A straight line gets two points; a tight arc gets as many as it
    needs. This is where STEP beats a mesh -- the sampling is chosen for the
    display, not inherited from whatever the exporter felt like."""
    if BRep_Tool.Degenerated_s(edge):
        return []
    try:
        adaptor = BRepAdaptor_Curve(edge)
    except Exception:
        return []
    try:
        d = GCPnts_TangentialDeflection(adaptor, ang_defl, curv_defl, 2)
        n = d.NbPoints()
        if n < 2:
            return []
        return [(d.Value(i).X(), d.Value(i).Y(), d.Value(i).Z())
                for i in range(1, n + 1)]
    except Exception:
        # fall back to uniform sampling if the adaptive routine refuses
        try:
            u0, u1 = adaptor.FirstParameter(), adaptor.LastParameter()
            pts = []
            for i in range(9):
                p = adaptor.Value(u0 + (u1 - u0) * i / 8.0)
                pts.append((p.X(), p.Y(), p.Z()))
            return pts
        except Exception:
            return []


def extract(path, out_path, solid_index=None, ref=None,
            ang_deg=12.0, curv_frac=0.0012, min_len=0.0,
            part=None, exclude=None):
    shape = read_step(path)

    target = shape
    if part or exclude:
        parts = named_parts(path)
        needle = (part or exclude).lower()
        hit = [s for (n, s) in parts if needle in n.lower()]
        miss = [s for (n, s) in parts if needle not in n.lower()]
        chosen = hit if part else miss
        print("  %s %r: %d of %d parts"
              % ("matching" if part else "excluding", part or exclude,
                 len(chosen), len(parts)))
        if not chosen:
            raise RuntimeError("no parts selected")
        target = compound(chosen)
    elif solid_index is not None:
        sl = solids(shape)
        if solid_index < 0 or solid_index >= len(sl):
            raise IndexError("solid %d out of range (%d solids)"
                             % (solid_index, len(sl)))
        target = sl[solid_index]
        print("  solid %d of %d" % (solid_index, len(sl)))

    lo, hi = bounds(read_step(ref) if ref else shape)
    if ref:
        print("  normalising against %s" % os.path.basename(ref))
    extent = max(hi[a] - lo[a] for a in range(3)) or 1.0
    centre = [(hi[a] + lo[a]) / 2.0 for a in range(3)]
    print("  frame: centre %.2f %.2f %.2f, extent %.2f"
          % (centre[0], centre[1], centre[2], extent))

    ang = math.radians(ang_deg)
    curv = extent * curv_frac
    min_len_abs = min_len * extent

    ed = edges_of(target)
    print("  %s edges in the B-rep" % format(len(ed), ","))

    out = []
    segments = 0
    skipped = 0
    dropped = 0

    for e in ed:
        pts = sample(e, ang, curv)
        if len(pts) < 2:
            skipped += 1
            continue
        if min_len_abs > 0.0:
            total = 0.0
            for i in range(len(pts) - 1):
                dx = pts[i + 1][0] - pts[i][0]
                dy = pts[i + 1][1] - pts[i][1]
                dz = pts[i + 1][2] - pts[i][2]
                total += math.sqrt(dx * dx + dy * dy + dz * dz)
            if total < min_len_abs:
                dropped += 1
                continue
        for i in range(len(pts) - 1):
            for p in (pts[i], pts[i + 1]):
                out.append((p[0] - centre[0]) / extent)
                out.append((p[1] - centre[1]) / extent)
                out.append((p[2] - centre[2]) / extent)
            segments += 1

    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<%df" % len(out), *out))

    src_kb = os.path.getsize(path) / 1024.0
    dst_kb = os.path.getsize(out_path) / 1024.0
    if dropped:
        print("  dropped %s edges shorter than %.3f of extent"
              % (format(dropped, ","), min_len))
    if skipped:
        print("  skipped %s degenerate edges" % format(skipped, ","))
    print("  %s segments" % format(segments, ","))
    print("  %.0f KB -> %.0f KB  (%.1f%% of the STEP)"
          % (src_kb, dst_kb, 100.0 * dst_kb / src_kb))
    return segments


def list_solids(path):
    shape = read_step(path)
    sl = solids(shape)
    print("  %d solid(s)" % len(sl))
    print()
    print("   #      edges     size (x, y, z)              centre (x, y, z)")
    rows = []
    for i, s in enumerate(sl):
        lo, hi = bounds(s)
        rows.append((i, len(edges_of(s)),
                     [hi[a] - lo[a] for a in range(3)],
                     [(hi[a] + lo[a]) / 2.0 for a in range(3)]))
    rows.sort(key=lambda r: -r[1])
    for (i, n, size, c) in rows[:30]:
        print("  %2d  %9s   %7.1f %7.1f %7.1f     %7.1f %7.1f %7.1f"
              % (i, format(n, ","), size[0], size[1], size[2], c[0], c[1], c[2]))
    if len(rows) > 30:
        print("  ... and %d more" % (len(rows) - 30))


def arg(name, default, cast=float):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = sys.argv[1]
    print(os.path.basename(src))

    if "--list" in sys.argv:
        list_solids(src)
        sys.exit(0)

    extract(
        src, sys.argv[2],
        solid_index=arg("--solid", None, int),
        ref=arg("--ref", None, str),
        ang_deg=arg("--angular", 12.0),
        curv_frac=arg("--deflection", 0.0012),
        min_len=arg("--minlen", 0.0),
        part=arg("--part", None, str),
        exclude=arg("--except", None, str),
    )
