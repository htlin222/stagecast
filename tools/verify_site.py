#!/usr/bin/env python3
"""Open the published site in a real browser and check every control works.

    uv run --with playwright --no-project live-demo/verify_site.py [url]

HTTP 200 proves a file was served. It does not prove the page rendered, and it
certainly does not prove a button does anything: the player was once a blank
panel for a whole deploy cycle because a centred flex child resolved to zero
height, and every check I had — status codes, CSS strings in the source — came
back green.

So drive it. Load the page, click the things, and look at the pixels.
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://htlin222.github.io/meta-pipe-talk/"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/site-check")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")
        if not ok:
            fails.append(name)

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL, wait_until="networkidle")
        pg.wait_for_timeout(2500)

        print(f"\n{URL}")
        check("no JavaScript errors", not errors, "; ".join(errors[:2]))

        # the player actually occupies space and drew something
        box = pg.locator("#player").bounding_box()
        check("player has a box", bool(box) and box["height"] > 200,
              f'{box["width"]:.0f}x{box["height"]:.0f}' if box else "no box")
        term = pg.locator("#player .ap-terminal, #player canvas, #player pre").first
        check("terminal rendered", term.count() > 0 and term.is_visible())

        # the brief, and START
        check("brief shown on load", pg.locator("#brief:not(.hidden)").count() == 1)
        brief = pg.locator("#brieftext").inner_text()
        check("brief carries the message", len(brief) > 120, f"{len(brief)} chars")
        check("keywords emphasised", pg.locator("#brieftext b").count() > 0,
              f"{pg.locator('#brieftext b').count()} bold runs")
        pg.screenshot(path=str(OUT / "00-brief.png"))
        pg.locator("#btn-start").click()
        pg.wait_for_timeout(1200)
        check("START reveals the player", pg.locator("#brief.hidden").count() == 1)

        # a chapter that plays for one second is an empty recording, and the
        # controls all work perfectly on top of one. Ask how long each cast is.
        import json as _json, urllib.request as _u
        base = URL.rstrip("/")
        short = []
        for st in pg.evaluate("STAGES.map(s => s.id)"):
            try:
                raw = _u.urlopen(f"{base}/casts/stage-{st}.cast", timeout=20).read().decode(
                    "utf-8", "replace").splitlines()
                last = next((float(_json.loads(l)[0]) for l in reversed(raw[1:]) if l.strip()), 0)
            except Exception:
                last = 0
            if last < 30:
                short.append(f"{st}={last:.0f}s")
        check("no empty chapters", not short, ", ".join(short))

        # chapters
        n = pg.locator("#rail button").count()
        check("chapter list", n == 10, f"{n} chapters")
        first = pg.locator("#rail button").first.inner_text()
        pg.locator("#rail button").nth(5).click()
        pg.wait_for_timeout(1800)
        cur = pg.locator('#rail button[aria-current="true"]').inner_text()
        check("switching chapters", cur != first, f"now {cur.splitlines()[0][:30]!r}")
        box2 = pg.locator("#player").bounding_box()
        check("player survives a switch", bool(box2) and box2["height"] > 200)
        pg.screenshot(path=str(OUT / "02-chapter-switched.png"))

        # the message sheet
        pg.locator("#btn-prompt").click()
        pg.wait_for_timeout(500)
        txt = pg.locator("#prompttext").inner_text()
        check("message sheet opens", pg.locator("#sheet-prompt.open").count() == 1)
        check("message has the prompt", len(txt) > 120, f"{len(txt)} chars")
        pg.screenshot(path=str(OUT / "03-message.png"))
        pg.locator("#close-prompt").click(); pg.wait_for_timeout(300)

        # about
        pg.locator("#about-link").click(); pg.wait_for_timeout(400)
        check("about sheet opens", pg.locator("#sheet-about.open").count() == 1)
        pg.screenshot(path=str(OUT / "04-about.png"))
        pg.locator("#close-about").click(); pg.wait_for_timeout(300)

        # keyboard
        pg.keyboard.press("]"); pg.wait_for_timeout(1500)
        check("] advances a chapter",
              pg.locator('#rail button[aria-current="true"]').inner_text() != cur)
        pg.keyboard.press("m"); pg.wait_for_timeout(400)
        check("m opens the message", pg.locator("#sheet-prompt.open").count() == 1)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)

        pg.locator("#rail button").first.click(); pg.wait_for_timeout(1800)
        pg.screenshot(path=str(OUT / "01-landing.png"))

        # white everywhere it should be
        bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        check("page is white", bg in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"), bg)
        b.close()

    print(f"\nshots in {OUT}")
    print("all controls work" if not fails else f"{len(fails)} failing: {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
