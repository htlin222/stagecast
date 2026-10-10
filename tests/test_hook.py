"""Issue #3: the Stop hook records which prompt the ended turn answered."""
import json
import os
import subprocess

from conftest import ROOT

HOOK = ROOT / "hooks" / "turn_ended.py"


def entry(text=None, blocks=None, **kw):
    content = text if text is not None else blocks
    return {"type": "user", "message": {"role": "user", "content": content}, **kw}


def run(tmp_path, transcript, prompts, said=()):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "prompts.json").write_text(json.dumps(prompts))
    if said:
        (state / "said.jsonl").write_text("".join(json.dumps(d) + "\n" for d in said))
    tr = tmp_path / "t.jsonl"
    tr.write_text("".join(json.dumps(e) + "\n" for e in transcript))
    subprocess.run(["python3", str(HOOK)], input=json.dumps({"transcript_path": str(tr), "cwd": str(tmp_path)}),
                   text=True, check=True, env=dict(os.environ, STAGECAST_STATE=str(state)))
    turns = [json.loads(x) for x in (state / "turns.jsonl").read_text().splitlines()]
    return state, turns[-1]["id"]


def test_matches_the_latest_human_message(tmp_path):
    tr = [entry("Do the first thing"), {"type": "assistant", "message": {"content": "ok"}},
          entry("Do the second thing\nwith more detail"),
          entry(blocks=[{"type": "tool_result", "content": "x"}]),          # not human text
          entry("<command>meta</command>", isMeta=True),                      # not human either
          entry("summary of the conversation", isCompactSummary=True)]
    state, hit = run(tmp_path, tr, {"01": "Do the first thing", "02": "Do the second thing\nwith more detail"})
    assert hit == "02"
    assert (state / "answered" / "02").exists() and not (state / "answered" / "01").exists()
    assert (state / "fp-02").exists() and (state / "turn-ended").exists()


def test_a_turn_answering_no_known_prompt_is_null(tmp_path):
    state, hit = run(tmp_path, [entry("something typed by hand")], {"01": "Do the first thing"})
    assert hit is None
    assert not list((state / "answered").iterdir())


def test_interjections_match_and_repeats_go_to_the_unanswered_one(tmp_path):
    said = [{"id": "say01", "text": "yes, go on"}, {"id": "say02", "text": "yes, go on"}]
    state, hit = run(tmp_path, [entry("yes, go on")], {"01": "x"}, said)
    assert hit == "say02"
    state, hit = run(tmp_path, [entry("yes, go on")], {"01": "x"}, said)
    assert hit == "say01"


def test_legacy_shell_hook_still_works(tmp_path):
    state = tmp_path / "state"
    subprocess.run(["bash", str(ROOT / "hooks" / "turn-ended.sh")], input="{}", text=True, check=True,
                   env=dict(os.environ, STAGECAST_STATE=str(state)))
    assert (state / "turn-ended").exists()
