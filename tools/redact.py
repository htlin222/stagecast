#!/usr/bin/env python3
"""Strip credentials out of recordings before they are published.

    uv run --no-project tools/redact.py [--config stagecast.toml] <dir-or-file> [...]

A cast is a recording of a terminal, and a terminal shows whatever was typed
into it. A worker that calls an API with `?api_key=...` puts that key on screen,
and it lands in the cast the same as anything else. The first run of this found
a live PubMed key in two casts, minutes before they would have been pushed to a
public repository.

Sources of secrets, all of them applied:

  - every value at least eight characters long in the RECORDED PROJECT's .env
    (next to stagecast.toml, i.e. $SC_BASE — never the stagecast checkout), and
    in any file listed in `[redact] env_files`
  - `[redact] literals = [...]`, and the REDACT environment variable (one value,
    or several separated by newlines) for one-off values
  - token shapes, whether or not they are in any file: Anthropic, OpenAI-style,
    GitHub classic and fine-grained, Slack, AWS

Each is replaced with a marker padded to exactly the original length. The
padding is not cosmetic: a cast is a stream of terminal output, and a
replacement of a different length shifts every column after it on that line.

tools/postprocess.py applies this to every event it publishes, and
tools/stills.sh to every frame it renders, so no export path reads an
unredacted original. Run it by hand only on copies, never on the originals in
.stagecast/recording/ — those are the source of truth and stay as recorded.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

MIN_SECRET_LEN = 8
# Order matters: the specific shape before the general one that would also match.
PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "anthropic"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "sk"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "gh"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "gh"),
    (re.compile(r"xox[abpr]-[A-Za-z0-9-]{10,}"), "slack"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws"),
]


def secrets_from_env(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if len(v) >= MIN_SECRET_LEN:
            out[k] = v
    return out


def load_secrets(base: pathlib.Path, redact_cfg: dict | None = None) -> dict[str, str]:
    """name → value, from the project's .env files, configured literals and $REDACT."""
    cfg = redact_cfg or {}
    out: dict[str, str] = {}
    for f in cfg.get("env_files", [".env"]):
        p = pathlib.Path(f)
        out.update(secrets_from_env(p if p.is_absolute() else base / p))
    for i, lit in enumerate(cfg.get("literals", []), 1):
        if lit:
            out[f"literal{i}"] = lit
    for i, lit in enumerate(os.environ.get("REDACT", "").splitlines(), 1):
        if lit.strip():
            out[f"REDACT{i}"] = lit.strip()
    return out


def marker(name: str, length: int) -> str:
    """A marker of exactly `length` characters, so no column moves."""
    text = f"[{name}-REDACTED]"
    if len(text) > length:
        return "*" * length
    return text + "*" * (length - len(text))


def redact(text: str, secrets: dict[str, str], counts: dict[str, int] | None = None) -> str:
    # Longest first: a value that contains another is replaced whole.
    for name, value in sorted(secrets.items(), key=lambda kv: -len(kv[1])):
        if value in text:
            if counts is not None:
                counts[name] = counts.get(name, 0) + text.count(value)
            text = text.replace(value, marker(name, len(value)))
    for pat, label in PATTERNS:
        def sub(m: re.Match[str]) -> str:
            if counts is not None:
                counts[f"{label}-shaped"] = counts.get(f"{label}-shaped", 0) + 1
            return marker(label.upper(), len(m.group(0)))
        text = pat.sub(sub, text)
    return text


def main() -> int:
    args = sys.argv[1:]
    cfg_path = None
    if args[:1] == ["--config"]:
        cfg_path, args = pathlib.Path(args[1]), args[2:]
    if not args:
        print(__doc__.strip())
        return 2
    base = pathlib.Path(os.environ.get("SC_BASE") or (cfg_path.parent if cfg_path else "."))
    redact_cfg = {}
    if cfg_path and cfg_path.exists():
        import tomllib
        redact_cfg = tomllib.loads(cfg_path.read_text()).get("redact", {})
    secrets = load_secrets(base, redact_cfg)
    if not secrets:
        print(f"no secrets in {base}/.env — only shape-based patterns will be applied")

    targets: list[pathlib.Path] = []
    for arg in args:
        p = pathlib.Path(arg)
        targets.extend(sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else [p])

    total = 0
    for f in targets:
        original = f.read_text(encoding="utf-8", errors="surrogateescape")
        counts: dict[str, int] = {}
        data = redact(original, secrets, counts)
        for k, n in counts.items():
            print(f"  {f}: {k} ×{n}")
            total += n
        if data != original:
            f.write_text(data, encoding="utf-8", errors="surrogateescape")

    print(f"\n{total} redaction(s)" if total else "\nnothing to redact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
