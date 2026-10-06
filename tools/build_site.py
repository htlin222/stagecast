#!/usr/bin/env python3
"""Render the chaptered player from stagecast.toml and the recorded segments.

    uv run --no-project tools/build_site.py <stagecast.toml> <out-dir>

Chapter lengths are measured, not declared: the number shown is how long the
chapter takes to *watch*, with idle compressed the way the player compresses it,
which is a different thing from how long the stage took.
"""
from __future__ import annotations
import json, pathlib, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def played_seconds(cast: pathlib.Path, idle_limit: float = 2.0) -> int:
    prev = total = 0.0
    for i, line in enumerate(cast.read_text(encoding="utf-8", errors="replace").splitlines()):
        if i == 0 or not line.strip():
            continue
        try:
            t = float(json.loads(line)[0])
        except Exception:
            continue
        total += min(t - prev, idle_limit)
        prev = t
    return round(total)


def main() -> int:
    cfg_path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "stagecast.toml")
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "site")
    cfg = tomllib.loads(cfg_path.read_text())
    base = cfg_path.parent
    casts = out / "casts"
    out.mkdir(parents=True, exist_ok=True)

    # A publish of ten one-second stubs once passed every control assertion,
    # because the controls worked perfectly on top of an empty recording. The
    # floor is the guard. A smoke test may lower it; a real run should not.
    floor = cfg.get("site", {}).get("min_chapter_seconds", 30)

    stages, prompts = [], {}
    for st in cfg.get("stage", []):
        cast = casts / f"stage-{st['id']}.cast"
        if not cast.exists():
            print(f"  no cast for stage {st['id']}, skipping", file=sys.stderr)
            continue
        secs = played_seconds(cast, cfg.get("recording", {}).get("idle_limit", 2))
        if secs < floor:
            print(f"  stage {st['id']} is {secs}s, under the {floor}s floor — "
                  f"an empty chapter, refusing", file=sys.stderr)
            return 1
        stages.append({"id": st["id"], "t": secs, "name": st["name"],
                       "note": st.get("note", "")})
        p = base / st["prompt"]
        if p.exists():
            prompts[st["id"]] = p.read_text().strip()

    if not stages:
        print("  nothing to build: no casts", file=sys.stderr)
        return 1

    proj = cfg.get("project", {})
    facts = "".join(
        f'<div><b>{f["value"]}</b><span>{f["label"]}</span></div>'
        for f in proj.get("facts", []))
    # An emphasis phrase that matches no prompt is a typo, and the bolding then
    # fails in total silence, so say so here rather than let it ship unnoticed.
    joined = " ".join(prompts.values()).lower()
    for k in cfg.get("site", {}).get("emphasise", []):
        if k.lower() not in joined:
            print(f"  warning: emphasise {k!r} appears in no prompt", file=sys.stderr)

    html = (ROOT / "site/template.html").read_text()
    for key, val in {
        "{{TITLE}}": f'{proj.get("name","")} — {proj.get("title","")}',
        "{{NAME}}": proj.get("name", ""),
        "{{BLURB}}": proj.get("blurb", ""),
        "{{FACTS}}": facts,
        "{{REPO}}": proj.get("repo", "#"),
        "{{STAGES}}": json.dumps(stages, ensure_ascii=False, indent=1),
        "{{KEYS}}": json.dumps(cfg.get("site", {}).get("emphasise", []),
                               ensure_ascii=False),
        "{{ABOUT}}": cfg.get("site", {}).get("about", ""),
    }.items():
        html = html.replace(key, val)

    (out / "index.html").write_text(html)
    (out / "prompts.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=1))
    total = round(sum(s["t"] for s in stages) / 60)
    print(f"  {len(stages)} chapters, {total} min as played → {out}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
