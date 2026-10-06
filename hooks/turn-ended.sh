#!/usr/bin/env bash
# A Stop hook: fires the moment the agent's turn ends.
#
# Register it in the worker's .claude/settings.json:
#
#   { "hooks": { "Stop": [ { "matcher": "", "hooks": [
#       { "type": "command",
#         "command": "bash /path/to/stagecast/hooks/turn-ended.sh",
#         "timeout": 10 } ] } ] } }
#
# Why this and not a sentinel in the prompt. Both tell the driver a turn ended.
# A sentinel has to be *asked for* — "when you are finished, write 01.done" —
# which puts the machinery on screen in every chapter and makes the recording
# look like a work order instead of someone using the tool. A hook is
# configuration: invisible to the recording, and it cannot be forgotten,
# mis-spelled, or written early.
#
# It answers "did the turn end", which is the question the pane cannot answer:
# Claude Code prints a spinner glyph in the line it leaves behind when a turn
# ENDS, so a finished stage and a working one look identical. It does NOT answer
# "did the work get done" — nothing in an agent's own report can. That is what
# the stage's `verify` is for. Use both: the hook says when to look, the check
# says whether to advance.

set -uo pipefail
dir="${STAGECAST_STATE:-${CLAUDE_PROJECT_DIR:-.}/.stagecast}"
mkdir -p "$dir"
date -u +%s > "$dir/turn-ended"
