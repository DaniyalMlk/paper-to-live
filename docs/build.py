#!/usr/bin/env python3
"""Write the site out.

    python docs/build.py

Kept apart from ``docs/pages.py`` so that the generator itself touches no
filesystem and the tests can call it directly. No dependency beyond the
standard library and the pipeline, because a documentation build that needs a
toolchain is a documentation build that stops working.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# `docs/site.py` would shadow the standard library's `site`, which is already
# imported before this script runs, so the generator is `pages`.
from pages import ROOT, build_site, measure

OUT = ROOT / "site"


def main() -> int:
    # Cleared rather than written over: a page the generator no longer produces
    # should not survive in the published site because it was there last time.
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    measured = measure()
    files = build_site(measured)
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")

    erosion = measured.payload["erosion"]
    print(
        f"site: {', '.join(sorted(files))}\n"
        f"erosion: {erosion['paper_sharpe_annual']:.2f} paper, "
        f"{erosion['surviving_sharpe_annual']:.2f} surviving "
        f"({erosion['fraction_surviving'] * 100:.0f}%); "
        f"{len(measured.rows)} evidence rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
