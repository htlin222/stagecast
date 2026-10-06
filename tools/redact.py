#!/usr/bin/env python3
"""Strip credentials out of recordings before they are published.

    uv run --no-project live-demo/redact.py <dir-or-file> [...]

A cast is a recording of a terminal, and a terminal shows whatever was typed
into it. A worker that calls an API with `?api_key=...` puts that key on screen,
and it lands in the cast the same as anything else. The first run of this found
a live PubMed key in two casts, minutes before they would have been pushed to a
public repository.

Every value in .env at least eight characters long is replaced, in place, with a
marker padded to exactly the original length. The padding is not cosmetic: a cast
is a stream of terminal output, and a replacement of a different length shifts
every column after it on that line.

Run this on the copies that are going to be published, never on the originals in
live-demo/recording/ — those are the source of truth and stay as recorded.
"""

from __future__ import annotations

import pathlib
import re
import sys

MIN_SECRET_LEN = 8
# Shapes worth catching even when they are not in .env.
PATTERNS = [
    (re.compile(rb"sk-[A-Za-z0-9]{20,}"), "sk"),
    (re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"), "gh"),
    (re.compile(rb"AKIA[0-9A-Z]{16}"), "aws"),
]


def secrets_from_env(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if len(v) >= MIN_SECRET_LEN:
            out[k.strip()] = v
    return out


def marker(name: str, length: int) -> bytes:
    """A marker of exactly `length` bytes, so no column moves."""
    text = f"[{name}-REDACTED]"
    if len(text) > length:
        return b"*" * length
    return (text + "*" * (length - len(text))).encode()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2

    root = pathlib.Path(__file__).resolve().parent.parent
    env = secrets_from_env(root / ".env")
    if not env:
        print("no .env — only shape-based patterns will be applied")

    targets: list[pathlib.Path] = []
    for arg in sys.argv[1:]:
        p = pathlib.Path(arg)
        targets.extend(sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else [p])

    total = 0
    for f in targets:
        data = original = f.read_bytes()
        for name, value in env.items():
            v = value.encode()
            if v in data:
                n = data.count(v)
                data = data.replace(v, marker(name, len(v)))
                print(f"  {f}: {name} ×{n}")
                total += n
        for pat, label in PATTERNS:
            def sub(m: re.Match[bytes]) -> bytes:
                return marker(label.upper(), len(m.group(0)))
            data, n = pat.subn(sub, data)
            if n:
                print(f"  {f}: {label}-shaped ×{n}")
                total += n
        if data != original:
            f.write_bytes(data)

    print(f"\n{total} redaction(s)" if total else "\nnothing to redact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
