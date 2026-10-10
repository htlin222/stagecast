#!/usr/bin/env bash
# The lint has to fail on the recording that shipped the bugs, and pass on one
# that did not. Without this, a lint that matches nothing looks identical to a
# lint that found nothing.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
L="$HERE/../tools/lint_casts.py"
t=0 f=0
run() { uv run --no-project python "$L" /dev/null "$1" >/dev/null 2>&1; }

mkdir -p "$HERE/.tmp-bad" "$HERE/.tmp-ok"
command cp "$HERE/fixtures/leaky.cast" "$HERE/.tmp-bad/"
command cp "$HERE/fixtures/clean.cast" "$HERE/.tmp-ok/"

t=$((t+1)); run "$HERE/.tmp-bad" && { echo "✖ lint passed a recording with known leaks"; f=$((f+1)); } || echo "✓ rejects the leaky recording"
t=$((t+1)); run "$HERE/.tmp-ok"  && echo "✓ accepts the clean recording" || { echo "✖ lint rejected a clean recording"; f=$((f+1)); }

# each leak shape named on its own, so a lint that catches one does not pass
t=$((t+3))
uv run --no-project python "$L" /dev/null "$HERE/.tmp-bad" 2>&1 | grep -q "bracketed-paste" && echo "✓ names the paste markers" || { echo "✖ missed the paste markers"; f=$((f+1)); }
uv run --no-project python "$L" /dev/null "$HERE/.tmp-bad" 2>&1 | grep -q "misfired" && echo "✓ names the harness misfire" || { echo "✖ missed the harness misfire"; f=$((f+1)); }
uv run --no-project python "$L" /dev/null "$HERE/.tmp-bad" 2>&1 | grep -q "bare ESC" && echo "✓ names the bare ESC" || { echo "✖ missed the bare ESC"; f=$((f+1)); }

# the quit that landed mid-stream, in its own directory so it is judged alone
mkdir -p "$HERE/.tmp-splice"; command cp "$HERE/fixtures/spliced-quit.cast" "$HERE/.tmp-splice/"
t=$((t+2))
run "$HERE/.tmp-splice" && { echo "✖ lint passed a quit spliced into the output"; f=$((f+1)); } || echo "✓ rejects the spliced quit"
uv run --no-project python "$L" /dev/null "$HERE/.tmp-splice" 2>&1 | grep -q "before the output stopped" && echo "✓ names the spliced quit" || { echo "✖ missed the spliced quit"; f=$((f+1)); }
rm -rf "$HERE/.tmp-splice"

rm -rf "$HERE/.tmp-bad" "$HERE/.tmp-ok"
[ "$f" = 0 ] && { echo "all $t checks pass"; exit 0; } || { echo "$f of $t failed"; exit 1; }
