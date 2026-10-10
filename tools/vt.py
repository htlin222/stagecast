"""The screen at a moment in a cast, as a few bytes that redraw it.

A chapter cast has to open on whatever the screen showed when the chapter
began. Concatenating every earlier byte would make the last chapter as big as
the whole recording; replaying them through a headless terminal emulator and
serialising the *screen* instead costs one screenful.
"""
from __future__ import annotations

import pyte
from pyte import graphics as G

RESET = "\x1b[0m\x1b[2J\x1b[3J\x1b[H"

_FG = {v: k for k, v in {**G.FG_ANSI, **G.FG_AIXTERM}.items() if v != "default"}
_BG = {v: k for k, v in {**G.BG_ANSI, **G.BG_AIXTERM}.items() if v != "default"}
# pyte keeps a 256-colour index as its RGB. Map it back, preferring 16–255 where
# an RGB is in both halves: SGR 30–37/90–97 survive as names anyway, so a hex
# equal to ffffff almost always came from 38;5;231, not 38;5;15 — and the theme
# repaints 0–15, which would turn Claude Code's white-on-237 into grey.
_IDX: dict[str, int] = {}
for _i in [*range(16, 256), *range(16)]:
    _IDX.setdefault(G.FG_BG_256[_i], _i)


def _colour(value: str, names: dict[str, int], base: int) -> str:
    if value == "default":
        return ""
    if value in names:
        return str(names[value])
    if value in _IDX:
        # Back to the palette index, so the player's theme still applies to it.
        return f"{base};5;{_IDX[value]}"
    try:
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return ""
    return f"{base};2;{r};{g};{b}"


def sgr(ch) -> str:
    parts = []
    for flag, code in (("bold", "1"), ("italics", "3"), ("underscore", "4"),
                       ("blink", "5"), ("reverse", "7"), ("strikethrough", "9")):
        if getattr(ch, flag, False):
            parts.append(code)
    fg = _colour(ch.fg, _FG, 38)
    bg = _colour(ch.bg, _BG, 48)
    parts += [p for p in (fg, bg) if p]
    return ";".join(parts)


def _blank(ch) -> bool:
    return ch.data in (" ", "") and ch.bg == "default" and not ch.reverse and not ch.underscore


def snapshot(screen: pyte.Screen) -> str:
    out = [RESET]
    if screen.margins:
        out.append(f"\x1b[{screen.margins.top + 1};{screen.margins.bottom + 1}r")
    for y in range(screen.lines):
        row = screen.buffer[y]
        last = max((x for x in range(screen.columns) if not _blank(row[x])), default=-1)
        if last < 0:
            continue
        out.append(f"\x1b[{y + 1};1H")
        cur = None
        for x in range(last + 1):
            ch = row[x]
            if ch.data == "":       # the right half of a wide character
                continue
            a = sgr(ch)
            if a != cur:
                out.append(f"\x1b[0;{a}m" if a else "\x1b[0m")
                cur = a
            out.append(ch.data)
    out.append("\x1b[0m")
    c = screen.cursor
    out.append(f"\x1b[{min(c.y, screen.lines - 1) + 1};{min(c.x, screen.columns - 1) + 1}H")
    # The pen as the application left it: a later event may print in a colour it set earlier.
    pen = sgr(c.attrs)
    if pen:
        out.append(f"\x1b[{pen}m")
    if c.hidden:
        out.append("\x1b[?25l")
    return "".join(out)


class Replayer:
    """Feed output events in order; take a snapshot whenever asked."""

    def __init__(self, cols: int, rows: int):
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)

    def feed(self, data: str) -> None:
        self.stream.feed(data)

    def snapshot(self) -> str:
        return snapshot(self.screen)


def screen_of(cols: int, rows: int, chunks) -> pyte.Screen:
    r = Replayer(cols, rows)
    for c in chunks:
        r.feed(c)
    return r.screen
