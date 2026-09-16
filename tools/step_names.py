"""
List the solids in a STEP file with the part names the CAD gave them.

The plain STEP reader throws names away. Reading through XCAF keeps them, which
turns "solid 68" into "Top Plate" -- the difference between guessing which body
is the hinged lid and simply knowing.

    python step_names.py model.step
    python step_names.py model.step --grep flap
"""

import sys
import os

from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def label_name(label):
    from OCP.Standard import Standard_GUID
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return ""


def load(path):
    doc = TDocStd_Document(TCollection_ExtendedString("step"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(False)
    reader.SetLayerMode(False)
    if not reader.ReadFile(path):
        raise RuntimeError("could not read %s" % path)
    reader.Transfer(doc)
    return doc


def info(shape):
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, m)
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    lo, hi = box.CornerMin(), box.CornerMax()
    size = [hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z()]
    ctr = [(hi.X() + lo.X()) / 2, (hi.Y() + lo.Y()) / 2, (hi.Z() + lo.Z()) / 2]
    return m.Extent(), size, ctr


def walk(tool, label, out, prefix=""):
    name = label_name(label) or "(unnamed)"
    full = (prefix + " / " + name) if prefix else name

    if tool.IsAssembly_s(label):
        children = TDF_LabelSequence()
        tool.GetComponents_s(label, children)
        for i in range(1, children.Length() + 1):
            child = children.Value(i)
            ref = TDF_Label()
            if tool.GetReferredShape_s(child, ref):
                walk(tool, ref, out, full)
            else:
                walk(tool, child, out, full)
        return

    try:
        shape = tool.GetShape_s(label)
    except Exception:
        return
    if shape is None or shape.IsNull():
        return

    sm = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_SOLID, sm)
    if sm.Extent() == 0:
        return
    out.append((full, shape))


def main():
    path = sys.argv[1]
    grep = None
    if "--grep" in sys.argv:
        grep = sys.argv[sys.argv.index("--grep") + 1].lower()

    print(os.path.basename(path))
    doc = load(path)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)

    found = []
    for i in range(1, roots.Length() + 1):
        walk(tool, roots.Value(i), found)

    rows = []
    for (name, shape) in found:
        n, size, ctr = info(shape)
        rows.append((name, n, size, ctr))
    rows.sort(key=lambda r: -r[1])

    if grep:
        rows = [r for r in rows if grep in r[0].lower()]
        print("  filtered to names containing %r" % grep)

    print("  %d part(s)\n" % len(rows))
    print("      edges     size (x, y, z)              centre (x, y, z)     name")
    for (name, n, size, ctr) in rows[:40]:
        print("  %9s  %6.1f %6.1f %6.1f   %7.1f %7.1f %7.1f    %s"
              % (format(n, ","), size[0], size[1], size[2],
                 ctr[0], ctr[1], ctr[2], name))
    if len(rows) > 40:
        print("  ... and %d more" % (len(rows) - 40))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main()
