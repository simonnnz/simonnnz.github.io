"""
Reads models.txt and rebuilds every wireframe listed in it.

    python build.py            rebuild everything
    python build.py chess      rebuild only names containing "chess"

Nothing here needs installing -- standard library only.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))

from extract_edges import extract

CONFIG = os.path.join(HERE, "models.txt")
OUTDIR = os.path.join(HERE, "edges")


def parse():
    rows = []
    with open(CONFIG, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            bits = [b.strip() for b in line.split("|")]
            if len(bits) != 4:
                print("  line %d: expected 4 fields separated by | -- skipped" % lineno)
                continue
            name, src, angle, minlen = bits
            src = os.path.expandvars(src)      # models.txt uses %USERPROFILE%
            try:
                rows.append({
                    "name": name,
                    "src": src,
                    "angle": float(angle),
                    "minlen": float(minlen),
                    "line": lineno,
                })
            except ValueError:
                print("  line %d: angle and min length must be numbers -- skipped" % lineno)
    return rows


def main():
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None

    if not os.path.isdir(OUTDIR):
        os.makedirs(OUTDIR)

    rows = parse()
    if only:
        rows = [r for r in rows if only in r["name"].lower()]
        print("filtering to names containing %r\n" % only)

    if not rows:
        print("nothing to build -- check models.txt")
        return 1

    ok = 0
    failed = []
    for r in rows:
        print("%s" % r["name"])
        if not os.path.isfile(r["src"]):
            print("  SOURCE NOT FOUND: %s" % r["src"])
            print("  (models.txt line %d)\n" % r["line"])
            failed.append(r["name"])
            continue
        out = os.path.join(OUTDIR, r["name"] + ".bin")
        try:
            extract(r["src"], out, r["angle"], r["minlen"])
            ok += 1
        except Exception as exc:
            print("  FAILED: %s" % exc)
            failed.append(r["name"])
        print()

    print("-" * 60)
    print("built %d of %d" % (ok, len(rows)))
    if failed:
        print("failed: %s" % ", ".join(failed))
    print("\nRefresh the page to see the changes.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
