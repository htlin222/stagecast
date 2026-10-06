#!/usr/bin/env bash
# Run a script in its own session, so nothing upstream can take it with it.
#
#   .demo/detach.sh <pidfile> <logfile> <script> [args...]
#
# `nohup ... & disown` is not enough. nohup ignores SIGHUP; it does nothing
# about a SIGTERM or SIGKILL sent to a process group, and a background job of an
# agent session is still in that session's group. Twice today the recorder and
# its watchdog died together, mid-run, with no error in either log — the
# signature of a group signal rather than a bug in either script.
#
# os.setsid() puts the process in a new session and a new process group with no
# controlling terminal, so the only things that can stop it are its own exit,
# stop.sh, or the machine. The double fork is what makes the setsid stick: the
# first child leads the new session, and the grandchild — which cannot reacquire
# a terminal — is what actually runs.

set -uo pipefail

pidfile="${1:?usage: detach.sh <pidfile> <logfile> <script> [args...]}"
logfile="${2:?}"
script="${3:?}"
shift 3

if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
  printf 'already running (pid %s) — stop it first\n' "$(cat "$pidfile")" >&2
  exit 1
fi

uv run --no-project python - "$pidfile" "$logfile" "$script" "$@" <<'PY'
import os, sys
pidfile, logfile, script, *args = sys.argv[1:]
if os.fork() == 0:
    os.setsid()
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    os.dup2(fd, 1); os.dup2(fd, 2)
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    pid = os.fork()
    if pid == 0:
        os.execvp("bash", ["bash", script, *args])
    open(pidfile, "w").write(str(pid))
    os._exit(0)
os.wait()
PY

sleep 2
pid="$(cat "$pidfile" 2>/dev/null)"
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  printf 'detached: %s (pid %s, session %s)\n' "$(basename "$script")" "$pid" \
    "$(ps -o sess= -p "$pid" 2>/dev/null | tr -d ' ')"
else
  printf 'failed to start %s; see %s\n' "$(basename "$script")" "$logfile" >&2
  exit 1
fi
