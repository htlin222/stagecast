#!/usr/bin/env python3
"""Raw recording → the published cast, chapters as asciinema markers.

    uv run --no-project --with pyte tools/postprocess.py <stagecast.toml> <site-dir>

The one pass every export goes through. Recordings are made with raw
wall-clock timing (`asciinema rec -i 86400`), so the times the driver and the
Stop hook logged line up with the cast; everything that changes time happens
here, through one function, so events, markers and chapter ends cannot drift
apart:

  t = 0        the moment the take was ready — startup dialogs fold away
  idle cap     any gap longer than `idle_limit` plays as `idle_limit`
  time-lapse   inside each turn (prompt sent → turn ended), the first `head`
               and last `foot` seconds play at 1x and the middle at `fast`x:
               the message going in and the answer coming out stay readable
  hold         the gap that contains a turn end plays as `hold` seconds, so a
               finished answer stays on screen before the next chapter
  end of take  the last ended turn plus `tail`, or where the driver began the
               teardown — so the last frame is the answer, not a quit

Then credentials are redacted in every event (tools/redact.py), and:

  demo.cast         every take joined, one "m" marker per chapter; no
                    idle_time_limit in the header, so nothing compresses twice
  casts/NNN.cast    one per chapter, opening on the screen as it stood when the
                    chapter began (replayed through a headless terminal and
                    serialised), so the page loads one chapter at a time
  chapters.json     id, name, kind, prompt, start `t`, turn `end`, `cast`
  meta.json         raw and played seconds, size, gzip size, event count
"""
from __future__ import annotations

import bisect
import gzip
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import redact as R  # noqa: E402
import sc_config as C  # noqa: E402

TAKE_GAP = 1.0      # between takes, so a restart reads as a pause, not a jump cut
TRIM_TAIL = 8.0     # legacy takes with no end signal: kept after the last real output
TRIM_BYTES = 250    # an event smaller than this is animation, not content


# --------------------------------------------------------------------------- takes
def takes_of(cfg: dict) -> list[dict]:
    state = cfg["state"]
    rec = state / "recording"
    session = C.jsonl(state / "session.jsonl")
    by: dict[str, dict] = {}
    for e in session:
        name = e.get("take")
        if not name:
            continue
        tk = by.setdefault(name, {"take": name, "stage": None})
        if e["event"] == "start":
            tk.update(start=e["t"], stage=e.get("stage"))
        elif e["event"] == "t0":
            tk["t0"] = e["t"]          # when asciinema's clock actually started
        elif e["event"] == "ready":
            tk["ready"] = e["t"]
        elif e["event"] in ("stop", "finish"):
            tk.setdefault("stop", e["t"])
    takes = [t for t in by.values() if "start" in t and (rec / t["take"]).exists()]
    takes.sort(key=lambda t: t["start"])
    # Recordings made before session.jsonl existed: seg-NNN-stepID.cast.
    for p in sorted(rec.glob("seg-*.cast")):
        m = re.search(r"step([0-9A-Za-z_-]+)\.cast$", p.name)
        takes.append({"take": p.name, "stage": m.group(1) if m else None, "legacy": True})

    if cfg["recording"]["mode"] == "per-stage":
        order = {s["id"]: i for i, s in enumerate(cfg["stages"])}
        latest: dict[str, dict] = {}
        for t in takes:
            latest[t["stage"]] = t     # later takes of a stage win
        takes = sorted((t for t in latest.values() if t["stage"] in order),
                       key=lambda t: order[t["stage"]])

    markers = C.jsonl(state / "markers.jsonl")
    turns = C.jsonl(state / "turns.jsonl")
    starts = [t.get("start", float("inf")) for t in takes]
    for i, t in enumerate(takes):
        lo = t.get("start", float("inf"))
        hi = min((s for s in starts if s > lo), default=float("inf"))
        t["markers"] = sorted((m for m in markers if m.get("take") == t["take"]
                               or (m.get("take") is None and lo <= m["t"] < hi)),
                              key=lambda m: m["t"])
        t["turns"] = sorted(x["t"] for x in turns if lo <= x["t"] < hi)
    return takes


# --------------------------------------------------------------------------- time
class Clock:
    """Raw (seconds since the take started) → playback time. One function for all."""

    def __init__(self, raw: list[float], ready: float, sends: list[float],
                 ends: list[float], pp: dict):
        self.ready, self.ends, self.pp = ready, ends, pp
        self.windows = []
        for s0 in sends:
            e = next((e for e in ends if e > s0), None)
            if e is not None and e - s0 > pp["head"] + pp["foot"]:
                self.windows.append((s0 + pp["head"], e - pp["foot"]))
        self.raw, self.play = [], []
        prev_raw, prev_play = ready, 0.0
        for r in raw:
            if r > ready:
                prev_play += self.gap(prev_raw, r)
                prev_raw = r
            self.raw.append(r)
            self.play.append(prev_play)

    def fast(self, r: float) -> bool:
        return any(lo <= r < hi for lo, hi in self.windows)

    def gap(self, r0: float, r1: float) -> float:
        if any(r0 <= e < r1 for e in self.ends):
            return self.pp["hold"]
        g = r1 - r0
        if self.fast(r0) and self.fast(r1):
            g /= self.pp["fast"]
        return min(g, self.pp["idle_limit"])

    def __call__(self, r: float) -> float:
        if r <= self.ready:
            return 0.0
        i = bisect.bisect_right(self.raw, r) - 1
        if i < 0 or self.raw[i] <= self.ready:
            return self.gap(self.ready, r)
        return self.play[i] + self.gap(self.raw[i], r)


def process_take(cfg: dict, tk: dict, secrets: dict, counts: dict) -> dict:
    pp = cfg["postprocess"]
    header, events = C.read_cast(cfg["state"] / "recording" / tk["take"])
    if not events:
        return {"header": header, "events": [], "marks": [], "ends": [], "dur": 0.0,
                "raw": 0.0}
    t0 = tk.get("t0", tk.get("start"))
    rel = (lambda w: w - t0) if t0 is not None else (lambda w: w)
    ready = rel(tk["ready"]) if "ready" in tk and t0 is not None else 0.0
    sends = [rel(m["t"]) for m in tk["markers"]]
    ends = [rel(t) for t in tk["turns"]]

    last = events[-1][0]
    t_end = last
    if "stop" in tk and t0 is not None:
        t_end = min(t_end, rel(tk["stop"]))
    if ends and (not sends or max(ends) >= max(sends)):
        t_end = min(t_end, max(ends) + pp["tail"])
    if tk.get("legacy") and "stop" not in tk and not ends:
        big = next((e[0] for e in reversed(events) if e[1] == "o" and len(e[2]) >= TRIM_BYTES), None)
        if big is not None:
            t_end = min(t_end, big + TRIM_TAIL)

    kept = [e for e in events if e[0] <= t_end]
    clock = Clock([e[0] for e in kept], ready, sends, ends, pp)
    out: list[list] = []
    for (_, kind, data), p in zip(kept, clock.play):
        if kind == "o":
            data = R.redact(data, secrets, counts)
            if out and out[-1][1] == "o" and p - out[-1][3] < pp["coalesce"]:
                out[-1][2] += data          # one frame's worth of output, one event
                continue
        out.append([p, kind, data, p])
    events_out = [e[:3] for e in out if e[1] == "o"]    # markers are re-made below

    end_play = events_out[-1][0] if events_out else 0.0
    turn_end_play = [clock(e) for e in ends if e <= t_end]
    # Every take ends on a still frame held long enough to read: a cast's
    # duration is its last event, so the hold needs an event to stand on.
    hold_to = max([end_play] + [x + pp["hold"] for x in turn_end_play[-1:]])
    if not turn_end_play:
        hold_to = end_play + pp["hold"]
    if hold_to > end_play:
        events_out.append([hold_to, "o", ""])
    marks = [(clock(s), m) for s, m in zip(sends, tk["markers"])]
    return {"header": header, "events": events_out, "marks": marks,
            "ends": turn_end_play, "dur": hold_to, "raw": max(0.0, t_end - ready)}


# --------------------------------------------------------------------------- build
def chapter_of(cfg: dict, m: dict, said: dict) -> dict:
    by_id = {s["id"]: s for s in cfg["stages"]}
    if m.get("kind") == "say":
        d = said.get(m["id"], {})
        return {"id": m["id"], "kind": "say", "name": "interjection",
                "prompt": d.get("text", ""), "after": d.get("after", m.get("after")),
                "note": "Typed live during the recording — not in the script."}
    st = by_id.get(m["id"], {})
    return {"id": m["id"], "kind": "stage", "name": st.get("name", m.get("label", m["id"])),
            "prompt": st.get("prompt_text", ""), "note": st.get("note", ""),
            "part": st.get("part", ""),
            "drop": [pathlib.Path(d).name for d in st.get("drop", [])],
            "recorded": st.get("recorded", "")}


def build(cfg: dict, out: pathlib.Path) -> int:
    from vt import RESET, Replayer   # needs pyte; only the build path does

    pp = cfg["postprocess"]
    secrets = R.load_secrets(cfg["base"], cfg["redact"])
    counts: dict[str, int] = {}
    takes = takes_of(cfg)
    if not takes:
        print("  no recordings in .stagecast/recording/ — run `stagecast record`", file=sys.stderr)
        return 1
    said = {d["id"]: d for d in C.jsonl(cfg["state"] / "said.jsonl")}
    per_stage = cfg["recording"]["mode"] == "per-stage"

    header = None
    events: list[list] = []
    chapters: list[dict] = []
    offset = raw_total = 0.0
    for tk in takes:
        r = process_take(cfg, tk, secrets, counts)
        if not r["events"]:
            continue
        header = header or r["header"]
        if events:
            offset = max(offset, events[-1][0]) + TAKE_GAP
            events.append([offset, "o", RESET])
        events += [[offset + e[0], e[1], e[2]] for e in r["events"]]
        ends = [offset + x for x in r["ends"]]
        marks = r["marks"]
        if per_stage and tk.get("stage"):
            # The chapter is the whole take: open on the fresh session.
            marks = [(0.0, {"id": tk["stage"], "kind": "stage"})] + \
                    [(p, m) for p, m in marks if m.get("kind") == "say"]
        if not marks and tk.get("legacy") and tk.get("stage"):
            marks = [(0.0, {"id": tk["stage"], "kind": "stage"})]
        take_chapters = []
        for p, m in marks:
            t = offset if (per_stage and m.get("kind") == "stage") else max(offset, offset + p - 0.5)
            ch = chapter_of(cfg, m, said)
            ch["t"] = t
            take_chapters.append(ch)
        for i, ch in enumerate(take_chapters):
            nxt = take_chapters[i + 1]["t"] if i + 1 < len(take_chapters) else float("inf")
            later = [e for e in ends if ch["t"] < e <= nxt + 0.5]
            ch["end"] = round(later[0], 3) if later else (
                round(offset + r["dur"], 3) if per_stage else None)
        chapters += take_chapters
        offset += r["dur"]
        raw_total += r["raw"]

    if not chapters:
        print("  the recordings carry no chapters (no markers.jsonl entries)", file=sys.stderr)
        return 1
    # Markers in order, never two at one instant (a zero-length chapter).
    for i in range(1, len(chapters)):
        chapters[i]["t"] = max(chapters[i]["t"], chapters[i - 1]["t"] + 0.01)
    total = max(events[-1][0], chapters[-1]["t"])
    for i, ch in enumerate(chapters):
        nxt = chapters[i + 1]["t"] if i + 1 < len(chapters) else total
        ch["t"] = round(ch["t"], 3)
        ch["dur"] = round(nxt - ch["t"], 3)
        ch["cast"] = f"casts/{i + 1:03d}.cast"

    rec = cfg["recording"]
    header = {k: v for k, v in (header or {}).items() if k not in ("idle_time_limit", "env")}
    header.update(version=2, width=header.get("width", rec["cols"]),
                  height=header.get("height", rec["rows"]))
    if cfg["project"].get("title"):
        header["title"] = cfg["project"]["title"]

    full = [e for e in events] + [[c["t"], "m", f"{c['id']} {c['name']}"] for c in chapters]
    full.sort(key=lambda e: (e[0], e[1] != "o"))
    out.mkdir(parents=True, exist_ok=True)
    C.write_cast(out / "demo.cast", header, full)

    # Chapter casts: the screen at the cut, then that chapter's own events.
    vt = Replayer(header["width"], header["height"])
    # Chapter times are rounded to the millisecond; an event at the very instant
    # of a cut belongs to the chapter that starts there.
    cuts = [0.0] + [c["t"] - 0.0005 for c in chapters[1:]] + [float("inf")]
    k = 0
    for i, ch in enumerate(chapters):
        lo, hi = cuts[i], cuts[i + 1]
        while k < len(events) and events[k][0] < lo:
            vt.feed(events[k][2])
            k += 1
        own = [[0.0, "o", vt.snapshot()]] if i else []
        while k < len(events) and events[k][0] < hi:
            own.append([events[k][0] - lo, "o", events[k][2]])
            vt.feed(events[k][2])
            k += 1
        C.write_cast(out / ch["cast"], header, own)

    (out / "chapters.json").write_text(json.dumps(chapters, ensure_ascii=False, indent=1))
    raw_bytes = (out / "demo.cast").read_bytes()
    meta = {"raw_seconds": round(raw_total, 1), "played_seconds": round(total, 1),
            "events": len(full), "bytes": len(raw_bytes),
            "gzip_bytes": len(gzip.compress(raw_bytes, 6))}
    (out / "meta.json").write_text(json.dumps(meta))

    for k_, n in sorted(counts.items()):
        print(f"  redacted {k_} ×{n}")
    mb = meta["bytes"] / 1e6
    print(f"  demo.cast: {meta['events']:,} events, {mb:.1f} MB raw, "
          f"{meta['gzip_bytes'] / 1e6:.2f} MB gzipped; "
          f"{raw_total / 60:.1f} min recorded → {total / 60:.1f} min played; "
          f"{len(chapters)} chapter(s)")
    if mb > cfg["site"]["warn_mb"]:
        print(f"  warning: demo.cast is over {cfg['site']['warn_mb']} MB — the page loads "
              f"one chapter cast at a time, but consider a lower [postprocess] fast/idle_limit",
              file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip())
        return 2
    return build(C.load(sys.argv[1]), pathlib.Path(sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
