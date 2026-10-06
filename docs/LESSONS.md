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
when its `verify` command passes, and at no other time. `stagecast` polls the
check; the agent's screen is not consulted.

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
`hooks/turn-ended.sh` is the hook; registering it is three lines of settings.

### A passing check ends the wait immediately

Waiting out a quiet period "to be safe" after the check already passes buys no
information and costs the grace period on every stage — close to four hours
across ten.

**Rule.** Check passes → done, now. The quiet period applies only when the agent
is silent *and* the check is failing, which is the one case where work may still
be in flight in a background shell.

### The check must be able to fail

A verify that was already true before the stage ran will pass on a stage that did
nothing. Write checks against a plausible half-finished attempt.

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

### Record one segment per stage

A repair costs one chapter instead of the whole take. Segments are joined at
build time, so the result is still one continuous recording, and the joins
double as chapter marks.

### A skipped stage will overwrite the segment it skipped

The recorder retires the previous take before each attempt. If the driver then
finds the stage already complete and skips it, the session still opens and
closes — leaving a one-second stub where the real recording was.

**Rule.** Keep the longest cast per stage (`tools/restore_real.py`), and never
assume a file in place is the good one.

### Dead air is not idle

`asciinema --idle-time-limit` compresses silence, but a stalled stage is not
silent: a spinner is an event. One segment ran 5,552 seconds of which 674 were
work.

**Rule.** Trim from the last substantial output, not from the last event
(`tools/trim_casts.py`). "Substantial" means a few hundred bytes; a spinner frame
is a handful.

### The agent will stop and ask

It cannot be answered, so it waits until the stall timer fires — ninety-five
minutes, in one case, because the prompt had not said which project to work in.

**Rule.** Every prompt names its working directory. Every prompt states the
decisions that would otherwise be questions.

---

## Credentials

### A terminal recording is a credential disclosure channel that looks like nothing

Nothing in a pipeline writes a key to a file. It passes one to a process — and
the terminal is watching. An agent calling an API with `?api_key=…` puts the key
on screen, and the cast keeps it. A real key was found in two casts minutes
before they would have been pushed to a public repository.

**Rule.** Scan before every publish, never as a one-off (`tools/redact.py`).
Replace with a marker **padded to the original length**: a cast is a stream of
terminal output, and a replacement of a different length shifts every column
after it on that line.

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
button you can press.

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

