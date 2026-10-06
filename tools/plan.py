#!/usr/bin/env python3
"""Flatten stagecast.toml into the table the shell driver reads.

    uv run --no-project tools/plan.py <stagecast.toml> <out.tsv>

Bash has no business parsing TOML, and the driver has no business knowing where
the config came from. One file describes the run; this turns it into rows.
"""
from __future__ import annotations
import pathlib, sys, tomllib

def seconds(v: str | int) -> int:
    if isinstance(v, int): return v
    v = str(v).strip()
    if v.endswith("m"): return int(float(v[:-1]) * 60)
    if v.endswith("h"): return int(float(v[:-1]) * 3600)
    return int(float(v.rstrip("s")))

def main() -> int:
    cfg = tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
    rows = ["\t".join([s["id"], s["prompt"], str(seconds(s.get("stall", "60m"))),
                       s["verify"]]) for s in cfg.get("stage", [])]
    pathlib.Path(sys.argv[2]).write_text("\n".join(rows) + "\n")
    r = cfg.get("recording", {})
    p = cfg.get("project", {})
    env = {
        "SC_COLS": r.get("cols", 118), "SC_ROWS": r.get("rows", 28),
        "SC_AGENT": r.get("agent", "claude"), "SC_IDLE": r.get("idle_limit", 2),
        "SC_SOCKET": r.get("socket", "stagecast"),
        # Wrap the prompt in \e[200~ … \e[201~. Claude Code, Codex and bash all
        # read it; a target that does not would echo the markers on screen.
        "SC_PASTE": "1" if r.get("bracketed_paste", True) else "0",
        # Sent before the prompt to clear a TUI's pending state. Empty for a
        # plain shell, where ESC is a meta prefix: ESC then the paste's own ESC
        # was what leaked "[200~printf: command not found" onto the screen.
        "SC_CLEAR": r.get("clear_key", "Escape"),
        # How this target is asked to leave. A TUI takes a slash command; a
        # shell takes `exit`. Sending Claude Code's "Escape then /exit" to a
        # plain bash means ESC-/ , which is readline's filename completion:
        # it completed to the one file in the directory and ran it.
        "SC_QUIT": r.get("quit", "/exit"),
        "SC_WORKDIR": p.get("workdir", "."), "SC_NAME": p.get("name", "run"),
    }
    print("\n".join(f'{k}="{v}"' for k, v in env.items()))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
