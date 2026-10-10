"""Issue #1: a fresh clone can build the demo; the template is tracked."""
import json
import os
import shutil
import subprocess

from conftest import ROOT


def test_the_template_is_tracked():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "templates/player.html"],
                         capture_output=True, text=True).stdout
    assert out.strip() == "templates/player.html"
    ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "templates/player.html"])
    assert ignored.returncode == 1


def test_demo_builds_from_the_committed_recording(tmp_path):
    demo = tmp_path / "demo"
    shutil.copytree(ROOT / "demo", demo, ignore=shutil.ignore_patterns(".stagecast", "site"))
    shutil.copytree(ROOT / "tests" / "fixtures" / "demo-state", demo / ".stagecast")
    r = subprocess.run([str(ROOT / "stagecast"), "build", "--prompts-md", "PROMPTS.md"], cwd=demo,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    site = demo / "site"
    html = (site / "index.html").read_text()
    assert "{{" not in html
    chapters = json.loads((site / "chapters.json").read_text())
    assert [c["id"] for c in chapters] == ["01", "02", "03"]
    assert all((site / c["cast"]).exists() for c in chapters)
    assert "Write a notes file" in (demo / "PROMPTS.md").read_text()


def test_verify_site_has_no_project_baked_in():
    src = (ROOT / "tools" / "verify_site.py").read_text()
    assert "meta-pipe" not in src and "== 10" not in src
