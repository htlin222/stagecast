"""Raw wall-clock recordings → playback time: issues #2, #5 and #10."""
import pyte

import postprocess
import sc_config as C
import vt
from conftest import jsonl, read_cast, write_cast

CONTINUOUS = """
[project]
name = "t"
title = "a test"
workdir = "work"
[recording]
mode = "continuous"
cols = 80
rows = 24
[postprocess]
idle_limit = 2
head = 5
foot = 5
fast = 8
hold = 8
tail = 3
[[stage]]
id = "01"
name = "First"
prompt = "Do the first thing"
verify = "true"
[[stage]]
id = "02"
name = "Second"
prompt = "Do the second thing"
verify = "true"
"""

T0 = 1_700_000_000.0


def synthetic(base, prompt_at=(10.0, 100.0), work=60.0):
    """A take with known times: a prompt, a minute of work, an answer, a turn end."""
    st = base / ".stagecast"
    events = [[0.2, "o", "\x1b[1mbanner\x1b[0m\r\n"], [3.0, "o", "❯ "]]
    turns, markers = [], []
    for k, (sid, at) in enumerate(zip(("01", "02"), prompt_at)):
        markers.append({"t": T0 + at, "id": sid, "kind": "stage", "take": "take-001-session.cast"})
        events.append([at + 0.6, "o", f"PROMPT-{sid}\r\n"])
        t = at + 1.0
        while t < at + work:
            events.append([t, "o", f"\x1b[38;5;{100 + k}mwork {t:.1f}\x1b[0m\r\n"])
            t += 0.5
        events.append([at + work + 0.2, "o", f"ANSWER-{sid}\r\n"])
        turns.append({"t": T0 + at + work + 0.5, "id": sid})
        events.append([at + work + 2.0, "o", "❯ "])
    write_cast(st / "recording" / "take-001-session.cast", events, idle_time_limit=2)
    jsonl(st / "session.jsonl", [
        {"t": T0 - 0.05, "event": "start", "take": "take-001-session.cast", "stage": None},
        {"t": T0, "event": "t0", "take": "take-001-session.cast"},
        {"t": T0 + 2.5, "event": "ready", "take": "take-001-session.cast"}])
    jsonl(st / "markers.jsonl", markers)
    jsonl(st / "turns.jsonl", turns)


def build(base):
    cfg = C.load(base / "stagecast.toml")
    assert postprocess.build(cfg, base / "site") == 0
    header, events = read_cast(base / "site" / "demo.cast")
    import json
    chapters = json.loads((base / "site" / "chapters.json").read_text())
    return cfg, header, events, chapters


def first(events, needle):
    return next(e[0] for e in events if e[1] == "o" and needle in e[2])


def test_marker_lands_within_a_second_of_the_prompt(project):
    base = project(CONTINUOUS)
    synthetic(base)
    _, _, events, chapters = build(base)
    marks = [e for e in events if e[1] == "m"]
    assert [m[2].split()[0] for m in marks] == ["01", "02"]
    for m, sid in zip(marks, ("01", "02")):
        shown = first(events, f"PROMPT-{sid}")
        assert 0 <= shown - m[0] <= 1.0, (shown, m[0])
    # chapters.json and the markers in the cast are the same numbers
    assert [c["t"] for c in chapters] == [m[0] for m in marks]


def test_header_never_compresses_twice(project):
    base = project(CONTINUOUS)
    synthetic(base)
    _, header, _, _ = build(base)
    assert "idle_time_limit" not in header


def test_startup_folds_into_zero(project):
    base = project(CONTINUOUS)
    synthetic(base)
    _, _, events, _ = build(base)
    assert first(events, "banner") == 0.0


def test_time_lapse_head_and_foot_at_1x_middle_fast(project):
    base = project(CONTINUOUS)
    synthetic(base)
    cfg, _, events, _ = build(base)
    pp = cfg["postprocess"]
    out = [e for e in events if e[1] == "o" and e[2].startswith("\x1b[38;5;100m")]
    times = {float(e[2].split()[1].split("\x1b")[0]): e[0] for e in out}
    # inside the head: 0.5 s apart in the recording, 0.5 s apart on playback
    assert abs((times[12.0] - times[11.5]) - 0.5) < 0.01
    # the middle: 0.5 s plays as 0.5 / fast
    assert abs((times[40.0] - times[39.5]) - 0.5 / pp["fast"]) < 0.01
    # inside the foot: back to 1x
    assert abs((times[67.0] - times[66.5]) - 0.5) < 0.01


def test_every_answer_is_held_before_the_next_chapter(project):
    base = project(CONTINUOUS)
    synthetic(base)
    cfg, _, events, chapters = build(base)
    answer = first(events, "ANSWER-01")
    assert chapters[1]["t"] - answer >= cfg["postprocess"]["hold"] - 0.01
    assert chapters[0]["end"] is not None and chapters[0]["end"] < chapters[1]["t"]


def test_take_ends_at_the_last_turn_plus_tail(project):
    base = project(CONTINUOUS)
    synthetic(base)
    # output long after the last turn ended — e.g. a spinner left running
    cast = base / ".stagecast/recording/take-001-session.cast"
    with cast.open("a") as f:
        f.write('[400.0, "o", "LATE"]\n')
    _, _, events, _ = build(base)
    assert not any("LATE" in e[2] for e in events if e[1] == "o")


def screen_state(screen):
    cell = lambda c: (c.data, c.fg, c.bg, c.bold, c.reverse, c.underscore)  # noqa: E731
    return [[cell(screen.buffer[y][x]) for x in range(screen.columns)] for y in range(screen.lines)]


def test_each_chapter_cast_opens_on_the_screen_a_full_replay_shows(project):
    """Issue #10: the chunked casts match a full replay at every chapter start."""
    base = project(CONTINUOUS)
    synthetic(base)
    cfg, header, events, chapters = build(base)
    w, h = header["width"], header["height"]
    out = [e for e in events if e[1] == "o"]
    for i, ch in enumerate(chapters):
        _, own = read_cast(base / "site" / ch["cast"])
        if i == 0:
            continue
        full = vt.screen_of(w, h, (e[2] for e in out if e[0] < ch["t"] - 0.0005))
        chunk = vt.screen_of(w, h, [own[0][2]])
        assert screen_state(full) == screen_state(chunk), f"chapter {ch['id']}"
        assert (full.cursor.x, full.cursor.y) == (chunk.cursor.x, chunk.cursor.y)
        # and the rest of the chapter replays to the same screen as the full cast
        nxt = chapters[i + 1]["t"] if i + 1 < len(chapters) else float("inf")
        full_end = vt.screen_of(w, h, (e[2] for e in out if e[0] < nxt - 0.0005))
        chunk_end = vt.screen_of(w, h, (e[2] for e in own))
        assert screen_state(full_end) == screen_state(chunk_end)


def test_snapshot_keeps_colours_as_palette_indices():
    s = pyte.Screen(20, 3)
    st = pyte.Stream(s)
    st.feed("\x1b[1;31mA\x1b[0m\x1b[38;5;231;48;5;237mB\x1b[38;2;1;2;3mC\x1b[0m\x1b[7mD")
    snap = vt.snapshot(s)
    assert "38;5;231" in snap and "48;5;237" in snap and "38;2;1;2;3" in snap
    again = vt.screen_of(20, 3, [snap])
    assert screen_state(again) == screen_state(s)


def test_chapter_casts_do_not_carry_earlier_chapters(project):
    base = project(CONTINUOUS)
    synthetic(base, work=200.0, prompt_at=(10.0, 300.0))
    _, _, _, chapters = build(base)
    last = (base / "site" / chapters[-1]["cast"]).read_text()
    assert "PROMPT-01" not in last.split("\n", 2)[2]       # only in the snapshot, if at all
    assert (base / "site" / chapters[-1]["cast"]).stat().st_size < \
        (base / "site" / "demo.cast").stat().st_size * 0.75


def test_build_reports_size_gzip_and_events(project, capsys):
    base = project(CONTINUOUS.replace("[site]", "") + "\n[site]\nwarn_mb = 0\n")
    synthetic(base)
    build(base)
    out = capsys.readouterr()
    assert "events" in out.out and "gzipped" in out.out
    assert "warning" in out.err
    import json
    meta = json.loads((base / "site" / "meta.json").read_text())
    assert meta["raw_seconds"] > meta["played_seconds"] > 0
    assert meta["gzip_bytes"] < meta["bytes"]
