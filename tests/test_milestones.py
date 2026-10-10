"""Issue #9: a milestone gallery read from git, never from the working tree."""
import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

TOML = """
[project]
name = "m"
workdir = "work"
repo = "https://github.com/you/repo"
[[stage]]
id = "01"
name = "Write"
prompt = "x"
verify = "true"
[[milestone]]
id = "first"
title = "First draft"
summary = "What existed after stage 01."
ref = "draft"
chapters = ["01"]
items = [
  { label = "notes", src = "notes.md" },
  { label = "table", src = "data/table.csv" },
  { label = "config", src = "config.toml", kind = "text" },
%s
]
"""


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def build(base, env=None):
    return subprocess.run(["python3", str(ROOT / "tools" / "build_milestones.py"),
                           str(base / "stagecast.toml"), str(base / "site")],
                          capture_output=True, text=True, env=env or os.environ)


@pytest.fixture
def repo(project):
    def make(extra=""):
        base = project(TOML % extra)
        w = base / "work"
        git(w, "init", "-q")
        (w / "data").mkdir()
        (w / "notes.md").write_text("# Notes\n\nAt the tag.\n")
        (w / "data" / "table.csv").write_text("a,b\n1,2\n3,4\n")
        (w / "config.toml").write_text('title = "<at the tag>"\n')
        if shutil.which("pandoc"):
            subprocess.run(["pandoc", "-o", str(w / "protocol.docx"), str(w / "notes.md")], check=True)
        git(w, "add", "-A")
        git(w, "commit", "-qm", "draft")
        git(w, "tag", "draft")
        # the working tree moves on; the gallery must not
        (w / "notes.md").write_text("# Notes\n\nLATER, not at the tag.\n")
        return base
    return make


def test_items_come_from_the_ref(repo):
    base = repo()
    r = build(base)
    assert r.returncode == 0, r.stderr
    ms = json.loads((base / "site" / "milestones.json").read_text())
    assert ms[0]["tree"] == "https://github.com/you/repo/tree/draft"
    assert ms[0]["chapters"] == ["01"]
    items = {i["label"]: i for i in ms[0]["items"]}
    d = base / "site" / "milestones" / "first"
    notes = (d / items["notes"]["view"]).read_text()
    assert "At the tag." in notes and "LATER" not in notes
    assert (d / items["notes"]["download"]).exists()
    table = (d / items["table"]["view"]).read_text()
    assert "<table>" in table and "<td>3</td>" in table
    assert (d / items["table"]["download"]).read_text().startswith("a,b")
    assert "&lt;at the tag&gt;" in (d / items["config"]["view"]).read_text()


def test_a_path_missing_at_the_ref_fails_clearly(repo):
    base = repo('{ label = "gone", src = "not/there.md" },')
    r = build(base)
    assert r.returncode == 1
    assert "not/there.md" in r.stderr and "draft" in r.stderr


def test_a_missing_tool_is_named(repo, tmp_path):
    base = repo()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for tool in ("git", "python3"):
        os.symlink(shutil.which(tool), bin_ / tool)
    r = build(base, env={**os.environ, "PATH": str(bin_)})
    assert r.returncode == 1
    assert "pandoc is not installed" in r.stderr


@pytest.mark.skipif(not all(shutil.which(t) for t in ("pandoc", "soffice", "pdftoppm")),
                    reason="needs pandoc, LibreOffice and poppler")
def test_docx_renders_as_page_images(repo):
    base = repo('{ label = "protocol", src = "protocol.docx" },')
    r = build(base)
    assert r.returncode == 0, r.stderr
    ms = json.loads((base / "site" / "milestones.json").read_text())
    it = next(i for i in ms[0]["items"] if i["label"] == "protocol")
    d = base / "site" / "milestones" / "first"
    view = (d / it["view"]).read_text()
    assert '<img loading="lazy"' in view
    assert list(d.glob("*.pages/p-*.jpg"))
    assert (d / it["download"]).suffix == ".docx" and (d / it["pdf"]).exists()
