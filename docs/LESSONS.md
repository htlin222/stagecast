# What this framework encodes

Every rule below is here because something broke. The symptom is given first,
because the symptom is what you will meet; the cause is usually somewhere else.

---

## Completion

### A finished stage looks exactly like a working one

Claude Code animates a spinner glyph while it works — and prints one of the same
glyphs in the line it leaves behind when a turn **ends**:

```
✻ Churned for 11m 7s
```

A driver that reads "is it busy?" from the pane therefore waits forever. One
stage sat for 84 minutes with its figures already written.

**Rule.** Never infer completion from the agent's appearance. A stage is finished
when the turn that received its prompt has ended *and* its `verify` command
passes, and at no other time. The agent's screen is not consulted.

### Ask the agent's runtime when a turn ends — do not ask the screen

A Stop hook fires the moment a turn ends. That is the one question the pane
genuinely cannot answer, and a hook answers it exactly.

It is not the same as a sentinel file, and the difference matters on camera. A
sentinel has to be *asked for* — "when you are finished, write `01.done`" — so
the machinery appears in every prompt and the recording reads like a work order
rather than someone using the tool. A hook is configuration: invisible to the
recording, impossible to forget, impossible to write early.

Use both signals, and keep them doing different jobs:

| | answers |
|---|---|
| Stop hook | did the turn **end** |
| `verify` | did it **produce** what it was meant to |

The hook says when to look; the check says whether to advance. A turn that ends
with a failing check is a stage that stopped short — or stopped to ask — and
saying so immediately is better than spending the stall budget to find out.
`hooks/turn_ended.py` is the hook; the claude-code preset registers it for you.

### The hook has to say which prompt the turn answered

A bare "a turn ended" timestamp is not enough once one session spans many
stages. A driver that restarted, a stale turn that ended late, a human typing
into the pane — each produces a turn end that is not the current stage's, and
the driver cannot tell.

**Rule.** The hook walks the transcript back to the most recent human message
and matches it against the stage prompts and `say` texts: `turns.jsonl` records
the id each ended turn answered (or `null`), and `answered/<id>` exists once the
turn that received `<id>` has ended. The driver advances on `answered/<id>`,
never on "some turn ended".

### A passing check does not end the turn

The first version polled `verify` and advanced the moment it passed — while the
agent was still writing the file, or about to revise it. In a continuous session
the next prompt was then pasted into a busy one.

**Rule.** With a hook, completion is both signals: the turn ended, the pane
settled, and the check passes. A check that passes mid-turn changes nothing;
waiting costs only the rest of that turn. Without a hook (`turn_signal =
"settle"`) a passing check plus a still pane is the best available.

### The check must be able to fail

A verify that was already true before the stage ran will pass on a stage that did
nothing. Write checks against a plausible half-finished attempt.

In a repository with history this is harder than it sounds: `git tag | grep -q
review` or `ls output/*.pdf` passes on artefacts from an earlier chapter or an
earlier take. The old up-front "already satisfied → skip" shortcut made that
worse — it skipped the stage before the agent saw it — and is now opt-in
(`skip_if_satisfied`).

**Rule.** A check must be scoped to after its chapter started.
`stagecast-check saved 05 review` accepts only a tag or commit made after stage
05's prompt was sent; `stagecast-check edited 06 05` only a repository that
changed since 05's turn ended; `answered 05` only the turn that received 05.

### A restart must not send anything twice

Re-running after an interruption re-sent a prompt the agent had already
received, which put the message in the recording twice; and re-verifying every
earlier stage against a repository later stages had changed failed checks like
"file X does not exist yet" that had been true at the time.

**Rule.** Record what happened, and trust the record. `markers.jsonl` says what
was sent, `answered/` what was answered, `verified/` what passed. `record` skips
verified stages without re-running their checks, and never re-sends a prompt
already sent in the live session — it waits on it, and presses Enter if the
driver died between the paste and the Enter.

### The check must ask for what the prompt asked for

Seven separate stalls in one project came from the same mismatch: the prompt said
"write the protocol", the check demanded `pico.yaml`; the prompt said "render the
manuscript", the check demanded `index.html` and Quarto had written
`_output/manuscript.html`. Every one of them was a stage that had finished.

**Rule.** If the prompt does not name a filename, the check must not require one.
Match on shape — `ls 09_qa/grade*.*` — or name the artefact in the prompt. Keeping
them in one file, as `stagecast.toml` does, makes the drift visible.

---

## Recording

### The prompt has to arrive intact, and be legible afterwards

Three separate things, each of which was wrong once.

**It must arrive as it was written.** `tmux send-keys -l` swallows newlines, so a
multi-paragraph prompt lands as one run-on line. Send it with a bracketed paste —
`load-buffer` then `paste-buffer -p` — and give it a second before Enter.

**It is in the cast, even when it looks like it is not.** Claude Code shows
`Pasting text…` while the paste lands and renders the whole message immediately
after. Searching a finished cast for a phrase from the prompt will find it. The
problem is never that it was lost.

**It is unreadable in passing.** At playback speed it goes by in seconds, and the
moment the agent answers it scrolls away — so the one thing that explains a
chapter is the one thing nobody can read. Hence the brief: every chapter opens on
its message, full bleed, with START handing over to the player. It also gives a
viewer something to copy, which for a demo that is teaching a method is worth
more than the video.

**Emphasis goes in the page, never in the file that was sent.** The prompts reach
the agent verbatim; adding `**bold**` for display would mean the recording shows
something other than what was asked. `stagecast.toml` carries the phrases to
emphasise; the renderer matches them.

One more, learned the expensive way: keep the machinery *out* of the prompt. An
early version appended "when you are finished write `01.done`" to every message,
and the result read like a work order in every chapter. The turn-end signal
belongs in a hook, the completion test belongs in `verify`, and the prompt should
contain nothing a person would not have typed.

### Record one segment per stage — unless the target is an agent

`per-stage` opens a fresh session for every stage: a repair costs one chapter,
and for a target that is not an agent (the demo's `worker.sh`) that is all
upside.

For an agent it is N cold starts. Stage N has none of stages 1..N-1 in context,
so every prompt restates everything and stops reading like what a person would
type; every chapter opens on an empty screen and ends on a teardown — the
alt-screen exit, a cleared terminal — instead of the answer. Half the lint rules
exist because of that teardown.

**Rule.** `mode = "continuous"` for an agent: one session, each stage the next
message, chapter boundaries kept as timestamps and written into the cast as
asciinema markers. `stagecast finish` stops asciinema with SIGINT *before*
killing tmux, so the last frame is the agent's final answer.

### A skipped stage used to overwrite the segment it skipped

The recorder retired the previous take before each attempt; when the driver then
found the stage already complete and skipped it, the session still opened and
closed — leaving a one-second stub where the real recording was.

**Rule.** Decide to skip *before* opening a session. Verified stages are skipped
from `verified/`, and no session is opened for them.

### Dead air is not idle

`asciinema --idle-time-limit` compresses silence, but a stalled stage is not
silent: a spinner is an event. One segment ran 5,552 seconds of which 674 were
work. And a long working stretch is not silent either: an agent working for
twenty minutes emits output constantly, so it played back at 1x.

**Rule.** End each take at its last ended turn plus a few seconds (or where the
driver began the teardown), and time-lapse the middle of every turn: the first
20 s and the last 15 s at 1x, the rest at 8x.

### Record raw time; compress afterwards

Compressing at record time (`--idle-time-limit`, or the `idle_time_limit` in a
user's `~/.config/asciinema/config`) breaks the mapping from cast time to wall
clock. The hook's turn ends and the driver's send times then cannot be placed in
the cast, and chapter markers computed from them land minutes off in a long run.

**Rule.** `asciinema rec -i 86400`, and every change of time in one function in
`tools/postprocess.py`, applied to events, markers and chapter ends alike. Take
cast time zero from the recorded process itself (`lib/agent.sh`): the driver's
clock starts before asciinema is up, and a cut computed from it lands that much
late — which is how a quit once got into the published cast.

### Never compress twice

`idleTimeLimit: 2` in the player, on top of a post-processed cast, silently undid
the eight-second answer hold and made player time drift from `chapters.json`: by
chapter ten, a seek to a marker landed on the previous chapter.

**Rule.** The published header has no `idle_time_limit`, and the player is never
given `idleTimeLimit`.

### A short answer flashes by

A turn that ends on a brief answer is followed almost at once by the next
prompt; on playback the answer was on screen for two seconds before the next
brief covered it.

**Rule.** The gap that contains a turn end plays as `hold` seconds (8), and the
player pauses on each chapter's last frame.

### The agent will stop and ask

Pre-empting every decision in the prompt is not enough, and over-specified
prompts bring back the work-order look. An AskUserQuestion widget does not end
the turn, so the Stop hook never fires and the run waits out the whole stall
budget; a question asked in prose ends the turn with a failing check.

**Rule.** Opt in to `answer_questions = "recommended"`: the driver reads the
options *from inside the widget only* — up from "Enter to select" to the nearest
rule line, so a numbered list earlier in the conversation is never taken for
one — waits a few seconds so the viewer can read the question, and picks the
option marked Recommended, else the first. For prose questions, the run stops
with exit 3; answer with `stagecast say "…"`, which is recorded, logged, and
shown on the page as an interjection that was not in the script — the
published page is honest about what was typed live. When a prompt is later
revised to fold that answer in, `recorded = "…"` on the stage keeps what was
actually sent.

### The paste has to land in the input box

In vim mode, the Escape sent to clear a TUI's pending state leaves the input in
NORMAL, where a paste is a string of commands; and an Enter can be swallowed
while the TUI re-renders.

**Rule.** If the pane shows `-- NORMAL --`, send `i` first. After Enter, if the
prompt's first characters are still in the *last* `❯` line, press Enter once
more — and never on an empty box.

### Keep the recorder out of the recording

Claude Code reads `CLAUDE.md` from every ancestor directory and the user's own
settings, hooks and MCP servers; a recording started from inside another Claude
Code session also inherits its `CLAUDE*` variables. All of it shaped what the
viewer saw — and an `@import` outside the project opened the session on a dialog
the readiness loop did not know, so the first stage sat until the wait expired.

**Rule.** `preset = "claude-code"`: `--setting-sources project,local`, a
generated `--settings` (light theme, the Stop hook), an env scrub, the trust,
bypass and import dialogs answered and folded into t = 0, and a refusal to
record in a workdir with an ancestor `CLAUDE.md` — anything under `$HOME`
included.

---

## Credentials

### A terminal recording is a credential disclosure channel that looks like nothing

Nothing in a pipeline writes a key to a file. It passes one to a process — and
the terminal is watching. An agent calling an API with `?api_key=…` puts the key
on screen, and the cast keeps it. A real key was found in two casts minutes
before they would have been pushed to a public repository.

**Rule.** Scan before every publish, never as a one-off (`tools/redact.py`), in
the one post-processing pass every export goes through — stills included.
Replace with a marker **padded to the original length**: a cast is a stream of
terminal output, and a replacement of a different length shifts every column
after it on that line.

### Read the secrets from the project being recorded

The redactor read `.env` from beside its own source — the stagecast checkout —
so for every real project it printed "no .env" and let the project's secrets
through, unless one happened to match a token shape. And the shapes missed
Anthropic keys (`sk-ant-…`: the `-` after `ant` broke the character class),
fine-grained GitHub tokens and Slack tokens.

**Rule.** `.env` comes from the directory of `stagecast.toml`, plus
`[redact] env_files`, `[redact] literals` and `$REDACT`; and `tests/` holds a
recording with one secret of every shape, asserted gone after `build`.

---

## Colour

### The ground is white, and there is no dark version

The point of a light recording is that frames go onto slides, and a slide is
white. A tinted page draws a visible rectangle around the terminal; a page that
follows the system into dark mode puts a black surround on a white screen.

**Rule.** One ground, `#ffffff`, everywhere — page, player, letterbox,
`::backdrop`. No `prefers-color-scheme` block. Verify by sampling pixels
(`tools/verify_background.py`), not by trusting the theme string.

### ANSI colour 0 is black, not the background

Setting palette entry 0 to white — because "the background is white" — makes
every glyph the TUI draws in colour 0 invisible. Colour 0 is how a terminal
application writes dark text on a coloured panel.

```
  wrong   ffffff,1c1917,ffffff,…      background, foreground, THEN colour 0
  right   ffffff,1c1917,1c1917,…
```

The background check cannot see this: the background is perfectly white and only
the text is gone. `tools/verify_contrast.py` looks for the symptom instead — a
coloured panel that is mostly near-white inside.

### An agent's own message may be drawn as a dark slab

Claude Code renders the message you sent as 256-colour 231 on 237 — near-white on
dark grey. Correct on a dark terminal; on a white page it is a black bar through
the middle, and anywhere colour 231 appears outside that block it is white text
on white. The site template restyles both.

---

## Layout

### A centred flex child has no height, and clips its own top

Both halves of this cost a day.

```css
display:flex; align-items:center;   /* the child resolves to height:auto = 0 */
```

A player sized with `fit:"both"` measured zero and drew nothing — a blank panel
that looked exactly like a broken embed. And when the child *is* taller than a
scrollable container, `align-items:center` pushes its top above the container
with no way to scroll back: the opening lines are gone, which looks exactly like
the header covering them.

**Rule.** Fill with `position:absolute; inset:0`. Centre with `margin:auto`.

### A fixed header row overflows onto the row below

Pinned at 60px it is right until the window narrows and the header wraps.

**Rule.** `grid-template-rows: auto 1fr`.

### An overlay must not cover the control that dismisses it

A brief covering the whole of `main` also covered the buttons underneath it.
Found by a browser that could not click a button it could see.

---

## Verification

### A status code proves a file was served, not that anything rendered

Three defects shipped green through status checks and CSS greps: a player that
drew nothing, a message block that was a black slab, and near-white text that was
invisible.

**Rule.** Drive the published page in a real browser and look at the pixels
(`tools/verify_site.py`). Click every control. A button you can see is not a
button you can press. Wait for the terminal to be drawn rather than for a fixed
number of seconds — a fixed wait is a race against the download — and read the
expected chapter count from the page, never from a constant.

### A template the ignore file swallowed

A bare `site/` rule, meant for build output, also matched the framework's own
template directory, so the template was never committed and `build` failed on
every fresh clone — while every check on the author's machine passed.

**Rule.** Anchor ignore rules to what they mean (`/demo/site/`), keep the
template where no output rule can reach it (`templates/`), and let CI build the
demo from a committed recording.

### `poster` breaks seeking

With `poster` set, `seek({marker: i})` then `play()` drew only the bytes after
the marker: no header, no statusline. The first chapter looked fine, which is
why it took a while.

**Rule.** Never pass `poster`. Each chapter cast opens on a full screen
snapshot, and `verify_site.py` asserts the first row is not blank after a jump.

### Assert on content, not only on structure

A publish of ten one-second stubs passed every control assertion, because the
controls worked perfectly on top of an empty recording.

**Rule.** Assert that each chapter is longer than a floor. Emptiness is a
failure mode, not an edge case.

---

## Process

### Never edit a script while it is running

Bash reads a script lazily. Editing one mid-run corrupts execution, and it dies
without a message. This happened twice, and both times the diagnosis went
somewhere else first.

**Rule.** A long run owns its scripts. Change them between runs, or put the fix
in a file the run reads fresh each time.

### Detach properly, or the run dies with the session

`nohup … & disown` does not protect against a signal sent to a process group, and
a background job of an agent session is in that group. Two unrelated processes
dying at the same moment is a group signal, not a bug in either.

**Rule.** `os.setsid()` in its own session (`lib/detach.sh`).

### Clear the previous output inside the build, not by hand

`rip` takes no `-r` and no `-f`. `rip -rf dir` exits with a usage error and the
directory survives — silently, for an afternoon. Stale pages are
indistinguishable from fresh ones.

**Rule.** The first step of any build is removing what the last one made.

### Look at all of it at once

A fault obvious across eighteen slides is invisible slide by slide. Contact
sheets, not spot checks.

## Driving a target that is not Claude Code

Every one of these was found by looking at the recording. The checks passed
throughout — the files were written, the stages advanced — so nothing else could
have caught them. The recording is the artefact; a green run that produces an
ugly one has failed.

### What you send to leave is part of the target, not of the driver

The teardown sent `Escape` then `/exit`, which is how Claude Code is asked to
quit. Sent to a plain shell, `ESC` followed by `/` is readline's **filename
completion**: it completed to the one file in the working directory and ran it,
leaving `bash: notes.md: command not found` at the end of the recording.

The same `Escape`, sent *before* the prompt to clear a TUI's pending state, met
the paste's own `\e[200~` and made readline insert the marker literally —
`bash: [200~printf: command not found`. Both marks that had been blamed on
bracketed paste came from the Escape.

**Rule.** `clear_key` and `quit` are per-target, like `agent`. One setting, one
meaning: `bracketed_paste` says whether to wrap the text, and nothing else.
Diagnosing the symptom (turning the markers off) left the real cause in place.

### `:-` treats empty as unset

`${SC_CLEAR:-Escape}` substitutes the default when the variable is **empty**, not
only when it is missing — so a target that asked for no clear key got `Escape`
anyway. `${SC_CLEAR-Escape}` distinguishes the two.

**Rule.** When empty is a legitimate value, use `-`, not `:-`, and test both the
unset and the empty case.

### `has-session` without `-t` asks about the whole socket

A wait loop on `tmux -L sock has-session` never finished: unrelated sessions were
living on that socket, so the answer was always yes. `lib/run.sh` passes `-t`;
the loop that hung did not.

**Rule.** Always name the session. A wait that cannot fail is not a wait.

### BSD grep has no `-P`

`grep -P "^$ID\t"` printed a usage error on every stage. A fallback hid the
consequence, so it ran for weeks as noise nobody read. A literal tab needs no
PCRE: `grep "^$ID$(printf '\t')"`.

**Rule.** GNU-only flags do not belong in a tool people run on macOS.

### A feature that fails by doing nothing must be made to speak

Emphasis matched case-sensitively and in silence: the list said `the check reads
it back`, the prompt said `The check reads it back`, and nothing bolded. Nothing
was wrong enough to report.

**Rule.** Matching ignores case, and `build` warns when an emphasis phrase
appears in no prompt. The first thing the warning found was a real dead phrase.

### A smoke test needs the guard it cannot satisfy

The empty-chapter floor refused to publish the three-stage demo, correctly: its
chapters are seconds long. A hard-coded 30 made the framework unable to
demonstrate itself.

**Rule.** `min_chapter_seconds`, defaulting to 30. A guard worth having is worth
configuring rather than removing.

### A check passing is not the output stopping

The check fires the moment the artefact exists. The target is still printing
what it did — so the teardown's keystrokes were spliced into the stream and the
recording ended on `exitwrote 4 lines`. The stage was correct; the recording was
not, and the recording is what ships.

**Rule.** Wait for the pane to hold still (`SC_SETTLE`, default 3s unchanged)
before asking the target to leave.

## Lint the recording, not only the page

Everything in the section above passed its stage check and was found by a person
watching the playback. That is not a check — it does not survive the next person,
or the next run. `tools/lint_casts.py` makes each one deterministic:

| tier | meaning | on a hit |
|---|---|---|
| **leak** | only the harness can produce this shape | refuse to publish |
| **noise** | the target produced it; a real session may do so legitimately | report, refuse only under `[lint] strict` |

Each message names the setting that is wrong, not just the symptom. A lint
nobody can act on gets switched off.

### A lint needs a recording that is known to be broken

`tests/fixtures/` holds the defective casts verbatim, and `tests/test_lint.sh`
asserts the lint fails on them, passes on a clean one, and **names each shape
separately** — a lint that catches one of four would otherwise look like a pass.

It earned this three times in one sitting, and each time the fault was in what
was written to catch the bug rather than in the bug:

- the bare-ESC fixture used `ESC [ w`, which is a valid CSI a terminal consumes;
  the real bytes were `ESC` then `w`, which is why the screen showed `^[wrote`
- the bare-ESC rule excluded only `[()=>`, so it fired on every recording, because
  bash sets the window title with OSC — `ESC ]`
- the spliced-quit rule had a lookbehind rejecting anything after whitespace,
  which rejected the line break, so **the recordings that had the defect were
  reported clean**

**Rule.** A check that has never failed on known-bad input has not been tested.
Without the fixture, a lint that matches nothing and a lint that found nothing
are the same output.

### Scaffold everything except the check

`stagecast init` writes a config from a directory of prompts: stage ids and
names off the filenames, every other field a `TODO`. It deliberately cannot
write `verify`. A check guessed from a filename would pass for the wrong reason,
and a stage that advances on the wrong reason is the single failure this whole
framework exists to prevent.

**Rule.** `record` refuses while any check is still a TODO, and names the stages.
Scaffolding that quietly produced a plausible check would be worse than none.

