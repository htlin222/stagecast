#!/usr/bin/env python3
"""Open the published site in a real browser and check every control works.

    uv run --with playwright --no-project tools/verify_site.py [url] [shots-dir]

The URL defaults to http://localhost:8000/ — serve site/ with
`python3 -m http.server` and run `stagecast verify`.

HTTP 200 proves a file was served. It does not prove the page rendered, and it
certainly does not prove a button does anything: the player was once a blank
panel for a whole deploy cycle because a centred flex child resolved to zero
height, and every check I had — status codes, CSS strings in the source — came
back green.

So drive it. Load the page, click the things, and look at what is drawn.
Nothing here knows how many chapters there should be: it reads that from the
page it was given.
"""
from __future__ import annotations

import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".stagecast/site-check")
WIDTHS = (1440, 1024, 390)


def launch(pw):
    exe = os.environ.get("STAGECAST_CHROMIUM")
    if exe:
        return pw.chromium.launch(executable_path=exe)
    try:
        return pw.chromium.launch()
    except Exception:
        return pw.chromium.launch(channel="chrome")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")
        if not ok:
            fails.append(name)

    with sync_playwright() as pw:
        b = launch(pw)
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL, wait_until="domcontentloaded")
        print(f"\n{URL}")

        def wait_ready(what: str, timeout: int = 30000) -> bool:
            # Wait for the terminal to be drawn, not for a fixed number of seconds:
            # a fixed wait is a race against the download.
            try:
                pg.wait_for_function("window.ready === true && document.querySelector('#player .ap-term, #player .ap-terminal')",
                                     timeout=timeout)
                return True
            except Exception:
                check(f"terminal rendered ({what})", False, "timed out")
                return False

        wait_ready("first load")
        check("no JavaScript errors", not errors, "; ".join(errors[:2]))
        chapters = pg.evaluate("CHAPTERS")
        n = len(chapters)
        check("the page has chapters", n > 0, f"{n}")
        if not n:
            b.close()
            return 1

        box = pg.locator("#player").bounding_box()
        check("player has a box", bool(box) and box["height"] > 200,
              f'{box["width"]:.0f}x{box["height"]:.0f}' if box else "no box")

        # the brief, and START
        check("brief shown on load", pg.locator("#brief:not(.hidden)").count() == 1)
        brief = pg.locator("#brieftext").inner_text()
        check("brief carries the message", len(brief.strip()) > 20, f"{len(brief)} chars")
        if pg.evaluate("KEYS.length"):
            bolds = pg.evaluate("""() => CHAPTERS.some((c, i) => { go(i);
                return document.querySelectorAll('#brieftext b').length > 0; })""")
            check("keywords emphasised", bolds)
            pg.evaluate("go(0)")
            wait_ready("back to the first chapter")
        pg.screenshot(path=str(OUT / "00-brief.png"))
        pg.locator("#btn-start").click()
        pg.wait_for_timeout(1500)
        check("START reveals the player", pg.locator("#brief.hidden").count() == 1)
        t = pg.evaluate("Promise.resolve(player.getCurrentTime())")
        check("START plays", (t or 0) > 0.2, f"t={t}")

        # A chapter that plays for one second is an empty recording, and the
        # controls all work perfectly on top of one.
        floor = pg.evaluate("MIN_CHAPTER")
        short = [f"{c['id']}={c['dur']:.0f}s" for c in chapters if c["kind"] == "stage" and c["dur"] < floor]
        check("no empty chapters", not short, ", ".join(short))
        rail = pg.locator("#rail button").count()
        check("chapter list", rail == n, f"{rail} of {n} chapters")

        # switching chapters, and the screen after a jump: every chapter cast must
        # open on the full screen (header and statusline present), never on a
        # blank top row — which is what `poster` did to marker seeks.
        k = min(3, n - 1)
        first = pg.locator('#rail button[aria-current="true"]').inner_text()
        pg.locator("#rail button").nth(k).click()
        wait_ready(f"chapter {k + 1}")
        cur = pg.locator('#rail button[aria-current="true"]').inner_text()
        check("switching chapters", n == 1 or cur != first, f"now {cur.splitlines()[0][:30]!r}")
        pg.locator("#btn-start").click()
        pg.wait_for_timeout(1200)
        row = pg.evaluate("""() => { const l = document.querySelector('#player .ap-line');
            return l ? l.textContent : null; }""")
        check("a jump shows the whole screen", bool(row and row.strip()), repr((row or "")[:40]))
        box2 = pg.locator("#player").bounding_box()
        check("player survives a switch", bool(box2) and box2["height"] > 200)
        pg.screenshot(path=str(OUT / "02-chapter-switched.png"))

        # Space: playing → paused → playing, never also the player's own toggle
        pg.keyboard.press("Space"); pg.wait_for_timeout(300)
        s1 = pg.evaluate("state")
        pg.keyboard.press("Space"); pg.wait_for_timeout(300)
        s2 = pg.evaluate("state")
        check("Space pauses and resumes", (s1, s2) == ("paused", "playing"), f"{s1} → {s2}")

        # the end of a chapter stops on its last frame
        pg.evaluate("Promise.resolve(player.getDuration()).then(d => player.seek(Math.max(0, d - 1)))")
        try:
            pg.wait_for_function("state === 'ended'", timeout=15000)
            ended = True
        except Exception:
            ended = False
        same = pg.locator('#rail button[aria-current="true"]').inner_text() == cur
        check("a chapter pauses at its end", ended and same and
              pg.locator("#endbar:not(.hidden)").count() == 1)
        if k + 1 < n:
            pg.keyboard.press("Space"); pg.wait_for_timeout(500)
            check("Space after the end opens the next brief", pg.evaluate("state") == "brief"
                  and pg.locator("#brief:not(.hidden)").count() == 1)
            pg.locator("#btn-peek").click(); pg.wait_for_timeout(300)
            check("peek shows the previous answer without playing",
                  pg.locator("#brief.hidden").count() == 1 and pg.evaluate("state") == "brief")
            pg.screenshot(path=str(OUT / "03-peek.png"))

        # the message sheet
        pg.locator("#btn-prompt").click(); pg.wait_for_timeout(300)
        txt = pg.locator("#prompttext").inner_text()
        check("message sheet opens", pg.locator("#sheet-prompt.open").count() == 1)
        check("message has the prompt", len(txt.strip()) > 20, f"{len(txt)} chars")
        pg.screenshot(path=str(OUT / "04-message.png"))
        pg.locator("#close-prompt").click(); pg.wait_for_timeout(200)

        # about
        pg.locator("#about-link").click(); pg.wait_for_timeout(300)
        check("about sheet opens", pg.locator("#sheet-about.open").count() == 1)
        pg.locator("#close-about").click(); pg.wait_for_timeout(200)

        # milestones, when there are any
        if pg.locator("#ms-link:not(.hidden)").count():
            pg.locator("#ms-link").click(); pg.wait_for_timeout(300)
            check("milestones sheet opens", pg.locator("#sheet-ms.open .ms").count() > 0)
            pg.locator("#sheet-ms .file").first.click(); pg.wait_for_timeout(1500)
            check("a milestone file opens", pg.locator("#viewer.open iframe, #viewer.open img").count() == 1)
            pg.screenshot(path=str(OUT / "05-milestone.png"))
            pg.keyboard.press("Escape"); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)

        # keyboard
        pg.evaluate("go(0)")
        wait_ready("first chapter")
        before = pg.locator('#rail button[aria-current="true"]').inner_text()
        pg.keyboard.press("]"); pg.wait_for_timeout(500)
        check("] advances a chapter", n == 1 or
              pg.locator('#rail button[aria-current="true"]').inner_text() != before)
        pg.keyboard.press("m"); pg.wait_for_timeout(300)
        check("m opens the message", pg.locator("#sheet-prompt.open").count() == 1)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        pg.keyboard.press("["); pg.wait_for_timeout(500)
        pg.keyboard.press("Space"); pg.wait_for_timeout(800)
        check("Space on a brief starts the chapter", pg.evaluate("state") == "playing")

        # no horizontal scroll, and nothing clipped, at desktop, tablet and phone widths
        for w in WIDTHS:
            pg.set_viewport_size({"width": w, "height": 900 if w > 600 else 844})
            pg.wait_for_timeout(500)
            sw, iw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
            pb = pg.locator("#player").bounding_box()
            check(f"fits at {w}px", sw <= iw and bool(pb) and pb["x"] + pb["width"] <= iw + 1,
                  f"scrollWidth {sw}, viewport {iw}")
            pg.screenshot(path=str(OUT / f"06-width-{w}.png"))
        pg.set_viewport_size({"width": 1440, "height": 900})

        # white everywhere it should be
        bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        check("page is white", bg in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"), bg)
        check("no JavaScript errors at the end", not errors, "; ".join(errors[:2]))
        b.close()

    print(f"\nshots in {OUT}")
    print("all controls work" if not fails else f"{len(fails)} failing: {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
