"""Issue #8: secrets come from the recorded project, every token shape is caught."""
import json
import os
import pathlib
import subprocess

import postprocess
import redact
import sc_config as C
from conftest import ROOT, jsonl, write_cast

ANTHROPIC = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8I9j0_-xyz"
OPENAI = "sk-proj" + "abcdefghijklmnopqrstuvwxyz0123"
GH_FINE = "github_pat_" + "11ABCDEFG0123456789_abcdefghijkl"
GH_CLASSIC = "ghp_" + "A" * 36
SLACK = "xoxb-" + "1234567890-abcdefghij"
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
ENV_VALUE = "project-secret-value-42"
LITERAL = "one-off-literal-9999"
FROM_ENV_VAR = "from-the-REDACT-variable"
SECRETS = [ANTHROPIC, OPENAI, GH_FINE, GH_CLASSIC, SLACK, AWS, ENV_VALUE, LITERAL, FROM_ENV_VAR]

TOML = """
[project]
name = "r"
workdir = "work"
[recording]
mode = "per-stage"
[redact]
literals = ["%s"]
[[stage]]
id = "01"
name = "Leak"
prompt = "go"
verify = "true"
""" % LITERAL


def make(project, monkeypatch):
    base = project(TOML)
    (base / ".env").write_text(f'export PROJECT_KEY="{ENV_VALUE}"\nSHORT=abc\n')
    monkeypatch.setenv("REDACT", FROM_ENV_VAR)
    line = "  ".join(SECRETS)
    st = base / ".stagecast"
    write_cast(st / "recording" / "take-001-01.cast",
               [[0.1, "o", "start\r\n"], [1.0, "o", f"|{line}|\r\n"], [2.0, "o", "end\r\n"]])
    jsonl(st / "session.jsonl", [{"t": 100.0, "event": "start", "take": "take-001-01.cast", "stage": "01"},
                                 {"t": 100.0, "event": "t0", "take": "take-001-01.cast"},
                                 {"t": 100.0, "event": "ready", "take": "take-001-01.cast"}])
    jsonl(st / "markers.jsonl", [{"t": 100.5, "id": "01", "kind": "stage", "take": "take-001-01.cast"}])
    return base, line


def test_every_shape_and_the_projects_env_are_redacted(project, monkeypatch):
    base, line = make(project, monkeypatch)
    # the framework lives elsewhere: its own directory must not be where .env is read
    assert ROOT not in base.parents
    assert postprocess.build(C.load(base / "stagecast.toml"), base / "site") == 0
    published = [base / "site" / "demo.cast", *sorted((base / "site" / "casts").glob("*.cast"))]
    for f in published:
        text = json.loads(json.dumps(f.read_text()))
        for s in SECRETS:
            assert s not in text, f"{s[:12]}… survived in {f.name}"


def test_redaction_keeps_columns(project, monkeypatch):
    base, line = make(project, monkeypatch)
    secrets = redact.load_secrets(base, C.load(base / "stagecast.toml")["redact"])
    out = redact.redact(line, secrets)
    assert len(out) == len(line)
    for s in SECRETS:
        assert s not in out


def test_specific_shape_wins_over_the_general_one():
    assert redact.redact(ANTHROPIC, {}).startswith("[ANTHROPIC-REDACTED]")


def test_short_env_values_are_left_alone(tmp_path):
    (tmp_path / ".env").write_text("A=short\nB=long-enough-value\n")
    assert redact.load_secrets(tmp_path) == {"B": "long-enough-value"}


def test_cli_reads_the_project_env_not_the_framework(project, tmp_path, monkeypatch):
    base, line = make(project, monkeypatch)
    copy = base / "copy.txt"
    copy.write_text(line)
    subprocess.run(["python3", str(ROOT / "tools" / "redact.py"), "--config",
                    str(base / "stagecast.toml"), str(copy)], check=True, capture_output=True,
                   env={k: v for k, v in os.environ.items() if k != "SC_BASE"})
    text = copy.read_text()
    for s in SECRETS:
        assert s not in text


def test_stills_cannot_carry_a_secret(project, monkeypatch):
    base, line = make(project, monkeypatch)
    original = base / ".stagecast/recording/take-001-01.cast"
    out = base / "frame.cast"
    subprocess.run(["python3", str(ROOT / "tools" / "still_frame.py"), str(original), str(out),
                    "5", str(base)], check=True, capture_output=True)
    text = out.read_text()
    assert "start" in text
    for s in SECRETS:
        assert s not in text
    assert "still_frame.py" in (ROOT / "tools" / "stills.sh").read_text()
