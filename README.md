# stagecast

Record an agent doing a long job, and publish it as something people can
actually watch.

Not a screen recorder. The problem it solves is that a three-hour agent session
is unwatchable and unverifiable: the interesting parts are minutes apart, the
prompts scroll away before anyone can read them, and nothing distinguishes a
stage that finished from a stage that *said* it finished.

```
stagecast.toml ──▶ record ──▶ build ──▶ a chaptered site
```

One file describes the run. Each stage is a chapter, each chapter opens on the
message it was sent, and **a stage advances only when its check passes** — never
because the agent looked finished.

---

## Why a check, and not the agent's word

```toml
[[stage]]
id     = "06"
name   = "Network model"
prompt = "prompts/06-nma.md"
stall  = "130m"
verify = "test -d 06_analysis/tables && ls 06_analysis/figures/*.png >/dev/null 2>&1"
```

`verify` runs with the working directory at the project and decides on its own
whether the stage is done. That is the whole discipline. An agent can report work
it did not do — it is a thing agents do — and a recording of one doing it is
worth nothing. A check against the artefact cannot be talked round.

It also removes the problem that costs the most time in practice: telling a
finished stage from a working one. Claude Code animates a spinner while it works
and prints one of the same glyphs in the line it leaves when a turn **ends**, so
a driver reading the screen waits forever. One stage sat for 84 minutes with its
output already on disk. See [docs/LESSONS.md](docs/LESSONS.md).

---

## Use

```sh
brew install asciinema tmux        # and agg, if you want GIFs
uv tool install playwright         # for `stagecast verify`

mkdir my-run && cd my-run
mkdir prompts && $EDITOR prompts/01-….md   # one file per chapter, in order
stagecast init                     # scaffolds stagecast.toml from them
$EDITOR stagecast.toml             # fill in the checks — see below
stagecast record                   # drive every stage that is not verified yet
stagecast build                    # post-process, redact, lint, render
stagecast verify https://…         # drive the published page in a browser
```

`init` reads the stage id and name off each filename and writes everything but
one field. `verify` is left as `TODO`, and `record` refuses to start while any
remain — a check inferred from a filename would pass for the wrong reason, which
is worse than not having one. That field is the whole discipline, so it is the
one you write yourself.

`build` writes `site/` — a single page, one cast per chapter, the whole cast as
`demo.cast`, and the prompts as data. Host it anywhere static.

### Recording Claude Code

```toml
[recording]
mode             = "continuous"    # one session; chapters are markers, never /exit
preset           = "claude-code"   # isolate the recorded session from yours
agent            = "claude --dangerously-skip-permissions"
answer_questions = "recommended"   # take the (Recommended) option of an AskUserQuestion
```

- **`mode = "continuous"`** opens one session and sends each stage as the next
  message in the same conversation. Every chapter keeps the context of the ones
  before it, and the recording ends on the agent's last answer rather than on a
  teardown. `per-stage` (the default) opens a fresh session per stage: right for
  a target that is not an agent, and a repair costs one chapter.
- **`preset = "claude-code"`** launches with `--setting-sources project,local`
  and a generated `--settings` file (light theme, the Stop hook registered), so
  your `~/.claude` settings, hooks and MCP servers stay out of the recording;
  scrubs inherited `CLAUDE*` / `AI_AGENT` variables when you record from inside
  another Claude Code session; answers the trust, bypass and external-import
  dialogs; and refuses a workdir with an ancestor `CLAUDE.md` (anything under
  `$HOME` included) unless `allow_ancestor_claude_md = true`. Use a workdir
  such as `/Users/Shared/<name>` or `/srv/<name>`.
- A stage advances only when **the turn that received its prompt has ended**
  (the Stop hook, `hooks/turn_ended.py`) **and its `verify` passes**. A turn that
  ends with a failing check stops the run with exit 3. Answer it with
  `stagecast say "…"` — recorded, and shown on the page as an interjection that
  was not in the script — then `stagecast record` again. Nothing already sent is
  sent twice, and verified stages are not re-checked against today's repository.
  Without the preset, register `hooks/turn_ended.py` yourself and set
  `turn_signal = "hook"`; otherwise a stage advances when its check passes and
  the pane holds still.
- `stagecast finish` stops asciinema before the session, so the last frame is
  the answer. `stagecast status` shows what is verified, sent and next;
  `--from ID` / `--until ID` / `--only ID` narrow a `record`.

Checks can be scoped to the chapter with `stagecast-check`, which is on `PATH`
while `verify` runs — in a repository with history, `git tag | grep -q review`
passes on a tag from an earlier chapter:

```toml
verify = "stagecast-check saved 05 review"        # a tag/commit made AFTER 05 was sent
verify = "stagecast-check edited 06 05"           # the repo changed since 05's turn ended
verify = "stagecast-check count 3 'output/**/*.pdf'"
```

A stage can also `drop = ["drops/review.md"]`: copied into `<workdir>/inbox/`
just before its prompt is sent, to stand in for something that arrived from
outside. `[[milestone]]` tables build a gallery of what each stage produced,
read from the git tag it was saved as (see `tools/build_milestones.py`), and
`stagecast build --prompts-md PROMPTS.md` writes the prompts as a script.

### Try it in five minutes

```sh
cd demo && ../stagecast all        # three real stages, about a minute
cd site && python3 -m http.server  # then open localhost:8000
```

The demo drives a plain `bash` rather than an agent, so it needs no API key and
nothing is mocked: each stage writes a file and the next stage's check reads it
back. It is the same machinery a three-hour run uses, small enough to watch.

![the chapter brief, and the recording underneath](docs/screenshot-brief.png)

Every chapter opens on the message it was sent — full width, keywords bold —
and hands over to the player on START. Playback stops on the chapter's last
frame; Space is the one key for "next step" (play, pause, resume, next chapter),
and "Previous answer" lifts the brief to reread the last chapter's ending.

---

## What it does between record and publish

Recordings are made with raw wall-clock timing, so the times the driver and the
Stop hook logged line up with the cast. `build` then does everything that
changes time in one pass (`tools/postprocess.py`):

| | |
|---|---|
| **time** | t = 0 where the session was ready, so startup dialogs fold away. Idle gaps cap at 2 s; inside each turn the first 20 s and the last 15 s play at 1x and the middle at 8x, so the message going in and the answer coming out stay readable; every finished answer is held 8 s. All of it under `[postprocess]` |
| **end** | each take ends at its last turn plus a few seconds, or where the driver began the teardown — never on a quit. One stalled segment once ran 5,552 seconds of which 674 were work |
| **redact** | every event, against the recorded project's `.env`, `[redact] literals`, `$REDACT`, and token shapes (Anthropic, OpenAI, GitHub, Slack, AWS), replaced with a marker **padded to the original length**. A real key was found in two casts minutes before they would have gone to a public repository |
| **chapter** | one cast per chapter, opening on the screen as it stood when the chapter began — replayed through a headless terminal, not concatenated — so the page loads one chapter at a time, however long the run |
| **lint** | scan the recording for shapes only the harness can leave — paste markers, a stray ESC, a quit spliced into output that had not finished. Each one passed its stage check and was found by eye; `tests/` keeps a known-broken cast so the lint cannot quietly stop matching |
| **render** | refuse to publish a chapter under `min_chapter_seconds` (30 by default), and fill the template: chapter briefs, a pause on each chapter's last frame, the message as text |

Emptiness is a failure mode, not an edge case: a publish of ten one-second stubs
once passed every control assertion, because the controls worked perfectly on top
of an empty recording.

---

## The look is part of it

White, and no dark version. Frames from these recordings go onto slides, and a
slide is white — so a tinted page draws a rectangle around the terminal and a
dark one puts a black surround on a white screen. One ground, `#ffffff`, from the
page through the player to the fullscreen backdrop.

Six colours, no accent. Emphasis is weight and space.

The terminal is **118 × 28**, which is 16:9 once the cell aspect is measured
rather than assumed. Chapter briefs are 21px over 62 characters, because they are
meant to be read standing still.

Full specification, with the reasoning: [docs/DESIGN.md](docs/DESIGN.md).

---

## Where it came from

Recording a ten-stage systematic review and meta-analysis end to end
([meta-pipe](https://github.com/htlin222/meta-pipe)), over three days, badly,
several times. Every rule in [docs/LESSONS.md](docs/LESSONS.md) is there because
something broke — including the ones that look obvious.

The two that cost the most:

- **A status code proves a file was served, not that anything rendered.** Three
  defects shipped green through status checks and source greps: a player that
  drew nothing, a message block that was a black slab, and near-white text that
  was invisible on white. `stagecast verify` drives the real page in a real
  browser and clicks every control, because a button you can see is not a button
  you can press.

- **Check and prompt must come from one place.** Seven stalls in one project were
  the same mismatch — the prompt said "write the protocol", the check demanded a
  filename nobody had asked for. Keeping both in `stagecast.toml` is not tidiness;
  it is what makes the drift visible.

MIT.
