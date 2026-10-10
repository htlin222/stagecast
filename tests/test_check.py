"""Issue #3: checks scoped to after the chapter started."""
import json
import os
import subprocess
import time

import pytest

from conftest import ROOT

CHECK = ROOT / "lib" / "bin" / "stagecast-check"


def git(repo, *a, env=None):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", **(env or {})})


def check(repo, state, *a):
    return subprocess.run([str(CHECK), *a], cwd=repo, capture_output=True,
                          env=dict(os.environ, STAGECAST_STATE=str(state))).returncode


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    (r / "a.txt").write_text("a")
    git(r, "add", "a.txt")
    git(r, "commit", "-qm", "first")
    git(r, "tag", "-a", "review-old", "-m", "review round one")
    state = tmp_path / "state"
    (state / "answered").mkdir(parents=True)
    return r, state


def test_saved_ignores_a_tag_older_than_the_prompt(repo):
    r, state = repo
    sent = int(time.time()) + 100           # the chapter's prompt went in after the old tag
    (state / "markers.jsonl").write_text(json.dumps({"t": sent, "id": "05"}) + "\n")
    assert check(r, state, "saved", "05", "review") != 0
    later = f"@{sent + 50} +0000"
    git(r, "tag", "-a", "review-new", "-m", "review round two",
        env={"GIT_COMMITTER_DATE": later})
    assert check(r, state, "saved", "05", "review") == 0


def test_saved_fails_for_a_stage_never_sent(repo):
    r, state = repo
    assert check(r, state, "saved", "99", "review") != 0


def test_answered_and_edited(repo):
    r, state = repo
    assert check(r, state, "answered", "01") != 0
    (state / "answered" / "01").write_text("1")
    assert check(r, state, "answered", "01") == 0
    fp = subprocess.run([str(CHECK), "fp"], cwd=r, capture_output=True, text=True,
                        env=dict(os.environ, STAGECAST_STATE=str(state))).stdout.strip()
    (state / "fp-01").write_text(fp)
    (state / "answered" / "02").write_text("1")
    assert check(r, state, "edited", "02", "01") != 0      # nothing changed since 01
    (r / "b.txt").write_text("new")
    assert check(r, state, "edited", "02", "01") == 0


def test_file_and_count_with_recursive_globs(repo):
    r, state = repo
    (r / "out" / "deep").mkdir(parents=True)
    (r / "out" / "deep" / "x.pdf").write_text("x")
    (r / "out" / "y.pdf").write_text("y")
    assert check(r, state, "file", "out/**/*.pdf") == 0
    assert check(r, state, "count", "2", "out/**/*.pdf") == 0
    assert check(r, state, "count", "3", "out/**/*.pdf") != 0
    assert check(r, state, "file", "nothing/*.pdf") != 0
