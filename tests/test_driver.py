"""Issue #3, #4, #7: what the driver decides, tested without a terminal."""
import argparse
import json
import os
import pathlib
import subprocess
import time

import drive
import sc_config as C
from conftest import ROOT

PANES = pathlib.Path(__file__).parent / "fixtures" / "panes"


def test_options_are_read_from_the_widget_only():
    opts = drive.question_options((PANES / "question.txt").read_text())
    assert len(opts) == 3
    assert "Multivariable Cox" in opts[0]
    assert drive.pick_option(opts, C.RECORDING["recommend"]) == 1


def test_a_list_earlier_in_the_conversation_is_never_an_option():
    opts = drive.question_options((PANES / "question-none.txt").read_text())
    assert [o.split(".", 1)[1].strip() for o in opts] == ["notes.md", "report.txt"]
    # nothing in the widget is recommended: the first option, not the earlier list's
    assert drive.pick_option(opts, C.RECORDING["recommend"]) == 0


def test_no_widget_no_options():
    assert drive.question_options("❯ hello\n1. one\n2. two\n") is None


TOML = """
[project]
name = "d"
workdir = "work"
[recording]
mode = "continuous"
preset = "claude-code"
agent = "claude --dangerously-skip-permissions"
mcp_config = "mcp.json"
[[stage]]
id = "01"
name = "A"
prompt = "prompts/a.txt"
verify = "true"
[[stage]]
id = "02"
name = "B"
prompt = "Just the text"
verify = "true"
drop = ["drops/review.md"]
[[stage]]
id = "03"
name = "C"
prompt = "c"
verify = "true"
"""


def load(base):
    return C.load(base / "stagecast.toml")


def test_prompt_is_a_file_or_the_text(project):
    base = project(TOML)
    (base / "prompts").mkdir()
    (base / "prompts" / "a.txt").write_text("From a file\n")
    cfg = load(base)
    assert [s["prompt_text"] for s in cfg["stages"]] == ["From a file", "Just the text", "c"]


def test_preset_builds_an_isolated_launch(project):
    base = project(TOML)
    cfg = load(base)
    state = drive.State(cfg)
    cmd = drive.agent_command(cfg, state)
    assert cmd.startswith("claude --dangerously-skip-permissions")
    assert "--setting-sources project,local" in cmd
    assert f"--mcp-config {base / 'mcp.json'}" in cmd
    settings = json.loads((state.dir / "session-settings.json").read_text())
    assert settings["theme"] == "light"
    hook = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "turn_ended.py" in hook
    assert cfg["recording"]["turn_signal"] == "hook"


def test_preflight_refuses_an_ancestor_claude_md(project, tmp_path):
    base = project(TOML)
    (tmp_path / "CLAUDE.md").write_text("private rules")
    cfg = load(base)
    why = drive.preflight(cfg)
    assert why and "CLAUDE.md" in why and "allow_ancestor_claude_md" in why
    cfg["recording"]["allow_ancestor_claude_md"] = True
    assert drive.preflight(cfg) is None


def test_preflight_refuses_a_workdir_under_home(project, monkeypatch, tmp_path):
    base = project(TOML)
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    why = drive.preflight(load(base))
    assert why and "$HOME" in why


def test_agent_wrapper_scrubs_the_parents_identity(tmp_path):
    (tmp_path / "recording").mkdir()
    (tmp_path / "agent.cmd").write_text("env")
    env = dict(os.environ, STAGECAST_STATE=str(tmp_path), STAGECAST_SCRUB="1",
               STAGECAST_ENV_KEEP="CLAUDE_CODE_NO_FLICKER", CLAUDECODE="1",
               CLAUDE_CODE_ENTRYPOINT="cli", AI_AGENT="claude", CLAUDE_CODE_NO_FLICKER="1",
               STAGECAST_TAKE="take-001-x.cast")
    out = subprocess.run(["bash", str(ROOT / "lib" / "agent.sh")], env=env,
                         capture_output=True, text=True).stdout
    names = {line.split("=", 1)[0] for line in out.splitlines()}
    assert "CLAUDECODE" not in names and "CLAUDE_CODE_ENTRYPOINT" not in names
    assert "AI_AGENT" not in names
    assert "CLAUDE_CODE_NO_FLICKER" in names and "STAGECAST_STATE" in names
    assert float((tmp_path / "recording" / "take-001-x.cast.t0").read_text()) > 0


def test_drops_are_copied_once_and_rerun_safely(project):
    base = project(TOML)
    (base / "drops").mkdir()
    (base / "drops" / "review.md").write_text("comments\n")
    cfg = load(base)
    st = cfg["stages"][1]
    assert drive.drop_files(cfg, st)
    assert (base / "work" / "inbox" / "review.md").read_text() == "comments\n"
    assert drive.drop_files(cfg, st)          # already there: neither fails nor duplicates
    assert sorted(p.name for p in (base / "work" / "inbox").iterdir()) == ["review.md"]


def test_missing_drop_is_refused(project):
    base = project(TOML)
    cfg = load(base)
    assert not drive.drop_files(cfg, cfg["stages"][1])


def args(**kw):
    return argparse.Namespace(**{"only": None, "start": None, "until": None, **kw})


def test_from_and_until(project):
    cfg = load(project(TOML))
    assert [s["id"] for s in drive.plan(cfg, args(start="02"))] == ["02", "03"]
    assert [s["id"] for s in drive.plan(cfg, args(until="02"))] == ["01", "02"]
    assert [s["id"] for s in drive.plan(cfg, args(only="03"))] == ["03"]


def test_scaffolded_checks_refuse_to_record(project):
    base = project(TOML.replace('verify = "true"\n[[stage]]\nid = "02"',
                                'verify = "TODO: a check"\n[[stage]]\nid = "02"', 1))
    cfg = load(base)
    cfg["recording"]["allow_ancestor_claude_md"] = True
    assert drive.refuse(cfg) == 2
