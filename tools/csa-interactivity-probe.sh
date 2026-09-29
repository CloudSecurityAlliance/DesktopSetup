#!/usr/bin/env bash
# CSA interactivity probe (macOS / Linux)
#
# Question it answers: when DesktopSetup runs an internal setup script, is there a
# terminal to prompt at? The setup scripts assume there is not, and skip their
# directory prompts on that basis. The comment in csa_choose_dir says "DesktopSetup
# runs this from a pipe" - but the documented install is
#
#     bash -c "$(curl -fsSL ...macos-update.sh)"
#
# which is COMMAND SUBSTITUTION, not a pipe: the script arrives as an argument and
# stdin is never redirected. This probe replicates the real chain and reports what
# `-t 0` actually says at each level.
#
#
# MEASURED SO FAR
#   Windows 11 / PowerShell 5.1, real console window, 2026-09-29: prompts DO run
#   (IsInputRedirected = False at every level). The .ps1 alongside this has the detail.
#   macOS: not yet measured - run this and compare. The prediction on record is that it
#   also runs, because `bash -c "$(curl ...)"` is command substitution rather than a pipe
#   and never touches stdin, which would make csa_choose_dir's comment wrong too.
# Run it from a REAL Terminal window. Then send back the log path it prints.

stamp=$(date +%Y%m%d-%H%M%S)
log="$HOME/csa-interactivity-probe-$stamp.log"

emit() { printf '%s\n' "$*" | tee -a "$log"; }

emit "CSA interactivity probe (macOS/Linux)  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
emit "=================================================================="
emit ""
emit "-- environment --"
emit "  uname                : $(uname -srm)"
emit "  bash                 : ${BASH_VERSION:-<not bash>}"
emit "  TERM                 : ${TERM:-<unset>}"
emit "  TERM_PROGRAM         : ${TERM_PROGRAM:-<unset>}"
emit "  NONINTERACTIVE       : ${NONINTERACTIVE:-<unset>}"
emit "  CI                   : ${CI:-<unset>}"
emit ""
emit "-- baseline: this shell, before any nesting --"
if [ -t 0 ]; then emit "  [ -t 0 ] stdin  : TTY"; else emit "  [ -t 0 ] stdin  : NOT a tty"; fi
if [ -t 1 ]; then emit "  [ -t 1 ] stdout : TTY"; else emit "  [ -t 1 ] stdout : NOT a tty"; fi
emit ""
emit "-- replicating the DesktopSetup chain --"

# Level 1: exactly how you invoke the installer - command substitution, NOT a pipe.
outer='
  if [ -t 0 ]; then echo "OUTER (macos-update.sh body, via bash -c \"\$(curl ...)\")"; echo "    stdin = TTY"; else echo "OUTER (macos-update.sh body)"; echo "    stdin = NOT a tty"; fi
  # Level 2: exactly how it runs an internal setup script.
  inner='"'"'if [ -t 0 ]; then echo "INNER (the internal setup script, via bash -c)"; echo "    stdin = TTY"; else echo "INNER (the internal setup script)"; echo "    stdin = NOT a tty"; fi'"'"'
  CSA_NESTED=1 bash -c "$inner"
'
bash -c "$outer" 2>&1 | while IFS= read -r line; do emit "  $line"; done

emit ""
emit "-- verdict --"
verdict=$(bash -c 'inner='"'"'[ -t 0 ] && echo RUN || echo SKIPPED'"'"'; CSA_NESTED=1 bash -c "$inner"')
if [ -t 0 ]; then base=TRUE; else base=FALSE; fi
emit "  csa_interactive would return  : $base"
emit "  => directory prompts would be : $verdict"
emit ""
emit "=================================================================="
printf '\nLOG WRITTEN TO: %s\n' "$log"
printf 'Send that path back.\n'
