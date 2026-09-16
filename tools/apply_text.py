"""
Puts the words from content.txt into index.html.

index.html carries markers like

    <!--@chess.lede-->  ...anything...  <!--/@-->

and this replaces whatever is between them with the matching entry from
content.txt. Everything outside the markers is left exactly as it is, so the
page keeps working and stays hand-editable.

Run it as many times as you like; it always produces the same result.

Standard library only.
"""

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(HERE, "content.txt")
PAGE = os.path.join(HERE, "index.html")
BACKUP = os.path.join(HERE, "index.backup.html")


# ---------------------------------------------------------------- parsing
def parse(path):
    """content.txt -> {key: value}. A value is a string, or a list of rows
    for the `|` separated blocks."""
    data = {}
    key = None
    buf = []

    def flush():
        if key is None:
            return
        text = "\n".join(buf).strip("\n")
        data[key] = text

    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()

            if stripped.startswith("#"):
                continue

            # "key:" or "key: value" at column 0 starts a new entry
            m = re.match(r"^([A-Za-z0-9_.\-]+):\s?(.*)$", line)
            if m and not line.startswith((" ", "\t")):
                flush()
                key = m.group(1)
                rest = m.group(2).strip()
                buf = [rest] if rest else []
                continue

            if key is not None:
                # inside a block: drop the common indent, keep blank lines
                buf.append(line[2:] if line.startswith("  ") else line)

    flush()
    return {k: v for k, v in data.items() if v != ""}


# ---------------------------------------------------------------- text -> html
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(s):
    """A very small amount of formatting, so you never have to type a tag."""
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)   # [text](url)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)            # **bold**
    s = re.sub(r"==([^=]+)==", r"<mark>\1</mark>", s)                    # ==needs work==
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)                      # `code`
    return s


def paragraphs(s, indent):
    """Blank line means new paragraph. The marker lives inside the first <p>,
    so paragraphs after the first close and reopen one."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", s) if p.strip()]
    joiner = "</p>\n" + " " * indent + "<p>"
    return joiner.join(inline(" ".join(p.split())) for p in parts)


def rows(s, sep="|"):
    out = []
    for line in s.split("\n"):
        line = line.strip()
        if not line:
            continue
        out.append([c.strip() for c in line.split(sep)])
    return out


def as_specs(s, indent):
    pad = " " * indent
    items = []
    for r in rows(s):
        if len(r) < 2:
            continue
        items.append("%s<li><b>%s</b><span>%s</span></li>" % (pad, inline(r[0]), inline(r[1])))
    return "\n" + "\n".join(items) + "\n" + " " * (indent - 2)


def as_awards(s, indent):
    pad = " " * indent
    items = []
    for r in rows(s):
        if len(r) < 2:
            continue
        items.append('%s<div class="award"><b>%s</b><span>%s</span></div>'
                     % (pad, inline(r[0]), inline(r[1])))
    return "\n" + "\n".join(items) + "\n" + " " * (indent - 2)


def as_log(s, indent):
    pad = " " * indent
    items = []
    for r in rows(s):
        if len(r) < 3:
            continue
        items.append(
            '%s<div class="log-item">\n'
            '%s  <time>%s</time>\n'
            '%s  <div><h4>%s</h4><p>%s</p></div>\n'
            '%s</div>' % (pad, pad, inline(r[0]), pad, inline(r[1]), inline(r[2]), pad))
    return "\n" + "\n".join(items) + "\n" + " " * (indent - 2)


def as_tags(s, indent):
    parts = [p.strip() for p in s.replace("\n", ",").split(",") if p.strip()]
    return "".join("<span>%s</span>" % inline(p) for p in parts)


SPECIAL = {"specs": as_specs, "awards": as_awards, "log": as_log, "disciplines": as_tags}


# ---------------------------------------------------------------- apply
MARKER = re.compile(r"(?P<open>[ \t]*)<!--@(?P<key>[A-Za-z0-9_.\-]+)-->"
                    r".*?<!--/@-->", re.S)


def main():
    if not os.path.isfile(CONTENT):
        print("content.txt not found next to index.html")
        return 1

    data = parse(CONTENT)
    page = open(PAGE, "r", encoding="utf-8").read()

    used = set()
    missing_content = []

    def repl(m):
        key = m.group("key")
        indent = len(m.group("open")) + 2
        if key not in data:
            missing_content.append(key)
            return m.group(0)                      # leave the page untouched
        used.add(key)
        kind = key.rsplit(".", 1)[-1]
        body = SPECIAL[kind](data[key], indent) if kind in SPECIAL \
            else paragraphs(data[key], indent - 2)
        return "%s<!--@%s-->%s<!--/@-->" % (m.group("open"), key, body)

    out, n = MARKER.subn(repl, page)

    shutil.copyfile(PAGE, BACKUP)
    with open(PAGE, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)

    print("updated %d of %d marked spots in index.html" % (len(used), n))
    if missing_content:
        print("\n  These spots are marked in the page but have nothing in content.txt,")
        print("  so they were left alone:")
        for k in sorted(set(missing_content)):
            print("    %s" % k)

    unused = sorted(set(data) - used)
    if unused:
        print("\n  These are in content.txt but no matching spot exists in the page.")
        print("  Check the spelling:")
        for k in unused:
            print("    %s" % k)

    print("\nPrevious version saved as index.backup.html")
    print("Refresh the page to see your changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
