#!/usr/bin/env bash
# Kept so settings that already point here keep working. The hook itself is
# hooks/turn_ended.py, which also records WHICH prompt the ended turn answered;
# see the docstring there for how to register it.
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/turn_ended.py"
