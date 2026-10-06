#!/usr/bin/env python3
"""Lint the recordings themselves.

Every defect in the "Driving a target that is not Claude Code" section of
docs/LESSONS.md passed its stage check and was found by a person watching the
playback. That is not a check. The recording is the artefact, so it gets linted
like one.

Two tiers, because they are different claims:

  leak   only the harness can produce this. Refuse.
  noise  the target produced it. Report it; refuse only under [lint] strict.
"""
import json, re, sys, tomllib
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][B0]|\x1b[=>]|\r")

# Shapes the driver leaves behind. Each one actually happened; the comment says
# what it meant, because a lint nobody can act on gets switched off.
LEAKS = [
    (re.compile(r"\[20[01]~"),
     "bracketed-paste markers reached the screen — clear_key is being sent into "
     "a target that reads ESC as a prefix, or bracketed_paste is wrong"),
    (re.compile(r"invalid option -- |^usage: (grep|sed|ls)\b", re.M),
     "a harness command misfired inside the recorded pane"),
    # ESC followed by something that introduces nothing. The recognised set is
    # listed rather than guessed: CSI "[", OSC "]", charset "()", save/restore
    # "78", and the single-character Fe/Fs escapes. A first attempt excluded only
    # "[()=>" and fired on every cast, because bash sets the window title with
    # OSC — a lint that cries wolf gets turned off, which is worse than none.
    (re.compile(r"\x1b(?![][()#%0-9=><DEHMNOPVWXZ\\^_clmno|}~+./*-])", re.S),
     "a bare ESC was typed into the pane — clear_key sent to a target that does "
     "not want one"),
]

NOISE = [
    (re.compile(r"command not found"), "a command the target could not run"),
    (re.compile(r"No such file or directory"), "a path that was not there"),
    (re.compile(r"Traceback \(most recent call last\)"), "an unhandled exception"),
]


def text(cast: Path) -> str:
    out = []
    for line in cast.read_text(errors="replace").splitlines()[1:]:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if len(ev) >= 3 and ev[1] == "o":
            out.append(ev[2])
    return "".join(out)


def context(body: str, m: re.Match) -> str:
    clean = ANSI.sub("", body)
    # locate on the cleaned text so the quoted line is what a viewer saw
    hit = clean.find(ANSI.sub("", m.group(0))) if m.group(0).strip() else -1
    i = hit if hit >= 0 else 0
    line = clean[clean.rfind("\n", 0, i) + 1 : clean.find("\n", i) % (len(clean) + 1)]
    return line.strip()[:110] or repr(m.group(0))[:60]


def spliced_quit(body: str, quit_str: str):
    """The quit typed into a stream that had not finished.

    A check passes the moment the artefact exists, while the target is still
    printing. Quitting then splices the keystrokes into the output — the real
    one read `exitwrote 4 lines`. The shape is exact: the quit string welded to
    a word on either side, which is why this is a leak and not a judgement call.
    """
    # The shape is the quit at the start of a line with the target's own output
    # welded to it: "exitwrote 4 lines". A first attempt excluded anything after
    # whitespace, which excluded the line break and so matched nothing — and the
    # recordings that had the defect were reported clean.
    q = re.escape(quit_str.lstrip("/"))
    return re.search(rf"^{q}(?=\w)", ANSI.sub("", body), re.M)


def main() -> int:
    cfg, whole = {}, {}
    cfgp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("stagecast.toml")
    if cfgp.exists():
        whole = tomllib.loads(cfgp.read_text())
        cfg = whole.get("lint", {})
        cfg.setdefault("quit", whole.get("recording", {}).get("quit", "/exit"))
    strict = cfg.get("strict", False)
    allowed = [re.compile(p) for p in cfg.get("allow", [])]

    casts = sorted(Path(sys.argv[2] if len(sys.argv) > 2 else ".stagecast/recording").glob("*.cast"))
    if not casts:
        print("  no casts to lint", file=sys.stderr)
        return 1

    bad = warned = 0
    for c in casts:
        body = text(c)
        for pat, why in LEAKS:
            for m in pat.finditer(body):
                if any(a.search(m.group(0)) for a in allowed):
                    continue
                print(f"  ✖ {c.name}: {why}\n      {context(body, m)}", file=sys.stderr)
                bad += 1
                break
        m = spliced_quit(body, cfg.get("quit", "exit"))
        if m:
            print(f"  ✖ {c.name}: the quit was typed before the output stopped — "
                  f"raise SC_SETTLE\n      {context(body, m)}", file=sys.stderr)
            bad += 1
        for pat, why in NOISE:
            m = pat.search(body)
            if not m or any(a.search(pat.pattern) for a in allowed):
                continue
            n = len(pat.findall(body))
            mark = "✖" if strict else "!"
            print(f"  {mark} {c.name}: {why} ({n}×)\n      {context(body, m)}",
                  file=sys.stderr)
            if strict:
                bad += 1
            else:
                warned += 1

    if bad:
        print(f"  {bad} problem(s) in the recordings — refusing", file=sys.stderr)
        return 1
    print(f"  {len(casts)} cast(s) clean" + (f", {warned} warning(s)" if warned else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
