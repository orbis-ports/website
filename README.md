# orbis-ports website

The public site for the PlayStation 4 ports in this organisation: RetroArchV, Sonic 3 A.I.R. and
OpenGothic. It is published at `prx0.com`, with the RetroArch core host at `cores.prx0.com`.
[SOURCES.md](SOURCES.md) says where every fact on the pages comes from.

Python 3 standard library only:

    python3 site.py --cores-json fixtures/cores.json --out out --redirect redirect/index.html
    python3 tools/check-html.py out [--external]
    python3 tools/parity.py fixtures/make-site-2026-09-15.html out/retroarch/index.html \
        --allow tools/parity-allow-make-site.tsv

`site.py` reads GitHub releases, so it uses `GITHUB_TOKEN`, or `gh auth token` when that is set up.

| Path | What it is |
|---|---|
| `site.py` | the generator |
| `ports/*.json` | one file per port |
| `data/retroarch/` | what has run on a console, recommended core options |
| `data/platform.json` | mesa-ps4 and orbis-compat |
| `icons/` | each port's package icon |
| `fixtures/` | `cores.json` for the 2026-09-15 cores, and the page make-site.py published for them |
| `tools/cores-json-from-live.py` | builds `cores.json` from a published index and its run's artifacts |
| `tools/parity.py` | compares the cores content of two RetroArch pages |
| `tools/check-html.py` | unclosed tags, duplicate ids, dead links |
