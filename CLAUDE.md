# Instructions for agents working in this repository

`site.py` builds the site at `https://prx0.com/`: a landing page and one page per PlayStation 4
port. [README.md](README.md) says how to run it; [SOURCES.md](SOURCES.md) says where every fact on
the pages comes from, and a new one belongs there too.

- ⚠ `https://cores.prx0.com/.index-extended` and the `*_libretro.prx.zip` files next to it are
  what installed RetroArch packages download cores from. Never write, delete or move anything in
  that bucket except `index.html`, which is the redirect to `prx0.com/retroarch/`.
- ⚠ Never ask for, print, or place a Cloudflare or GitHub token value in the conversation, a file
  in this repo, or shell history. Give the maintainer the `gh secret set …` command to run
  themselves.
- Do not commit or push unless the maintainer asks. Keep commit messages to a subject plus two
  short lines.
- Python 3 standard library only. No npm, no external fonts or scripts on the pages.
- Facts on the pages come from releases, `cores.json`, `data/` or a cited source, never from
  memory. When something user-facing is not written down anywhere, ask.
- `tools/parity.py` guards the RetroArch page against losing rows, verdicts, settings or source
  links; `tools/check-html.py` guards the tags and links. Run both after changing `site.py`.
