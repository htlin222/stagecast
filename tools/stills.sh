#!/usr/bin/env bash
# Pull slide-ready PNG frames out of a cast at chosen moments.
#
#   tools/stills.sh <cast> <seconds> [<seconds> ...]
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
# Output lands in ./stills/ (or $STILLS_OUT) as t<seconds>.png, at the same
# 26pt pure white settings as the GIFs, and carries a real 300 dpi pHYs chunk —
# a PNG without one is treated as 72 dpi by a slide deck however many pixels it
# has.
#
# Every frame goes through tools/redact.py on the way, with the recorded
# project's .env ($SC_BASE, else the current directory), so a still made from
# an original in .stagecast/recording/ cannot carry an unredacted secret.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAST="${1:?usage: stills.sh <cast> <seconds> [...]}"; shift
OUT="${STILLS_OUT:-stills}"
FONT_DIR="${AGG_FONT_DIR:-$HOME/Library/Fonts}"

# background, foreground, then ANSI 0-7. Colour 0 is BLACK, not the background:
# setting it to white made every glyph the TUI drew in colour 0 -- which is how
# it writes dark text on a coloured panel -- invisible on that panel.
AGG_THEME='ffffff,1c1917,1c1917,cf222e,1a7f37,9a6700,0969da,8250df,1b7c83,57534e'
AGG_FONT='JetBrainsMono NF,Noto Sans CJK TC'
AGG_SIZE=${AGG_SIZE:-26}

mkdir -p "$OUT"

for t in "$@"; do
  flat="$(mktemp -t mpstill).cast"
  uv run --quiet --no-project "$HERE/still_frame.py" "$CAST" "$flat" "$t" "${SC_BASE:-$PWD}"
  if agg --theme "$AGG_THEME" --font-dir "$FONT_DIR" --font-family "$AGG_FONT" \
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
