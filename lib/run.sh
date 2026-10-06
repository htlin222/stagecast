#!/usr/bin/env bash
# Drive one stage: send its prompt, then wait for its CHECK — never for the
# agent to look finished. See docs/LESSONS.md § Completion.
set -uo pipefail
PLAN="${SC_PLAN:?}"; ID="${1:?stage id}"
# Slurped once: the table may be edited while a long run is in flight.
ROW="$(grep -P "^$ID\t" "$PLAN" || grep "^$ID	" "$PLAN")"
IFS=$'\t' read -r _ PROMPT STALL CHECK <<< "$ROW"
S="${SC_SOCKET:-stagecast}"; W="${SC_WORKDIR:-.}"
say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
verify() { ( cd "$W" && eval "$CHECK" ) >/dev/null 2>&1; }
alive() { tmux -L "$S" has-session -t "$S" 2>/dev/null; }

if verify; then say "⏭ $ID already satisfied"; exit 0; fi

# Bracketed paste: send-keys -l swallows newlines and a multi-paragraph prompt
# arrives as one run-on line.
printf '%s' "$(cat "$SC_BASE/$PROMPT")" | tmux -L "$S" load-buffer -
tmux -L "$S" send-keys -t "$S" Escape 2>/dev/null; sleep 1
tmux -L "$S" paste-buffer -p -t "$S"; sleep 2
tmux -L "$S" send-keys -t "$S" Enter
say "▶ $ID sent; stalls after ${STALL}s without output"

last_change=$(date +%s); last_rev=""
while :; do
  verify && { say "✓ $ID complete and verified"; exit 0; }
  alive  || { say "✖ $ID — the terminal went away"; exit 5; }
  rev="$(tmux -L "$S" capture-pane -p -t "$S" 2>/dev/null | cksum | cut -d' ' -f1)"
  if [ "$rev" != "$last_rev" ]; then last_rev="$rev"; last_change=$(date +%s)
  elif [ $(( $(date +%s) - last_change )) -ge "$STALL" ]; then
    say "✖ $ID produced no output for ${STALL}s — stalled"; exit 1
  fi
  sleep "${SC_POLL:-10}"
done
