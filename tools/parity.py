#!/usr/bin/env python3
"""Compare the cores content of two RetroArch pages.

    python3 tools/parity.py <old page> <new page> [--allow <file>]

Each page is a path or a URL. The two must agree on:
  - the core rows, in the same order;
  - the "On a PS4" verdict and its note, and whether the row links recommended settings;
  - the recommended-settings blocks, option by option;
  - the licence and its non-commercial mark;
  - the "Built from" links, href and text.

Written for PLAN.md phase 2, comparing site.py's render with the page make-site.py published at
cores.prx0.com, and kept as the regression test for phase 6: a render from the cores.json the cores
workflow writes must match the render before it.

--allow names differences that are corrections, one per line: core, field, reason, tab-separated.
Every allowed difference must occur - a stale allowance is an error too, so the file cannot quietly
outlive what it excuses.
"""

import argparse
import html.parser
import re
import sys
import urllib.request

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        return re.sub(r"\s+", " ", "".join(c if isinstance(c, str) else c.text() for c in self.children)).strip()

    def iter(self, tag=None):
        for c in self.children:
            if isinstance(c, Node):
                if tag is None or c.tag == tag:
                    yield c
                yield from c.iter(tag)

    def classes(self):
        return set(self.attrs.get("class", "").split())


class Tree(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("#root", {}, None)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def load(src):
    if re.match(r"https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": "orbis-ports-website"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
    else:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
    t = Tree()
    t.feed(text)
    t.close()
    return t.root


def cores_table(root):
    for table in root.iter("table"):
        heads = [th.text() for th in table.iter("th")]
        if heads[:2] == ["Core", "On a PS4"]:
            return table
    raise SystemExit("!! no cores table (Core, On a PS4, ...) on the page")


def rows(root):
    out = []
    for tr in cores_table(root).iter("tr"):
        tds = list(c for c in tr.children if isinstance(c, Node) and c.tag == "td")
        if len(tds) < 6:
            continue
        core_link = next(tds[0].iter("a"))
        hw = tds[1]
        badge = next((s for s in hw.iter("span") if "hwb" in s.classes() or "untested" in s.classes()), None)
        note = next((s.text() for s in hw.iter("span") if "hwnote" in s.classes()), "")
        lic = tds[3]
        nc = any("nc" in s.classes() for s in lic.iter("span"))
        lic_text = "".join(c for c in lic.children if isinstance(c, str)).strip()
        out.append({
            "core": core_link.attrs["href"].rsplit("/", 1)[-1],
            "name": core_link.text(),
            "verdict": ("%s %s" % (" ".join(sorted(badge.classes())), badge.text())) if badge else "",
            "note": note,
            "settings_link": " ".join(a.attrs.get("href", "") for a in hw.iter("a") if "optlink" in a.classes()),
            "licence": lic_text,
            "noncommercial": str(nc),
            "source": " ".join("%s=%s" % (a.attrs.get("href"), a.text()) for a in tds[5].iter("a"))
                      or tds[5].text(),
        })
    return out


def settings(root):
    """opt-<core> -> [(label, value, why)] in page order."""
    out = {}
    for h3 in root.iter("h3"):
        oid = h3.attrs.get("id", "")
        if not oid.startswith("opt-"):
            continue
        siblings = h3.parent.children
        nxt = next(c for c in siblings[siblings.index(h3) + 1:] if isinstance(c, Node))
        out[oid] = [tuple(td.text() for td in tr.iter("td")) for tr in nxt.iter("tr") if list(tr.iter("td"))]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--allow", help="expected differences: core<TAB>field<TAB>reason per line")
    args = ap.parse_args()

    allowed = {}
    if args.allow:
        with open(args.allow, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                core, field, reason = (line.rstrip("\n").split("\t") + ["", ""])[:3]
                allowed[(core, field)] = reason

    old_root, new_root = load(args.old), load(args.new)
    old_rows, new_rows = rows(old_root), rows(new_root)
    diffs = []

    old_order, new_order = [r["core"] for r in old_rows], [r["core"] for r in new_rows]
    if old_order != new_order:
        gone = [c for c in old_order if c not in new_order]
        added = [c for c in new_order if c not in old_order]
        diffs.append(("*", "rows", "order or set differs; only in old: %s; only in new: %s"
                      % (" ".join(gone) or "-", " ".join(added) or "-"), ""))
    new_by = {r["core"]: r for r in new_rows}
    for o in old_rows:
        n = new_by.get(o["core"])
        if not n:
            continue
        for field in ("name", "verdict", "note", "settings_link", "licence", "noncommercial", "source"):
            if o[field] != n[field]:
                diffs.append((o["core"], field, o[field], n[field]))

    old_opts, new_opts = settings(old_root), settings(new_root)
    if list(old_opts) != list(new_opts):
        diffs.append(("*", "settings", "blocks: %s" % " ".join(old_opts), " ".join(new_opts)))
    for oid, opts in old_opts.items():
        if new_opts.get(oid, opts) != opts:
            diffs.append((oid, "settings", repr(opts), repr(new_opts.get(oid))))

    failures, used = 0, set()
    for core, field, old, new in diffs:
        key = (core, field)
        if key in allowed:
            used.add(key)
            print("-- expected: %s %s: %s\n     old: %s\n     new: %s" % (core, field, allowed[key], old, new))
        else:
            failures += 1
            print("!! %s %s\n     old: %s\n     new: %s" % (core, field, old, new))
    for key in sorted(set(allowed) - used):
        failures += 1
        print("!! allowed difference did not occur, remove it: %s %s" % key)

    print("== %d rows, %d settings blocks compared; %d difference(s), %d unexpected"
          % (len(old_rows), len(old_opts), len(diffs), failures))
    return 1 if failures or not old_rows else 0


if __name__ == "__main__":
    sys.exit(main())
