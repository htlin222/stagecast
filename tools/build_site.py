#!/usr/bin/env python3
"""Render the chaptered player from stagecast.toml and the post-processed casts.

    uv run --no-project tools/build_site.py <stagecast.toml> <site-dir> [--prompts-md PATH]

Reads <site-dir>/chapters.json and meta.json (tools/postprocess.py) and fills
templates/player.html. stagecast.toml is the single source of the prompts: the
page, prompts.json and PROMPTS.md are all generated from it, so they cannot
drift apart.

Chapter lengths are measured, not declared: the number shown is how long the
chapter takes to *watch*, next to how long the run actually took.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sc_config as C  # noqa: E402

TEMPLATE = C.FRAMEWORK / "templates" / "player.html"


def duration(s: float) -> str:
    if s >= 3600:
        return f"{s / 3600:.1f} h"
    if s >= 60:
        return f"{s / 60:.0f} min"
    return f"{s:.0f} s"


def prompts_md(cfg: dict, chapters: list[dict]) -> str:
    """A copy-pasteable script: every prompt, its drops, what was really sent."""
    proj = cfg["project"]
    says = [c for c in chapters if c["kind"] == "say"]
    out = [f"# {proj.get('name', 'Prompts')}" + (f" — {proj['title']}" if proj.get("title") else ""),
           "", f"Generated from `{cfg['path'].name}` by `stagecast build --prompts-md`. "
           "Edit that file, not this one.", ""]
    part = None
    for s in cfg["stages"]:
        if s.get("part") and s["part"] != part:
            part = s["part"]
            out += [f"## {part}", ""]
        out += [f"### {s['id']} · {s['name']}", ""]
        if s["drop"]:
            names = ", ".join(f"`{pathlib.Path(d).name}`" for d in s["drop"])
            out += [f"_{cfg['recording']['drop_dir']} ← {names} (placed just before this prompt)_", ""]
        out += ["```text", s["prompt_text"], "```", ""]
        if s.get("recorded"):
            out += [f"> During the recording only this was sent: “{s['recorded']}”. "
                    "The prompt above folds in what was added live, so it needs no interjection.", ""]
        for c in says:
            if c.get("after") == s["id"]:
                out += [f"- ↳ interjection, typed live during the recording: “{c['prompt']}”", ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("site")
    ap.add_argument("--prompts-md")
    a = ap.parse_args()
    cfg = C.load(a.config)
    out = pathlib.Path(a.site)
    try:
        chapters = json.loads((out / "chapters.json").read_text())
    except FileNotFoundError:
        print("  no chapters.json — tools/postprocess.py runs first", file=sys.stderr)
        return 1
    meta = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}

    # A publish of ten one-second stubs once passed every control assertion,
    # because the controls worked perfectly on top of an empty recording. The
    # floor is the guard. A smoke test may lower it; a real run should not.
    floor = cfg["site"]["min_chapter_seconds"]
    for c in chapters:
        if c["kind"] == "stage" and c["dur"] < floor:
            print(f"  stage {c['id']} plays for {c['dur']:.0f}s, under the {floor}s floor — "
                  f"an empty chapter, refusing", file=sys.stderr)
            return 1
    stages = [c for c in chapters if c["kind"] == "stage"]
    if not stages:
        print("  nothing to build: no stage chapters", file=sys.stderr)
        return 1

    proj = cfg["project"]
    played = meta.get("played_seconds") or (chapters[-1]["t"] + chapters[-1]["dur"])
    facts = [(str(f["value"]), str(f["label"])) for f in proj.get("facts", [])]
    if meta.get("raw_seconds"):
        facts.append((duration(meta["raw_seconds"]), "recorded"))
    facts.append((duration(played), "as played"))
    facts_html = "".join(f"<div><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>"
                         for v, k in facts)

    # An emphasis phrase that matches no prompt is a typo, and the bolding then
    # fails in total silence, so say so here rather than let it ship unnoticed.
    keys = cfg["site"]["emphasise"]
    joined = " ".join(c["prompt"] for c in chapters).lower()
    for k in keys:
        if k.lower() not in joined:
            print(f"  warning: emphasise {k!r} appears in no prompt", file=sys.stderr)

    if not TEMPLATE.exists():
        print(f"  the player template is missing: {TEMPLATE}", file=sys.stderr)
        return 1
    page = TEMPLATE.read_text()
    title = " — ".join(x for x in (proj.get("name", ""), proj.get("title", "")) if x)
    for key, val in {
        "{{TITLE}}": html.escape(title or "stagecast"),
        "{{NAME}}": html.escape(proj.get("name", "")),
        "{{BLURB}}": html.escape(proj.get("blurb", "")),
        "{{FACTS}}": facts_html,
        "{{REPO}}": html.escape(proj.get("repo", "#"), quote=True),
        "{{ABOUT}}": cfg["site"]["about"],
        "{{CHAPTERS}}": json.dumps(chapters, ensure_ascii=False).replace("</", "<\\/"),
        "{{KEYS}}": json.dumps(keys, ensure_ascii=False).replace("</", "<\\/"),
        "{{MIN_CHAPTER}}": json.dumps(floor),
    }.items():
        page = page.replace(key, val)
    (out / "index.html").write_text(page)

    prompts = {c["id"]: c["prompt"] for c in chapters}
    (out / "prompts.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=1))
    if a.prompts_md:
        pathlib.Path(a.prompts_md).write_text(prompts_md(cfg, chapters))
        print(f"  prompts → {a.prompts_md}")
    says = len(chapters) - len(stages)
    print(f"  {len(stages)} chapter(s)" + (f", {says} interjection(s)" if says else "")
          + f", {duration(played)} as played → {out}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
