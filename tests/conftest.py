import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402


def write_cast(path: pathlib.Path, events, width=80, height=24, **header):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(json.dumps({"version": 2, "width": width, "height": height, **header}) + "\n")
        for e in events:
            f.write(json.dumps(e) + "\n")


def jsonl(path: pathlib.Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def read_cast(path: pathlib.Path):
    lines = path.read_text().splitlines()
    return json.loads(lines[0]), [json.loads(x) for x in lines[1:] if x.strip()]


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project directory outside the framework, with its own config."""
    monkeypatch.delenv("STAGECAST_STATE", raising=False)
    monkeypatch.delenv("REDACT", raising=False)

    def make(toml: str) -> pathlib.Path:
        (tmp_path / "work").mkdir(exist_ok=True)
        (tmp_path / "stagecast.toml").write_text(toml)
        return tmp_path
    return make
