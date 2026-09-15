#!/usr/bin/env python3
"""Check a built site tree: well-formed pages, and links that go somewhere.

    python3 tools/check-html.py out [--external]

For every *.html under the tree:
  - every element that needs a closing tag has one, in the right order;
  - no id is used twice, and every #fragment link names an id on its page;
  - every relative link resolves to a file in the tree (a directory means its index.html).
With --external, every distinct http(s) link is also requested and must not answer an error.
"""

import argparse
import concurrent.futures
import glob
import html.parser
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# Elements whose end tag HTML lets you leave out. The pages close them anyway; this only keeps a
# parser from calling an implied close an error.
OPTIONAL_END = {"p", "li", "td", "th", "tr", "thead", "tbody", "option"}


class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids, self.links = [], [], {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            if a["id"] in self.ids:
                self.errors.append("line %d: id '%s' used twice" % (self.getpos()[0], a["id"]))
            self.ids[a["id"]] = True
        for key in ("href", "src"):
            if a.get(key):
                self.links.append((self.getpos()[0], a[key]))
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            self.errors.append("line %d: </%s> on a void element" % (self.getpos()[0], tag))
            return
        if not any(t == tag for t, _ in self.stack):
            self.errors.append("line %d: </%s> closes nothing" % (self.getpos()[0], tag))
            return
        while self.stack:
            t, line = self.stack.pop()
            if t == tag:
                return
            if t not in OPTIONAL_END:
                self.errors.append("line %d: <%s> is never closed (closed by </%s> on line %d)"
                                   % (line, t, tag, self.getpos()[0]))

    def finish(self):
        for t, line in self.stack:
            if t not in OPTIONAL_END:
                self.errors.append("line %d: <%s> is never closed" % (line, t))


def check_external(urls):
    def probe(url):
        for method in ("HEAD", "GET"):
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "orbis-ports-website"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return url, resp.status
            except urllib.error.HTTPError as err:
                if method == "HEAD" and err.code in (403, 405):
                    continue
                return url, err.code
            except (urllib.error.URLError, TimeoutError) as err:
                return url, str(err)
        return url, "no answer"

    bad = []
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        for url, status in pool.map(probe, sorted(urls)):
            if not (isinstance(status, int) and status < 400):
                bad.append("%s -> %s" % (url, status))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--external", action="store_true", help="also request every http(s) link")
    args = ap.parse_args()

    failures, external, pages = [], set(), 0
    for path in sorted(glob.glob(os.path.join(args.root, "**", "*.html"), recursive=True)):
        pages += 1
        p = Page()
        with open(path, encoding="utf-8") as fh:
            p.feed(fh.read())
        p.close()
        p.finish()
        failures += ["%s: %s" % (path, err) for err in p.errors]
        for line, link in p.links:
            parsed = urllib.parse.urlsplit(link)
            if parsed.scheme in ("http", "https"):
                external.add(urllib.parse.urlunsplit(parsed._replace(fragment="")))
            elif parsed.scheme in ("data", "mailto"):
                continue
            elif not parsed.path:
                if parsed.fragment and parsed.fragment not in p.ids:
                    failures.append("%s:%d: #%s names no id on the page" % (path, line, parsed.fragment))
            else:
                target = os.path.normpath(os.path.join(os.path.dirname(path), urllib.parse.unquote(parsed.path)))
                if os.path.isdir(target):
                    target = os.path.join(target, "index.html")
                if not os.path.isfile(target):
                    failures.append("%s:%d: %s does not exist in the tree" % (path, line, link))

    if args.external:
        print("== requesting %d external links" % len(external))
        failures += check_external(external)

    for f in failures:
        print("!! " + f)
    print("== %d page(s), %d problem(s)" % (pages, len(failures)))
    return 1 if failures or not pages else 0


if __name__ == "__main__":
    sys.exit(main())
