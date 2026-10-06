# Architecture, layout and type

Numbers here are the ones that worked, with the reason attached. Change them
knowingly; most were arrived at by changing them unknowingly first.

---

## Architecture

```
  stagecast.toml ── one file: the chapters, their prompts, their checks
         │
         ▼
  ┌─ driver ──────────────────────────────────────────────┐
  │  sends one prompt, waits for the CHECK, never advances │   ← lib/run.sh
  │  until the artefact exists                             │
  └───────────────────────────────────────────────────────┘
         │ one tmux + asciinema session per stage
         ▼
  segments ── seg-001-step01.cast, seg-002-step02.cast, …
         │
         │  restore ─ keep the longest cast per stage
         │  trim    ─ cut from the last substantial output
         │  concat  ─ offset timestamps, join into one
         │  redact  ─ scan for credentials, pad replacements
         ▼
  site ── chaptered player, one brief per chapter
         │
         ▼
  verify ── a real browser clicks every control and reads pixels
```

Two processes, deliberately. The **worker** is an ordinary agent session that
knows nothing about being recorded. The **driver** sends each prompt and judges
each result. Nothing in the worker's prompt mentions sentinels, stages or
recording — which is what lets the recording look like a person using the tool,
because that is all it is.

The driver's only completion signal is the stage's `verify` command. It never
reads the worker's screen to decide anything. See `LESSONS.md § Completion`.

---

## The terminal

```
cols 118   rows 28
```

Readability on a projected slide is governed by **characters per line**, not by
font size in pixels: more columns on the same frame means a narrower glyph, so
the count is chosen first and the frame follows.

The frame shape then has to be derived, not guessed. A monospace cell is taller
than it is wide, and by how much depends on the font and its line height — for
JetBrains Mono rendered by `agg` at these settings, measured off a real frame:

```
  1591 × 1055 px at 100 × 28   →   cell 15.91 × 37.7   →   aspect 0.422
```

So for a 16:9 frame, `cols / rows = 1.778 / 0.422 = 4.21`:

| | frame |
|---|---|
| 100 × 28 | 1.51 — noticeably square |
| 110 × 26 | 1.79 |
| **118 × 28** | **1.78**, and keeps the vertical room |

Measure your own font before trusting these: render one frame, divide.

`--idle-time-limit 2`: a stage that spends forty minutes fetching abstracts plays
back in minutes without speeding up the typing.

---

## Colour

Six values. Nothing has a hue except the terminal's own output.

```
  --ink    #1c1917    body text, active chapter, buttons
  --muted  #57534e    captions, secondary
  --faint  #8c8681    numbers in the rail, hints
  --line   #e7e5e4    every rule and border
  --bg     #ffffff    page, player, letterbox, ::backdrop
  --card   #ffffff
```

No accent colour. Emphasis is weight and space. An accent rule under the title
read as decoration and was removed.

Terminal palette, as an agg theme string — **background, foreground, then ANSI
0–7**:

```
ffffff,1c1917,1c1917,cf222e,1a7f37,9a6700,0969da,8250df,1b7c83,57534e
```

Colour 0 stays dark. See `LESSONS.md § Colour`.

---

## Layout

```
┌──────────────────────────────────────────────────┐
│ header            auto height, min 60px          │
├──────────┬───────────────────────────────────────┤
│ rail     │ screen        1fr                     │
│ 248px    │   player / brief / sheets             │
│          ├───────────────────────────────────────┤
│          │ foot          auto                    │
└──────────┴───────────────────────────────────────┘
```

- `grid-template-rows: auto 1fr` — never a fixed header height
- `grid-template-columns: 248px 1fr` — 150px below 760px wide
- the player fills its cell with `position:absolute; inset:0`, never flex centring
- overlays cover **the screen row only**, so the controls that dismiss them stay
  reachable
- fullscreen changes the viewport and nothing else: same header, same rail

Breakpoints: 1100px drops the header facts, 760px drops the one-line blurb and
narrows the rail. Both exist to prevent the header wrapping, not to rearrange it.

---

## Type

| | size | and why |
|---|---|---|
| brief (the message) | **21px / 1.95 / 62ch** | it is meant to be read standing still; 62 characters is a comfortable measure at that size |
| body, header blurb | 15px / 1.6 | |
| caption under the player | 13px | present but not competing |
| chapter rail | 13px | |
| hints, facts labels | 12px | |
| header title | 16px, 600 | |
| START | 13px, 600, tracking .14em | a button, read as a label |

One family throughout: `ui-sans-serif, -apple-system, "Segoe UI", system-ui`.
Monospace only for paths, filenames and the terminal.

---

## The brief

Every chapter opens on the message it was sent — full bleed, START bottom left —
rather than on a paused terminal.

The reason is not decorative. In the recording the message goes past in seconds
and scrolls away the moment the agent answers, so the one thing that explains the
chapter is the one thing nobody can read. Holding it still also gives the viewer
something to copy.

Emphasis is applied **in the page, never in the file that was sent**. The prompts
go to the agent verbatim; marking them up for display would change what the
recording shows being asked.

---

## Figures, if the run produces any

Landscape A4, `11.69 × 8.27in`, 300 dpi, with a real `pHYs` chunk — a PNG without
one is treated as 72 dpi however many pixels it holds. Give each figure the
proportions its content asks for rather than one canvas for all of them: a
five-row forest plot on 16:9 is mostly white, and a 6×6 matrix on it is a
letterbox.

No baked-in titles. A figure carries data; the caption carries the explanation,
and wherever the figure is published the caption is already there.
