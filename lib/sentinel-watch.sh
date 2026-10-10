#!/usr/bin/env bash
# Optional belt and braces: nothing here guesses whether the agent is idle, it
# only re-reads stagecast.toml and re-evaluates each check. Useful when the
# config is being corrected while a long run is in flight.
#
#   lib/sentinel-watch.sh [stagecast.toml]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$(cd "$(dirname "${1:-stagecast.toml}")" && pwd)/$(basename "${1:-stagecast.toml}")"
while :; do
  uv run --quiet --no-project python - "$CFG" "$HERE/../tools" <<'PY'
import os, subprocess, sys, time
sys.path.insert(0, sys.argv[2])
import sc_config as C
cfg = C.load(sys.argv[1])
env = dict(os.environ, STAGECAST_STATE=str(cfg["state"]),
           PATH=f"{C.FRAMEWORK / 'lib' / 'bin'}:{os.environ['PATH']}")
for s in cfg["stages"]:
    if subprocess.run(["bash", "-c", s.get("verify", "false")], cwd=cfg["workdir"],
                      env=env, capture_output=True).returncode == 0:
        print(time.strftime("%H:%M:%S", time.gmtime()), "✓", s["id"], "check passes", flush=True)
PY
  sleep "${SC_WATCH_INTERVAL:-30}"
done
