#!/usr/bin/env python3
"""Drive the recorded session: send each stage's prompt, advance only on proof.

    drive.py CONFIG record [--only ID] [--from ID] [--until ID]
    drive.py CONFIG start              open the continuous session (record does this too)
    drive.py CONFIG say TEXT [--after ID]
    drive.py CONFIG finish             stop the recording without quitting the agent
    drive.py CONFIG status

Two recording modes (`[recording] mode`):

  per-stage    one tmux + asciinema + agent session per stage, torn down after
               it. A repair costs one chapter. Right for targets that are not
               an agent, like the demo's worker.sh.
  continuous   one session for the whole run; each stage is the next message
               in the same conversation and nothing is /exit-ed in between.
               Chapters are timestamps (markers.jsonl), turned into asciinema
               markers by tools/postprocess.py.

A stage is complete when BOTH signals agree (`[recording] turn_signal`):

  hook     the Stop hook says the turn that received *this* prompt ended
           (.stagecast/answered/<id>), the pane has settled, and `verify` passes.
  settle   for a target with no hook: `verify` passes and the pane settles.

Exit codes of `record`: 0 done, 1 stalled, 2 config refused, 3 a turn ended but
its check fails (the agent stopped short or asked — answer with `say`, then run
`record` again: nothing already sent is sent twice), 5 the terminal went away.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sc_config as C  # noqa: E402

FW = C.FRAMEWORK


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S", time.gmtime()), msg, flush=True)


# --------------------------------------------------------------------------- tmux
class Term:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.sock = cfg["recording"]["socket"]

    def tmux(self, *args: str, input: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", self.sock, *args], input=input,
                              capture_output=True, text=True)

    def pane(self) -> str:
        # Always name the session: has-session/capture-pane without -t ask about
        # the whole socket. See docs/LESSONS.md § has-session.
        return self.tmux("capture-pane", "-p", "-t", self.sock).stdout

    def alive(self) -> bool:
        return self.tmux("has-session", "-t", self.sock).returncode == 0

    def keys(self, *keys: str) -> None:
        self.tmux("send-keys", "-t", self.sock, *keys)

    def pane_pid(self) -> int | None:
        out = self.tmux("display-message", "-p", "-t", self.sock, "#{pane_pid}").stdout.strip()
        return int(out) if out.isdigit() else None

    def kill(self) -> None:
        self.tmux("kill-session", "-t", self.sock)


def settle(term: Term, seconds: int, limit: int = 60) -> None:
    """Wait for the pane to hold still. A check passing is not the output stopping."""
    prev, still = None, 0
    for _ in range(limit):
        now = term.pane()
        still = still + 1 if now == prev else 0
        prev = now
        if still >= seconds:
            return
        time.sleep(1)


# --------------------------------------------------------------------------- state
class State:
    def __init__(self, cfg: dict):
        self.dir: pathlib.Path = cfg["state"]
        self.rec = self.dir / "recording"
        for d in (self.dir, self.rec, self.rec / "_aborted", self.dir / "answered",
                  self.dir / "verified"):
            d.mkdir(parents=True, exist_ok=True)

    def p(self, name: str) -> pathlib.Path:
        return self.dir / name

    def session(self) -> list[dict]:
        return C.jsonl(self.p("session.jsonl"))

    def current_take(self) -> dict | None:
        starts = [e for e in self.session() if e.get("event") == "start"]
        return starts[-1] if starts else None

    def next_take_no(self) -> int:
        nos = [int(m.group(1)) for e in self.session()
               if (m := re.match(r"take-(\d+)", e.get("take", "")))]
        return max(nos, default=0) + 1

    def answered(self, sid: str) -> bool:
        return (self.dir / "answered" / sid).exists()

    def verified(self, sid: str) -> bool:
        return (self.dir / "verified" / sid).exists()

    def mark_verified(self, sid: str) -> None:
        (self.dir / "verified" / sid).write_text(str(time.time()))

    def sent_in_take(self, take: str | None) -> set[str]:
        return {m["id"] for m in C.jsonl(self.p("markers.jsonl")) if m.get("take") == take}


def verify(cfg: dict, state: State, expr: str | None) -> bool:
    if not expr:
        return True
    env = dict(os.environ, PATH=f"{FW / 'lib' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
               STAGECAST_STATE=str(state.dir))
    return subprocess.run(["bash", "-c", expr], cwd=cfg["workdir"], env=env,
                          capture_output=True).returncode == 0


# --------------------------------------------------------------------------- agent
def preflight(cfg: dict) -> str | None:
    """Refuse a workdir that would let the recorder's own setup into the recording."""
    rec = cfg["recording"]
    if rec["preset"] != "claude-code" or rec["allow_ancestor_claude_md"]:
        return None
    wd = cfg["workdir"]
    home = pathlib.Path.home().resolve()
    suggest = (f"/Users/Shared/{wd.name}" if sys.platform == "darwin" else f"/srv/{wd.name}")
    tail = (f"\n    Claude Code reads CLAUDE.md from every ancestor directory, so the viewer "
            f"would see your private rules shaping the agent.\n    Move the workdir (e.g. "
            f"{suggest}) or set [recording] allow_ancestor_claude_md = true.")
    if wd == home or home in wd.parents:
        return f"workdir {wd} is under $HOME{tail}"
    for d in wd.parents:
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            if (d / name).is_file():
                return f"{d / name} is an ancestor of the workdir {wd}{tail}"
    return None


def session_settings(cfg: dict, state: State) -> pathlib.Path:
    """Settings for the recorded session only: light theme and the Stop hook.

    Passed with --settings, so nobody has to edit their own ~/.claude to record.
    """
    hook = f"python3 {shlex.quote(str(FW / 'hooks' / 'turn_ended.py'))}"
    data = {"theme": "light",
            "hooks": {"Stop": [{"matcher": "", "hooks": [
                {"type": "command", "command": hook, "timeout": 20}]}]}}
    path = state.p("session-settings.json")
    path.write_text(json.dumps(data, indent=1))
    return path


def agent_command(cfg: dict, state: State) -> str:
    rec = cfg["recording"]
    cmd = rec["agent"]
    if rec["preset"] == "claude-code":
        cmd += " --setting-sources project,local"
        cmd += f" --settings {shlex.quote(str(session_settings(cfg, state)))}"
        if rec["mcp_config"]:
            mcp = pathlib.Path(rec["mcp_config"])
            mcp = mcp if mcp.is_absolute() else cfg["base"] / mcp
            cmd += f" --mcp-config {shlex.quote(str(mcp))}"
    return cmd


def asciinema_args(cfg: dict, cast: pathlib.Path, agent: str) -> list[str]:
    rec = cfg["recording"]
    ver = subprocess.run(["asciinema", "--version"], capture_output=True, text=True).stdout
    # -i 86400: record raw wall-clock time. It also overrides an idle_time_limit
    # in the user's ~/.config/asciinema/config. Compressing at record time means
    # the hook's and the driver's timestamps no longer line up with the cast;
    # tools/postprocess.py does the compression instead.
    args = ["asciinema", "rec", "--overwrite", "-q", "-i", "86400", "-c", agent]
    if re.search(r"\b3\.", ver):
        args += ["--output-format", "asciicast-v2", "--window-size", f"{rec['cols']}x{rec['rows']}"]
    else:
        args += ["--cols", str(rec["cols"]), "--rows", str(rec["rows"])]
    return args + [str(cast)]


def start_take(cfg: dict, state: State, term: Term, label: str, stage: str | None) -> str | None:
    rec = cfg["recording"]
    take = f"take-{state.next_take_no():03d}-{C.slug(label)}.cast"
    cast = state.rec / take
    (state.p("agent.cmd")).write_text(agent_command(cfg, state))
    agent = f"bash {shlex.quote(str(FW / 'lib' / 'agent.sh'))}"
    env = {"STAGECAST_STATE": str(state.dir), "STAGECAST_HOME": str(FW), "STAGECAST_TAKE": take,
           "STAGECAST_SCRUB": "1" if rec["preset"] == "claude-code" else "0",
           "STAGECAST_ENV_KEEP": " ".join(rec["env_keep"])}
    line = " ".join(["env", *(f"{k}={shlex.quote(v)}" for k, v in env.items()),
                     *map(shlex.quote, asciinema_args(cfg, cast, agent))])
    term.kill()
    r = term.tmux("new-session", "-d", "-s", term.sock, "-x", str(rec["cols"]),
                  "-y", str(rec["rows"]), "-c", str(cfg["workdir"]), line)
    if r.returncode:
        log(f"✖ could not start tmux: {r.stderr.strip()}")
        return None
    C.append(state.p("session.jsonl"), {"t": time.time(), "event": "start", "take": take,
                                        "stage": stage})
    wait_ready(cfg, term)
    t0 = state.rec / f"{take}.t0"
    if t0.exists():
        C.append(state.p("session.jsonl"), {"t": float(t0.read_text().strip().replace(",", ".")),
                                            "event": "t0", "take": take})
    C.append(state.p("session.jsonl"), {"t": time.time(), "event": "ready", "take": take})
    return take


def wait_ready(cfg: dict, term: Term) -> None:
    """Wait for the target to come up, answering first-launch dialogs on the way.

    Everything before the "ready" mark is folded into t=0 by postprocess.py, so
    the dialogs never reach the published cast.
    """
    rec = cfg["recording"]
    ready = re.compile(rec["ready"]) if rec["ready"] else None
    prev, still = None, 0
    for _ in range(90):
        screen = term.pane()
        if "Allow external CLAUDE.md file imports" in screen:
            term.keys("Enter")          # the default is No
            time.sleep(3)
            continue
        if "Yes, I trust this folder" in screen or "Yes, I accept" in screen:
            term.keys("Down")
            time.sleep(0.5)
            term.keys("Enter")
            time.sleep(3)
            continue
        if ready and ready.search(screen):
            break
        if not ready:
            # No marker to look for: up is when something is on screen and it
            # has stopped changing.
            still = still + 1 if (screen.strip() and screen == prev) else 0
            prev = screen
            if still >= rec["settle"]:
                break
        time.sleep(1)
    else:
        log("! the target never looked ready; carrying on")
    time.sleep(1)


# --------------------------------------------------------------------------- send
def send(cfg: dict, term: Term, text: str) -> None:
    rec = cfg["recording"]
    # Clears a TUI's pending state; empty for a target that reads ESC as a prefix.
    if rec["clear_key"]:
        term.keys(rec["clear_key"])
        time.sleep(1)
    # In vim mode, Escape leaves the input box in NORMAL, where a paste is a
    # string of commands. Get back to INSERT first.
    if "-- NORMAL --" in term.pane():
        term.keys("i")
        time.sleep(0.5)
    # Bracketed paste: send-keys -l swallows newlines and a multi-paragraph
    # prompt arrives as one run-on line.
    term.tmux("load-buffer", "-", input=text)
    term.tmux("paste-buffer", *(["-p"] if rec["bracketed_paste"] else []), "-t", term.sock)
    time.sleep(2)
    term.keys("Enter")
    # An Enter can be swallowed while the TUI re-renders. If the text is still
    # in the input box — the LAST ❯ line, earlier ones are the conversation —
    # press it once more. Never on an empty box.
    time.sleep(4)
    if still_in_box(term, text):
        log("  (Enter again)")
        term.keys("Enter")


def still_in_box(term: Term, text: str) -> bool:
    """Is this text sitting unsent in the input box — the LAST ❯ line?"""
    head = (text.strip().splitlines() or [""])[0][:12].strip()
    if not head:
        return False
    box = next((ln for ln in reversed(term.pane().splitlines()) if ln.lstrip().startswith("❯")), "")
    return head in box


OPTION = re.compile(r"^\s*(❯\s*)?\d+\.\s")
RULE = re.compile(r"\s*─{10,}.*")


def question_options(screen: str) -> list[str] | None:
    """The options of an AskUserQuestion widget, read from inside the widget only.

    Walk up from the "Enter to select" footer to the nearest rule line: numbered
    lists printed earlier in the conversation are never options.
    """
    lines = screen.splitlines()
    ends = [i for i, ln in enumerate(lines) if "Enter to select" in ln]
    if not ends:
        return None
    end = ends[-1]
    begin = next((i for i in range(end - 1, -1, -1) if RULE.fullmatch(lines[i])), 0)
    return [ln for ln in lines[begin:end] if OPTION.match(ln)]


def pick_option(opts: list[str], pattern: str) -> int:
    rx = re.compile(pattern)
    return next((i for i, o in enumerate(opts) if rx.search(o)), 0)


def answer_question(cfg: dict, term: Term, screen: str) -> bool:
    rec = cfg["recording"]
    if rec["answer_questions"] != "recommended":
        return False
    if "Enter to select" not in screen:
        if re.search(r"Submit answers|Review your answers", screen):
            time.sleep(3)
            term.keys("Enter")
            log("  (responder) submitted the answers")
            return True
        return False
    opts = question_options(screen) or []
    pick = pick_option(opts, rec["recommend"])
    time.sleep(rec["question_delay"])     # let the viewer read the question
    for _ in range(pick):
        term.keys("Down")
        time.sleep(0.4)
    term.keys("Enter")
    log(f"  (responder) chose option {pick + 1}: {opts[pick].strip()[:60] if opts else '?'}")
    time.sleep(3)
    return True


def drop_files(cfg: dict, stage: dict) -> bool:
    """Copy a stage's drops into the inbox, just before its prompt is sent."""
    if not stage["drop"]:
        return True
    inbox = cfg["workdir"] / cfg["recording"]["drop_dir"]
    inbox.mkdir(parents=True, exist_ok=True)
    for rel in stage["drop"]:
        src = cfg["base"] / rel
        if not src.is_file():
            log(f"✖ {stage['id']}: drop {rel} does not exist")
            return False
        dst = inbox / src.name
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            log(f"  {cfg['recording']['drop_dir']} ← {src.name} (already there)")
            continue
        shutil.copy2(src, dst)
        log(f"  {cfg['recording']['drop_dir']} ← {src.name}")
    return True


# --------------------------------------------------------------------------- wait
def wait_turn(cfg: dict, state: State, term: Term, sid: str, check: str | None,
              stall: int) -> int:
    rec = cfg["recording"]
    hook = rec["turn_signal"] == "hook"
    turn_file = state.p("turn-ended")
    turn_mark = turn_file.read_text() if turn_file.exists() else ""
    last_rev, last_change = None, time.time()
    while True:
        if not term.alive():
            log(f"✖ {sid} — the terminal went away")
            return 5
        if hook:
            if state.answered(sid):
                settle(term, rec["settle"])
                if verify(cfg, state, check):
                    state.mark_verified(sid)
                    log(f"✓ {sid} turn ended and verified")
                    return 0
                return stopped_short(term, sid, check)
        else:
            if verify(cfg, state, check) and check:
                settle(term, rec["settle"])
                state.mark_verified(sid)
                log(f"✓ {sid} complete and verified")
                return 0
            now_mark = turn_file.read_text() if turn_file.exists() else ""
            if now_mark != turn_mark:
                return stopped_short(term, sid, check)
        screen = term.pane()
        if answer_question(cfg, term, screen):
            last_change = time.time()       # a choice made is activity
            continue
        rev = hash(screen)
        if rev != last_rev:
            last_rev, last_change = rev, time.time()
        elif time.time() - last_change >= stall:
            log(f"✖ {sid} produced no output for {stall}s — stalled")
            return 1
        time.sleep(rec["poll"])


def stopped_short(term: Term, sid: str, check: str | None) -> int:
    # The turn ended and the check does not pass: a stage that stopped short —
    # or stopped to ask. Worth saying now rather than burning the stall budget.
    log(f"⚠ {sid} — turn ended but the check still fails:\n    {check}")
    print("\n".join(term.pane().rstrip().splitlines()[-15:]), flush=True)
    log("  answer with `stagecast say \"…\"`, then `stagecast record` resumes without re-sending")
    return 3


# --------------------------------------------------------------------------- record
def plan(cfg: dict, a: argparse.Namespace) -> list[dict]:
    stages = cfg["stages"]
    ids = [s["id"] for s in stages]
    for flag in ("only", "start", "until"):
        v = getattr(a, flag, None)
        if v and v not in ids:
            raise SystemExit(f"no stage {v!r} in {cfg['path'].name} (have {', '.join(ids)})")
    if a.only:
        return [s for s in stages if s["id"] == a.only]
    lo = ids.index(a.start) if a.start else 0
    hi = ids.index(a.until) + 1 if a.until else len(ids)
    return stages[lo:hi]


def refuse(cfg: dict) -> int:
    # A scaffolded check is not a check: a run that started anyway would
    # advance on nothing — the one thing this framework exists to prevent.
    todo = [s for s in cfg["stages"] if "TODO:" in s.get("verify", "")]
    if todo:
        log(f"✖ {len(todo)} stage(s) still have a TODO check — fill them in before recording")
        for s in todo:
            print(f"    {s['id']}\t{s['name']}")
        return 2
    if not cfg["stages"]:
        log("✖ no [[stage]] in the config")
        return 2
    why = preflight(cfg)
    if why:
        log(f"✖ {why}")
        return 2
    return 0


def write_prompts(cfg: dict, state: State) -> None:
    """What the Stop hook matches the transcript's last human message against."""
    state.p("prompts.json").write_text(json.dumps(
        {s["id"]: s["prompt_text"] for s in cfg["stages"]}, ensure_ascii=False, indent=1))


def mark(state: State, sid: str, kind: str, label: str, take: str | None, **kw) -> None:
    C.append(state.p("markers.jsonl"), {"t": time.time(), "id": sid, "kind": kind,
                                        "label": label, "take": take, **kw})


def cmd_record(a: argparse.Namespace) -> int:
    cfg = C.load(a.config)
    rc = refuse(cfg)
    if rc:
        return rc
    if cfg["recording"]["mode"] == "continuous":
        return record_continuous(a)
    if cfg["recording"]["mode"] != "per-stage":
        log(f"✖ unknown [recording] mode {cfg['recording']['mode']!r}")
        return 2
    return record_per_stage(a)


def satisfied_already(cfg: dict, state: State, st: dict) -> bool:
    if cfg["recording"]["skip_if_satisfied"] and verify(cfg, state, st.get("verify")):
        state.mark_verified(st["id"])
        log(f"⏭ {st['id']} already satisfied (skip_if_satisfied)")
        return True
    return False


def record_per_stage(a: argparse.Namespace) -> int:
    done: set[str] = set()
    while True:
        cfg = C.load(a.config)          # re-read: stages may be inserted mid-run
        state, term = State(cfg), Term(cfg)
        write_prompts(cfg, state)
        todo = [s for s in plan(cfg, a) if s["id"] not in done
                and (a.only or not state.verified(s["id"]))]
        if not todo:
            break
        st = todo[0]
        sid = st["id"]
        done.add(sid)
        if satisfied_already(cfg, state, st):
            continue
        # Retire any earlier take of this stage rather than leaving two.
        for old in state.rec.glob(f"take-*-{C.slug(sid)}.cast"):
            old.rename(state.rec / "_aborted" / f"{time.strftime('%H%M%S')}-{old.name}")
        for f in (state.dir / "answered" / sid, state.p(f"fp-{sid}"), state.dir / "verified" / sid):
            f.unlink(missing_ok=True)
        log(f"▶ stage {sid} {st['name']}")
        take = start_take(cfg, state, term, sid, sid)
        if not take:
            return 5
        if not drop_files(cfg, st):
            term.kill()
            return 2
        mark(state, sid, "stage", f"{sid} {st['name']}", take)
        send(cfg, term, st["prompt_text"])
        log(f"  sent; stalls after {st['stall_s']}s without output")
        rc = wait_turn(cfg, state, term, sid, st.get("verify"), st["stall_s"])
        teardown(cfg, state, term, take)
        if rc:
            log(f"✖ stopped at stage {sid} (rc={rc})")
            return rc
    log("✓ all stages recorded")
    return 0


def teardown(cfg: dict, state: State, term: Term, take: str) -> None:
    rec = cfg["recording"]
    # Wait for the pane to hold still before asking it to leave: quitting into
    # a stream that had not finished left "exitwrote 4 lines" on screen.
    settle(term, rec["settle"])
    # Everything after this mark is the teardown; postprocess.py cuts it.
    C.append(state.p("session.jsonl"), {"t": time.time(), "event": "stop", "take": take})
    if rec["clear_key"]:
        term.keys(rec["clear_key"])
        time.sleep(1)
    term.keys(rec["quit"])
    time.sleep(1)
    term.keys("Enter")
    time.sleep(3)
    term.kill()


def record_continuous(a: argparse.Namespace) -> int:
    cfg = C.load(a.config)
    state, term = State(cfg), Term(cfg)
    if not term.alive():
        rc = cmd_start(a)
        if rc:
            return rc
    while True:
        cfg = C.load(a.config)          # re-read: stages may be inserted mid-run
        state = State(cfg)
        write_prompts(cfg, state)
        take = (state.current_take() or {}).get("take")
        todo = [s for s in plan(cfg, a) if not state.verified(s["id"])]
        if not todo:
            break
        st = todo[0]
        sid = st["id"]
        if state.answered(sid) or sid in state.sent_in_take(take):
            # Sent earlier and the driver restarted: wait on it, never send twice.
            log(f"↻ {sid} already sent — waiting on it")
            # Killed between the paste and the Enter, the prompt is still in the box.
            if not state.answered(sid) and still_in_box(term, st["prompt_text"]):
                log("  (Enter — the prompt was pasted but never submitted)")
                term.keys("Enter")
        elif satisfied_already(cfg, state, st):
            continue
        else:
            if not drop_files(cfg, st):
                return 2
            settle(term, cfg["recording"]["settle"])
            mark(state, sid, "stage", f"{sid} {st['name']}", take)
            log(f"▶ {sid} {st['name']}")
            send(cfg, term, st["prompt_text"])
        rc = wait_turn(cfg, state, term, sid, st.get("verify"), st["stall_s"])
        if rc:
            return rc
        if a.only:
            break
    log("✓ all stages done — the session is still recording; `stagecast finish` to close it")
    return 0


def cmd_start(a: argparse.Namespace) -> int:
    cfg = C.load(a.config)
    if cfg["recording"]["mode"] != "continuous":
        log("✖ start is for [recording] mode = \"continuous\"; per-stage opens a session per stage")
        return 2
    rc = refuse(cfg)
    if rc:
        return rc
    state, term = State(cfg), Term(cfg)
    write_prompts(cfg, state)
    if term.alive():
        log("session already running")
        return 0
    take = start_take(cfg, state, term, "session", None)
    if not take:
        return 5
    log(f"▶ session up → {take}")
    return 0


def cmd_say(a: argparse.Namespace) -> int:
    """An unscripted message into the live session, recorded as what it was."""
    cfg = C.load(a.config)
    state, term = State(cfg), Term(cfg)
    if not term.alive():
        log("✖ no live session to say anything into (say needs mode = \"continuous\")")
        return 5
    take = (state.current_take() or {}).get("take")
    said = C.jsonl(state.p("said.jsonl"))
    sid = f"say{len(said) + 1:02d}"
    after = a.after or next((m["id"] for m in reversed(C.jsonl(state.p("markers.jsonl")))
                             if m.get("kind") == "stage"), None)
    C.append(state.p("said.jsonl"), {"id": sid, "text": a.text, "after": after, "t": time.time()})
    settle(term, cfg["recording"]["settle"])
    mark(state, sid, "say", f"↳ {a.text[:24]}", take, after=after)
    log(f"▶ {sid} (after {after}): {a.text}")
    send(cfg, term, a.text)
    if cfg["recording"]["turn_signal"] == "hook":
        return wait_turn(cfg, state, term, sid, None, cfg["stages"][0]["stall_s"] if cfg["stages"] else 3600)
    settle(term, max(5, cfg["recording"]["settle"]), 600)
    return 0


def cmd_finish(a: argparse.Namespace) -> int:
    cfg = C.load(a.config)
    state, term = State(cfg), Term(cfg)
    if not term.alive():
        log("no session running")
        return 0
    settle(term, 5, 120)
    take = (state.current_take() or {}).get("take")
    C.append(state.p("session.jsonl"), {"t": time.time(), "event": "finish", "take": take})
    # Stop asciinema first, so the cast ends on the agent's live screen rather
    # than on the teardown that /exit would print.
    pid = term.pane_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.25)
    time.sleep(1)
    term.kill()
    log(f"■ recording closed: {state.rec / take if take else state.rec}")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    cfg = C.load(a.config)
    state, term = State(cfg), Term(cfg)
    take = (state.current_take() or {}).get("take")
    sent = {m["id"] for m in C.jsonl(state.p("markers.jsonl"))}
    for st in cfg["stages"]:
        sid = st["id"]
        mark_ = ("✓" if state.verified(sid) else "…" if state.answered(sid)
                 else "→" if sid in sent else " ")
        print(f"  {mark_} {sid:>4}  {st['name']}")
    for d in C.jsonl(state.p("said.jsonl")):
        print(f"  ↳ {d['id']:>4}  after {d.get('after')}: {d['text'][:60]}")
    print(f"  mode {cfg['recording']['mode']}, session {'alive' if term.alive() else 'none'}"
          + (f", take {take}" if take else ""))
    print("  ✓ verified  … turn ended, check failing  → sent")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="stagecast")
    ap.add_argument("config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--only")
    r.add_argument("--from", dest="start")
    r.add_argument("--until")
    sub.add_parser("start")
    s = sub.add_parser("say")
    s.add_argument("text")
    s.add_argument("--after")
    sub.add_parser("finish")
    sub.add_parser("status")
    a = ap.parse_args()
    for k in ("only", "start", "until"):
        setattr(a, k, getattr(a, k, None))
    return {"record": cmd_record, "start": cmd_start, "say": cmd_say,
            "finish": cmd_finish, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
