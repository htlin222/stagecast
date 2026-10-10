#!/usr/bin/env python3
"""Scaffold a stagecast.toml from a directory of prompts.

The point of the framework is that a stage advances when its check passes and at
no other time, so the one field this cannot write for you is `verify`. It is
left as TODO and `record` refuses to start while any remain: a check guessed
from a filename would pass for the wrong reason, which is worse than none.
"""
import re, sys
from pathlib import Path

SKEL = '''# Written by `stagecast init`. Fill in every TODO before recording.

[project]
name    = "{name}"
title   = "TODO: one line under the name"
blurb   = "TODO: what this run was, in a sentence"
workdir = "."          # where the stages' checks are run
repo    = "TODO: https://github.com/you/your-repo"

facts = [
  {{ value = "{n}", label = "stages" }},
]

[recording]
cols       = 118       # 16:9 once the cell aspect is measured
rows       = 28
agent      = "claude"
# mode   = "continuous"    # one session for every stage — right for an agent
# preset = "claude-code"   # keep your own ~/.claude setup out of the recording

[site]
emphasise = []         # phrases to bold in the chapter briefs
about = """
<p>TODO: a paragraph for the about panel.</p>
"""

{stages}'''

STAGE = '''[[stage]]
id     = "{id}"
name   = "{name}"
prompt = "{prompt}"
stall  = "30m"
verify = "TODO: a command that exits 0 only when this stage is really done"
note   = "TODO: one line under the player"
'''


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "prompts")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "stagecast.toml")
    if not src.is_dir():
        print(f"  no such directory: {src}", file=sys.stderr)
        return 2
    if out.exists():
        print(f"  {out} exists — move it aside first", file=sys.stderr)
        return 2

    files = sorted(p for p in src.iterdir()
                   if p.is_file() and p.suffix in {".md", ".txt", ""} and not p.name.startswith("."))
    if not files:
        print(f"  no prompt files in {src}/", file=sys.stderr)
        return 2

    stages = []
    for i, f in enumerate(files, 1):
        m = re.match(r"(\d+)[-_. ]*(.*)", f.stem)
        sid = m.group(1) if m else f"{i:02d}"
        rest = (m.group(2) if m else f.stem).replace("-", " ").replace("_", " ").strip()
        stages.append(STAGE.format(id=sid, name=(rest.capitalize() or f"Stage {sid}"),
                                   prompt=f"{src.as_posix()}/{f.name}"))

    out.write_text(SKEL.format(name=Path.cwd().name, n=len(files),
                               stages="\n".join(stages)))
    print(f"  {out} — {len(files)} stage(s) from {src}/")
    print(f"  fill in every TODO; `record` will refuse while a verify is one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
