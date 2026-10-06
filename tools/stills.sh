#!/usr/bin/env bash
# Pull slide-ready PNG frames out of a cast at chosen moments.
#
#   live-demo/stills.sh <cast> <seconds> [<seconds> ...]
#
# A GIF is the wrong thing to put on a slide: large, animated, and the moment
# you want is one frame somewhere in the middle. agg has no single-frame mode,
# and simply truncating the cast does not help — agg still renders every frame
# up to the cut, which for a two-hour recording is thousands of them.
#
# The trick: the screen at time T is nothing more than every output byte before
# T applied in order. So collapse them into one event at t=0. agg then has a
# single frame to draw, and a still costs a second instead of ten minutes.
#
# Output lands in claude-demo/stills/ as t<seconds>.png, at the same 26pt pure
# white settings as the GIFs, and carries a real 300 dpi pHYs chunk — a PNG
# without one is treated as 72 dpi by a slide deck however many pixels it has.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
CAST="${1:?usage: stills.sh <cast> <seconds> [...]}"; shift
OUT="$REPO/claude-demo/stills"

# background, foreground, then ANSI 0-7. Colour 0 is BLACK, not the background:
# setting it to white made every glyph the TUI drew in colour 0 -- which is how
# it writes dark text on a coloured panel -- invisible on that panel.
AGG_THEME='ffffff,1c1917,1c1917,cf222e,1a7f37,9a6700,0969da,8250df,1b7c83,57534e'
AGG_FONT='JetBrainsMono NF,Noto Sans CJK TC'
AGG_SIZE=${AGG_SIZE:-26}

mkdir -p "$OUT"

for t in "$@"; do
  flat="$(mktemp -t mpstill).cast"
  uv run --no-project python - "$CAST" "$flat" "$t" <<'PY'
import json, sys
src, dst, t = sys.argv[1], sys.argv[2], float(sys.argv[3])
chunks, header = [], None
with open(src, encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i == 0:
            header = line.rstrip("\n"); continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue                      # a cast cut short by a hard kill
        if float(e[0]) > t:
            break
        if e[1] == "o":
            # JetBrainsMono has no U+23F5 and agg will not fall back the way
            # CoreText does, so substitute the glyph that means the same thing.
            chunks.append(e[2].replace("⏵", "▶").replace("⏴", "◀"))
with open(dst, "w", encoding="utf-8") as o:
    o.write(header + "\n")
    o.write(json.dumps([0.0, "o", "".join(chunks)]) + "\n")
PY
  if agg --theme "$AGG_THEME" --font-dir "$HOME/Library/Fonts" --font-family "$AGG_FONT" \
         --font-size "$AGG_SIZE" --last-frame-duration 1 \
         "$flat" "$OUT/t${t}.gif" 2>/dev/null; then
    uv run --with pillow --no-project python - "$OUT/t${t}.gif" "$OUT/t${t}.png" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1])
im.seek(getattr(im, "n_frames", 1) - 1)
frame = im.convert("RGB")
frame.save(sys.argv[2], dpi=(300, 300))
print(f"  t={sys.argv[1].rsplit('/t',1)[1][:-4]}s  {sys.argv[2]}  {frame.size[0]}x{frame.size[1]}")
PY
    rm -f "$OUT/t${t}.gif"
  else
    printf '  ✖ could not render a frame at %ss\n' "$t"
  fi
  rm -f "$flat"
done
