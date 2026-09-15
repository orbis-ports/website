#!/usr/bin/env python3
"""Build prx0.com: a landing page for every orbis-ports PlayStation 4 port, and a page per port.

    python3 site.py --ports ports --cores-json <path|url> --out out [--redirect <file>]

Inputs, and nothing else:

    ports/*.json                 one hand-written file per port
    GitHub releases              the newest release per port: version, package, size, notes
    GitHub repositories          a port's notes file while it has no release; licences
    cores.json                   the published RetroArch cores (tools/cores-json-from-live.py)
    data/retroarch/*.tsv         what has run on a console, and recommended core options
    data/platform.json           the projects every port is built on

⚠ THE RETROARCH PAGE IS A LICENCE DOCUMENT BEFORE IT IS A DOWNLOAD PAGE. RetroArch is GPLv3 and
most cores are GPL of some vintage, so distributing the binaries obliges us to point at the
CORRESPONDING source - the exact commit each binary was built from, not "the project". Those
commits come from the manifests the cores run writes beside the binaries, carried in cores.json.
This page was moved here from RetroArch's ps4/make-site.py; the comments marked ⚠ below were
paid for there and are kept with the code they explain.

Every number on a page comes from one of the inputs above. Nothing is typed into a template.
"""

import argparse
import base64
import fnmatch
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://prx0.com/"
UA = {"User-Agent": "orbis-ports-website"}

e = html.escape


def warn(msg):
    print("== " + msg, file=sys.stderr)


# ---------------------------------------------------------------------------------------------
# Fetching

def github_token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    # Locally, the gh login if there is one. Unauthenticated, the API allows 60 calls an hour.
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


class GitHub:
    def __init__(self):
        self.token = github_token()

    def get(self, url, accept="application/vnd.github+json"):
        req = urllib.request.Request(url, headers=dict(UA, Accept=accept))
        if self.token and url.startswith("https://api.github.com/"):
            req.add_header("Authorization", "Bearer " + self.token)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def api(self, path):
        return json.loads(self.get("https://api.github.com/" + path))

    def releases(self, repo):
        return self.api("repos/%s/releases?per_page=100" % repo)

    def file(self, repo, ref, path):
        """A file from a repository at a ref, or None when it is not there."""
        try:
            return self.get("https://api.github.com/repos/%s/contents/%s?ref=%s" % (repo, path, ref),
                            accept="application/vnd.github.raw").decode("utf-8")
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise

    def license(self, repo):
        spdx = (self.api("repos/" + repo).get("license") or {}).get("spdx_id")
        return None if spdx in (None, "NOASSERTION") else spdx


def read_source(src):
    if re.match(r"https?://", src):
        req = urllib.request.Request(src, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
    with open(src, encoding="utf-8") as fh:
        return fh.read()


def latest_release(gh, port):
    """The newest non-draft release whose tag starts with the port's prefix, or None."""
    rels = [r for r in gh.releases(port["repo"])
            if not r.get("draft") and r["tag_name"].startswith(port["tag_prefix"])]
    if not rels:
        return None
    rel = max(rels, key=lambda r: r.get("published_at") or r.get("created_at") or "")
    assets = {a["name"]: a for a in rel.get("assets", [])}
    pkg = next((a for n, a in sorted(assets.items()) if fnmatch.fnmatch(n, port["pkg_asset"])), None)
    if not pkg:
        # ⚠ A RELEASE WITH NO PACKAGE IS NOT "NOT RELEASED". Say it loudly; the card shows the
        # release without a download button rather than pretending the port has none.
        warn("%s: release %s has no asset matching %s" % (port["id"], rel["tag_name"], port["pkg_asset"]))
    sha = assets.get(pkg["name"] + ".sha256") if pkg else None
    # The prefix ends in "v"; the version keeps it: retroarch-ps4-v0.1.8 -> v0.1.8.
    version = rel["tag_name"][len(port["tag_prefix"]) - 1:]
    return {
        "tag": rel["tag_name"],
        "name": rel.get("name") or rel["tag_name"],
        "version": version,
        "url": rel["html_url"],
        "date": (rel.get("published_at") or rel.get("created_at") or "")[:10],
        "body": rel.get("body") or "",
        "pkg": {"name": pkg["name"], "url": pkg["browser_download_url"], "bytes": pkg["size"]} if pkg else None,
        "sha256": {"name": sha["name"], "url": sha["browser_download_url"]} if sha else None,
    }


# ---------------------------------------------------------------------------------------------
# Small helpers

def mb(n):
    """Package sizes, as the cores workflow printed them: decimal megabytes."""
    return "%.1f MB" % (n / 1000000.0)


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return "%.0f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0


def plural(n, one, many):
    return one if n == 1 else many


def icon_data_uri(path):
    """The application's own icon0.png, inlined.

    ⚠ THE SAME FILE THE PACKAGE SHIPS, not a drawing of it. An earlier version of the RetroArch
    page carried a hand-written SVG approximation, which looked like an approximation.

    Inlined on the RetroArch page because its whole audience is people about to be offline:
    saved to disk, it still has its icon and needs nothing from the network.
    """
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


# ---------------------------------------------------------------------------------------------
# Markdown, the subset the ports' release notes use

def md_inline(text):
    codes = []

    def keep_code(m):
        codes.append("<code>%s</code>" % e(m.group(1)))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = e(text, quote=False)

    def link(m):
        label, url = m.group(1), m.group(2)
        if not re.match(r"https?://", html.unescape(url)):
            return m.group(0)
        return '<a href="%s">%s</a>' % (url.replace('"', "&quot;"), label)

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], text)


LIST_ITEM = re.compile(r"^(\d+\.|[-*])\s+")


def md_blocks(lines):
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.lstrip().startswith("```"):
            body, i = [], i + 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            indent = min((len(l) - len(l.lstrip()) for l in body if l.strip()), default=0)
            out.append("<pre><code>%s</code></pre>" % e("\n".join(l[indent:] for l in body)))
        elif re.match(r"^#{1,6}\s", line):
            level = max(2, min(4, len(line) - len(line.lstrip("#"))))
            out.append("<h%d>%s</h%d>" % (level, md_inline(line.lstrip("#").strip()), level))
            i += 1
        elif re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
        elif LIST_ITEM.match(line):
            ordered = line[0].isdigit()
            items = []
            while i < len(lines):
                m = LIST_ITEM.match(lines[i])
                if not m or m.group(1)[0].isdigit() != ordered:
                    break
                width = m.end()
                item, i = [lines[i][width:]], i + 1
                # An item runs on through indented lines and the blank lines between them.
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.strip() and not nxt.startswith(" "):
                        break
                    if not nxt.strip():
                        ahead = next((l for l in lines[i:] if l.strip()), "")
                        if not ahead.startswith(" "):
                            break
                    item.append(nxt[width:] if nxt[:width].strip() == "" else nxt.lstrip())
                    i += 1
                items.append(item)
                while i < len(lines) and not lines[i].strip() and i + 1 < len(lines) and LIST_ITEM.match(lines[i + 1]):
                    i += 1
            lis = []
            for item in items:
                inner = md_blocks(item)
                if inner.count("<p>") == 1 and inner.startswith("<p>") and inner.endswith("</p>"):
                    inner = inner[3:-4]
                lis.append("<li>%s</li>" % inner)
            tag = "ol" if ordered else "ul"
            out.append('<%s class="steps">%s</%s>' % (tag, "\n".join(lis), tag) if ordered
                       else "<ul>%s</ul>" % "\n".join(lis))
        else:
            para = []
            while (i < len(lines) and lines[i].strip() and not LIST_ITEM.match(lines[i])
                   and not re.match(r"^#{1,6}\s", lines[i]) and not lines[i].lstrip().startswith("```")):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>%s</p>" % md_inline(" ".join(para)))
    return "\n".join(out)


def markdown(text):
    return md_blocks(text.replace("\r\n", "\n").split("\n"))


# ---------------------------------------------------------------------------------------------
# RetroArch data: what has run on a console, and recommended options

# ⚠ WHAT HAS BEEN SEEN ON A CONSOLE, KEPT IN A FILE RATHER THAN IN THIS SCRIPT. Every other input
# here is produced by a build; this one is produced by somebody holding a pad, and a verdict typed
# into a string literal would be the one fact on the page nobody could trace. core-tested.tsv names
# where each run is written down.
STATUSES = {
    # status -> (badge text, what it means, for the legend)
    "plays":  ("Plays",  "a game runs and is playable"),
    "slow":   ("Slow",   "runs, below full speed"),
    "boots":  ("Boots",  "loads and responds; no game recorded yet"),
    "broken": ("Broken", "loads, then fails"),
}


def read_tested(path):
    """core -> (status, note), or None when there is no file to read."""
    if not path or not os.path.exists(path):
        return None
    tested = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.startswith("#") or not line.strip():
                continue
            parts = re.split(r"\t+", line.rstrip("\n"))
            if len(parts) < 2:
                continue
            core, status = parts[0].strip(), parts[1].strip()
            note = parts[2].strip() if len(parts) > 2 else ""
            # ⚠ A typo in the status column must not quietly read as "untested" - that is the
            # one wrong answer this column exists not to give.
            if status not in STATUSES:
                sys.stderr.write("!! %s:%d: unknown status '%s' for %s\n" % (path, n, status, core))
                continue
            tested[core] = (status, "" if note == "-" else note)
    return tested


def read_options(path):
    """core -> [(label, value, why), ...] in file order, or None when there is no file to read."""
    if not path or not os.path.exists(path):
        return None
    options = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.startswith("#") or not line.strip():
                continue
            parts = [p.strip() for p in re.split(r"\t+", line.rstrip("\n"))]
            # ⚠ A SHORT ROW IS A MISTAKE, NOT A ROW WITH NOTHING TO SAY. Every column but evidence
            # is shown or checked, and a recommendation with no value is an instruction nobody can
            # follow.
            if len(parts) < 5:
                sys.stderr.write("!! %s:%d: expected core, key, label, value, why\n" % (path, n))
                continue
            core, _key, label, value, why = parts[:5]
            options.setdefault(core, []).append((label, value, why))
    return options


NONCOMMERCIAL = ("non-commercial", "noncommercial", "mame", "cc by-nc")


def is_noncommercial(lic):
    low = (lic or "").lower()
    return any(k in low for k in NONCOMMERCIAL)


def load_cores(src):
    doc = json.loads(read_source(src))
    if doc.get("schema") != 1:
        raise SystemExit("!! %s: schema %r, this generator reads schema 1" % (src, doc.get("schema")))
    if not doc.get("cores"):
        raise SystemExit("!! %s lists no cores - refusing to write a page about nothing" % src)
    return doc


FRONTEND = "https://github.com/orbis-ports/RetroArch"


def source_cell(core, frontend_commit):
    """The corresponding source for one core: its repository at the commit it was built from.

    ⚠ A SHA WITH "+N" MEANS N PATCHES FROM RETROARCH'S ps4/core-patches/<core> WENT ON TOP OF IT.
    The old page linked tree/<sha>+N, which is not a commit and answers 404, and named no patches -
    for a GPL notice, upstream's tree alone is not what the binary was built from. The patches are
    linked at the frontend commit the cores run built from.
    """
    repo, sha = core.get("repo") or "", core.get("sha") or ""
    if not repo:
        return "—"
    tree = repo.rstrip("/")
    if sha in ("", "-"):
        # No sha means the manifest did not record one. The repository link is still correct and
        # still points at source; it is one commit less precise, and saying so beats implying a
        # precision that is not there.
        return '<a href="%s">source</a>' % e(tree)
    if sha == "unknown":
        return '<a href="%s">source</a> <span class="nc">commit unknown</span>' % e(tree)
    base, _, patches = sha.partition("+")
    cell = ('<a href="%s/tree/%s">%s</a>' % (e(tree), e(base), e(base)) if "github.com" in tree
            else '<a href="%s">%s</a>' % (e(tree), e(base)))
    if patches:
        n = int(patches)
        label = "+%d %s" % (n, plural(n, "patch", "patches"))
        if frontend_commit:
            cell += ' <a href="%s/tree/%s/ps4/core-patches/%s">%s</a>' % (
                FRONTEND, e(frontend_commit), e(core["name"]), label)
        else:
            cell += " " + label
    return cell


# ---------------------------------------------------------------------------------------------
# Pages

CSS = """
:root{
  --ground:#12151c; --raised:#1a1f2b; --sunk:#0d1016;
  --ink:#e6e9f0; --muted:#939cad; --faint:#6b7386;
  --rule:#262c3a; --accent:#e96a3a; --warn:#d9a441; --ok:#6cc08b; --bad:#e5707a;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  padding:0 20px 96px;
}
.wrap{max-width:1100px;margin:0 auto}
/* ⚠ CENTRED, NOT FLUSH LEFT, AND 86 CHARACTERS RATHER THAN 68. The classic 65-75 measure is
   for prose read at length; this is reference material scanned in short passages, and at 68 in
   a 1100px column it looked starved. 86 is past the textbook range on purpose - the line height
   is 1.65, which carries the extra width. The reading column stays bounded because that is what
   reads comfortably - but pinned to the left of a 1100px wrapper it sits under a full-width row of
   download cards with the right half empty, and the page looks broken rather than restrained.
   Centring costs the shared left edge and buys a balanced page; here the wide elements are
   cards and tables, which have their own frames, so the lost alignment is not missed. */
.prose{max-width:86ch;margin-left:auto;margin-right:auto}
code,kbd,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
code{background:var(--sunk);border:1px solid var(--rule);border-radius:4px;padding:.08em .38em;font-size:.88em;overflow-wrap:anywhere}
pre{background:var(--sunk);border:1px solid var(--rule);border-radius:8px;padding:10px 14px;overflow-x:auto}
pre code{background:none;border:0;padding:0}
a{color:var(--accent)}
a:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

nav.crumb{padding-top:18px;font-size:.88rem}
nav.crumb a{text-decoration:none}
header{border-bottom:1px solid var(--rule);padding:56px 0 32px;margin-bottom:40px}
nav.crumb + header{padding-top:28px}
/* The masthead is centred; the sections below are not. A masthead is looked at, and centring
   is what that shape expects. A section heading is read, and belongs on the same left edge as
   the cards or table it introduces. */
.brand{display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:center}
.mark{width:56px;height:56px;flex:0 0 auto;border-radius:12px;display:block}
h1{font-size:2rem;margin:0;letter-spacing:-.015em;text-wrap:balance;text-align:center}
.tag{color:var(--muted);margin:.5rem auto 0;max-width:60ch;text-align:center}
.meta{margin-top:20px;display:flex;gap:10px;flex-wrap:wrap;font-size:.82rem;justify-content:center}
.pill{background:var(--raised);border:1px solid var(--rule);border-radius:999px;padding:4px 12px;color:var(--muted)}
.pill b{color:var(--ink);font-weight:600}

h2{font-size:1.28rem;margin:52px 0 14px;letter-spacing:-.01em}
h3{font-size:1rem;margin:28px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}
p{margin:0 0 14px}

.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));margin:22px 0}
.card{background:var(--raised);border:1px solid var(--rule);border-radius:10px;padding:20px;display:flex;flex-direction:column;gap:6px}
.card .what{font-weight:600;font-size:1.02rem}
.card .why{color:var(--muted);font-size:.9rem;flex:1}
.card .go{margin-top:10px;display:inline-block;background:var(--accent);color:#12151c;font-weight:650;
  text-decoration:none;padding:9px 15px;border-radius:7px;text-align:center;font-size:.92rem}
.card .size{color:var(--faint);font-size:.8rem;font-variant-numeric:tabular-nums}
.card .alt{font-size:.85rem;text-align:center}

/* A port card on the landing page: the download card with the port's icon and state on top. */
.port .head{display:flex;align-items:center;gap:14px}
.port .head img{width:48px;height:48px;border-radius:10px;flex:0 0 auto}
.port .head .what{font-size:1.12rem}
.port ul.needs{margin:4px 0 0;padding-left:1.1em;color:var(--muted);font-size:.86rem}
.state{display:inline-block;border-radius:4px;padding:1px 7px;font-size:.78rem;font-weight:600;white-space:nowrap}
.state.released{background:rgba(108,192,139,.14);color:var(--ok)}
.state.unreleased{background:rgba(217,164,65,.14);color:var(--warn)}
.card .soon{margin-top:10px;display:block;border:1px dashed var(--rule);color:var(--muted);
  padding:8px 15px;border-radius:7px;text-align:center;font-size:.92rem}

ol.steps{margin:0 0 14px;padding-left:1.3em}
ol.steps li{margin:.4em 0}

.note{border-left:3px solid var(--warn);background:var(--raised);padding:14px 18px;border-radius:0 8px 8px 0;margin:20px 0}
/* ⚠ THE BOX IS WIDE; THE MEASURE MUST NOT BE. Directly under the download buttons, this note
   answers the question those buttons raise, so it spans them - but 940px of 16px text is about
   105 characters per line, half again past comfortable. Two columns fill the width and keep
   each line near 60. Justifying instead would only trade a ragged edge for word-space rivers:
   there is no hyphenation to absorb the slack, and unbreakable tokens like CE-34878-0 and
   /data/retroarch/savestates would blow gaps through the lines that carry them. */
.note.wide{max-width:none}
@media (min-width:760px){
  .note.wide{column-count:2;column-gap:34px}
  .note.wide p{margin-top:0;break-inside:avoid}
  .note.wide p:last-child{margin-bottom:0}
}
.note b{color:var(--warn)}
.note p:last-child{margin-bottom:0}

/* ⚠ THE TABLE GETS THE WHOLE COLUMN, AND THE COLUMN IS WIDE ENOUGH FOR IT. An earlier attempt
   pulled the table outside the wrapper with a negative margin, which widened the page's scroll
   area and left every other block sitting off-centre - the fix for one column pushed the entire
   document to the left. The wrapper is 1100px instead, cells wrap, and nothing escapes it. */
.tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:10px;margin:18px 0}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{text-align:left;padding:9px 13px;border-bottom:1px solid var(--rule);vertical-align:top}
.cores td:first-child{min-width:22ch}
.ports td:first-child{min-width:14ch}
.ports td:last-child{min-width:28ch}
.cores th:nth-child(4),.cores td:nth-child(4){min-width:11ch}
/* Second, not after System: at phone width only the first two columns show before the table
   scrolls, and whether a core has worked on the console is what a visitor there came to find. */
td.hw{min-width:18ch;color:var(--muted)}
td.hw .hwnote{display:block;font-size:.8rem;margin-top:3px}
th{background:var(--sunk);color:var(--muted);font-weight:600;position:sticky;top:0}
tr:last-child td{border-bottom:0}
td.num{font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}
td.mono{white-space:nowrap}
td.sys{color:var(--muted);min-width:12ch}
.nc{display:inline-block;background:rgba(217,164,65,.14);color:var(--warn);border-radius:4px;
  padding:1px 7px;font-size:.78rem;margin-left:6px}

/* The status badge is the nc badge's shape in the status's colour, so a column of them reads as
   one family with the licence marks rather than a second vocabulary. Untested is plain faint text:
   it is the default state of most rows, and a badge on every one of them would be noise. */
.hwb{display:inline-block;border-radius:4px;padding:1px 7px;font-size:.78rem;font-weight:600;white-space:nowrap}
.hwb.plays{background:rgba(108,192,139,.14);color:var(--ok)}
.hwb.slow{background:rgba(217,164,65,.14);color:var(--warn)}
.hwb.boots{background:rgba(147,156,173,.16);color:var(--ink)}
.hwb.broken{background:rgba(229,112,122,.14);color:var(--bad)}
.untested{color:var(--faint)}
.optlink{display:block;font-size:.8rem;margin-top:3px}
.opts h3{margin:26px 0 8px;scroll-margin-top:16px}
.opts td.val{white-space:nowrap;font-weight:600}
ul.legend{list-style:none;padding:0;margin:0 0 14px;display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.88rem;color:var(--muted)}

footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--rule);color:var(--faint);font-size:.85rem}
@media (max-width:600px){ header{padding-top:36px} h1{font-size:1.6rem} }
"""


def page(title, description, body, favicon):
    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="%s">
<title>%s</title>
<meta name="description" content="%s">
<style>%s</style>
</head><body><div class="wrap">
%s
</div></body></html>
""" % (e(favicon), e(title), e(description), CSS, body)


def crumb():
    return '<nav class="crumb"><a href="../">&larr; All PlayStation&nbsp;4 ports</a></nav>'


def download_card(port, rel):
    """The package card on a port's own page."""
    if not rel:
        return ('<div class="card"><span class="what">%s</span>'
                '<span class="why">No PlayStation&nbsp;4 package has been released yet.</span>'
                '<span class="soon">Not released yet</span></div>' % e(port["name"]))
    parts = ['<div class="card"><span class="what">%s %s</span>' % (e(port["name"]), e(rel["version"])),
             '<span class="why">The application package, released %s.</span>' % e(rel["date"])]
    if rel["pkg"]:
        parts.append('<span class="size">%s</span>' % mb(rel["pkg"]["bytes"]))
        parts.append('<a class="go" href="%s">Download .pkg</a>' % e(rel["pkg"]["url"]))
    alt = ['<a href="%s">Release notes</a>' % e(rel["url"])]
    if rel["sha256"]:
        alt.append('<a href="%s">SHA-256</a>' % e(rel["sha256"]["url"]))
    parts.append('<span class="alt">%s</span></div>' % " &middot; ".join(alt))
    return "".join(parts)


def summary_of(port, cores):
    return port["summary"].replace("{cores}", str(len(cores["cores"])) if cores else "")


def render_landing(ports, rels, cores, platform, licences):
    cards = []
    for port in ports:
        rel = rels[port["id"]]
        needs = "".join("<li>%s</li>" % e(r) for r in port.get("requires", []))
        head = ('<div class="head"><img src="%s" alt="" width="48" height="48"><div>'
                '<span class="what">%s</span><br>%s</div></div>'
                % (e(port["icon"]), e(port["name"]),
                   '<span class="state released">Released</span>' if rel and rel["pkg"]
                   else '<span class="state unreleased">Not released yet</span>'))
        body = ['<div class="card port">', head,
                '<span class="why">%s%s</span>' % (e(summary_of(port, cores)),
                                                   '<ul class="needs">%s</ul>' % needs if needs else "")]
        if rel and rel["pkg"]:
            body.append('<span class="size">%s &middot; %s &middot; %s</span>'
                        % (e(rel["version"]), e(rel["date"]), mb(rel["pkg"]["bytes"])))
            body.append('<a class="go" href="%s">Download .pkg</a>' % e(rel["pkg"]["url"]))
        else:
            body.append('<span class="soon">No package yet</span>')
        body.append('<a class="alt" href="%s/">About %s &rarr;</a></div>' % (e(port["id"]), e(port["name"])))
        cards.append("".join(body))

    rows = "".join(
        '<tr><td><a href="%s/">%s</a></td><td class="mono">%s</td><td class="mono">%s</td><td class="sys">%s</td></tr>'
        % (e(p["id"]), e(p["name"]), e(p["title_id"]), e(p["files_in"]), e(p["quit"])) for p in ports)

    # One sentence per firmware and GoldHEN pair, naming the ports tested on it - and who tested,
    # where that is written down.
    groups = {}
    for p in ports:
        if p.get("tested_on"):
            key = (p["tested_on"]["firmware"], p["tested_on"]["goldhen"])
            by = p["tested_on"].get("by")
            groups.setdefault(key, []).append(e(p["name"]) + (" (by %s)" % e(by) if by else ""))
    tested = "".join(
        "<p><b>Tested on firmware %s with GoldHEN %s</b>: %s. Other firmware and other jailbreak builds "
        "may work — nobody has checked, and a report either way is useful.</p>"
        % (e(fw), e(gh), ", ".join(names)) for (fw, gh), names in groups.items())
    # The masthead shows the pair only when every port shares it; otherwise the sentences say it.
    pills = ""
    if len(groups) == 1 and sum(len(n) for n in groups.values()) == len(ports):
        fw, gh = next(iter(groups))
        pills = ('<div class="meta"><span class="pill">Firmware <b>%s</b></span>'
                 '<span class="pill">GoldHEN <b>%s</b></span></div>' % (e(fw), e(gh)))

    plat = "".join(
        '<li><a href="https://github.com/%s">%s</a> — %s%s</li>'
        % (e(x["repo"]), e(x["repo"]), e(x["what"]),
           " (%s)" % e(licences[x["repo"]]) if licences.get(x["repo"]) else "")
        for x in platform)

    body = """
<header>
  <div class="brand"><div>
    <h1>PlayStation&nbsp;4 ports</h1>
    <p class="tag">Games and emulators from <a href="https://github.com/orbis-ports">orbis-ports</a>, for a
       jailbroken PlayStation&nbsp;4 running GoldHEN. Each one is a package you install yourself.</p>
  </div></div>
  %s
</header>

<h2>The ports</h2>
<div class="grid">
%s
</div>

<div class="prose">
<h2 id="install">Installing a package</h2>
<p>Every port here needs a jailbroken console running <b>GoldHEN</b>, and installs the same way:</p>
<ol class="steps">
  <li>Copy the <code>.pkg</code> to <code>/data/pkg</code> on the console over FTP.</li>
  <li>On the console: <b>Settings &rarr; Debug Settings &rarr; Package Installer</b>, or GoldHEN's own
      package installer.</li>
  <li>Pick the package and install it.</li>
</ol>
%s
<p>Each port installs under its own title id, and the console decides collisions by title id, not by
the name on screen: a port sits <em>beside</em> another build of the same program rather than
replacing it.</p>
</div>

<div class="tablewrap"><table class="ports">
<thead><tr><th>Port</th><th>Title id</th><th>Keeps its files in</th><th>Quit with</th></tr></thead>
<tbody>%s</tbody></table></div>

<div class="prose">
<div class="note">
<p><b>Quit from inside, not from the console.</b> Closing a port from the console's own menu — the PS
button, then <em>Close Application</em> — does not end it cleanly. Use the quit entry in the table
above; each port's page says what happens otherwise.</p>
</div>

<h2>What they are built on</h2>
<p>All of them draw through the same graphics stack and link against the same platform layer.</p>
<ul>%s</ul>
</div>

<footer>
  <p>Versions and downloads are read from each port's GitHub releases when this site is built, by
     <code>site.py</code> in <a href="https://github.com/orbis-ports/website">orbis-ports/website</a>.</p>
</footer>
""" % (pills, "\n".join(cards), tested, rows, plat)
    return page("PlayStation 4 ports", "PlayStation 4 ports from orbis-ports: RetroArchV, Sonic 3 A.I.R. "
                "and OpenGothic, for a jailbroken console with GoldHEN.", body, ports[0]["icon"])


def render_notes_page(port, rel, notes, notes_from, licence):
    """A port whose page is its release notes: Sonic 3 A.I.R., OpenGothic."""
    icon = "../" + port["icon"]
    pills = []
    if rel:
        pills.append('<span class="pill">Version <b>%s</b></span>' % e(rel["version"]))
        pills.append('<span class="pill">Released <b>%s</b></span>' % e(rel["date"]))
    else:
        pills.append('<span class="pill"><b>Not released yet</b></span>')
    pills.append('<span class="pill">Title id <b>%s</b></span>' % e(port["title_id"]))
    if port.get("tested_on"):
        pills.append('<span class="pill">Firmware <b>%s</b></span>' % e(port["tested_on"]["firmware"]))
        pills.append('<span class="pill">GoldHEN <b>%s</b></span>' % e(port["tested_on"]["goldhen"]))
    needs = "".join("<li>%s</li>" % e(r) for r in port.get("requires", []))

    if rel:
        where = ('<p>The notes below are the text of the release <a href="%s">%s</a>.</p>'
                 % (e(rel["url"]), e(rel["name"])))
        src = '<a href="https://github.com/%s/tree/%s">%s</a> at <code>%s</code>' % (
            e(port["repo"]), e(rel["tag"]), e(port["repo"]), e(rel["tag"]))
    else:
        where = ('<div class="note"><p><b>There is no PlayStation&nbsp;4 package of %s yet.</b> '
                 'Nothing on this page can be downloaded, and the upstream project\'s own releases are builds for '
                 'desktop systems, not for the console. The notes below are <code>%s</code> on the port\'s '
                 '<code>%s</code> branch, the file its first release will carry. This page offers the '
                 'package as soon as that release exists.</p></div>'
                 % (e(port["name"]), e(notes_from), e(port["branch"])))
        src = '<a href="https://github.com/%s/tree/%s">%s</a>, branch <code>%s</code>' % (
            e(port["repo"]), e(port["branch"]), e(port["repo"]), e(port["branch"]))

    body = """
%s
<header>
  <div class="brand"><img class="mark" src="%s" alt="" width="56" height="56"><div>
    <h1>%s for PlayStation&nbsp;4</h1>
    <p class="tag">%s</p>
  </div></div>
  <div class="meta">%s</div>
</header>

<h2>Download</h2>
<div class="grid">
  %s
  <div class="card"><span class="what">Before you start</span>
    <span class="why">A jailbroken console running GoldHEN, and:</span>
    <ul class="needs">%s</ul>
    <a class="alt" href="../#install">How to install a package &rarr;</a></div>
</div>

<div class="prose">
%s
%s

<h2>Source code and licence</h2>
<p>%s%s. The graphics stack and platform layer it is built on are listed on
<a href="../">the ports page</a>.</p>
</div>

<footer>
  <p>Generated by <code>site.py</code> in <a href="https://github.com/orbis-ports/website">orbis-ports/website</a>
     from %s.</p>
</footer>
""" % (crumb(), e(icon), e(port["name"]), e(port["summary"]), "\n    ".join(pills),
       download_card(port, rel), needs, where,
       markdown(notes) if notes else "<p>No release notes are written down for this port yet.</p>",
       src, " — licensed <b>%s</b>, as its licence file says" % e(licence) if licence else "",
       "the release on GitHub" if rel else "the port's repository")
    return page("%s for PlayStation 4" % port["name"], port["summary"], body, icon)


def render_retroarch(port, rel, cores, tested, options, icon_uri):
    rows = []
    nc_count = 0
    hw_count = 0
    options = options or {}
    displays = {}
    listed = cores["cores"]
    for core in listed:
        name = core["name"]
        display = core.get("display_name") or name
        displays[name] = display
        lic = core.get("license") or "—"
        if is_noncommercial(lic):
            nc_count += 1
        status, note = (tested or {}).get(name, ("", ""))
        if status:
            hw_count += 1
            hw_cell = '<span class="hwb %s">%s</span>' % (status, STATUSES[status][0])
            if note:
                hw_cell += '<span class="hwnote">%s</span>' % e(note)
        else:
            # Without the file nothing is known either way, and "untested" would be a claim.
            # With it, no row is exactly what "untested" means.
            hw_cell = '<span class="untested">%s</span>' % ("untested" if tested is not None else "—")
        if name in options:
            hw_cell += '<a class="optlink" href="#opt-%s">Recommended settings</a>' % e(name)
        rows.append(
            '<tr><td><a href="%s%s">%s</a></td><td class="hw">%s</td><td class="sys">%s</td>'
            '<td>%s%s</td><td class="num">%s</td><td class="mono num">%s</td></tr>'
            % (e(cores["base"]), e(core["file"]), e(display), hw_cell, e(core.get("system") or ""),
               e(lic), '<span class="nc">non-commercial</span>' if is_noncommercial(lic) else "",
               e(core.get("size") or ""), source_cell(core, cores.get("frontend_commit"))))
    legend = "".join('<li><span class="hwb %s">%s</span> %s</li>' % (k, v[0], e(v[1]))
                     for k, v in STATUSES.items())
    # ⚠ NO FILE, NO SENTENCE. "0 of the 113 have been run on a real PlayStation 4" is what this
    # would otherwise print, and it is false in a way no reader could detect.
    hw_intro = "" if tested is None else """\
<p><b>%d of the %d have been run on a real PlayStation&nbsp;4</b>, and the <em>On a PS4</em> column
says what happened. Everything else has only been built: it compiles, links and loads as a module,
and nobody has yet written down what it does with a game. A report either way is useful.</p>
<ul class="legend">%s<li><span class="untested">untested</span> built, never run on a console</li></ul>
<p>A result describes the build that was on the console that day. Cores are rebuilt from upstream on
every run, so the file here can be newer than the one that was tested.</p>""" % (hw_count, len(listed), legend)

    # In index order, so the section reads in the same order as the table it links from; a core
    # with advice but no row in this index has nothing to link to and is left out (main() says so).
    opt_blocks = []
    for core in listed:
        name = core["name"]
        if name not in options:
            continue
        trs = "".join('<tr><td>%s</td><td class="val">%s</td><td class="sys">%s</td></tr>'
                      % (e(label), e(value), e(why)) for label, value, why in options[name])
        opt_blocks.append(
            '<h3 id="opt-%s">%s</h3>\n<div class="tablewrap"><table>\n'
            '<thead><tr><th>Option</th><th>Set to</th><th>Why</th></tr></thead>\n'
            '<tbody>%s</tbody></table></div>' % (e(name), e(displays.get(name, name)), trs))
    opt_section = "" if not opt_blocks else """\
<h2>Recommended settings</h2>
<div class="prose">
<p>Most cores run well on their defaults. These are the exceptions: options whose default was
chosen for a desktop computer and is wrong on this console, or that a game here was found to need.
Change them under <b>Quick Menu &rarr; Options</b> while a game is running, and keep them with
<b>Manage Core Options &rarr; Save Core Options</b>.</p>
</div>
<div class="opts">
%s
</div>
""" % "\n".join(opt_blocks)

    bundle = cores.get("bundle")
    if bundle:
        bundle_card = (
            '<div class="card"><span class="what">Every core, one archive</span>'
            '<span class="why">All %d cores as <code>.prx</code> files. For a console with no '
            'network: unzip and copy them across over FTP.</span>'
            '<span class="size">%s</span>'
            '<a class="go" href="%s%s">Download cores</a></div>'
            % (len(listed), human(bundle["bytes"]), e(cores["base"]), e(bundle["file"])))
    else:
        bundle_card = ""

    tested_on = port.get("tested_on") or {}
    version = rel["version"] if rel else "not released"
    pills = ['<span class="pill">Package <b>%s</b></span>' % e(version),
             '<span class="pill">Cores <b>%d</b></span>' % len(listed),
             '<span class="pill">Index <b>%s</b></span>' % e(cores["index_date"])]
    if tested_on:
        pills += ['<span class="pill">Firmware <b>%s</b></span>' % e(tested_on["firmware"]),
                  '<span class="pill">GoldHEN <b>%s</b></span>' % e(tested_on["goldhen"])]

    if rel and rel["pkg"]:
        pkg_card = """<div class="card">
    <span class="what">RetroArchV %s</span>
    <span class="why">The application package. Install it once; everything else can come later
      over the console's own updater.</span>
    <span class="size">%s</span>
    <a class="go" href="%s">Download .pkg</a>
  </div>""" % (e(rel["version"]), mb(rel["pkg"]["bytes"]), e(rel["pkg"]["url"]))
    else:
        pkg_card = download_card(port, rel)

    if rel:
        frontend = ('<a href="%s/tree/%s">orbis-ports/RetroArch</a> at <code>%s</code>'
                    % (FRONTEND, e(rel["tag"]), e(rel["version"])))
    else:
        frontend = '<a href="%s">orbis-ports/RetroArch</a>' % FRONTEND

    if cores.get("recipe_total") is not None:
        recipe_limit = ("<li>%d of the %d cores in the build recipe do not build for this platform yet. "
                        "The ones listed here are the ones that link and export a working entry point.</li>"
                        % (cores["recipe_missing"], cores["recipe_total"]))
    else:
        recipe_limit = ""

    run = (' by <a href="%s">the cores run</a> that published them' % e(cores["run"])) if cores.get("run") else ""

    body = """
%s
<header>
  <div class="brand"><img class="mark" src="%s" alt="" width="56" height="56"><div>
    <h1>RetroArchV for PlayStation&nbsp;4</h1>
    <p class="tag">Emulation on a jailbroken console, running Vulkan through RADV and desktop
       OpenGL&nbsp;4.6 through zink. %d cores, built for this hardware.</p>
  </div></div>
  <div class="meta">
    %s
  </div>
</header>

<h2>Download</h2>
<div class="grid">
  %s
  %s
</div>

<div class="note wide">
<p><b>Quit from inside the application, not from the console.</b> Use RetroArch's own
<b>Quit RetroArch</b> entry, or the Quit combo on the pad. It returns to the console's menu with
no dialog. Earlier versions showed <code>CE-34878-0</code> here; they ended by returning from
<code>main()</code>, which takes the process down outside the path the system expects.</p>
<p>Closing it the console's way instead — the PS button, then <em>Close Application</em> — still
shows <code>CE-34878-0</code>. The console returns to its menu and nothing needs restarting, but the
application is killed outright there and never gets to shut itself down, so Quit is the better
habit.</p>
</div>

<div class="prose">
<h2>Install</h2>
<p>Install the package like every port here: <a href="../#install">copy it to the console and use the
Package Installer</a>, then launch <b>RetroArchV</b>.</p>
<p>It installs under its own title id, <code>%s</code>, so it sits <em>beside</em> any
RetroArch already on the console rather than replacing it — the system decides collisions by
title id, not by the name on screen.</p>

<h3>First run</h3>
<p><b>Online Updater &rarr; Update Core Info Files.</b> Do this before browsing the core list.
Core metadata is not shipped inside the package, so until those files arrive the downloader
lists <code>.prx</code> filenames instead of names like &ldquo;Nintendo&nbsp;64&nbsp;(Mupen64Plus-Next)&rdquo;.
Everything works either way; only the labels are missing.</p>

<h2>With a console that has no network</h2>
<p>Download the archive above on another machine, unzip it, and copy the <code>.prx</code> files
into <code>/data/retroarch/cores</code> over FTP. Nothing else is needed — the core list is read
from that directory at startup.</p>
<div class="note">
<p><b>Copy them, do not extract them on the console.</b> A file arriving over FTP is created
executable, which is what the module loader requires. Files unpacked by other routes may not be,
and a core without that bit fails to load with no explanation beyond
&ldquo;Failed to open libretro core&rdquo;.</p>
</div>
<p>Core metadata works the same way offline: the <code>.info</code> files live in
<code>/data/retroarch/info</code> and can be copied across from
<a href="http://buildbot.libretro.com/assets/frontend/info.zip">libretro's bundle</a>.</p>

<h2>Where everything lives</h2>
<p>All of it sits under <code>/data/retroarch/</code>, which is writable and survives
reinstalling the package. Put files there over FTP and RetroArch finds them at startup — there is
no import step.</p>
</div>

<div class="tablewrap"><table>
<thead><tr><th>Directory</th><th>What goes in it</th></tr></thead>
<tbody>
<tr><td class="mono">/data/retroarch/cores</td><td class="sys">Cores, as <code>.prx</code> files</td></tr>
<tr><td class="mono">/data/retroarch/info</td><td class="sys">Core metadata — names, supported extensions, required BIOS files</td></tr>
<tr><td class="mono">/data/retroarch/system</td><td class="sys">BIOS and firmware. A core that needs one looks here and nowhere else</td></tr>
<tr><td class="mono">/data/retroarch/roms</td><td class="sys">Content. Only a convention — games can sit anywhere the console can read</td></tr>
<tr><td class="mono">/data/retroarch/savefiles</td><td class="sys">Battery saves, memory cards</td></tr>
<tr><td class="mono">/data/retroarch/savestates</td><td class="sys">Save states</td></tr>
<tr><td class="mono">/data/retroarch/config</td><td class="sys">Per-core configuration overrides, and <code>config/remaps</code> for input remaps</td></tr>
<tr><td class="mono">/data/retroarch/playlists</td><td class="sys">Playlists built by the scanner</td></tr>
<tr><td class="mono">/data/retroarch/thumbnails</td><td class="sys">Box art and screenshots</td></tr>
<tr><td class="mono">/data/retroarch/shaders</td><td class="sys">Shader presets and passes</td></tr>
<tr><td class="mono">/data/retroarch/shader-cache</td><td class="sys">The OpenGL driver's compiled shaders, read back on the next run</td></tr>
<tr><td class="mono">/data/retroarch/overlays</td><td class="sys">Overlays, and <code>overlays/keyboards</code> for on-screen keyboards</td></tr>
<tr><td class="mono">/data/retroarch/assets</td><td class="sys">Menu assets — icons, fonts, the XMB and Ozone themes</td></tr>
<tr><td class="mono">/data/retroarch/database/rdb</td><td class="sys">Content databases the scanner matches against</td></tr>
<tr><td class="mono">/data/retroarch/cheats</td><td class="sys">Cheat files</td></tr>
<tr><td class="mono">/data/retroarch/logs</td><td class="sys">Logs</td></tr>
<tr><td class="mono">/data/retroarch/retroarch.cfg</td><td class="sys">The main configuration file</td></tr>
</tbody></table></div>

<div class="prose">
<div class="note">
<p><b>Edit the configuration with RetroArch closed.</b> It keeps its settings in memory and
writes the whole file out when it exits, so a change made over FTP while it is running is
overwritten on quit — not merged, replaced.</p>
</div>
<p>The package itself is mounted read-only at <code>/app0</code> and holds only the executable,
the icon and the certificate bundle. Nothing there needs editing, and nothing there can be.</p>

<h2>Configuring it</h2>
<p>Once the cores are in place, this is ordinary RetroArch. Controller mapping, shaders,
overlays, per-core options, save states, rewind, netplay's absence, the scanner, playlists — all
of it behaves as it does everywhere else, with the same menus in the same places. The
<a href="https://docs.libretro.com/">libretro documentation</a> applies unchanged, and so does
any guide written for another platform.</p>
<p>Two habits worth having early: <b>Load Content</b> scans a directory for anything a core
claims, and per-core settings live under <b>Quick Menu &rarr; Options</b> while the game is
running, saved with <b>Manage Core Options</b>.</p>

<h2>Source code and licences</h2>
<p>RetroArch is licensed under the <b>GNU General Public License, version 3</b>, and most cores
here are GPL of one vintage or another. Distributing these binaries obliges us to hand you the
source they were built from — not the project in general, but the exact commit. That is what the
last column of the table below is: each core's version links to the tree it was compiled from, and
a core built with patches of this port's own also links those patches.</p>
<p>The frontend and the platform work:</p>
<ul>
  <li>%s — the frontend, GPLv3, forked from
      <a href="https://github.com/libretro/RetroArch">libretro/RetroArch</a></li>
  <li><a href="https://github.com/orbis-ports/mesa-ps4">orbis-ports/mesa-ps4</a> — Mesa with a
      PlayStation&nbsp;4 winsys and video-out layer (MIT)</li>
  <li><a href="https://github.com/orbis-ports/orbis-compat">orbis-ports/orbis-compat</a> — the
      platform overlay: libc and pthread corrections, packaging, logging</li>
  <li><a href="https://github.com/orbis-ports/beetle-psx-libretro">orbis-ports/beetle-psx-libretro</a>
      — the PlayStation core, forked for this platform</li>
  <li><a href="https://github.com/orbis-ports/3dsTrident">orbis-ports/3dsTrident</a>
      — the Nintendo 3DS core, forked for this platform</li>
  <li><a href="https://bearssl.org/">BearSSL</a> (MIT) for TLS, and the
      <a href="https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain">OpenOrbis toolchain</a></li>
</ul>
<div class="note">
<p><b>%d of these cores carry non-commercial terms</b> and are marked in the table. They may not
be redistributed commercially, and neither may this collection as a whole while they are part of
it. Nothing here is sold, and nothing here should be.</p>
</div>

<h2>Known limits</h2>
<ul>
  <li>Closing the application from the console's own menu still shows <code>CE-34878-0</code>.
      It is cosmetic — the console recovers on its own. Quit from inside RetroArch does not.</li>
  %s
  <li>Cores are built from upstream's tip on the day the build ran, so a core's version is a
      date rather than a release number.</li>
</ul>
</div>

%s
<h2>The cores</h2>
<div class="prose">
<p>Every file the console's own Core Downloader offers, and where each came from.</p>
%s
</div>
<div class="tablewrap"><table class="cores">
<thead><tr><th>Core</th><th>On a PS4</th><th>System</th><th>Licence</th><th>Size</th><th>Built from</th></tr></thead>
<tbody>
%s
</tbody></table></div>

<footer>
  <p>Index published %s &middot; cores served from <code>%s</code> &middot;
     this page is generated by <code>site.py</code> in
     <a href="https://github.com/orbis-ports/website">orbis-ports/website</a>, from the
     <code>cores.json</code> written%s beside the binaries it describes.</p>
</footer>
""" % (crumb(), e(icon_uri), len(listed), "\n    ".join(pills), pkg_card, bundle_card,
       e(port["title_id"]), frontend, nc_count, recipe_limit, opt_section, hw_intro, "\n".join(rows),
       e(cores["index_date"]), e(cores["base"]), run)
    return page("RetroArchV for PlayStation 4",
                "RetroArch for the PlayStation 4: the package, %d cores, and the source they were built from."
                % len(listed), body, icon_uri)


def render_redirect(target):
    """cores.prx0.com/index.html once the page has moved. R2 objects cannot answer with a 301."""
    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0; url=%s">
<link rel="canonical" href="%s">
<title>RetroArchV for PlayStation 4 has moved</title>
<style>body{margin:0;padding:48px 20px;background:#12151c;color:#e6e9f0;font:16px/1.65 system-ui,sans-serif;text-align:center}a{color:#e96a3a}</style>
</head><body>
<p>This page has moved to <a href="%s">%s</a>.</p>
<p>The cores themselves are still served from here, so RetroArch's Core Downloader is unaffected.</p>
</body></html>
""" % (e(target), e(target), e(target), e(target))


# ---------------------------------------------------------------------------------------------

def check_cores(cores, tested, options):
    """⚠ Say what is missing rather than quietly rendering a dash."""
    listed = [c["name"] for c in cores["cores"]]
    for label, names in (
            ("no commit sha", [c["name"] for c in cores["cores"] if c.get("sha") in ("", "-", None)]),
            ("an unknown commit", [c["name"] for c in cores["cores"] if c.get("sha") == "unknown"]),
            ("no repository", [c["name"] for c in cores["cores"] if not c.get("repo")]),
            ("no licence", [c["name"] for c in cores["cores"] if not c.get("license")])):
        if names:
            warn("%d core(s) with %s: %s" % (len(names), label, " ".join(sorted(names))))
    if not cores.get("bundle"):
        # ⚠ SAY SO. Without the bundle the page renders perfectly well and simply has no
        # "every core, one archive" card - which is the single thing an offline visitor came for.
        warn("NO BUNDLE in cores.json: the RetroArch page will have no all-cores download")
    # ⚠ AND SAY WHICH VERDICTS DID NOT LAND. A core withheld on purpose keeps its row in the TSV,
    # which is right - the verdict is still true - but a renamed core would lose its row here
    # silently, and a tested core shown as "untested" is the column's one unforgivable error.
    if tested is None:
        warn("NO core-tested.tsv: the On a PS4 column will be blank for every core")
    else:
        unlisted = sorted(c for c in tested if c not in listed)
        warn("%d core(s) with a hardware verdict" % (len(tested) - len(unlisted)))
        if unlisted:
            warn("%d verdict(s) for cores not in this index: %s" % (len(unlisted), " ".join(unlisted)))
    if options:
        missing = sorted(c for c in options if c not in listed)
        warn("recommended settings for %d core(s)" % (len(options) - len(missing)))
        if missing:
            warn("settings for cores not in this index, not shown: %s" % " ".join(missing))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("== %s, %d bytes" % (path, len(text.encode("utf-8"))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ports", default=os.path.join(HERE, "ports"), help="directory of <id>.json")
    ap.add_argument("--cores-json", required=True, help="path or URL of cores.json")
    ap.add_argument("--data", default=os.path.join(HERE, "data"), help="directory holding retroarch/ and platform.json")
    ap.add_argument("--out", required=True, help="where the site tree is written")
    ap.add_argument("--redirect", help="also write the cores.prx0.com/index.html redirect to this file")
    args = ap.parse_args()

    ports = []
    for path in sorted(glob.glob(os.path.join(args.ports, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            ports.append(json.load(fh))
    ports.sort(key=lambda p: (p.get("order", 99), p["id"]))
    if not ports:
        raise SystemExit("!! no ports in %s" % args.ports)

    gh = GitHub()
    if not gh.token:
        warn("no GitHub token: unauthenticated API calls, 60 an hour")

    cores = load_cores(args.cores_json)
    tested = read_tested(os.path.join(args.data, "retroarch", "core-tested.tsv"))
    options = read_options(os.path.join(args.data, "retroarch", "core-options.tsv"))
    check_cores(cores, tested, options)
    with open(os.path.join(args.data, "platform.json"), encoding="utf-8") as fh:
        platform = json.load(fh)

    rels = {}
    for port in ports:
        rels[port["id"]] = latest_release(gh, port)
        rel = rels[port["id"]]
        warn("%s: %s" % (port["id"], "%s, %s" % (rel["tag"], mb(rel["pkg"]["bytes"]) if rel["pkg"] else "no pkg")
                         if rel else "not released yet"))

    licences = {x["repo"]: x.get("license") or gh.license(x["repo"]) for x in platform}

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(os.path.join(args.out, "icons"))
    for port in ports:
        shutil.copyfile(os.path.join(HERE, port["icon"]), os.path.join(args.out, port["icon"]))

    write(os.path.join(args.out, "index.html"), render_landing(ports, rels, cores, platform, licences))

    for port in ports:
        rel = rels[port["id"]]
        target = os.path.join(args.out, port["id"], "index.html")
        if port["page"] == "retroarch":
            icon = icon_data_uri(os.path.join(HERE, port["icon"]))
            write(target, render_retroarch(port, rel, cores, tested, options, icon))
        else:
            notes, notes_from = (rel["body"], None) if rel else (
                gh.file(port["repo"], port["branch"], port["notes_path"]), port["notes_path"])
            write(target, render_notes_page(port, rel, notes, notes_from, gh.license(port["repo"])))

    if args.redirect:
        write(args.redirect, render_redirect(SITE + "retroarch/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
