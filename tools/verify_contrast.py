#!/usr/bin/env python3
"""Check that no glyph in a rendered frame is invisible against what is behind it.

    uv run --with pillow --no-project live-demo/verify_contrast.py <png> [...]

The white-background theme had ANSI colour 0 mapped to #ffffff. Colour 0 is
black; it is what a TUI uses to write dark text on a coloured panel. Mapping it
to white made every such glyph white-on-lavender, which a background check
cannot see -- the background was perfectly white, and the text was gone.

So look for the symptom instead: a run of near-white pixels enclosed by a
coloured panel. Reported as the share of panel area that is near-white, per
distinct panel colour. A panel that is more than about a third near-white is
almost certainly hiding text.
"""

from __future__ import annotations

import sys
from collections import Counter

from PIL import Image

NEAR_WHITE = 246
MIN_PANEL_PX = 4000


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2

    bad = 0
    for path in sys.argv[1:]:
        im = Image.open(path)
        im.seek(getattr(im, "n_frames", 1) - 1)
        rgb = im.convert("RGB")
        w, h = rgb.size
        px = rgb.load()

        # Which non-white colours cover enough area to be a panel?
        counts = Counter(px[x, y] for y in range(0, h, 2) for x in range(0, w, 2))
        panels = [
            c for c, n in counts.items()
            if n * 4 > MIN_PANEL_PX and not all(v >= NEAR_WHITE for v in c)
        ]

        print(f"{path}")
        for panel in sorted(panels, key=lambda c: -counts[c])[:6]:
            rows = [y for y in range(0, h, 2) if any(px[x, y] == panel for x in range(0, w, 4))]
            if not rows:
                continue
            y0, y1 = min(rows), max(rows)
            inside = [
                px[x, y]
                for y in range(y0, y1 + 1, 2)
                for x in range(0, w, 2)
                if px[x, y] == panel or all(v >= NEAR_WHITE for v in px[x, y])
            ]
            if not inside:
                continue
            white = sum(1 for c in inside if all(v >= NEAR_WHITE for v in c))
            share = white / len(inside) * 100
            flag = "  SUSPECT: text may be white-on-panel" if share > 33 else ""
            print(f"  panel #{panel[0]:02x}{panel[1]:02x}{panel[2]:02x}"
                  f"  rows {y0}-{y1}  near-white inside {share:.0f}%{flag}")
            if share > 33:
                bad += 1
    print(f"\n{'ok' if bad == 0 else f'{bad} suspect panel(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
