# Plan: one landing page for every orbis-ports PlayStation 4 port

This repository will build and publish the public website for the ports in the `orbis-ports`
organisation. Today there is exactly one page: the RetroArch cores page at
`https://cores.prx0.com/index.html`. It is generated inside the RetroArch repository by
`ps4/make-site.py` and published by the RetroArch cores workflow. The goal is a landing page that
presents every port, with the RetroArch page moved here as one of them. After that, all
site code is removed from the RetroArch repository.

This file is written for the agent that does the work. Read it whole before starting. The phases
are ordered. Each one ends with a check that must pass before the next starts.

Everything referenced here is pinned. Snapshot of the source page: `orbis-ports/RetroArch` at
commit `274fff628c` (branch `ps4-support`), written 2026-09-15.

---

## 1. The ports

| Port | Repository | Package | Public release | Notes |
|---|---|---|---|---|
| **RetroArchV** | [orbis-ports/RetroArch](https://github.com/orbis-ports/RetroArch), branch `ps4-support` | `RetroArchV-PS4-vX.Y.Z.pkg`, title id `RTRV00001` | tags `retroarch-ps4-v*`, latest `retroarch-ps4-v0.1.8` | 113 libretro cores served from `cores.prx0.com`; release notes in `ps4/RELEASE-NOTES.md` |
| **Sonic 3 A.I.R.** | [orbis-ports/sonic3air](https://github.com/orbis-ports/sonic3air), branch `ps4-support` | `Sonic3AIR-PS4-vV-rN.pkg` + `.sha256` | tags `sonic3air-ps4-v<upstream>-r<rev>`, latest `sonic3air-ps4-v26.08.15.0-r1` | release body carries install notes; workflow `.github/workflows/ps4.yml` |
| **OpenGothic** | [orbis-ports/OpenGothic](https://github.com/orbis-ports/OpenGothic), branch `ps4-support` | built locally so far (`ps4/build.sh`), icon `ps4/icon0.png` | **no PS4 release yet** - the repo's releases/tags are upstream's desktop ones (`v0.92`) | needs a USB keyboard (commit `ee1567f6`); needs the game's own data files |

⚠ **OpenGothic has no public PS4 package.** Do not link upstream's desktop release as if it were the
port. Its card must say it is not released yet, and it must switch to a download automatically once
a PS4 release exists. Pick and document a tag prefix (proposal: `opengothic-ps4-v*`) and match on
it, the same way RetroArch and Sonic are matched.

Shared platform facts, true for all three: jailbroken console with GoldHEN; tested on firmware
11.00 with GoldHEN v2.4b18.10; install the `.pkg` from `/data/pkg` with *Settings → Debug Settings →
Package Installer*. Graphics run on [mesa-ps4](https://github.com/orbis-ports/mesa-ps4)
(RADV, plus OpenGL 4.6 through zink) and the platform layer is
[orbis-compat](https://github.com/orbis-ports/orbis-compat). Take the exact wording from each
port's release notes, not from this summary.

---

## 2. What exists today (the RetroArch page)

### 2.1 Files in `orbis-ports/RetroArch`

| Path | Role | Fate |
|---|---|---|
| `ps4/make-site.py` (755 lines, Python stdlib only) | renders `index.html`, builds the all-cores bundle zip | page code moves here; the bundle builder stays in RetroArch (see 4.2) |
| `ps4/core-tested.tsv` | per-core "ran on a PS4" verdicts (plays/slow/boots/broken) + evidence column | moves here, it is editorial content |
| `ps4/core-options.tsv` | per-core recommended options (key, label, value, why, evidence) | moves here |
| `ps4/icon0.png` | app icon, inlined as favicon and header mark | **copy**, do not move - the `.pkg` build uses it (`Makefile.orbis:127`) |
| `.github/workflows/cores.yml`, step "Build and publish the download page" (~line 1225) | runs make-site.py, uploads `index.html` + `orbis-cores-<date>.zip` to R2 | replaced by a data publish + a dispatch to this repo (4.2, phase 6) |

Read `make-site.py` in full before writing anything. Its comments record decisions that were paid
for, and each one must survive the move:

- **"untested" is a claim.** It appears only when the verdict file was read. A verdict for a core
  missing from the index is reported on stderr, not silently dropped.
- **Source links point at the exact commit** each core was built from. This is a GPL obligation,
  not decoration. It must never degrade to "the project" link.
- **Non-commercial licences** are counted and marked per row.
- **The bundle card is required.** Without it an offline user has nothing. The generator warns
  when it is missing.
- **Recommended settings** render only from `core-options.tsv`, in index order, and link from each
  core's row.
- **Layout decisions**: centred 86ch prose column in a 1100px wrapper; tables get their own
  horizontal scroll; the "On a PS4" column is second so it shows at phone width.

### 2.2 How it is published

- **Host.** Cloudflare R2 bucket (repository variable `R2_CORES_BUCKET` in RetroArch; the bucket is
  `orbis-cores`), public at `CORES_BASE_URL` = `https://cores.prx0.com/`. Uploads use
  `npx wrangler@4 r2 object put … --remote`. Secrets in the RetroArch repo:
  `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
- **Same directory as the cores**, on purpose: `.index-extended`, every `*_libretro.prx.zip`, the
  bundle and `index.html` all sit in one place.
- **Page inputs at build time:**
  - `dist/.index-extended`: date, crc, filename, per core;
  - `dist/cores-manifest*.tsv`: result, size, commit sha, per core;
  - the libretro-super recipe at a pinned ref: repository URL per core, plus
    `ps4/core-recipe-extra`, which wins;
  - `libretro-core-info` at a pinned ref: display name, system, licence;
  - the two TSVs;
  - the latest `retroarch-ps4-v*` release: pkg URL, size, version.
- **When it rebuilds.** Only when a cores run publishes. A new frontend tag does not refresh the
  page, so it keeps offering the old version until the next cores run. This is a known defect of
  the current setup; phase 6 step 2 fixes it.
- `https://prx0.com/` (the apex) resolves to Cloudflare but serves nothing today (HTTP connect
  fails).

### 2.3 ⚠ Hard constraint: the console's core downloader

`config.def.h:1981` compiles `ORBIS_BUILDBOT_SERVER_URL "https://cores.prx0.com/"` into every
RetroArch package already installed on consoles. RetroArch builds each download URL as
`<buildbot_url><filename>`, using filenames from `.index-extended`.

**`https://cores.prx0.com/.index-extended` and every `https://cores.prx0.com/*_libretro.prx.zip` must
keep answering 200 at exactly those URLs, through every phase of this work.** R2 is the host
because it keeps the leading dot in `.index-extended`; GitHub Releases rename it. Nothing in this
repository may write, prune or re-prefix objects in that bucket except `index.html`, which becomes the
redirect in phase 5. The cores workflow in RetroArch owns everything else there, the bundle and
`cores.json` included.

Check after every deploy:

```sh
curl -s -o /dev/null -w '%{http_code}\n' https://cores.prx0.com/.index-extended   # 200
f=$(curl -s https://cores.prx0.com/.index-extended | awk 'NR==1{print $3}')
curl -s -o /dev/null -w '%{http_code}\n' "https://cores.prx0.com/$f"             # 200
```

### 2.4 Content on the current page (all of it must land somewhere)

The sections, in order:
1. Header: icon, tagline, pills for package version, core count, index date, firmware, GoldHEN.
2. Download cards: the package, and the all-cores archive.
3. Note: quit from inside the app, not from the console, because of CE-34878-0.
4. Install.
5. First run: Update Core Info Files.
6. With a console that has no network.
7. Where everything lives: the directory table.
8. Edit the config with RetroArch closed.
9. Configuring it.
10. Source code and licences.
11. Known limits.
12. Recommended settings.
13. The cores: table and legend.
14. Footer.

⚠ Some copy has gone stale; fix it during the move and take the facts from `ps4/RELEASE-NOTES.md`
at the pinned commit:
- the tagline says "OpenGL ES through zink" (it is desktop GL 4.6 now);
- "Known limits" says "63 of the 164 cores" (the release notes say 69 of 182 do not build).

---

## 3. Target

- **`https://prx0.com/`: the landing page.** One card per port, with name, icon, one-line
  description, status, latest version with download (or "not released yet") and a link to the
  port page. Then the shared material, written once: requirements (GoldHEN, firmware), how to
  install a `.pkg`, and the platform projects (mesa-ps4, orbis-compat) with licences.
- **`https://prx0.com/retroarch/`**: the current RetroArch page, migrated, minus the shared
  install material now on the landing page (link to it instead).
- **`https://prx0.com/sonic3air/`** and **`https://prx0.com/opengothic/`**: port pages built from
  each port's release notes (or README section) plus requirements: game data, keyboard for
  OpenGothic.
- **`https://cores.prx0.com/index.html`**: becomes a redirect to `https://prx0.com/retroarch/`,
  a static page with meta refresh + link, because R2 objects cannot send 301s. Everything else at
  `cores.prx0.com` stays untouched (2.3).

Stack: Python 3 standard library only, the same as `make-site.py`. No npm build, no framework, no
external fonts or scripts. One generator, `site.py`, reads `ports/*.json` (one file per port) plus
fetched data and writes a static tree to `out/`. The visual language (CSS tokens, dark ground,
orange accent) comes from `make-site.py`; extend it rather than redesign.

---

## 4. Data contracts

### 4.1 Per-port metadata: `ports/<id>.json`, hand-written, in this repo

```json
{
  "id": "retroarch",
  "name": "RetroArchV",
  "repo": "orbis-ports/RetroArch",
  "branch": "ps4-support",
  "tag_prefix": "retroarch-ps4-v",
  "pkg_asset": "RetroArchV-PS4-*.pkg",
  "title_id": "RTRV00001",
  "icon": "icons/retroarch.png",
  "summary": "Emulation frontend with 113 libretro cores built for the console.",
  "notes_path": "ps4/RELEASE-NOTES.md",
  "requires": ["GoldHEN", "network for the Core Downloader, or the offline bundle"]
}
```

For every port, the generator takes the release list through the GitHub REST API
(`GET /repos/{repo}/releases`): the newest non-draft release whose tag starts with `tag_prefix`, and
the asset matching `pkg_asset`, giving URL, size and date. With no such release, the port shows as
"not released yet".

Unauthenticated calls have a 60/hour limit. In CI, use `GITHUB_TOKEN`. Locally, `gh auth token` if
present.

Icons are copied into this repo: `icons/`. Sources:
- `RetroArch/ps4/icon0.png`;
- `OpenGothic/ps4/icon0.png`;
- for Sonic, find the packaging icon in `orbis-ports/sonic3air` (its PS4 packaging step).

### 4.2 RetroArch cores data: published by RetroArch, consumed here

Only the RetroArch cores workflow has `dist/` (the manifests), so it must publish what the page
needs as data. **The agent here defines the schema and writes the generator against it; the change
to `cores.yml` is phase 6**, done in the RetroArch repository.

Contract: `https://cores.prx0.com/cores.json`, written by `cores.yml` after `.index-extended`:

```json
{
  "schema": 1,
  "index_date": "2026-09-15",
  "run": "https://github.com/orbis-ports/RetroArch/actions/runs/<id>",
  "bundle": {"file": "orbis-cores-2026-09-15.zip", "bytes": 123456789},
  "recipe_missing": 69, "recipe_total": 182,
  "cores": [
    {"name": "trident", "file": "trident_libretro.prx.zip", "crc": "…", "date": "2026-09-15",
     "size": "26M", "sha": "402316c", "repo": "https://github.com/orbis-ports/3dsTrident",
     "display_name": "…", "system": "…", "license": "…"}
  ]
}
```

- The bundle keeps being built and uploaded by `cores.yml`. It is an artifact of the cores, and
  it needs `dist/`. Moving `build_bundle()` into a small script under RetroArch's `ps4/` is part of
  phase 6.
- Until phase 6 lands, produce a `cores.json` for development with `tools/cores-json-from-live.py`
  (write it). It should read the live `.index-extended`, the pinned recipe and core-info refs, and
  the RetroArch repo at the pinned commit. Mark the commit column "unknown" where no manifest is
  available: **never invent a sha**. Keep the result as `fixtures/cores.json`, and test the
  generator against it.

---

## 5. Phases

### Phase 0: decisions to confirm with the maintainer before writing deploy code

Build phases 1-3 locally without these. Deploy (phase 5) needs them.

1. **Hosting for `prx0.com`.**
   - Proposal: a second R2 bucket with a custom domain on the apex. It needs the same tooling as
     today (`wrangler r2 object put`), and no new product.
   - Alternative: Cloudflare Pages.
2. **URL layout** from section 3 (`/`, `/retroarch/`, `/sonic3air/`, `/opengothic/`).
3. **OpenGothic tag prefix** for its future PS4 releases.
4. **Secrets for this repo:** `CLOUDFLARE_API_TOKEN` (scoped to the site bucket, plus write on
   `orbis-cores` for `index.html` and the redirect only) and `CLOUDFLARE_ACCOUNT_ID`.
   - ⚠ **The token value never passes through an agent conversation or shell history.** The
     maintainer enters it at a prompt, e.g. `gh secret set CLOUDFLARE_API_TOKEN -R orbis-ports/website`
     (it reads stdin), or from a `umask 077` file that is wiped afterwards.
   - An agent may only print the command for the maintainer to run.

### Phase 1: generator skeleton + landing page

- `site.py --ports ports --cores-json <path|url> --out out`.
- Outputs: `out/index.html`, one directory per port.
- Landing cards read releases live (4.1).
- **Check:** `python3 site.py … --out out` runs with no network errors. The landing page lists 3
  ports. RetroArch and Sonic show their current versions and pkg sizes, matching
  `gh release view`. OpenGothic shows "not released yet". The page validates: no unclosed tags. It
  works at 400px width with no horizontal body scroll.

### Phase 2: migrate the RetroArch page

- Port `make-site.py` rendering into `site.py`, reading `cores.json` (4.2) instead of `dist/`, the
  recipe and core-info.
- Move `core-tested.tsv` and `core-options.tsv` here as `data/retroarch/` with their header
  comments, and keep `read_tested` / `read_options` validation.
- Move the shared install material to the landing page; link to it from the RetroArch page.
- Fix the stale copy (2.4).
- **Check (parity):** render against `fixtures/cores.json` and compare with the live
  `https://cores.prx0.com/index.html`. The comparison must match on:
  - same core rows in the same order;
  - same "On a PS4" verdicts and notes;
  - same recommended-settings blocks;
  - same source links and licence marks.
  Write the comparison as `tools/parity.py`, parsing both HTMLs, and keep it: it is the regression
  test for phase 6.

### Phase 3: Sonic 3 A.I.R. and OpenGothic pages

- Sonic: content from the latest release body (install, data files, controls). Link the release
  and the `.sha256`.
- OpenGothic: what it is, that it needs the original game data and a USB keyboard, current state
  ("not released yet"), and the source link.
  - ⚠ Ask the maintainer for anything user-facing that is not written down in the OpenGothic repo.
    Do not fill gaps with guesses about compatibility or performance.
- **Check:** every factual sentence on these pages traces to a release body, README, or commit.
  List the sources in `SOURCES.md`.

### Phase 4: CI in this repo

- Workflow `.github/workflows/site.yml`.
- Triggers: `push` to main; `workflow_dispatch`; `repository_dispatch` types `retroarch-cores`,
  `port-release`; and a daily `schedule` as a backstop.
- It builds `out/` and runs the parity and link checks. Deploy happens only on main.
- **Check:** a dispatch from `gh workflow run site.yml` builds and uploads the artifact, with the
  deploy step skipped until phase 5.

### Phase 5: deploy

- Upload `out/` to the chosen host (phase 0).
- Upload the redirect page to `orbis-cores` as `index.html`, only after `prx0.com/retroarch/`
  answers 200.
- **Check:**
  - `https://prx0.com/` and all port pages answer 200;
  - `https://cores.prx0.com/index.html` redirects;
  - the core downloader checks in 2.3 still pass;
  - on a console, RetroArch's Core Downloader still lists cores (ask the maintainer to confirm).

### Phase 6: cut the site out of RetroArch (done in `orbis-ports/RetroArch`, not here)

Done from the RetroArch working tree after phase 5 passes, by the maintainer's RetroArch session.
Listed here so this repo's contract matches it.

1. `cores.yml`:
   - replace "Build and publish the download page" with a step that builds the bundle
     (`ps4/make-bundle.py`, extracted from `build_bundle()`) and writes `cores.json` per 4.2;
   - upload both, then `cores.json` last (after `.index-extended`);
   - then `gh api repos/orbis-ports/website/dispatches -f event_type=retroarch-cores` with a token
     that can dispatch: a fine-grained PAT or GitHub App secret, entered by the maintainer (same
     rule as phase 0).
2. `frontend.yml`: on a `retroarch-ps4-v*` tag, dispatch `port-release`, so a new version shows
   without waiting for a cores run (fixes 2.2's defect).
3. Delete `ps4/make-site.py`, `ps4/core-tested.tsv` and `ps4/core-options.tsv`. Keep `ps4/icon0.png`.
4. Fix references: comments in `cores.yml` (~line 656 and ~1206), `ps4/README.md` if it mentions
   the page, and `ps4/RELEASE-NOTES.md` "at `cores.prx0.com`" → `prx0.com/retroarch`.
5. Sonic's `ps4.yml` release job and OpenGothic's future release job dispatch `port-release` too.
6. **Check:**
   - one cores dispatch in RetroArch produces `cores.json`;
   - the site rebuild follows automatically;
   - `tools/parity.py` passes against the previous render;
   - the checks in 2.3 pass.

---

## 6. Working rules for this repository

- Commit messages: subject plus at most two short lines. Reasoning goes in code comments and this
  plan, not the git log.
- Do not commit or push until asked. Iterate in the working tree.
- Keep the generator dependency-free: Python stdlib, no pip. The old page ran in CI with nothing
  installed, and that is worth keeping.
- Every number on a page comes from data (a release, `cores.json`, a TSV) or from a cited source.
  Nothing is typed into a template by hand.
- Update this plan when a decision is made: replace the proposal text with the decision and the
  date.
