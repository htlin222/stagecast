#!/usr/bin/env python3
"""Cut the dead air off the end of a recording segment.

    uv run --no-project live-demo/trim_casts.py <dir>

A stage that finished but was not recognised as finished kept recording: the
spinner glyph Claude Code leaves in its closing summary line looks identical to
the one it animates while working, so the runner waited on a stage that was
already done. asciinema's --idle-time-limit cannot compress that, because the
pane is not idle — a cursor blink is an event.

What is left is a segment whose last substantial output is an hour before its
end. Find that output and cut shortly after it. Substantial means an event
carrying more than a few hundred bytes: a spinner frame is a handful.
"""

from __future__ import annotations

import json
import pathlib
import sys

TAIL_S = 8          # how much to keep after the last real output
MIN_BYTES = 250     # an event smaller than this is animation, not content


def trim(path: pathlib.Path) -> tuple[float, float]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header, events = lines[0], []
    for line in lines[1:]:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not events:
        return 0.0, 0.0

    original = float(events[-1][0])
    cut_at = original
    for e in reversed(events):
        if e[1] == "o" and len(e[2]) >= MIN_BYTES:
            cut_at = float(e[0]) + TAIL_S
            break

    kept = [e for e in events if float(e[0]) <= cut_at]
    if len(kept) < len(events):
        path.write_text(
            header + "\n" + "\n".join(json.dumps(e) for e in kept) + "\n",
            encoding="utf-8")
    return original, float(kept[-1][0]) if kept else 0.0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    total_before = total_after = 0.0
    for f in sorted(pathlib.Path(sys.argv[1]).glob("*.cast")):
        before, after = trim(f)
        total_before += before
        total_after += after
        mark = "  ←trimmed" if after < before - 1 else ""
        print(f"  {f.name:28} {before:7.0f}s → {after:6.0f}s{mark}")
    print(f"\ntotal {total_before/3600:.1f}h → {total_after/3600:.1f}h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
