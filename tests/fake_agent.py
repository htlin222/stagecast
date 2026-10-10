#!/usr/bin/env python3
"""A stand-in for Claude Code, for testing the driver without a model.

Reads one message per line, keeps a transcript in Claude Code's JSONL shape,
"works" for a moment, does what a keyword asks, and then runs the real Stop
hook — exactly as Claude Code would at the end of a turn. Nothing here judges
anything; it exists so continuous mode, interjections and restarts can be
exercised deterministically.

  create NAME   writes NAME in the working directory
  slow          works for longer (to kill the driver mid-turn)
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time

state = pathlib.Path(os.environ["STAGECAST_STATE"])
hook = pathlib.Path(os.environ["STAGECAST_HOME"]) / "hooks" / "turn_ended.py"
transcript = state / "fake-transcript.jsonl"

print("fake agent · ? for shortcuts\n", flush=True)
while True:
    sys.stdout.write("❯ ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        break
    text = line.strip()
    if not text:
        continue
    if text in ("/exit", "exit"):
        break
    with transcript.open("a") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
        # a tool result: no text block, which the hook must walk past
        f.write(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}) + "\n")
    for i in range(12 if "slow" in text else 3):
        print(f"  · working {i}", flush=True)
        time.sleep(0.5)
    for name in re.findall(r"create (\S+)", text):
        pathlib.Path(name.strip(".,")).write_text("made\n")
        print(f"  wrote {name}", flush=True)
    print(f"● done: {text[:40]}\n", flush=True)
    subprocess.run([sys.executable, str(hook)], input=json.dumps(
        {"transcript_path": str(transcript), "cwd": os.getcwd()}), text=True)
