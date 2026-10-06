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
