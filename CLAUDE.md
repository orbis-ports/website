# Instructions for agents working in this repository

Start with [PLAN.md](PLAN.md). It is the task, the constraints and the order of work.

- ⚠ `https://cores.prx0.com/.index-extended` and the `*_libretro.prx.zip` files next to it are
  what installed RetroArch packages download cores from. Never write, delete or move anything in
  that bucket except `index.html` and the bundle (PLAN.md 2.3).
- ⚠ Never ask for, print, or place a Cloudflare or GitHub token value in the conversation, a file
  in this repo, or shell history. Give the maintainer the `gh secret set …` command to run
  themselves.
- Do not commit or push unless the maintainer asks. Keep commit messages to a subject plus two
  short lines.
- Python 3 standard library only. No npm, no external fonts or scripts on the pages.
- Facts on the pages come from releases, `cores.json`, the TSVs or a cited source, never from
  memory. When something user-facing is not written down anywhere, ask.
