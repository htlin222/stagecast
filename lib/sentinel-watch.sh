#!/usr/bin/env bash
# Optional belt and braces: nothing here guesses whether the agent is idle, it
# only re-reads the plan and re-evaluates each check. Useful when the plan is
# being corrected while a long run is in flight — the driver holds its copy in
# memory, this one does not.
set -uo pipefail
PLAN="${SC_PLAN:?}"; W="${SC_WORKDIR:-.}"
while :; do
  while IFS=$'\t' read -r id _ _ check; do
    ( cd "$W" && eval "$check" ) >/dev/null 2>&1 \
      && printf '%s ✓ %s check passes\n' "$(date -u +%H:%M:%S)" "$id"
  done < "$PLAN"
  sleep "${SC_WATCH_INTERVAL:-30}"
done
