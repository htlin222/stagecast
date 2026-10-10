"""Read stagecast.toml once, with every default in one place.

Every tool that needs the config imports this rather than re-reading the TOML
with its own idea of the defaults: a default that differs between the driver
and the builder is a recording that cannot be built.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import tomllib
from typing import Any

FRAMEWORK = pathlib.Path(__file__).resolve().parent.parent

RECORDING = {
    "mode": "per-stage",            # or "continuous": one session, chapters as markers
    "cols": 118, "rows": 28,
    "agent": "claude",
    "socket": "stagecast",
    "bracketed_paste": True,
    "clear_key": "Escape",
    "quit": "/exit",
    "preset": "",                   # "claude-code": isolate the recorded session
    "mcp_config": "",
    "allow_ancestor_claude_md": False,
    "env_keep": ["CLAUDE_CODE_NO_FLICKER"],
    "ready": None,                  # regex that means "the target is up"; None = auto
    "turn_signal": None,            # "hook" | "settle"; None = hook under the preset
    "answer_questions": "",         # "recommended" to answer AskUserQuestion widgets
    "recommend": r"Recommended|推薦|建議",
    "question_delay": 6,
    "drop_dir": "inbox",
    "skip_if_satisfied": False,
    "stall": "60m",
    "settle": 3,
    "poll": 5,
}

POSTPROCESS = {
    "idle_limit": 2.0,   # any gap longer than this plays as this
    "head": 20.0,        # first seconds of each turn at 1x
    "foot": 15.0,        # last seconds of each turn at 1x
    "fast": 8.0,         # the middle of a turn plays this many times faster
    "hold": 8.0,         # a finished answer stays on screen at least this long
    "tail": 6.0,         # kept after the last ended turn of a take
    "coalesce": 1 / 60,  # output events closer than this become one
}

SITE = {
    "min_chapter_seconds": 30,
    "warn_mb": 5,
    "emphasise": [],
    "about": "",
}

CLAUDE_READY = r"bypass permissions|for shortcuts|\? for shortcuts|Try \""


def seconds(v: str | int | float) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    v = str(v).strip()
    if v.endswith("h"):
        return int(float(v[:-1]) * 3600)
    if v.endswith("m"):
        return int(float(v[:-1]) * 60)
    return int(float(v.rstrip("s")))


def is_claude(agent: str) -> bool:
    try:
        first = shlex.split(agent)[0]
    except (ValueError, IndexError):
        return False
    return pathlib.Path(first).name == "claude"


def prompt_text(base: pathlib.Path, value: str) -> str:
    """A prompt is a path to a file, or — when no such file exists — the text."""
    if "\n" not in value and len(value) < 512:
        p = base / value
        if p.is_file():
            return p.read_text().strip()
    return value.strip()


def load(path: str | os.PathLike = "stagecast.toml") -> dict[str, Any]:
    path = pathlib.Path(path).resolve()
    raw = tomllib.loads(path.read_text())
    base = path.parent

    rec = {**RECORDING, **raw.get("recording", {})}
    if os.environ.get("SC_SETTLE"):
        rec["settle"] = int(os.environ["SC_SETTLE"])
    if os.environ.get("SC_POLL"):
        rec["poll"] = float(os.environ["SC_POLL"])
    claude = rec["preset"] == "claude-code" or is_claude(rec["agent"])
    if rec["ready"] is None:
        rec["ready"] = CLAUDE_READY if claude else ""
    if rec["turn_signal"] is None:
        # "hook" only where the hook is certainly registered: waiting on a hook
        # nobody installed is waiting out the stall timer on every stage.
        rec["turn_signal"] = "hook" if rec["preset"] == "claude-code" else "settle"

    pp = {**POSTPROCESS, **raw.get("postprocess", {})}
    # `[recording] idle_limit` predates [postprocess]; honour it if that is all there is.
    if "idle_limit" in raw.get("recording", {}) and "idle_limit" not in raw.get("postprocess", {}):
        pp["idle_limit"] = float(raw["recording"]["idle_limit"])

    project = dict(raw.get("project", {}))
    workdir = pathlib.Path(project.get("workdir", "."))
    workdir = workdir if workdir.is_absolute() else (base / workdir)

    stages = []
    for s in raw.get("stage", []):
        s = dict(s)
        s["prompt_text"] = prompt_text(base, s["prompt"])
        s["stall_s"] = seconds(s.get("stall", rec["stall"]))
        s.setdefault("name", s["id"])
        s.setdefault("note", "")
        s.setdefault("drop", [])
        stages.append(s)

    milestones = list(raw.get("milestone", []))
    ms_file = base / "milestones.toml"
    if not milestones and ms_file.exists():
        milestones = tomllib.loads(ms_file.read_text()).get("milestone", [])

    redact = {"env_files": [".env"], "literals": [], **raw.get("redact", {})}

    state = pathlib.Path(os.environ.get("STAGECAST_STATE", base / ".stagecast"))
    return {
        "path": path, "base": base, "state": state, "workdir": workdir.resolve(),
        "project": project, "recording": rec, "postprocess": pp,
        "site": {**SITE, **raw.get("site", {})}, "lint": raw.get("lint", {}),
        "redact": redact, "stages": stages, "milestones": milestones,
        "milestones_cfg": raw.get("milestones", {}),
    }


# ---------------------------------------------------------------- state files
def jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue   # a line cut short by a hard kill
    return out


def append(path: pathlib.Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_cast(path: pathlib.Path) -> tuple[dict, list[list]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header = json.loads(lines[0]) if lines else {}
    v3 = header.get("version") == 3     # asciinema 3: intervals, not timestamps
    if v3:
        term = header.get("term", {})
        header = {"version": 2, "width": term.get("cols"), "height": term.get("rows"),
                  **{k: v for k, v in header.items() if k not in ("version", "term")}}
    events, t = [], 0.0
    for line in lines[1:]:
        if not line.strip() or line.startswith("#"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue       # a cast truncated by a hard kill ends mid-line
        if isinstance(e, list) and len(e) >= 3:
            t = t + float(e[0]) if v3 else float(e[0])
            events.append([t, e[1], e[2]])
    return header, events


def write_cast(path: pathlib.Path, header: dict, events: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for e in events:
            f.write(json.dumps([round(e[0], 6), e[1], e[2]], ensure_ascii=False) + "\n")


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-") or "x"
