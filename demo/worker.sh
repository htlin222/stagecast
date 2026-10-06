#!/usr/bin/env bash
# A scripted worker. It reads one instruction, matches a keyword, and runs one
# fixed step — that is all. It is not an agent and does not imitate one: there
# is no model here, no API key, and the same input always produces the same
# output. What the demo exercises is the machinery *around* the target — send a
# message, wait, check the artefact, move on — which is identical whether the
# thing on the other end is this or Claude Code.
set -u
say() { printf '  %s\n' "$*"; }

printf 'worker — reads an instruction, does one thing, says what it did\n\n'

while true; do
  printf '› '
  IFS= read -r line || break
  case "$line" in
    ""|exit|quit) printf '\n' ; exit 0 ;;
  esac

  # Order matters, and by verb rather than noun: "count the lines in the notes
  # file" names the notes too, and matching on that ran the wrong step.
  case "$line" in
    *[Ss]ummar*)
      say "writing SUMMARY.md"
      { printf '# Summary\n\n'; cat report.txt
        printf '\nEach stage was gated on a file, not on a report.\n'; } > SUMMARY.md
      sleep 1
      say "SUMMARY.md · $(wc -l < SUMMARY.md | tr -d ' ') lines" ;;
    *[Cc]ount*)
      say "reading notes.md"
      sleep 1
      n="$(wc -l < notes.md | tr -d ' ')"
      printf 'notes.md has %s lines\n' "$n" > report.txt
      say "report.txt · $(cat report.txt)" ;;
    *[Nn]otes*)
      say "writing notes.md"
      printf '# Notes\n\nThe check reads it back.\nNothing advances on a claim.\n' > notes.md
      sleep 1
      say "notes.md · $(wc -l < notes.md | tr -d ' ') lines" ;;
    *)
      say "no step matches that instruction" ;;
  esac
  printf '\n'
done
