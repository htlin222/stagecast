#!/usr/bin/env python3
"""Join recording segments into one cast.

    uv run --no-project live-demo/concat_casts.py <out.cast> <seg1.cast> [seg2.cast ...]

A run that survives a dead terminal produces one segment per recorded session.
They are the same demonstration, so they play as one file: keep the first
header, and shift each later segment's timestamps past the end of the one
before it. A short gap is inserted between segments so the restart reads as a
pause rather than a jump cut.
"""

from __future__ import annotations

import json
import sys

GAP_S = 1.5


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip())
        return 2

    out_path, segments = sys.argv[1], sys.argv[2:]
    header = None
    offset = 0.0
    written = 0

    with open(out_path, "w", encoding="utf-8") as out:
        for seg in segments:
            last = 0.0
            with open(seg, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    if i == 0:
                        if header is None:
                            header = json.loads(line)
                            out.write(json.dumps(header) + "\n")
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a cast truncated by a hard kill ends mid-line
                    last = float(event[0])
                    event[0] = round(last + offset, 6)
                    out.write(json.dumps(event) + "\n")
                    written += 1
            offset += last + GAP_S
            print(f"  {seg}: {last:.0f}s")

    print(f"→ {out_path}: {len(segments)} segment(s), {written} events, {offset:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
