r"""
Exports a SolidWorks document to STL, without modifying it.

    python tools\solidworks_export.py "<path to .SLDASM>" <out.stl>
    python tools\solidworks_export.py --active <out.stl>      (use the open document)

Opens the document read-only through the SolidWorks API, writes one STL for
the whole assembly, then closes it. It never saves the original: the file is
opened with the read-only flag and closed with CloseDoc, which discards
anything SolidWorks did on open (a rebuild, a resolved reference). Nothing in
the CAD tree is written except the STL, which goes where you point it.

A big assembly can take minutes to open, so --active reuses a document that is
already open rather than paying that twice.

Needs SolidWorks installed and licensed, and `pip install pywin32`.
"""

import os
import sys
import time

import pythoncom
import win32com.client as win32

DOC_ASSEMBLY = 2
DOC_PART = 1
OPEN_READONLY = 2
OPEN_SILENT = 1
SAVE_SILENT = 1                       # swSaveAsOptions_Silent


def prop(obj, name):
    """Late binding gives properties, not accessors; call only if callable."""
    v = getattr(obj, name)
    return v() if callable(v) else v


def main():
    args = sys.argv[1:]
    use_active = args[0] == "--active"
    src = None if use_active else os.path.abspath(args[0])
    out = os.path.abspath(args[1])
    os.makedirs(os.path.dirname(out), exist_ok=True)

    pythoncom.CoInitialize()
    if use_active:
        sw = win32.GetActiveObject("SldWorks.Application")
    else:
        sw = win32.Dispatch("SldWorks.Application")
    sw.Visible = True                 # a hidden licence prompt would hang forever
    print("SolidWorks %s" % prop(sw, "RevisionNumber"))

    if use_active:
        doc = sw.ActiveDoc
        if doc is None:
            raise SystemExit("no document open in SolidWorks")
        print("using the open document: %s" % prop(doc, "GetTitle"))
    else:
        kind = DOC_ASSEMBLY if src.lower().endswith(".sldasm") else DOC_PART
        print("opening (read-only) %s" % src)
        t0 = time.time()
        errs = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warns = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        doc = sw.OpenDoc6(src, kind, OPEN_READONLY | OPEN_SILENT, "", errs, warns)
        if doc is None:
            raise SystemExit("open failed, error %s warning %s" % (errs.value, warns.value))
        print("  opened in %.0f s (errors %s, warnings %s)" % (time.time() - t0, errs.value, warns.value))

    title = prop(doc, "GetTitle")
    err = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    t0 = time.time()
    # the export-data argument is a typed null, not Python's None
    nothing = win32.VARIANT(pythoncom.VT_DISPATCH, None)
    ok = doc.Extension.SaveAs(out, 0, SAVE_SILENT, nothing, err, warn)
    print("export %s in %.0f s (error %s, warning %s)" % (
        "ok" if ok else "FAILED", time.time() - t0, err.value, warn.value))

    sw.CloseDoc(title)                # closes without saving the original
    print("closed %s" % title)
    if not ok or not os.path.isfile(out):
        raise SystemExit(1)
    print("%s  %.1f MB" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
