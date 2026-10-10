#!/usr/bin/env python3
"""Check that a rendered frame's background really is the colour it was asked to be.

    uv run --with pillow --no-project tools/verify_background.py <gif> [#rrggbb]

Frames from this recording end up on slides, and a slide background is white, so
a tinted terminal background shows as a grey rectangle the moment it is pasted in.
None of the built-in themes is pure white — `solarized-light` is #fdf6e3 and agg's
`github-light` renders #eceff4 — and a theme string that agg does not understand
fails quietly, leaving a background that looks fine until it is next to real white.

So: sample the pixels. Exit non-zero if they disagree with the requested colour.
"""

from __future__ import annotations

import sys
from collections import Counter

from PIL import Image


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2

    path = sys.argv[1]
    want_hex = sys.argv[2].lstrip("#") if len(sys.argv) > 2 else "ffffff"
    want = tuple(int(want_hex[i : i + 2], 16) for i in (0, 2, 4))

    im = Image.open(path)
    # The last frame carries the most content, so it is the least flattering test.
    im.seek(getattr(im, "n_frames", 1) - 1)
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    counts = Counter(px[x, y] for y in range(0, h, 4) for x in range(0, w, 4))
    dominant, n = counts.most_common(1)[0]
    share = n / sum(counts.values()) * 100
    corners = {px[2, 2], px[w - 3, 2], px[2, h - 3], px[w - 3, h - 3]}

    def fmt(c: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*c)

    print(f"  size       {w}x{h}, {getattr(im, 'n_frames', 1)} frames")
    print(f"  dominant   {fmt(dominant)} ({share:.1f}%)")
    print(f"  corners    {', '.join(sorted(fmt(c) for c in corners))}")
    print(f"  wanted     {fmt(want)}")

    ok = dominant == want and corners == {want}
    print(f"  verdict    {'pass' if ok else 'FAIL'}")
    if not ok:
        print("\n  The theme did not take. agg's custom theme is background FIRST,")
        print("  then foreground, then the eight palette colours — not the order the")
        print("  flag name suggests.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
