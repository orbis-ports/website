# Where each fact on the site comes from

Every factual sentence `site.py` writes, and where it is written down. Numbers, versions, dates,
sizes, commits and licences of cores are not listed one by one: they are read at build time from
the source named in the last column and are never typed into a template.

Abbreviations:

- **RA notes**: `orbis-ports/RetroArch` `ps4/RELEASE-NOTES.md` at `274fff628c`, the body of
  release `retroarch-ps4-v0.1.8`.
- **Sonic release**: the body of `orbis-ports/sonic3air` release `sonic3air-ps4-v26.08.15.0-r1`
  (from `Oxygen/sonic3air/build/_ps4/RELEASE-NOTES.md`).
- **OG notes**: `orbis-ports/OpenGothic` `ps4/RELEASE-NOTES.md` on `ps4-support` (`3eb6c75b`), the body
  of release `opengothic-ps4-v0.92-r1` after the "Based on upstream" line `ps4.yml` adds.
- **make-site page**: the page `ps4/make-site.py` published at `https://cores.prx0.com/index.html`
  for the 2026-09-15 index, kept as `fixtures/make-site-2026-09-15.html`.

## Read at build time

| On the page | Source |
|---|---|
| Version, release date, package size and link, SHA-256 link, release name | GitHub REST `GET /repos/{repo}/releases`: newest non-draft release whose tag starts with `tag_prefix`, asset matching `pkg_asset` |
| "Released" / "Not released yet" | the same call: no such release means not released |
| Sonic 3 A.I.R. and OpenGothic page bodies | the release body verbatim; with no release, `notes_path` on `branch` |
| Licence of a port repository (Sonic GPL-3.0, OpenGothic MIT) | GitHub REST `GET /repos/{repo}`, `license.spdx_id` |
| orbis-compat licence (MIT) | the same |
| Core rows, sizes, commits, repositories, names, systems, licences, index date, bundle | `cores.json` (PLAN.md 4.2) |
| "N of the M cores in the build recipe do not build" | `cores.json` `recipe_missing` / `recipe_total`, counted from the run's manifests; 69 of 182 agrees with RA notes "Known limits" |
| "N of the M have been run on a real PlayStation 4", verdicts, notes | `data/retroarch/core-tested.tsv` (evidence column per row) |
| Recommended settings | `data/retroarch/core-options.tsv` (evidence column per row) |
| Non-commercial count and marks | the licence strings in `cores.json`, matched as make-site.py matched them |

## Landing page (`/`)

| Sentence | Source |
|---|---|
| Ports are for a jailbroken PlayStation 4 running GoldHEN | RA notes line 1; Sonic release "on a jailbroken console (GoldHEN)"; OG notes line 1 |
| Each one is a package you install yourself | the Install section of all three |
| RetroArchV summary: "RetroArch, the libretro emulation frontend, with {cores} cores built for this console" | RA notes line 1 and "What is here: 113 cores, built for this console"; the count from `cores.json` |
| Sonic 3 A.I.R. summary | `orbis-ports/sonic3air` `README.md` line 3 |
| OpenGothic summary | `orbis-ports/OpenGothic` `README.md` line 2 |
| RetroArchV needs network for the Core Downloader, or the offline bundle | RA notes "First run"; make-site page "With a console that has no network" |
| Sonic needs the Sonic 3 & Knuckles ROM from the Steam release, not included | Sonic release, Install 2 |
| OpenGothic needs your own Gothic II installation, not included; a USB keyboard | OG notes, Install 2 and 3 |
| Copy the `.pkg` to `/data/pkg` over FTP; Settings → Debug Settings → Package Installer | RA notes "Install" |
| … or GoldHEN's own package installer | Sonic release and OG notes, Install 1 |
| RetroArchV tested on firmware 11.00 with GoldHEN v2.4b18.10, by SiSTRo; other firmware may work, nobody has checked | RA notes "Install"; values in `ports/retroarch.json` `tested_on` |
| Each port installs under its own title id; collisions are decided by title id | RA notes "Install" |
| Title ids RTRV00001, SAIR00001, TMPS10021 | RA notes; Sonic release Install 1; OG notes Install 1 |
| Keeps its files in `/data/retroarch/` | make-site page "Where everything lives" |
| … `/data/sonic3air/` | Sonic release Install 2 and "Settings, progress and the log file are kept in `/data/sonic3air/savedata/`" |
| … `/data/OpenGothic/` | OG notes "Saves are kept in `/data/OpenGothic/`" |
| Quit with Quit RetroArch or the Quit combo | RA notes "Quitting" |
| Quit with Exit in the game's main menu | Sonic release and OG notes, "Known issues" |
| Closing from the console's menu does not end a port cleanly | RA notes "Quitting" (CE-34878-0); Sonic release "does not work properly"; OG notes "does not answer the system's close request" |
| All of them draw through the same graphics stack and link against the same platform layer | RA notes line 3 (RADV, zink); Sonic release "(mesa-ps4)"; OG notes "Vulkan on RADV (mesa-ps4)"; orbis-compat repository description "Every other repository in this org depends on it" |
| mesa-ps4: RADV for Vulkan, OpenGL 4.6 through zink | mesa-ps4 repository description "RADV on the PlayStation 4"; RA notes line 3 and "New in v0.1.7" |
| mesa-ps4 is MIT | `docs/license.rst` in mesa-ps4; make-site page "(MIT)". GitHub detects no single licence for Mesa, so this one is in `data/platform.json` |
| orbis-compat: toolchain files, libc and pthread shims, Vulkan loader shim, packaging, logging | orbis-compat repository description |

## Sonic 3 A.I.R. (`/sonic3air/`) and OpenGothic (`/opengothic/`)

| Sentence | Source |
|---|---|
| Tagline | the summary, as on the landing page |
| Title id pill | as on the landing page |
| "Before you start": jailbroken console with GoldHEN, and the requirements | as on the landing page |
| Everything under "The notes below are the text of the release …" | the release body, rendered, not edited |
| While unreleased: "There is no PlayStation 4 package yet" | GitHub releases: none with the port's tag prefix |
| … upstream's own releases are builds for desktop systems | OpenGothic `README.md` "Supported systems: Windows, Linux, MacOS" |
| … the notes are the file its first release will carry | the port's `ps4.yml` release job, `body_path` built from `ps4/RELEASE-NOTES.md` |
| Source at the release tag (or branch), licence | GitHub releases; GitHub REST `license.spdx_id` |

## RetroArchV (`/retroarch/`)

The page is the make-site page moved here, and every sentence not listed below is unchanged from
it. Changed or added:

| Sentence | Source |
|---|---|
| Tagline: "Vulkan through RADV and desktop OpenGL 4.6 through zink" (was "OpenGL ES") | RA notes line 3 |
| Install: now a link to the landing page's install section; title id paragraph kept | PLAN.md section 3 |
| Directory table: `/data/retroarch/shader-cache` | RA notes "New in v0.1.8", "Less stutter when new shaders appear" |
| Source list: orbis-ports/3dsTrident, the Nintendo 3DS core, forked for this platform | RA notes "New in v0.1.8"; `ps4/core-recipe-extra` trident line |
| A core built with patches of this port's own also links those patches | `ps4/core-patches/README.md`: "a core built with patches shows `<commit>+<n>`" |
| Known limits: "N of the M cores in the build recipe do not build" (was 63 of 164) | `cores.json`; RA notes "Known limits" |
| Built from: trident links orbis-ports/3dsTrident, dosbox_pure links schellingb/dosbox-pure | `ps4/core-recipe-extra`, which wins over the recipe in `build-cores.sh`; see `tools/parity-allow-make-site.tsv` |
| Footer: generated by site.py from cores.json | this repository |

## cores.prx0.com/index.html (the redirect)

| Sentence | Source |
|---|---|
| The page has moved to prx0.com/retroarch/ | PLAN.md section 3 |
| The cores are still served from here, so the Core Downloader is unaffected | PLAN.md 2.3; RetroArch `config.def.h:1981` |
