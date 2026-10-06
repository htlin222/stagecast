#!/usr/bin/env bash
# One recorded session per stage, so a repair costs one chapter.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN="${SC_PLAN:?}"; OUT="${SC_OUT:?}"; S="${SC_SOCKET:-stagecast}"
COLS="${SC_COLS:-118}"; ROWS="${SC_ROWS:-28}"
mkdir -p "$OUT/_aborted"
n=$(find "$OUT" -maxdepth 1 -name 'seg-*.cast' 2>/dev/null | wc -l | tr -d ' ')
say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }

while IFS=$'\t' read -r id _ _ _; do
  [ -n "${SC_ONLY:-}" ] && [ "$id" != "$SC_ONLY" ] && continue
  n=$((n+1)); cast="$(printf '%s/seg-%03d-step%s.cast' "$OUT" "$n" "$id")"
  # Retire any earlier take rather than leaving two.
  for old in "$OUT"/seg-*-step"$id".cast; do
    [ -e "$old" ] && command mv "$old" "$OUT/_aborted/$(date +%H%M%S)-$(basename "$old")"
  done
  say "▶ stage $id → $(basename "$cast")"
  tmux -L "$S" kill-session -t "$S" 2>/dev/null
  tmux -L "$S" new-session -d -s "$S" -x "$COLS" -y "$ROWS" -c "${SC_WORKDIR:-.}" \
    "asciinema rec '$cast' --idle-time-limit ${SC_IDLE:-2} --cols $COLS --rows $ROWS \
       -c '${SC_AGENT:-claude}'"
  for _ in $(seq 1 45); do
    tmux -L "$S" capture-pane -p -t "$S" 2>/dev/null | grep -qE 'shortcuts|Welcome|bypass|Try "' && break
    sleep 2
  done
  bash "$HERE/run.sh" "$id"; rc=$?
  # A check passing does not mean the output has stopped. The check fires the
  # moment the artefact exists, while the target is still printing what it did —
  # so quitting here cut into the stream and left "exitwrote 4 lines" on screen.
  # Wait for the pane to hold still before asking it to leave.
  prev=""; still=0
  for _ in $(seq 1 60); do
    now="$(tmux -L "$S" capture-pane -p -t "$S" 2>/dev/null)"
    if [ "$now" = "$prev" ]; then
      still=$((still+1)); [ "$still" -ge "${SC_SETTLE:-3}" ] && break
    else
      still=0; prev="$now"
    fi
    sleep 1
  done
  [ -n "${SC_CLEAR-Escape}" ] && { tmux -L "$S" send-keys -t "$S" "${SC_CLEAR-Escape}" 2>/dev/null; sleep 1; }
  tmux -L "$S" send-keys -t "$S" "${SC_QUIT:-/exit}" 2>/dev/null; sleep 1
  tmux -L "$S" send-keys -t "$S" Enter 2>/dev/null; sleep 4
  tmux -L "$S" kill-session -t "$S" 2>/dev/null
  [ "$rc" = 0 ] || { say "✖ stopped at stage $id (rc=$rc)"; exit "$rc"; }
  [ -n "${SC_ONLY:-}" ] && break
done < "$PLAN"
say "✓ all stages recorded"
