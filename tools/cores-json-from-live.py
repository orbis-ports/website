#!/usr/bin/env python3
"""Write cores.json (PLAN.md 4.2) for a cores set that is already published.

The cores workflow in orbis-ports/RetroArch is meant to write this file itself, next to
.index-extended, because only that job holds every input at once. Until it does, this rebuilds the
same file from the outside:

    .index-extended        https://cores.prx0.com/.index-extended, or --index
    cores-manifest-*.tsv   --manifests: the shard artifacts of the run that published that index
    the recipe             libretro-super at the ref cores.yml pins, plus ps4/core-recipe-extra
    core info              libretro-core-info at the ref cores.yml pins
    the bundle size        a HEAD request for orbis-cores-<index date>.zip

The artifacts of a cores run are fetched with, for example:

    gh run download <run id> -R orbis-ports/RetroArch -p 'cores-shard-*' -D <dir>

⚠ WITHOUT --manifests EVERY COMMIT IS "unknown", AND THAT IS THE POINT. The sha is the corresponding
source for a GPL binary. A sha taken from anywhere but the manifest written beside the binary could
name a different build, and it would look exactly as true as a right one. The index fragments in the
artifacts carry the CRC of each .prx, so the manifests are only used after every fragment has been
checked against the published index.

Every input has a local override (--index, --recipe, --recipe-extra, --info) so the cores workflow
can run this same code inside the publish job once it takes over (PLAN.md phase 6).
"""

import argparse
import glob
import io
import json
import os
import re
import sys
import tarfile
import urllib.error
import urllib.request

FRONTEND_REPO = "orbis-ports/RetroArch"
# The commit PLAN.md is pinned to; the run that published the 2026-09-15 index was built from it.
FRONTEND_COMMIT = "274fff628c7b185f1bd926b32afb3f77b82cf3c0"
RECIPE_PATH = "recipes/linux/cores-linux-x64-generic"

# ⚠ CORES BUILT FROM A FORK OF OUR OWN, whose source is NOT where the recipe points. The same list as
# PS4_CORE_FORKS in RetroArch's ps4/build-cores.sh and FORKS in the old ps4/make-site.py. Applied
# after the recipe and the extra file, so neither can put upstream back.
FORKS = {
    "mednafen_psx_hw": "https://github.com/orbis-ports/beetle-psx-libretro",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "orbis-ports-website"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def read_text(src):
    if re.match(r"https?://", src):
        return fetch(src).decode("utf-8")
    with open(src, encoding="utf-8") as fh:
        return fh.read()


def parse_index(text):
    """[(date, crc, filename, core)] in index order. Same rules as core_updater_list.c."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        date, crc, filename = parts
        name = filename
        for suffix in (".zip", ".prx"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        if name.endswith("_libretro"):
            name = name[: -len("_libretro")]
        out.append((date, crc, filename, name))
    return out


def read_manifests(dirs):
    """core -> (result, size, sha), and the index fragments found beside them."""
    man, fragments = {}, []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "**", "cores-manifest-*.tsv"), recursive=True)):
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 4:
                        man[parts[0]] = (parts[1], parts[2], parts[3])
        for path in sorted(glob.glob(os.path.join(d, "**", "index-fragment-*.txt"), recursive=True)):
            fragments.extend(parse_index(read_text(path)))
    return man, fragments


def parse_recipe(text, repos=None):
    repos = {} if repos is None else repos
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith("http"):
            repos[parts[0]] = parts[2]
    return repos


def parse_info_file(text):
    fields = {}
    for key in ("display_name", "systemname", "license"):
        m = re.search(r'^%s = "(.*)"' % key, text, re.M)
        if m:
            fields[key] = m.group(1)
    return fields


def read_info_tarball(data):
    info = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            base = os.path.basename(member.name)
            if member.isfile() and base.endswith("_libretro.info"):
                text = tar.extractfile(member).read().decode("utf-8", "replace")
                info[base[: -len("_libretro.info")]] = parse_info_file(text)
    return info


def read_info_dir(path):
    info = {}
    for p in glob.glob(os.path.join(path, "*_libretro.info")):
        with open(p, encoding="utf-8", errors="replace") as fh:
            info[os.path.basename(p)[: -len("_libretro.info")]] = parse_info_file(fh.read())
    return info


def pinned_ref(workflow, var):
    """The default sha cores.yml gives an env var: `VAR: ${{ ... || '<sha>' }}`."""
    m = re.search(r"^\s*%s:.*\|\|\s*'([0-9a-f]{40})'" % var, workflow, re.M)
    if not m:
        raise SystemExit("!! no pinned %s in cores.yml" % var)
    return m.group(1)


def head_bytes(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "orbis-ports-website"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            n = resp.headers.get("Content-Length")
            return int(n) if n else None
    except urllib.error.HTTPError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="https://cores.prx0.com/.index-extended", help="path or URL")
    ap.add_argument("--base", default="https://cores.prx0.com/", help="where the index and cores are served")
    ap.add_argument("--manifests", action="append", default=[], help="directory of cores-manifest-*.tsv; repeatable")
    ap.add_argument("--frontend-commit", default=FRONTEND_COMMIT,
                    help="orbis-ports/RetroArch commit the cores were built from (pins, recipe extra, patches)")
    ap.add_argument("--recipe", help="local libretro-super recipe instead of the pinned one")
    ap.add_argument("--recipe-extra", help="local ps4/core-recipe-extra instead of the one at --frontend-commit")
    ap.add_argument("--info", help="local directory of *_libretro.info instead of the pinned bundle")
    ap.add_argument("--bundle", help="bundle filename (default orbis-cores-<index date>.zip)")
    ap.add_argument("--bundle-bytes", type=int, help="its size (default: HEAD request to --base)")
    ap.add_argument("--run", default="", help="URL of the cores run that published the index")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    base = args.base if args.base.endswith("/") else args.base + "/"
    raw = "https://raw.githubusercontent.com/%s/%s/" % (FRONTEND_REPO, args.frontend_commit)

    index = parse_index(read_text(args.index))
    if not index:
        raise SystemExit("!! %s lists no cores" % args.index)

    man, fragments = read_manifests(args.manifests)
    if args.manifests:
        if not man:
            raise SystemExit("!! no cores-manifest-*.tsv under %s" % " ".join(args.manifests))
        # ⚠ THE MANIFESTS MUST DESCRIBE THE PUBLISHED FILES. A fragment is written beside the
        # archives it hashes, so a CRC mismatch means these artifacts are from another run.
        published = {f: (d, c) for d, c, f, _ in index}
        seen = {f: (d, c) for d, c, f, _ in fragments}
        wrong = sorted(f for f in published if seen.get(f) != published[f])
        if wrong:
            raise SystemExit("!! %d published core(s) do not match the artifacts' index fragments "
                             "(missing or a different CRC): %s" % (len(wrong), " ".join(wrong[:20])))
        print("== artifacts match the index: %d fragments" % len(fragments))

    workflow = None if (args.recipe and args.info) else fetch(raw + ".github/workflows/cores.yml").decode("utf-8")

    if args.recipe:
        recipe_text = read_text(args.recipe)
    else:
        ref = pinned_ref(workflow, "LIBRETRO_SUPER_REF")
        recipe_text = fetch("https://raw.githubusercontent.com/libretro/libretro-super/%s/%s" % (ref, RECIPE_PATH)).decode("utf-8")
        print("== recipe: libretro-super@%s" % ref[:10])
    extra_text = read_text(args.recipe_extra) if args.recipe_extra else fetch(raw + "ps4/core-recipe-extra").decode("utf-8")
    # ⚠ THE EXTRA FILE WINS OVER THE RECIPE, as it does in build-cores.sh. The old page read the
    # recipe alone and linked trident to upstream while the binary came from orbis-ports/3dsTrident.
    repos = parse_recipe(extra_text, parse_recipe(recipe_text))
    repos.update(FORKS)

    if args.info:
        info = read_info_dir(args.info)
    else:
        ref = pinned_ref(workflow, "CORE_INFO_REF")
        info = read_info_tarball(fetch("https://codeload.github.com/libretro/libretro-core-info/tar.gz/" + ref))
        print("== core info: libretro-core-info@%s, %d files" % (ref[:10], len(info)))

    index_date = index[0][0]
    bundle = args.bundle or "orbis-cores-%s.zip" % index_date
    bundle_bytes = args.bundle_bytes if args.bundle_bytes is not None else head_bytes(base + bundle)
    if bundle_bytes is None:
        print("== NO BUNDLE at %s%s: cores.json will have none, and the page no offline download"
              % (base, bundle), file=sys.stderr)

    cores = []
    for date, crc, filename, name in index:
        fields = info.get(name, {})
        if name in man:
            _, size, sha = man[name]
            sha = "" if sha.strip() in ("", "-") else sha.strip()
        else:
            size, sha = "", "unknown"
        cores.append({
            "name": name, "file": filename, "crc": crc, "date": date,
            "size": size.strip() if size.strip() != "-" else "", "sha": sha,
            "repo": (repos.get(name) or "").rstrip("/").removesuffix(".git"),
            "display_name": fields.get("display_name", ""),
            "system": fields.get("systemname", ""),
            "license": fields.get("license", ""),
        })

    doc = {
        "schema": 1,
        "index_date": index_date,
        "base": base,
        "run": args.run,
        "frontend_commit": args.frontend_commit,
        "bundle": {"file": bundle, "bytes": bundle_bytes} if bundle_bytes is not None else None,
        "recipe_total": len(man) if man else None,
        "recipe_missing": sum(1 for r in man.values() if r[0] != "OK") if man else None,
        "cores": cores,
    }
    for label, names in (("no commit sha", [c["name"] for c in cores if c["sha"] in ("", "unknown")]),
                         ("no repository", [c["name"] for c in cores if not c["repo"]]),
                         ("no licence", [c["name"] for c in cores if not c["license"]])):
        if names:
            print("== %d core(s) with %s: %s" % (len(names), label, " ".join(sorted(names))))

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("== %s: %d cores, index %s" % (args.out, len(cores), index_date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
