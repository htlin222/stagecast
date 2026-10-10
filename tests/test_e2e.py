"""Continuous mode end to end, against tests/fake_agent.py: issues #2, #3, #7.

Needs tmux and asciinema; skipped without them.
"""
import json
import os
import pathlib
import shutil
import signal
import subprocess
import time

import pytest

from conftest import ROOT, read_cast

pytestmark = pytest.mark.skipif(not (shutil.which("tmux") and shutil.which("asciinema")),
                                reason="needs tmux and asciinema")
FIXTURE = ROOT / "tests" / "fixtures" / "continuous"


def sc(base, *a, **kw):
    return subprocess.run([str(ROOT / "stagecast"), *a], cwd=base, capture_output=True, text=True,
                          env={**os.environ, "SC_SETTLE": "1"}, **kw)


@pytest.fixture
def run(tmp_path):
    base = tmp_path / "run"
    shutil.copytree(FIXTURE, base)
    toml = (base / "stagecast.toml").read_text()
    toml = toml.replace("../../../fake_agent.py", str(ROOT / "tests" / "fake_agent.py"))
    toml = toml.replace('socket          = "stagecast-e2e"', f'socket          = "sc-e2e-{os.getpid()}"')
    (base / "stagecast.toml").write_text(toml)
    (base / "work").mkdir()
    yield base
    sc(base, "finish")


def jsonl(p):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def test_one_session_interjection_restart_and_finish(run):
    state = run / ".stagecast"
    r = sc(run, "record")
    # stage 02's prompt does not make two.txt: the turn ends, the check fails
    assert r.returncode == 3, r.stdout + r.stderr
    assert "turn ended but the check still fails" in r.stdout
    r = sc(run, "say", "ok, create two.txt then")
    assert r.returncode == 0, r.stdout

    # kill the driver mid-turn on stage 03, then run again: never sent twice
    p = subprocess.Popen([str(ROOT / "stagecast"), "record"], cwd=run, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, env={**os.environ, "SC_SETTLE": "1"},
                         start_new_session=True)
    for _ in range(100):
        if any(m["id"] == "03" for m in jsonl(state / "markers.jsonl")):
            break
        time.sleep(0.2)
    time.sleep(1)
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    r = sc(run, "record")
    assert r.returncode == 0, r.stdout
    assert "03 already sent" in r.stdout
    sent = [m["id"] for m in jsonl(state / "markers.jsonl")]
    assert sent == ["01", "02", "say01", "03"]
    turns = jsonl(state / "turns.jsonl")
    assert [t["id"] for t in turns] == ["01", "02", "say01", "03"]

    # re-running after completion re-evaluates nothing that is verified
    (run / "work" / "one.txt").unlink()
    r = sc(run, "record")
    assert r.returncode == 0 and "▶" not in r.stdout

    # the session was never quit between stages; finish stops asciinema first
    r = sc(run, "finish")
    assert r.returncode == 0
    casts = list((state / "recording").glob("take-*.cast"))
    assert len(casts) == 1
    _, raw = read_cast(casts[0])
    text = "".join(e[2] for e in raw if e[1] == "o")
    assert "exit" not in text.split("● done: slow")[-1]

    r = sc(run, "build", "--prompts-md", "PROMPTS.md")
    assert r.returncode == 0, r.stdout + r.stderr
    _, events = read_cast(run / "site" / "demo.cast")
    marks = [e[2].split()[0] for e in events if e[1] == "m"]
    assert marks == ["01", "02", "say01", "03"]
    last = "".join(e[2] for e in events if e[1] == "o")
    assert last.rstrip().endswith("❯") and "done: slow" in last[-300:]
    chapters = json.loads((run / "site" / "chapters.json").read_text())
    assert chapters[2]["kind"] == "say" and chapters[2]["after"] == "02"
    md = (run / "PROMPTS.md").read_text()
    assert md.index("ok, create two.txt then") > md.index("### 02") and md.index("ok, create") < md.index("### 03")
    html = (run / "site" / "index.html").read_text()
    assert "↳ interjection" in html and "not in the script" in html
