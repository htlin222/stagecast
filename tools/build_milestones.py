#!/usr/bin/env python3
"""Build the player's milestone gallery: what each stage produced, from git.

    uv run --no-project tools/build_milestones.py <stagecast.toml> <site-dir>

Milestones are `[[milestone]]` tables in stagecast.toml, or in a milestones.toml
next to it:

    [[milestone]]
    id       = "irb-initial"
    title    = "IRB initial submission"
    summary  = "One line under the title."
    ref      = "irb-initial-review"      # tag or commit: files come from HERE
    chapters = ["03", "04", "05"]
    items    = [ { label = "config", src = "config.toml", kind = "text" },
                 { label = "protocol", src = "docs/protocol.docx" } ]

Every file is read with `git show <ref>:<path>` from the recorded project's
repository (`[milestones] repo`, default the project workdir) — never from the
working tree — so a milestone shows exactly what existed at that point in the
run, and doubles as a check a viewer can see that the stage's artefacts exist.

    pdf, png, jpg, gif, svg   copied; a PDF also gets page images
    md                        pandoc → HTML (the .md is kept for download)
    csv                       an HTML table of the first rows (the .csv is kept)
    text (default)            HTML <pre>
    docx                      LibreOffice → PDF → page images (the .docx is kept)

PDFs are shown as page images stacked in an HTML page, never embedded: mobile
Safari and headless Chromium draw an embedded PDF blank.

Writes <site-dir>/milestones/<id>/… and <site-dir>/milestones.json.
"""
from __future__ import annotations

import csv
import html
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sc_config as C  # noqa: E402

CSV_ROWS = 120
KIND_BY_EXT = {"md": "md", "markdown": "md", "csv": "csv", "docx": "docx", "pdf": "pdf",
               "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
               "svg": "image", "webp": "image"}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
:root {{ --ink:#1c1917; --muted:#57534e; --line:#e7e5e4; --soft:#fafaf9; }}
body {{ margin:0; padding:24px 28px 48px; background:#fff; color:var(--ink);
  font:15px/1.7 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif; }}
main {{ max-width:880px; margin:0 auto; }}
h1,h2,h3 {{ line-height:1.35; }} h1 {{ font-size:22px; }} h2 {{ font-size:18px; margin-top:28px; }}
a {{ color:var(--ink); }} img {{ max-width:100%; }}
table {{ border-collapse:collapse; font-size:13px; margin:12px 0; display:block; overflow-x:auto; }}
th,td {{ border:1px solid var(--line); padding:4px 8px; text-align:left; vertical-align:top; white-space:nowrap; }}
th {{ background:var(--soft); position:sticky; top:0; }}
pre,code {{ font:13px ui-monospace,"SF Mono",Menlo,monospace; }}
pre {{ background:var(--soft); padding:12px; overflow-x:auto; border-radius:4px; white-space:pre-wrap; }}
blockquote {{ margin:12px 0; padding:4px 14px; border-left:3px solid var(--line); color:var(--muted); }}
.note {{ color:var(--muted); font-size:13px; margin:0 0 14px; }}
@media (max-width:600px) {{ body {{ padding:16px; }} }}
</style></head><body><main>{body}</main></body></html>"""


class Missing(Exception):
    pass


def need(tool: str, why: str) -> str:
    exe = shutil.which(tool)
    if not exe:
        raise Missing(f"{tool} is not installed — it is needed to {why}")
    return exe


def page(title: str, body: str) -> str:
    return PAGE.format(title=html.escape(title), body=body)


def git_bytes(repo: pathlib.Path, ref: str, path: str) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True)
    if r.returncode:
        err = r.stderr.decode(errors="replace").strip()
        raise Missing(f"{path!r} does not exist at {ref!r} in {repo} ({err.splitlines()[-1] if err else 'git show failed'})")
    return r.stdout


def table_html(text: str, limit: int) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return '<p class="note">empty</p>'
    head, data = rows[0], rows[1:]
    note = f"{len(data)} rows × {len(head)} columns" + (f"; the first {limit} shown" if len(data) > limit else "")
    th = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in data[:limit])
    return f'<p class="note">{note}</p><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def soffice_pdf(src: pathlib.Path, outdir: pathlib.Path) -> pathlib.Path:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise Missing(f"LibreOffice (soffice) is not installed — it is needed to preview {src.name}")
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([exe, f"-env:UserInstallation=file://{profile}", "--headless",
                        "--convert-to", "pdf", "--outdir", str(outdir), str(src)],
                       capture_output=True, check=True, timeout=300)
    pdf = outdir / (src.stem + ".pdf")
    if not pdf.exists():
        raise Missing(f"LibreOffice did not produce a PDF from {src.name}")
    return pdf


def pdf_preview(pdf: pathlib.Path, title: str) -> str:
    """Page images and an HTML page that stacks them: every browser can show this."""
    exe = need("pdftoppm", f"render the pages of {pdf.name} (install poppler)")
    pages = pdf.with_suffix(".pages")
    pages.mkdir(exist_ok=True)
    subprocess.run([exe, "-jpeg", "-jpegopt", "quality=72", "-scale-to-x", "1100",
                    "-scale-to-y", "-1", str(pdf), str(pages / "p")], check=True, capture_output=True)
    imgs = sorted(pages.glob("p-*.jpg"))
    figs = "".join(
        f'<figure style="margin:0 0 18px"><img loading="lazy" alt="page {k}" '
        f'style="width:100%;box-shadow:0 0 0 1px var(--line)" src="{quote(pages.name)}/{i.name}">'
        f'<figcaption class="note" style="text-align:center">page {k}</figcaption></figure>'
        for k, i in enumerate(imgs, 1))
    note = f'<p class="note">{len(imgs)} page(s) · <a href="{quote(pdf.name)}">the PDF</a></p>'
    view = pdf.with_name(pdf.name + ".html")
    view.write_text(page(title, f"<h1>{html.escape(title)}</h1>{note}{figs}"))
    return view.name


def build_item(repo: pathlib.Path, it: dict, ref: str, outdir: pathlib.Path, n: int) -> dict:
    src = it["src"]
    name = pathlib.PurePosixPath(src).name
    ext = pathlib.PurePosixPath(name).suffix.lower().lstrip(".")
    stem = f"{n:02d}-{C.slug(pathlib.PurePosixPath(name).stem)}"
    kind = it.get("kind") or KIND_BY_EXT.get(ext, "text")
    label = it.get("label", name)
    entry = {"label": label, "kind": kind, "ref": ref, "src": src}
    blob = git_bytes(repo, ref, src)
    if kind == "md":
        pandoc = need("pandoc", f"render {src}")
        (outdir / f"{stem}.md").write_bytes(blob)
        body = subprocess.run([pandoc, "-f", "gfm", "-t", "html"], input=blob,
                              capture_output=True, check=True).stdout.decode()
        (outdir / f"{stem}.html").write_text(page(label, body))
        entry |= {"view": f"{stem}.html", "download": f"{stem}.md"}
    elif kind == "csv":
        (outdir / f"{stem}.csv").write_bytes(blob)
        body = f"<h1>{html.escape(label)}</h1>" + table_html(blob.decode("utf-8-sig", "replace"), CSV_ROWS)
        (outdir / f"{stem}.html").write_text(page(label, body))
        entry |= {"view": f"{stem}.html", "download": f"{stem}.csv"}
    elif kind == "docx":
        docx = outdir / f"{stem}.docx"
        docx.write_bytes(blob)
        pdf = soffice_pdf(docx, outdir)
        entry |= {"kind": "docx", "view": pdf_preview(pdf, label), "pdf": pdf.name,
                  "download": docx.name}
    elif kind == "pdf":
        pdf = outdir / f"{stem}.pdf"
        pdf.write_bytes(blob)
        entry |= {"view": pdf_preview(pdf, label), "pdf": pdf.name}
    elif kind == "image":
        (outdir / f"{stem}.{ext}").write_bytes(blob)
        entry |= {"view": f"{stem}.{ext}", "download": f"{stem}.{ext}"}
    else:
        body = f"<h1>{html.escape(label)}</h1><pre>{html.escape(blob.decode('utf-8', 'replace'))}</pre>"
        (outdir / f"{stem}.html").write_text(page(label, body))
        (outdir / f"{stem}.{ext or 'txt'}").write_bytes(blob)
        entry |= {"kind": "text", "view": f"{stem}.html", "download": f"{stem}.{ext or 'txt'}"}
    return entry


def tree_url(repo_url: str, ref: str) -> str:
    if re.match(r"https://(github|gitlab)\.com/", repo_url or ""):
        return f"{repo_url.rstrip('/')}/tree/{quote(ref)}"
    return ""


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip())
        return 2
    cfg = C.load(sys.argv[1])
    site = pathlib.Path(sys.argv[2])
    repo = pathlib.Path(cfg["milestones_cfg"].get("repo", cfg["workdir"]))
    repo = repo if repo.is_absolute() else (cfg["base"] / repo)
    ids = {s["id"] for s in cfg["stages"]}
    root = site / "milestones"
    shutil.rmtree(root, ignore_errors=True)   # a stale file is indistinguishable from a fresh one
    out, failed = [], []
    for m in cfg["milestones"]:
        for ch in m.get("chapters", []):
            if ch not in ids:
                print(f"  warning: milestone {m['id']} names chapter {ch!r}, which is no stage",
                      file=sys.stderr)
        outdir = root / C.slug(m["id"])
        outdir.mkdir(parents=True)
        items = []
        for n, it in enumerate(m.get("items", []), 1):
            try:
                items.append(build_item(repo, it, it.get("ref", m["ref"]), outdir, n))
            except Missing as e:
                failed.append(f"{m['id']}: {e}")
            except subprocess.CalledProcessError as e:
                failed.append(f"{m['id']}: {it['src']}: {e.cmd[0]} failed "
                              f"({(e.stderr or b'').decode(errors='replace').strip()[:200]})")
        out.append({"id": C.slug(m["id"]), "title": m.get("title", m["id"]),
                    "summary": m.get("summary", ""), "ref": m["ref"],
                    "tree": tree_url(cfg["project"].get("repo", ""), m["ref"]),
                    "chapters": m.get("chapters", []), "items": items})
        print(f"  milestone {m['id']}: {len(items)} file(s) from {m['ref']}")
    if failed:
        for f in failed:
            print(f"  ✖ {f}", file=sys.stderr)
        return 1
    (site / "milestones.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
