#!/usr/bin/env bash
# The recorded process: runs inside asciinema, inside the tmux pane.
#
# The command comes from $STAGECAST_STATE/agent.cmd, written by tools/drive.py,
# so nothing on its way here has to survive three layers of shell quoting.
#
# With the claude-code preset (STAGECAST_SCRUB=1) the parent's identity is
# dropped first. A recording is often started from inside another Claude Code
# session, and its CLAUDE* / AI_AGENT variables would otherwise leak into the
# recorded one and change what it is and how it behaves.
set -u
# Cast time zero, as near to asciinema's own as can be had: this runs the moment
# asciinema spawns it. The driver's clock started earlier, by however long
# asciinema took to come up, and a cut computed from it lands that much late.
if [ -n "${STAGECAST_TAKE:-}" ]; then
  printf '%s\n' "${EPOCHREALTIME:-$(python3 -c 'import time; print(time.time())')}" \
    > "${STAGECAST_STATE:?}/recording/$STAGECAST_TAKE.t0"
fi
if [ "${STAGECAST_SCRUB:-0}" = 1 ]; then
  for v in $(env | grep -oE '^(CLAUDE[A-Za-z0-9_]*|AI_AGENT)=' | tr -d '='); do
    case " ${STAGECAST_ENV_KEEP:-} " in *" $v "*) continue ;; esac
    unset "$v"
  done
fi
cmd="$(cat "${STAGECAST_STATE:?}/agent.cmd")"
eval "exec $cmd"
