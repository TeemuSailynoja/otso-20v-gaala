#!/usr/bin/env python3
"""Compare two rendered-DOM captures from tools/render_gate.sh.

    tools/dump_diff.py <before-dir> <after-dir> [--raw]

The dumps contain two kinds of thing. One is the rendered page: the DOM the script
built. The other is source text that happens to live inside the document — the
`<style>` block and the inline `<script>` — which dump-dom serializes whether or
not it did anything. Phase 11 moves exactly those two things out of index.html, so
a byte comparison would report a 55 KB change that is not a change in the page.

So the comparison normalizes: every <style> and <script> element keeps its
attributes and loses its body. What is left is the rendered DOM, and that is what
has to be identical. `--raw` skips the normalization, for when the point *is* the
markup of the shell.

The attributes are kept on purpose: after the split the shell should show
<link rel="stylesheet" href="css/site.css"> and <script type="module"
src="js/main.js">, and a silently missing stylesheet would otherwise look like a
pass.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

# Attributes kept, body dropped. Non-greedy so two blocks do not merge.
BLOCK = re.compile(r"<(style|script)\b([^>]*)>.*?</\1>", re.DOTALL | re.IGNORECASE)


def normalize(text: str) -> str:
    return BLOCK.sub(lambda m: f"<{m.group(1)}{m.group(2)} />", text)


def main(before: str, after: str, raw: bool = False) -> int:
    bdir, adir = Path(before), Path(after)
    names = sorted(p.name for p in bdir.glob("route*.html"))
    missing = set(names) ^ {p.name for p in adir.glob("route*.html")}
    if missing:
        print(f"DIFFERENT ROUTE SETS: {sorted(missing)}")
        return 1

    bad = 0
    for name in names:
        b = (bdir / name).read_text(encoding="utf-8")
        a = (adir / name).read_text(encoding="utf-8")
        if not raw:
            b, a = normalize(b), normalize(a)
        if b == a:
            print(f"identical  {name}")
            continue
        bad += 1
        print(f"DIFFERS    {name}  ({len(b)} -> {len(a)} chars)")
        diff = difflib.unified_diff(
            b.splitlines(), a.splitlines(), "before", "after", lineterm="", n=1
        )
        for line in list(diff)[:40]:
            print("   " + line[:200])
    print(f"\n{len(names) - bad} of {len(names)} routes render identically")
    return 1 if bad else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--raw"]
    if len(args) < 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(args[0], args[1], "--raw" in sys.argv))
