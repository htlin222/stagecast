#!/usr/bin/env python3
"""Stop hook: a turn just ended. Record WHEN, and WHICH prompt it answered.

Registered for you by the claude-code preset (`[recording] preset`). To register
it by hand, in the recorded project's .claude/settings.json:

    { "hooks": { "Stop": [ { "matcher": "", "hooks": [
        { "type": "command",
          "command": "python3 /path/to/stagecast/hooks/turn_ended.py",
          "timeout": 20 } ] } ] } }

Reads the hook's JSON on stdin, walks `transcript_path` back to the most recent
human message, and matches it against the stage prompts and `say` texts
(newest and unanswered first). Writes to $STAGECAST_STATE:

  turns.jsonl     {"t": epoch, "id": stage id, or null for a turn that answers
                  no known prompt}
  answered/<id>   exists once the turn that received <id> has ended
  fp-<id>         a fingerprint of the repo at that moment (stagecast-check edited)
  turn-ended      the time of the last ended turn (what older drivers read)

Why a hook and not a sentinel in the prompt: a sentinel has to be asked for —
"when you are finished, write 01.done" — which puts the machinery on screen in
every chapter. A hook is configuration: invisible, and it cannot be forgotten,
mis-spelled or written early. It answers "did the turn end", never "was the
work done" — that is what each stage's `verify` is for.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent


def texts(entry: dict):
    c = entry.get("message", {}).get("content")
    if isinstance(c, str):
        yield c
    elif isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                yield b.get("text", "")


def last_human_message(transcript: pathlib.Path) -> str | None:
    try:
        lines = transcript.read_text().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "user" or e.get("isMeta") or e.get("isCompactSummary"):
            continue
        body = " ".join(texts(e)).strip()
        if body:            # tool results carry no text block: keep walking
            return body
    return None


def wanted(state: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        out.update(json.loads((state / "prompts.json").read_text()))
    except (OSError, ValueError):
        pass
    try:
        for line in (state / "said.jsonl").read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            out[d["id"]] = d["text"]
    except OSError:
        pass
    return {k: v.strip() for k, v in out.items() if v and v.strip()}


def match(body: str, want: dict[str, str], answered) -> str | None:
    norm = " ".join(body.split())
    hits = [k for k, v in reversed(list(want.items()))
            if body.startswith(v) or norm.startswith(" ".join(v.split()))]
    # Newest first, unanswered first: the same `say` text may be sent twice.
    return next((k for k in hits if not answered(k)), hits[0] if hits else None)


def main() -> int:
    default = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".stagecast"
    state = pathlib.Path(os.environ.get("STAGECAST_STATE", default))
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        ev = {}
    now = time.time()
    (state / "answered").mkdir(parents=True, exist_ok=True)

    body = last_human_message(pathlib.Path(ev["transcript_path"])) if ev.get("transcript_path") else None
    hit = match(body, wanted(state), lambda k: (state / "answered" / k).exists()) if body else None
    if hit:
        fp = subprocess.run([str(HERE.parent / "lib" / "bin" / "stagecast-check"), "fp"],
                            cwd=ev.get("cwd") or ".", capture_output=True, text=True,
                            env=dict(os.environ, STAGECAST_STATE=str(state))).stdout.strip()
        (state / f"fp-{hit}").write_text(fp)
        (state / "answered" / hit).write_text(str(now))
    with (state / "turns.jsonl").open("a") as f:
        f.write(json.dumps({"t": now, "id": hit}) + "\n")
    (state / "turn-ended").write_text(str(now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
