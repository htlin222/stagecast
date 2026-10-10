#!/usr/bin/env python3
"""Collapse a cast into one event holding the screen at time T, redacted.

    uv run --no-project tools/still_frame.py <cast> <out.cast> <seconds> [project-dir]

The screen at time T is nothing more than every output byte before T applied in
order, so a renderer given this has a single frame to draw. Everything goes
through tools/redact.py with the recorded project's .env and [redact] settings:
stills are made from originals, and must not be the one export path that skips it.
"""
import json
import pathlib
import sys
import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import redact  # noqa: E402
import sc_config as C  # noqa: E402


def main() -> int:
    src, dst, t = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), float(sys.argv[3])
    base = pathlib.Path(sys.argv[4] if len(sys.argv) > 4 else ".")
    cfg = base / "stagecast.toml"
    rcfg = tomllib.loads(cfg.read_text()).get("redact", {}) if cfg.exists() else {}
    secrets = redact.load_secrets(base, rcfg)
    header, events = C.read_cast(src)
    # JetBrainsMono has no U+23F5 and agg will not fall back the way CoreText
    # does, so substitute the glyph that means the same thing.
    text = "".join(e[2] for e in events if e[1] == "o" and e[0] <= t)
    text = text.replace("⏵", "▶").replace("⏴", "◀")
    with dst.open("w", encoding="utf-8") as o:
        o.write(json.dumps(header) + "\n")
        o.write(json.dumps([0.0, "o", redact.redact(text, secrets)]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
