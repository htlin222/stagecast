#!/usr/bin/env python3
"""Put the real segment back when a skipped stage left a stub in its place.

    uv run --no-project live-demo/restore_real.py <recording-dir> [...]

record.sh retires the previous take before each attempt. When run.sh then finds
the stage already complete and skips it, the session still opens and closes, so
what is left in the directory is a one-second stub and the real recording is in
_aborted/. For each stage, keep whichever cast is longest.
"""
from __future__ import annotations
import json, pathlib, re, sys

def dur(p: pathlib.Path) -> float:
    last = 0.0
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            if line.strip():
                try: last = float(json.loads(line)[0])
                except Exception: pass
    except Exception:
        return 0.0
    return last

def main() -> int:
    for d in map(pathlib.Path, sys.argv[1:]):
        best: dict[str, tuple[float, pathlib.Path]] = {}
        for p in list(d.glob("seg-*.cast")) + list((d / "_aborted").glob("*seg-*.cast")):
            m = re.search(r"step([0-9]+v?)\.cast$", p.name)
            if not m: continue
            s, t = m.group(1), dur(p)
            if s not in best or t > best[s][0]:
                best[s] = (t, p)
        for s, (t, p) in sorted(best.items()):
            live = d / f"seg-{s.zfill(3)}-step{s}.cast"
            cur = next(iter(d.glob(f"seg-*-step{s}.cast")), None)
            if cur and cur.resolve() == p.resolve():
                print(f"  {s:>4}  {t:6.0f}s  in place"); continue
            target = cur if cur else live
            if cur: cur.unlink()
            target.write_bytes(p.read_bytes())
            print(f"  {s:>4}  {t:6.0f}s  restored from {p.parent.name}/")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
