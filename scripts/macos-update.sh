#!/usr/bin/env bash

# Cloud Security Alliance — macOS Update Script
#
# Updates all tools managed by macos-work-tools.sh and macos-ai-tools.sh:
#   1. Homebrew formulas and casks (Git, Node.js, apps, etc.)
#   2. Global npm packages (Codex, Gemini, Wrangler)
#   3. ~/.default_venv — repaired onto Python 3.14 (standard build) when it
#      needs it, never created here; its document deps refreshed
#   4. pip + all pip packages (in active venv or system Python)
#   5. Claude Code — updated via `claude update`
#
# Before updating, saves a snapshot of all installed versions to:
#   ~/Library/Logs/CSA-DesktopSetup/pre-update-<timestamp>.txt
#
# Usage:
#   bash scripts/macos-update.sh
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"

set -euo pipefail

SCRIPT_VERSION="2026-11-11T01:25Z"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Each update run will add any entries from this list that aren't yet
# registered (and that the user's gh account can access), then refresh
# all registered marketplaces.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/macos-ai-tools.sh      (installer, macOS)
#   scripts/windows-ai-tools.ps1   (installer, Windows)
#   scripts/macos-plugins.sh       (standalone plugins, macOS)
#   scripts/windows-plugins.ps1    (standalone plugins, Windows)
#   scripts/windows-update.ps1     (full updater, Windows)
# All six files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the scripts will drift.
# One entry per internal MCP server. Top-level, beside CSA_MARKETPLACES, because
# macos-ai-tools.sh's installation plan has to count it and a list local to the function that
# runs it cannot be counted from the plan. It was local, that plan named two of these four by
# hand, and two servers were installed the person had not been shown. Kept here in every script
# carrying setup_csa_internal_tools so the shared function stays byte-identical.
CSA_INTERNAL_SETUPS=(
  csa-google-workspace-setup.sh
  csa-google-gmail-calendar-setup.sh
  csa-skilljar-setup.sh
  csa-zendesk-setup.sh
)

CSA_MARKETPLACES=(
  "CloudSecurityAlliance-Internal/Accounting-Plugins"
  "CloudSecurityAlliance-Internal/CINO-Plugins"
  "CloudSecurityAlliance-Internal/CSA-Plugins"
  "CloudSecurityAlliance-Internal/Research-Plugins"
  "CloudSecurityAlliance-Internal/Training-Plugins"
  "CloudSecurityAlliance/csa-plugins-official"
)

# Marketplace name → GitHub repo. Function-based lookup rather than
# an associative array because macOS ships bash 3.2, which does not
# support `declare -A`. See the matching block in
# scripts/macos-ai-tools.sh for full rationale.
#
# KEEP IN SYNC: duplicated as plugin_marketplace_repo in
#   scripts/macos-ai-tools.sh
#   scripts/macos-plugins.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-ai-tools.ps1
#   scripts/windows-plugins.ps1
#   scripts/windows-update.ps1
plugin_marketplace_repo() {
  case "$1" in
    # Public
    claude-plugins-official) echo "anthropics/claude-plugins-official" ;;
    anthropic-agent-skills)  echo "anthropics/skills" ;;
    # CSA-internal
    accounting-plugins)      echo "CloudSecurityAlliance-Internal/Accounting-Plugins" ;;
    csa-cino-plugins)        echo "CloudSecurityAlliance-Internal/CINO-Plugins" ;;
    csa-plugins)             echo "CloudSecurityAlliance-Internal/CSA-Plugins" ;;
    csa-research-plugins)    echo "CloudSecurityAlliance-Internal/Research-Plugins" ;;
    csa-training-plugins)    echo "CloudSecurityAlliance-Internal/Training-Plugins" ;;
    csa-plugins-official)    echo "CloudSecurityAlliance/csa-plugins-official" ;;
    *) ;;  # unknown — print nothing
  esac
}

# ── CSA MCP server ──────────────────────────────────────────────────
# See scripts/macos-ai-tools.sh for full rationale. Keep these constants
# and the setup_csa_mcp_server function in sync across all six scripts.
CSA_MCP_NAME="csa-mcp"
CSA_MCP_URL="https://cloudsecurityalliance.org/mcp"
CSA_MCP_GATE_REPO="CloudSecurityAlliance-Internal/CSA-Plugins"

# The interpreter the internal setup scripts install their servers on. Declared in all six
# entry scripts, and pinned equal by tests/test_python_pins.py; before that only the two
# *-ai-tools scripts declared it and -update / -plugins passed an empty value.
CSA_PYTHON_PREFERRED="3.14"

# ── Output helpers ──────────────────────────────────────────────────

if [[ -t 1 ]]; then
  BOLD="\033[1m"
  BLUE="\033[1;34m"
  GREEN="\033[1;32m"
  YELLOW="\033[1;33m"
  RED="\033[1;31m"
  RESET="\033[0m"
else
  BOLD="" BLUE="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()    { printf "${BLUE}==>${BOLD} %s${RESET}\n" "$*"; }
success() { printf "${GREEN}==>${BOLD} %s${RESET}\n" "$*"; }
warn()    { printf "${YELLOW}Warning:${RESET} %s\n" "$*" >&2; }
error()   { printf "${RED}Error:${RESET} %s\n" "$*" >&2; }
abort()   { error "$@"; exit 1; }
SCRIPT_LABEL="macos-update.sh"
CSA_RAW_BASE="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts"

# ── Debug logging ───────────────────────────────────────────────────
#
# CSA_DEBUG=1 records everything this script prints - its own output AND every command's,
# since the redirection below is process-wide - to a timestamped file, while still showing it
# on screen. Off by default.
#
#   CSA_DEBUG=1 bash -c "$(curl -fsSL .../macos-update.sh)"
#
# An environment variable rather than a --debug flag because the documented invocation is
# `curl … | bash`, which gives the script no argument vector at all (NONINTERACTIVE already
# works this way).
#
# Process-wide, rather than a wrapper around each command: bash has no equivalent of the
# NativeCommandError problem that forces the Windows scripts to funnel every native call
# through Invoke-Native*, so there is no existing choke point here - and adding one to ~1000
# lines of direct calls would be a large change that could only capture the calls it was
# remembered at. `exec > >(…)` captures everything, including output from code written before
# anyone thought about logging.
#
# CSA_LOG is exported so anything this script invokes - notably the CSA-internal setup, which
# is fetched and run as a separate bash process - appends to the SAME file. One file per run:
# the person debugging is being asked to send a log, and "send both of them, and mind the
# timestamps" is how half a report goes missing.

# ANSI stripped (the console keeps its colour, the file does not need it), then credential
# shapes redacted with the key kept: `client_secret: <redacted>` still says which line
# failed, `<redacted>` does not. The first expression tolerates the JSON shape
# ("client_secret": "…"), because the quote between key and colon otherwise breaks the match
# - and that is exactly how a credentials file is written.
# Line-buffered if this sed can be. This feeds the FILE only (see the exec below), so it is
# not what decides whether a prompt appears - but without it the log lags, and a child
# process writing straight to the same file lands ahead of the parent's own lines. BSD sed
# spells it -l, GNU sed -u, and some have neither - so ask, once, rather than assume.
CSA_SED_UNBUF=""
if sed -l -E 's/a/a/' </dev/null >/dev/null 2>&1; then
  CSA_SED_UNBUF="-l"
elif sed -u -E 's/a/a/' </dev/null >/dev/null 2>&1; then
  CSA_SED_UNBUF="-u"
fi

csa_redact() {
  # Unquoted on purpose: empty must expand to NO argument, not to an empty one.
  # shellcheck disable=SC2086
  sed ${CSA_SED_UNBUF} -E \
    -e 's/'$'\033''\[[0-9;]*m//g' \
    -e 's/(oauth_token|client_secret|refresh_token|access_token|private_key)("?[[:space:]]*[:=][[:space:]]*"?)[^[:space:],}"]+/\1\2<redacted>/gI' \
    -e 's/(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})/<redacted>/g' \
    -e 's/("?temp_clone_token"?[[:space:]]*[:=][[:space:]]*"?)[A-Za-z0-9]{16,}/\1<redacted>/g' \
    -e 's/(Bearer[[:space:]]+)[^[:space:]]{16,}/\1<redacted>/g' \
    -e 's/ya29\.[A-Za-z0-9._-]{20,}/<redacted>/g'
}

# Accepts 1, true, yes or on, in any case. Not a --debug flag: the documented invocation is
# `bash -c "$(curl ...)"`, which passes no argument vector for a flag to arrive in.
csa_debug_requested() {
  case "$(printf '%s' "${CSA_DEBUG:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *)             return 1 ;;
  esac
}

CSA_LOG_INHERITED=""
if csa_debug_requested; then
  if [[ -n "${CSA_LOG:-}" ]]; then
    CSA_LOG_INHERITED=1
    printf '\n--- %s %s ---\n' "${SCRIPT_LABEL:-desktopsetup}" "${SCRIPT_VERSION}" >> "$CSA_LOG"
  else
    CSA_LOG="${HOME}/desktopsetup-$(date +%Y%m%d-%H%M%S).log"
    ( umask 077; : > "$CSA_LOG" )      # 0600 from creation, not chmod-ed afterwards
    {
      echo "=== DesktopSetup $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
      echo "This log is REDACTED for known credential shapes, but review it before sharing."
      echo "$(uname -sr) · bash ${BASH_VERSION} · ${SCRIPT_LABEL:-desktopsetup} ${SCRIPT_VERSION}"
    } >> "$CSA_LOG"
  fi
  CSA_DEBUG=1                        # normalised, so a child sees 1 whatever was typed
  export CSA_DEBUG CSA_LOG
  # The terminal is fed by `tee` DIRECTLY, and the redactor sits on a branch that only writes
  # the file. That ordering is the whole point, and it is not cosmetic:
  #
  # With the redactor in front of the terminal - `csa_redact | tee -a "$CSA_LOG"` - sed holds
  # anything not yet terminated by a newline. Every prompt in these scripts is exactly that:
  # `read -r -p "Continue? [Y/n] "` writes no newline, so the question never appeared, the
  # script sat waiting on stdin, and it looked like a hang. Pressing Ctrl-C flushed the pipe
  # and revealed the prompt on the way out. There are eleven `read -p` sites and roughly
  # fifteen partial-line `printf`s (progress markers like "Testing... "), so fixing this at
  # the call sites would mean touching all of them and hoping the next one remembers.
  #
  # `tee` writes what it reads, when it reads it, so a partial line reaches the terminal
  # immediately. Line-buffering only has to be good enough for the FILE now, which it is.
  # Measured: with the redactor first, a partial line was still invisible three seconds later;
  # with tee first it appeared at once, and the log came out identical either way.
  #
  # A side benefit: the terminal keeps its colour, since ANSI is now stripped only on the
  # branch heading for the file.
  #
  # Verified on bash 3.2.57 (macOS): all 400 lines survive a clean exit, an `exit N`, and an
  # uncaught failure under `set -e`.
  exec > >(tee -a >(csa_redact >> "$CSA_LOG")) 2>&1
  [[ -z "$CSA_LOG_INHERITED" ]] && info "debug logging to $CSA_LOG" || true
fi

# Printed at the end of every run, either way: the moment somebody needs the logging
# incantation is the moment the run went wrong, not later in a README they are not reading.
csa_debug_hint() {
  if [[ -n "${CSA_LOG:-}" && -z "${CSA_LOG_INHERITED:-}" ]]; then
    info "debug log: $CSA_LOG  (redacted, but review before sharing)"
  elif [[ -z "${CSA_LOG:-}" ]]; then
    # The exact command, not "the same command". Somebody reading this has just watched
    # something go wrong; asking them to reconstruct what they typed is asking them to give up.
    printf '  if anything above went wrong, re-run with logging on and send the log:\n'
    printf '    CSA_DEBUG=1 bash -c "$(curl -fsSL -H '"'"'Cache-Control: no-cache'"'"' %s/%s)"\n' \
      "$CSA_RAW_BASE" "$SCRIPT_LABEL"
  fi
}

# Runs on EVERY exit path, which is the point. Until now `csa_debug_hint` was called after
# `main "$@"`, so under `set -euo pipefail` a failure exited before reaching it — and the debug
# log exists precisely so somebody can report a failure. The one moment you need to know where
# the log is, the script did not tell you. It also said nothing at all about having stopped: a
# real run died mid-way and printed no error, no status, no pointer, and simply looked finished.
csa_on_exit() {
  local status=$?
  if [[ $status -ne 0 ]]; then
    printf '\n'
    warn "stopped early (exit $status). The last line above is where it got to."
    if [[ -z "${CSA_LOG:-}" ]]; then
      warn "no debug log was written — re-run with CSA_DEBUG=1 to get one."
    fi
  fi
  csa_debug_hint
  return $status
}
trap csa_on_exit EXIT


# ── Preconditions ───────────────────────────────────────────────────

[[ -n "${BASH_VERSION:-}" ]] || abort "Bash is required."
[[ "$(uname -s)" == "Darwin" ]] || abort "This script supports macOS only."

if [[ "${EUID:-${UID}}" == "0" ]]; then
  if [[ ! -f /.dockerenv ]] && [[ ! -f /run/.containerenv ]]; then
    abort "Don't run this as root."
  fi
fi

# Detect interactive vs non-interactive
if [[ -z "${NONINTERACTIVE-}" ]]; then
  if [[ -n "${CI-}" ]]; then
    warn "Non-interactive mode: \$CI is set."
    NONINTERACTIVE=1
  elif [[ ! -t 0 ]]; then
    warn "Non-interactive mode: stdin is not a TTY."
    NONINTERACTIVE=1
  fi
fi

# ── Helpers ─────────────────────────────────────────────────────────

has_command() { command -v "$1" >/dev/null 2>&1; }

# npm 11.19+ ends a global install with an `npm warn install-scripts` block: native dependencies
# (node-pty and @github/keytar, under the Gemini CLI) declare install scripts that a future npm
# will run only from an allowlist. Measured on npm 11.19.0 / node 26.8.1 (Homebrew's unversioned
# node, which is what a clean machine got before #74 pinned node@24) — the scripts still RUN: `node-pty/build/` holds the node-gyp
# Makefiles afterwards and both modules load. It is a pre-announcement, not a failure.
#
# It does not read like one (issue #51). This installer is run by people who do not use npm, on
# a machine they were handed an hour ago, and five lines of `npm warn` under "Updating Gemini
# CLI" is indistinguishable from something breaking. The funding footer goes for the same
# reason. Both are kept verbatim under CSA_DEBUG=1, where anyone debugging npm needs them.
#
# sed, not `grep -v`: `set -o pipefail` is on and a grep matching nothing exits 1, so on the day
# npm stops printing this block a clean run would start reporting failure — `npm update -g X ||
# npm install -g X` taking its fallback for nothing, and macos-update.sh warning about an update
# that worked. sed exits 0 whatever it matches, so npm's own status propagates.
# tests/test_npm_output_filter.py holds that case, and the `grep -v` control proving it is real.
csa_npm() {
  if csa_debug_requested; then
    npm "$@"
  else
    # Deliberately NOT $CSA_SED_UNBUF. BSD sed spells line-buffering -l as a bare flag; GNU
    # sed spells -l N and takes an argument, so on GNU it swallows the first -e and treats
    # '/^npm warn install-scripts/d' as an input FILENAME: stdin is never read, npm's summary
    # vanishes, and the "no such file" error quotes the pattern back. csa_redact gets away
    # with the same variable only because -E follows it and absorbs the argument. Buffering
    # buys nothing here anyway - npm prints its summary once, at the end.
    npm "$@" 2>&1 | sed \
      -e '/^npm warn install-scripts/d' \
      -e '/looking for funding$/d' \
      -e '/run `npm fund` for details$/d'
  fi
}

confirm() {
  if [[ -n "${NONINTERACTIVE-}" ]]; then return 0; fi
  local reply
  read -r -p "$1 [Y/n] " reply
  case "${reply:-Y}" in
    [Yy]*) return 0 ;;
    *)     return 1 ;;
  esac
}

# An unaccepted Xcode license makes EVERY Homebrew command fail with the same error, and
# `xcode-select -p` cannot see it: "the tools are installed" and "the license is accepted" are
# independent states, and a machine fresh from `xcode-select --install` has the first without
# the second.
#
# Without this gate one root cause became five symptoms (#87): `brew update`, pandoc, typst and
# the document preflight deps each warned and continued, and only the fifth - Git - aborted. So
# the one actionable line, which Homebrew itself printed, scrolled past four CSA messages that
# each described a consequence ("document rendering stays broken") instead of the cause.
#
# Keyed on the literal refusal text, not on a predictive probe of the license state: a state
# probe has to special-case CLT-only machines against ones with full Xcode (`xcodebuild -version`
# answers differently on each) and goes stale as Xcode changes, whereas a string this specific
# cannot stop a run that would otherwise have worked.
#
# `/usr/bin/git` is the probe because it is a Command Line Tools shim present on every Mac, so it
# refuses in exactly the way every `brew` subprocess is about to - no extra dependency, and no
# assumption that Homebrew is installed yet.
csa_xcode_license_checked=0
csa_require_xcode_license() {
  if [[ "$csa_xcode_license_checked" == 1 ]]; then return 0; fi
  csa_xcode_license_checked=1
  local probe
  probe="$(/usr/bin/git --version 2>&1 || true)"
  case "$probe" in
    *"agreed to the Xcode"*|*"Xcode/iOS license"*) ;;
    *) return 0 ;;
  esac
  error "The Xcode license has not been accepted, so Homebrew cannot install anything."
  printf '  Run this, then re-run this script:\n    sudo xcodebuild -license accept\n' >&2
  exit 1
}

ensure_brew_in_path() {
  csa_require_xcode_license
  if has_command brew; then return 0; fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

# ── Snapshot ────────────────────────────────────────────────────────

LOG_DIR="$HOME/Library/Logs/CSA-DesktopSetup"
TIMESTAMP="$(date +%Y%m%dT%H%M%S)"
SNAPSHOT_FILE="$LOG_DIR/pre-update-${TIMESTAMP}.txt"
PIP_FREEZE_FILE="$LOG_DIR/pre-update-${TIMESTAMP}-pip-freeze.txt"

snapshot() {
  mkdir -p "$LOG_DIR"

  info "Saving pre-update snapshot"

  {
    echo "=== CSA DesktopSetup Pre-Update Snapshot ==="
    echo "Date: $(date)"
    echo "macOS: $(sw_vers -productVersion)"
    echo ""

    echo "──── Homebrew Formulas ────"
    if has_command brew; then
      brew list --formula --versions 2>/dev/null || echo "(none)"
    else
      echo "(Homebrew not installed)"
    fi
    echo ""

    echo "──── Homebrew Casks ────"
    if has_command brew; then
      brew list --cask --versions 2>/dev/null || echo "(none)"
    else
      echo "(Homebrew not installed)"
    fi
    echo ""

    echo "──── npm Global Packages ────"
    if has_command npm; then
      npm list -g --depth=0 2>/dev/null || echo "(none)"
    else
      echo "(npm not installed)"
    fi
    echo ""

    echo "──── pip Packages ────"
    if has_command python3; then
      echo "Python: $(python3 --version 2>/dev/null || echo unknown)"
      [[ -n "${VIRTUAL_ENV:-}" ]] && echo "venv: $VIRTUAL_ENV"
      echo ""
      python3 -m pip list 2>/dev/null || echo "(none)"
    else
      echo "(Python not available)"
    fi
    echo ""
  } > "$SNAPSHOT_FILE"

  # Save pip freeze separately for easy rollback
  if has_command python3; then
    {
      echo "# CSA DesktopSetup pip snapshot — $(date)"
      echo "# Python: $(python3 --version 2>/dev/null || echo unknown)"
      [[ -n "${VIRTUAL_ENV:-}" ]] && echo "# venv: $VIRTUAL_ENV"
      echo "# Restore with: python3 -m pip install -r $(basename "$PIP_FREEZE_FILE")"
      echo ""
      python3 -m pip freeze 2>/dev/null
    } > "$PIP_FREEZE_FILE"
  fi

  success "Snapshot saved: $SNAPSHOT_FILE"
}

# ── Preflight ───────────────────────────────────────────────────────

preflight() {
  ensure_brew_in_path

  echo ""
  info "Update plan:"
  echo ""

  # Homebrew
  if has_command brew; then
    info "Checking Homebrew for outdated packages..."
    echo ""

    local outdated_formulas outdated_casks
    outdated_formulas=$(brew outdated --formula --verbose 2>/dev/null || true)
    outdated_casks=$(brew outdated --cask --verbose 2>/dev/null || true)

    if [[ -n "$outdated_formulas" ]]; then
      echo "  Homebrew formulas to upgrade:"
      echo "$outdated_formulas" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  Homebrew formulas: all up to date"
    fi
    echo ""

    if [[ -n "$outdated_casks" ]]; then
      echo "  Homebrew casks to upgrade:"
      echo "$outdated_casks" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  Homebrew casks: all up to date"
    fi
  else
    echo "  Homebrew: not installed (skipping)"
  fi
  echo ""

  # npm
  if has_command npm; then
    local outdated_npm
    outdated_npm=$(npm outdated -g 2>/dev/null || true)

    if [[ -n "$outdated_npm" ]]; then
      echo "  npm global packages to update:"
      echo "$outdated_npm" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  npm global packages: all up to date"
    fi
  else
    echo "  npm: not installed (skipping)"
  fi
  echo ""

  # ~/.default_venv (update_default_venv): its repair and why, or that there is none. Never
  # created here.
  echo "  Default venv: $(default_venv_plan --no-create)"
  echo ""

  # pip
  if has_command python3; then
    local outdated_pip venv_note=""
    outdated_pip=$(python3 -m pip list --outdated --format=columns 2>/dev/null || true)
    [[ -n "${VIRTUAL_ENV:-}" ]] && venv_note=" (venv: $(basename "$VIRTUAL_ENV"))"

    if [[ -n "$outdated_pip" ]]; then
      echo "  pip packages to update${venv_note}:"
      echo "$outdated_pip" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  pip packages${venv_note}: all up to date"
    fi
  else
    echo "  Python: not available (skipping pip)"
  fi
  echo ""

  # Claude Code
  if has_command claude; then
    echo "  Claude Code: will run \`claude update\`"
  else
    echo "  Claude Code: not installed (skipping)"
  fi
  echo ""

  # Plugin marketplaces
  if has_command claude; then
    echo "  Plugin marketplaces: refresh registered, add accessible CSA repos"
    install_plugins_preview
    echo "  CSA MCP server     : register $CSA_MCP_NAME if your GitHub account has CSA-Internal access"
    echo "                       sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
    # DERIVED, for the reason the marketplace line is. This preview named none of the four
    # internal servers while installing all four, so a person agreed to a list that omitted
    # every one of them. Enumerated so the plan and the run cannot disagree.
    echo "  Internal MCP servers install/upgrade ${#CSA_INTERNAL_SETUPS[@]} servers on Python ${CSA_PYTHON_PREFERRED} (standard build) if your GitHub account has CSA-Internal access"
    local setup_name
    for setup_name in "${CSA_INTERNAL_SETUPS[@]}"; do
      echo "                       ${setup_name%-setup.sh}"
    done
    echo "                       each prints what it may do before it is used"
    echo ""
    # Windows's plan has named this file since the snapshot was added; macOS's did
    # not, so a macOS user was never told a file was being written - while
    # $SNAPSHOT_FILE is written here AND printed in the closing summary. Found by
    # check-plan-covers-steps.py once it covered all six scripts rather than two.
    echo "  Snapshot           : $SNAPSHOT_FILE"
    echo ""
  fi
}

# ── Update steps ────────────────────────────────────────────────────

update_brew() {
  if ! has_command brew; then return 0; fi

  info "Updating Homebrew"
  brew update || warn "brew update failed; continuing"

  # Never --greedy. Without it, `brew upgrade` skips casks that update themselves, and the
  # desktop AI apps all do (claude, chatgpt, google-gemini; Copilot is not a cask at all) - so
  # this never replaces a running desktop app, and there is nothing to ask anyone to quit.
  # windows-update.ps1 has to ask, because `winget upgrade --all` makes no such distinction.
  info "Upgrading Homebrew packages"
  brew upgrade || warn "brew upgrade failed; continuing"

  info "Cleaning up old versions"
  brew cleanup || true
}

update_npm() {
  if ! has_command npm; then return 0; fi

  info "Updating global npm packages"
  csa_npm update -g || warn "npm update -g failed; continuing"
}

update_pip() {
  if ! has_command python3; then return 0; fi

  local venv_note=""
  [[ -n "${VIRTUAL_ENV:-}" ]] && venv_note=" (venv: $(basename "$VIRTUAL_ENV"))"

  info "Updating pip itself${venv_note}"
  python3 -m pip install --upgrade pip || warn "pip upgrade failed; continuing"

  info "Updating pip packages${venv_note}"
  local outdated
  outdated=$(python3 -m pip list --outdated --format=json 2>/dev/null || echo "[]")

  if [[ "$outdated" == "[]" ]] || [[ -z "$outdated" ]]; then
    echo "  All pip packages are up to date"
    return 0
  fi

  # Extract package names and upgrade them one at a time
  local pkg_names
  pkg_names=$(echo "$outdated" | python3 -c "import sys, json; print(' '.join(p['name'] for p in json.load(sys.stdin)))" 2>/dev/null || true)

  if [[ -z "$pkg_names" ]]; then return 0; fi

  for pkg in $pkg_names; do
    info "  Upgrading $pkg"
    python3 -m pip install --upgrade "$pkg" 2>/dev/null || warn "Failed to upgrade $pkg; continuing"
  done
}

# Install packages into a venv that may not contain pip.
#
# `"$venv/bin/python3" -m pip` assumed pip was there and failed with "No module named pip" on a
# real machine (#86), leaving csa-preflight broken while the warning named the packages rather
# than the cause. A venv created by `uv venv` has NO pip - uv omits it by design - and this
# script installs uv itself a few steps earlier, so a uv-made venv is an ordinary state here,
# not an exotic one. The `[[ ! -x ... ]]` guard above exists precisely to accept a venv this
# script did not create, which is the case that has no pip.
#
# `uv pip install --python <interpreter>` targets an existing venv without needing pip inside it,
# and is substantially faster. `ensurepip` is the fallback for a machine where the uv install
# failed; a venv built by `python3 -m venv` already has pip and takes neither path.
#
# $1 venv python   $2... packages
csa_venv_pip_install() {
  local vpy="$1"; shift
  if has_command uv; then
    if uv pip install --quiet --python "$vpy" "$@"; then return 0; fi
    warn "uv could not install into $vpy - falling back to pip"
  fi
  if ! "$vpy" -m pip --version >/dev/null 2>&1; then
    if ! "$vpy" -m ensurepip --upgrade >/dev/null 2>&1; then
      warn "$vpy has no pip and ensurepip failed - cannot install $*"
      return 1
    fi
  fi
  "$vpy" -m pip install --quiet --upgrade "$@"
}

# ── The CSA Python ───────────────────────────────────────────────────
# ONE interpreter, named by one resolver, verified by running it (#179). The resolver it
# replaces returned the first PATH or uv interpreter that cleared a floor, and on a real Mac
# that was Homebrew's 3.15 (PATH python3) or uv's free-threaded python3.14t: when 3.14t is the
# only uv-managed 3.14, `uv python find 3.14` returns it (measured, uv 0.13.7). All four CSA
# servers landed on 3.14t that way. So nothing here trusts a name, a version string or
# `uv tool list --show-python` (which prints the same thing for both builds): every candidate
# is run and asked.
#
# KEEP SELF-CONTAINED: these three functions depend only on has_command, info, warn and
# CSA_PYTHON_PREFERRED, so they can be shared byte-identically with another script.

# $1 interpreter. Exit 0 iff it runs, is CSA_PYTHON_PREFERRED, and is the standard build
# (sysconfig Py_GIL_DISABLED falsy - it is 1 on 3.14t). Silent. -I so neither the caller's
# working directory nor PYTHONPATH can shadow sysconfig.
python_is_csa_build() {
  local got
  [[ -n "${1:-}" ]] || return 1
  got="$("$1" -I -c 'import sys, sysconfig; print("%d.%d" % sys.version_info[:2], 1 if sysconfig.get_config_var("Py_GIL_DISABLED") else 0)' 2>/dev/null)" || return 1
  if [[ "$got" == "${CSA_PYTHON_PREFERRED} 0" ]]; then
    return 0
  fi
  return 1
}

# Prints the CSA Python's path, or exits 1. NEVER installs anything: the preflight calls this
# before the person has agreed to anything.
#
#   1. `uv python find --system --managed-python`. --system is REQUIRED: measured on uv 0.13.7,
#      with VIRTUAL_ENV set it otherwise returns the active venv's python, which would make a
#      venv the base of everything built on this.
#   2. every `variant == "default"` CPython in uv's JSON listing. Parsed by Python, not awk,
#      because a path may contain a space. uv 0.13.7 may report its ~/.local/bin shim as `path`
#      with the managed interpreter as `symlink`; the managed one is tried first, and either
#      is accepted only if it verifies, so nothing depends on whether a shim exists.
#   3. Homebrew's opt/python@X.Y, which is stable across `brew upgrade` (its Cellar target is not).
#
# A path is returned as uv printed it - the minor-version directory cpython-3.14-<platform>,
# a link uv points at the current patch release - never resolved to the patch directory
# (cpython-3.14.10-<platform>), which a patch upgrade replaces.
find_csa_python() {
  local first="" listed="" cands="" parser cand prefix
  local parse='import json, sys
for e in json.loads(sys.argv[1]):
    if e.get("variant") == "default" and e.get("implementation") == "cpython":
        for p in (e.get("symlink"), e.get("path")):
            if p:
                print(p)'
  if has_command uv; then
    first="$(uv python find --system --managed-python "$CSA_PYTHON_PREFERRED" 2>/dev/null)" || first=""
    if [[ -n "$first" ]] && python_is_csa_build "$first"; then
      printf '%s\n' "$first"
      return 0
    fi
    listed="$(uv python list --only-installed --managed-python "$CSA_PYTHON_PREFERRED" --output-format json 2>/dev/null)" || listed=""
    if [[ -n "$listed" ]]; then
      # Any Python that runs can parse JSON, including a 3.14t that failed the check above.
      for parser in "$first" /usr/bin/python3; do
        [[ -n "$parser" ]] || continue
        if cands="$("$parser" -I -c "$parse" "$listed" 2>/dev/null)"; then
          break
        fi
        cands=""
      done
      while IFS= read -r cand; do
        if [[ -n "$cand" ]] && python_is_csa_build "$cand"; then
          printf '%s\n' "$cand"
          return 0
        fi
      done <<< "$cands"
    fi
  fi
  if has_command brew; then
    prefix="$(brew --prefix 2>/dev/null)" || prefix=""
    cand="${prefix}/opt/python@${CSA_PYTHON_PREFERRED}/bin/python${CSA_PYTHON_PREFERRED}"
    if [[ -n "$prefix" ]] && python_is_csa_build "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  fi
  return 1
}

# Provisions the CSA Python and prints its path - ONLY the path goes to stdout, so a caller can
# write py="$(ensure_csa_python)"; every other line goes to stderr. Exits 1, with a warning,
# when neither uv nor Homebrew could provide one.
#
# `uv python install` runs even when a 3.14 is already there, because "a 3.14" may be only the
# free-threaded one and installing the standard build beside it is the fix: once both exist,
# uv's own resolution prefers the standard build (measured, uv 0.13.7). A no-op when present.
# Never `3.14+gil`: uv 0.13.7 never downloads for a +gil request, so it fails on a clean machine.
ensure_csa_python() {
  local found
  if has_command uv; then
    info "Ensuring Python ${CSA_PYTHON_PREFERRED} (uv-managed, standard build)" >&2
    uv python install "$CSA_PYTHON_PREFERRED" >&2 \
      || warn "uv could not install Python ${CSA_PYTHON_PREFERRED}"
  fi
  if found="$(find_csa_python)"; then
    printf '%s\n' "$found"
    return 0
  fi
  if has_command brew; then
    info "Installing python@${CSA_PYTHON_PREFERRED} via Homebrew, the fallback" >&2
    brew install "python@${CSA_PYTHON_PREFERRED}" >&2 \
      || warn "Homebrew could not install python@${CSA_PYTHON_PREFERRED}"
    if found="$(find_csa_python)"; then
      printf '%s\n' "$found"
      return 0
    fi
  fi
  warn "No Python ${CSA_PYTHON_PREFERRED} standard build: neither uv nor Homebrew could provide one"
  return 1
}

# ~/.default_venv is where macos-ai-tools.sh puts the document-pipeline preflight deps, because
# Homebrew's python3 is PEP 668 externally-managed; document-pipeline's launchers probe it.
CSA_VENV="$HOME/.default_venv"
# The same packages macos-ai-tools.sh installs there (see its comments): the core, which must
# install, and markitdown[all]>=0.1.9 (#157), best effort, because it cannot install on an Intel Mac.
CSA_DOC_PY_DEPS=(pyyaml pymupdf csa-google-workspace)
CSA_DOC_PY_DEPS_OPTIONAL=("markitdown[all]>=0.1.9")

# $1 a venv's python. Installs CSA_DOC_PY_DEPS_OPTIONAL, best effort: a failure warns, naming the
# cause where it is known, and returns 0, so it never blocks a build, the flip or anything after.
# With uv, `uv pip` only - pip would resolve the same index and fail the same way, slower.
#
# Why markitdown is optional (measured on PyPI 2026-11-10): markitdown 0.1.9 requires magika
# unconditionally, magika requires onnxruntime, and onnxruntime 1.31.1 publishes no macOS x86_64
# wheel for any Python. Installed in one call with the core deps, it made an Intel Mac unable to
# build ~/.default_venv-3.14 at all.
csa_venv_optional_install() {
  if has_command uv; then
    if uv pip install --quiet --python "$1" "${CSA_DOC_PY_DEPS_OPTIONAL[@]}"; then
      return 0
    fi
  elif csa_venv_pip_install "$1" "${CSA_DOC_PY_DEPS_OPTIONAL[@]}"; then
    return 0
  fi
  if [[ "$(uname -m 2>/dev/null)" == "x86_64" ]]; then
    warn "Skipped ${CSA_DOC_PY_DEPS_OPTIONAL[*]}: markitdown needs onnxruntime, which publishes no Intel-Mac wheels. The other document deps are installed"
  else
    warn "Skipped ${CSA_DOC_PY_DEPS_OPTIONAL[*]}: it did not install (see above). The other document deps are installed"
  fi
  return 0
}

# ── ~/.default_venv: a link to a versioned venv ─────────────────────
# document-pipeline's bash launchers probe $HOME/.default_venv/bin/python3. It is a RELATIVE link
# to a versioned directory, ${CSA_VENV}-${CSA_PYTHON_PREFERRED} (the CINO's decision, 2026-11-10,
# #179): a repair builds the new directory and flips the link, so every old directory is kept
# for rollback and the one an active shell is using never moves (D1). Before that it was a real
# directory built on whatever python3 PATH offered - Homebrew's 3.15, a 3.13, uv's free-threaded
# 3.14t, or a Homebrew Cellar path the next `brew upgrade` deletes.
#
# KEEP IN SYNC: CSA_VENV, CSA_DOC_PY_DEPS, CSA_DOC_PY_DEPS_OPTIONAL, the three CSA-Python
# functions above, csa_venv_optional_install and every function from venv_cfg_get to
# ensure_default_venv are duplicated byte-identically in macos-update.sh
# (tools/check-duplication.py; tests/test_python_pins.py for the arrays).
# tests/test_venv_replacement.py runs them.

# $1 pyvenv.cfg, $2 key. Prints the value - everything after the first "=", trimmed, inner
# spaces kept, because a home path may contain one - or exits 1. `uv venv` writes version_info,
# `python -m venv` writes version.
venv_cfg_get() {
  local line key val
  if [[ ! -f "$1" ]]; then
    return 1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" != *=* ]]; then
      continue
    fi
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#"${key%%[![:space:]]*}"}"
    if [[ "$key" == "$2" ]]; then
      val="${line#*=}"
      val="${val#"${val%%[![:space:]]*}"}"
      val="${val%"${val##*[![:space:]]}"}"
      printf '%s\n' "$val"
      return 0
    fi
  done < "$1"
  return 1
}

# $1 a venv directory. Prints the ONE reason it must be rebuilt and exits 0; exits 1, silently,
# when it is absent or sound. Sound: bin/python3 runs, is CSA_PYTHON_PREFERRED, is the standard
# build, and was not recorded on a Homebrew Cellar path.
#
# A dangling bin/python3 - its interpreter deleted, so -L is true and -x false - is BROKEN, never
# absent. The Cellar test reads the RECORDED path, never realpath: the first symlink hop out of
# the venv, or pyvenv.cfg's home. Homebrew's opt/python@X.Y is stable across `brew upgrade` though
# its realpath is in the Cellar; only a recorded path containing /Cellar/ is deleted by the next
# upgrade.
venv_rebuild_reason() {
  local dir="${1%/}" got cur hop rec="" home="" n=0
  if [[ ! -e "$dir" && ! -L "$dir" ]]; then
    return 1
  fi
  if [[ ! -x "$dir/bin/python3" ]]; then
    echo "its Python no longer exists"
    return 0
  fi
  got="$("$dir/bin/python3" -I -c 'import sys, sysconfig; print("%d.%d" % sys.version_info[:2], 1 if sysconfig.get_config_var("Py_GIL_DISABLED") else 0)' 2>/dev/null)" || got=""
  case "$got" in
    [0-9]*.[0-9]*" "[01]) ;;
    *)
      echo "its Python does not run"
      return 0
      ;;
  esac
  if [[ "${got% *}" != "$CSA_PYTHON_PREFERRED" ]]; then
    echo "it is Python ${got% *}, not ${CSA_PYTHON_PREFERRED}"
    return 0
  fi
  if [[ "${got#* }" != "0" ]]; then
    echo "it is the free-threaded build"
    return 0
  fi
  cur="$dir/bin/python3"
  while [[ -L "$cur" && $n -lt 16 ]]; do
    hop="$(readlink "$cur")" || break
    case "$hop" in
      /*) ;;
      *) hop="${cur%/*}/$hop" ;;
    esac
    case "$hop" in
      "$dir"/*) cur="$hop" ;;
      *)
        rec="$hop"
        break
        ;;
    esac
    n=$((n + 1))
  done
  home="$(venv_cfg_get "$dir/pyvenv.cfg" home)" || home=""
  if [[ "$rec" == */Cellar/* || "$home" == */Cellar/* ]]; then
    echo "it is built on a Homebrew Cellar path, which the next brew upgrade deletes"
    return 0
  fi
  return 1
}

# $1 a venv directory, $2 a suffix for a name collision. Prints where the directory goes when it
# is moved aside: ${CSA_VENV}-<X.Y> from pyvenv.cfg (version_info, or version), or
# ${CSA_VENV}-unknown, plus -<$2> when that name is taken. ${CSA_VENV}-${CSA_PYTHON_PREFERRED} is
# always taken: it is the venv being built.
venv_aside_name() {
  local v="" major minor name
  v="$(venv_cfg_get "$1/pyvenv.cfg" version_info)" || v="$(venv_cfg_get "$1/pyvenv.cfg" version)" || v=""
  name="${CSA_VENV}-unknown"
  if [[ "$v" == [0-9]*.[0-9]* ]]; then
    major="${v%%.*}"
    minor="${v#*.}"
    minor="${minor%%.*}"
    if [[ -n "$minor" && "$major$minor" != *[!0-9]* ]]; then
      name="${CSA_VENV}-${major}.${minor}"
    fi
  fi
  if [[ -e "$name" || -L "$name" || "$name" == "${CSA_VENV}-${CSA_PYTHON_PREFERRED}" ]]; then
    name="${name}-$2"
  fi
  printf '%s\n' "$name"
}

# $1 a Python to run, $2 the old venv, $3 the new one. Prints, on one line, the top-level
# packages the old venv had that the new one lacks - what a rebuild did not bring back. Read
# from the old venv's metadata, so it works when the old venv's own interpreter is gone.
venv_extra_packages() {
  local code='import glob, os, re, sys
from importlib import metadata
def norm(s):
    return re.sub(r"[-_.]+", "-", s).lower()
def dists(venv):
    found = dict()
    for d in metadata.distributions(path=glob.glob(os.path.join(venv, "lib", "python*", "site-packages"))):
        try:
            name = d.metadata["Name"]
        except Exception:
            name = None
        if name:
            found.setdefault(norm(name), (name, d))
    return found
old, new = dists(sys.argv[1]), dists(sys.argv[2])
gone = dict((k, v) for k, v in old.items() if k not in new and k not in ("pip", "setuptools", "wheel"))
needed = set()
for name, d in gone.values():
    for r in d.requires or []:
        m = re.match(r"[A-Za-z0-9._-]+", r)
        if m:
            needed.add(norm(m.group(0)))
print(" ".join(sorted(v[0] for k, v in gone.items() if k not in needed)))'
  "$1" -I -c "$code" "$2" "$3" 2>/dev/null
}

# Classifies $CSA_VENV and changes nothing. Prints "<state>TAB<path>TAB<reason>", "-" for none:
#   ok          a link to a sound ${CSA_VENV}-${CSA_PYTHON_PREFERRED}
#   rebuild     a link to ${CSA_VENV}-${CSA_PYTHON_PREFERRED}, which is not sound
#   flip        a link to anything else that will not do: an older or newer ${CSA_VENV}-<X.Y>, a
#               target that no longer exists, or a broken venv of the person's own (<path>)
#   foreign-ok  a link this installer did not make, to a sound venv: left alone
#   migrate     a real directory, from before the versioned layout
#   create      nothing there
#   other       neither a directory nor a link
# One classifier, so the plan row (default_venv_plan) and the repair (ensure_default_venv) cannot
# describe two different decisions.
default_venv_state() {
  local versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}" raw target name reason
  local xy='^[0-9]+[.][0-9]+$'
  if [[ -L "$CSA_VENV" ]]; then
    raw="$(readlink "$CSA_VENV")" || raw=""
    case "$raw" in
      /*) target="$raw" ;;
      *) target="${CSA_VENV%/*}/$raw" ;;
    esac
    if [[ -e "$versioned" && "$CSA_VENV" -ef "$versioned" ]]; then
      if reason="$(venv_rebuild_reason "$versioned")"; then
        printf 'rebuild\t%s\t%s\n' "$versioned" "$reason"
      else
        printf 'ok\t%s\t-\n' "$versioned"
      fi
      return 0
    fi
    if [[ ! -e "$target" ]]; then
      printf 'flip\t%s\t%s\n' "$target" "it no longer exists"
      return 0
    fi
    name="${target##*/}"
    if reason="$(venv_rebuild_reason "$target")"; then
      printf 'flip\t%s\t%s\n' "$target" "$reason"
    elif [[ "$name" == "${CSA_VENV##*/}-"* && "${name#"${CSA_VENV##*/}"-}" =~ $xy && "${target%/*}" -ef "${CSA_VENV%/*}" ]]; then
      printf 'flip\t%s\t%s\n' "$target" "it is not ${versioned##*/}"
    else
      printf 'foreign-ok\t%s\t-\n' "$target"
    fi
    return 0
  fi
  if [[ -d "$CSA_VENV" ]]; then
    reason="$(venv_rebuild_reason "$CSA_VENV")" || reason="-"
    printf 'migrate\t%s\t%s\n' "$CSA_VENV" "$reason"
    return 0
  fi
  if [[ -e "$CSA_VENV" ]]; then
    printf 'other\t%s\t-\n' "$CSA_VENV"
    return 0
  fi
  printf 'create\t%s\t-\n' "$versioned"
}

# The plan row: what ensure_default_venv will do on this machine, and why. Changes nothing.
# $1 --no-create gives the wording for -update, which never creates a venv and installs no Python.
#
# It asks find_csa_python, as the run does first, because the Python decides the outcome: -update
# with none found changes nothing, and a Cellar-pinned venv is not rebuilt onto a Python that is on
# a Cellar path too. A plan that said "rebuild" there named a step that never runs. find_csa_python
# never installs, so the plan can ask it before anyone has agreed to anything.
default_venv_plan() {
  local versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}"
  local deps="${CSA_DOC_PY_DEPS[*]} (then ${CSA_DOC_PY_DEPS_OPTIONAL[*]}, best effort)"
  local state action old reason build="" vr aside fix kept="" py="" leave=""
  state="$(default_venv_state)" || state=""
  IFS=$'\t' read -r action old reason <<< "$state"
  if [[ "$reason" == "-" ]]; then
    reason=""
  fi
  if [[ ! -e "$versioned" && ! -L "$versioned" ]]; then
    build="build $versioned on Python ${CSA_PYTHON_PREFERRED}"
  elif vr="$(venv_rebuild_reason "$versioned")"; then
    build="rebuild $versioned ($vr), keeping the old one beside it"
  fi
  case "$action" in
    ok)
      printf '%s\n' "install/refresh $deps in $CSA_VENV (Python ${CSA_PYTHON_PREFERRED}, standard build)"
      return 0
      ;;
    foreign-ok)
      printf '%s\n' "install/refresh $deps in $CSA_VENV, your own link to $old (sound, left as it is)"
      return 0
      ;;
    other)
      printf '%s\n' "skip: $CSA_VENV is not a directory or a link to one, and is left as it is"
      return 0
      ;;
    create)
      if [[ "${1:-}" == "--no-create" ]]; then
        printf '%s\n' "none at $CSA_VENV - this script never creates one (macos-ai-tools.sh does)"
        return 0
      fi
      fix="${build:-use $versioned}, link $CSA_VENV to it"
      ;;
    migrate)
      aside="$(venv_aside_name "$CSA_VENV" "<timestamp>")" || aside="${CSA_VENV}-<X.Y>"
      fix="${build:+$build, }move the directory $CSA_VENV to $aside${reason:+ ($reason)}, link $CSA_VENV to ${versioned##*/}"
      ;;
    flip)
      if [[ -e "$old" ]]; then
        kept=", which is kept"
      fi
      fix="${build:+$build, }link $CSA_VENV to ${versioned##*/} instead of $old ($reason)$kept"
      ;;
    rebuild)
      fix="rebuild $versioned ($reason), keeping the old one beside it"
      ;;
    *)
      return 0
      ;;
  esac
  py="$(find_csa_python)" || py=""
  if [[ -z "$py" && "${1:-}" == "--no-create" ]]; then
    leave="there is no Python ${CSA_PYTHON_PREFERRED} standard build installed, and this script installs none - run macos-ai-tools.sh to repair it"
  elif [[ -n "$py" && "$reason" == *Cellar* && "$py" == */Cellar/* ]]; then
    leave="the only Python ${CSA_PYTHON_PREFERRED} is on a Cellar path too"
  fi
  if [[ -n "$leave" ]]; then
    # The same test the callers apply before installing the deps: sound, or Cellar-pinned (which
    # still runs today).
    if [[ -z "$reason" || "$reason" == *Cellar* ]]; then
      printf '%s\n' "leave $CSA_VENV as it is${reason:+ ($reason)}: $leave; install/refresh $deps in it"
    else
      printf '%s\n' "leave $CSA_VENV as it is ($reason): $leave; nothing is installed into it"
    fi
    return 0
  fi
  if [[ -z "$py" ]]; then
    fix="on the Python ${CSA_PYTHON_PREFERRED} the Python row installs: $fix"
  fi
  printf '%s\n' "$fix; install/refresh $deps in it"
}

# Makes ${CSA_VENV}-${CSA_PYTHON_PREFERRED} a sound venv on $1 (the CSA Python), with
# CSA_DOC_PY_DEPS installed, then CSA_DOC_PY_DEPS_OPTIONAL tried. Prints the path a broken one was
# moved to, if any - ONLY that goes to stdout. Exits 1, with a warning and nothing changed, when it
# cannot. The optional set never decides that: it is tried quietly after the core, and a failure
# is reported once, by the caller's own attempt at the final path (install_doc_python_deps,
# update_default_venv), which also covers a venv that needed no build.
#
#   absent  `uv venv --seed` straight at the final path (`python -m venv` without uv).
#   broken  BUILD FIRST, SWAP LAST: `uv venv --seed --relocatable` at .new-$$, the deps with
#           `uv pip` only, then the broken one renamed to .broken-<ts> and the new one into place.
#           Measured: a venv built at one path and renamed breaks `activate` and every console
#           script, which hardcode the creation path. --relocatable survives the rename for the
#           seed scripts and for scripts `uv pip` installs, but NOT for one the venv's own pip
#           installs (exit 127) - so csa_venv_pip_install, whose fallback is that pip, is never
#           used here. Without uv there is no relocatable build: the broken one is renamed away
#           first and `python -m venv` builds at the final path, and a failure puts it back.
# A build whose deps failed is removed: a replacement that cannot do the job is not one, and the
# venv it would replace may still serve csa-preflight.
default_venv_build() {
  local py="$1" versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}" reason new broken
  if [[ ! -e "$versioned" && ! -L "$versioned" ]]; then
    info "Building $versioned on $py" >&2
    if has_command uv; then
      if uv venv --quiet --seed --python "$py" "$versioned" >&2 \
        && csa_venv_pip_install "$versioned/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
        csa_venv_optional_install "$versioned/bin/python3" >/dev/null 2>&1
        return 0
      fi
    elif "$py" -m venv "$versioned" >&2 \
      && csa_venv_pip_install "$versioned/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
      csa_venv_optional_install "$versioned/bin/python3" >/dev/null 2>&1
      return 0
    fi
    rm -rf "$versioned"
    warn "Could not build $versioned - nothing else was changed"
    return 1
  fi
  if ! reason="$(venv_rebuild_reason "$versioned")"; then
    return 0
  fi
  broken="${versioned}.broken-$(date +%Y%m%d%H%M%S)"
  info "Rebuilding $versioned on $py: $reason" >&2
  if has_command uv; then
    new="${versioned}.new-$$"
    rm -rf "$new"
    if ! uv venv --quiet --seed --relocatable --python "$py" "$new" >&2 \
      || ! uv pip install --quiet --python "$new/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
      rm -rf "$new"
      warn "Could not build a replacement for $versioned - leaving it exactly as it was"
      return 1
    fi
    uv pip install --quiet --python "$new/bin/python3" "${CSA_DOC_PY_DEPS_OPTIONAL[@]}" >/dev/null 2>&1 || true
    if ! mv "$versioned" "$broken"; then
      rm -rf "$new"
      warn "Could not move $versioned aside - leaving it exactly as it was"
      return 1
    fi
    if ! mv "$new" "$versioned"; then
      mv "$broken" "$versioned" || true
      rm -rf "$new"
      warn "Could not move the replacement into place - $versioned is as it was"
      return 1
    fi
  else
    if ! mv "$versioned" "$broken"; then
      warn "Could not move $versioned aside - leaving it exactly as it was"
      return 1
    fi
    if ! "$py" -m venv "$versioned" >&2 \
      || ! csa_venv_pip_install "$versioned/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
      rm -rf "$versioned"
      mv "$broken" "$versioned" || true
      warn "Could not rebuild $versioned - the old one is back, exactly as it was"
      return 1
    fi
    csa_venv_optional_install "$versioned/bin/python3" >/dev/null 2>&1
  fi
  warn "$versioned rebuilt on $py ($reason); the previous one is kept at $broken"
  printf '%s\n' "$broken"
}

# Leaves $CSA_VENV a RELATIVE link to a sound ${CSA_VENV}-${CSA_PYTHON_PREFERRED} on the CSA
# Python, repairing whatever default_venv_state found and keeping every old directory. Returns 0
# always: document deps are never worth the rest of the run.
#   --no-create  (-update) repair what exists, never create one, never install a Python:
#                find_csa_python only, so no Homebrew fallback either (D4).
# Otherwise find_csa_python first and ensure_csa_python only when it finds nothing, because
# install_python has just run ensure_csa_python and a second install would announce itself twice.
#
# The flip is `ln -sfn` then `mv -h`. -h is REQUIRED: measured on macOS, a plain `mv` onto a link
# to a directory exits 0, leaves the link unchanged and drops the new link INSIDE the old target.
# `ln -sfn` overwrites a leftover .link-new. A real directory is renamed aside first, so the gap is
# one rename. ~/.zshrc is never edited: its `[ ! -d "$HOME/.default_venv" ]` follows the link.
#
# Rebuilt even when it is the active venv (D1). $VIRTUAL_ENV is compared with -ef, never as a
# string: `activate` records the creation path (~/.default_venv-3.14), and shells opened before
# the migration hold ~/.default_venv. The active shell's directory never moves - or, for a real
# directory, its path now resolves through the link - so nothing it holds dangles; it gets a
# to-do to open a new terminal.
ensure_default_venv() {
  local create=1 versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}" state action old reason
  local what py="" broken="" aside="" why="" active=0 v extras=""
  if [[ "${1:-}" == "--no-create" ]]; then
    create=0
  fi
  state="$(default_venv_state)" || state=""
  IFS=$'\t' read -r action old reason <<< "$state"
  if [[ "$reason" != "-" ]]; then
    why=" ($reason)"
  fi
  case "$action" in
    ok)
      return 0
      ;;
    foreign-ok)
      info "$CSA_VENV links to $old, which this installer did not make; it is a sound Python ${CSA_PYTHON_PREFERRED} venv, so it is left as it is"
      return 0
      ;;
    other)
      warn "$CSA_VENV is not a directory or a link to one - left as it is"
      return 0
      ;;
    create)
      if [[ $create -eq 0 ]]; then
        return 0
      fi
      what="$CSA_VENV"
      ;;
    rebuild)
      what="$versioned$why"
      ;;
    flip)
      what="$CSA_VENV, a link to $old$why,"
      ;;
    migrate)
      what="$CSA_VENV, a directory from before the versioned layout$why,"
      ;;
    *)
      return 0
      ;;
  esac

  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    if [[ "$VIRTUAL_ENV" -ef "$CSA_VENV" ]]; then
      active=1
    fi
    for v in "$CSA_VENV"-*; do
      if [[ "$VIRTUAL_ENV" -ef "$v" ]]; then
        active=1
      fi
    done
  fi

  if ! py="$(find_csa_python)"; then
    py=""
    if [[ $create -eq 1 ]]; then
      py="$(ensure_csa_python)" || py=""
    fi
  fi
  if [[ -z "$py" ]]; then
    warn "$what needs a Python ${CSA_PYTHON_PREFERRED} standard build to build on, and there is no Python ${CSA_PYTHON_PREFERRED} standard build - left as it is"
    return 0
  fi
  if [[ "$reason" == *Cellar* && "$py" == */Cellar/* ]]; then
    warn "$what but the only Python ${CSA_PYTHON_PREFERRED} is on a Cellar path too - left as it is"
    return 0
  fi

  if ! broken="$(default_venv_build "$py")"; then
    return 0
  fi

  if [[ "$action" == "migrate" ]]; then
    aside="$(venv_aside_name "$CSA_VENV" "$(date +%Y%m%d%H%M%S)")" || aside=""
    if [[ -z "$aside" ]] || ! mv "$CSA_VENV" "$aside"; then
      warn "Could not move $CSA_VENV aside - left as it is; $versioned is ready and the next run links it"
      return 0
    fi
    old="$aside"
  fi
  if [[ "$action" == "rebuild" ]]; then
    old="$broken"
  else
    if ! { ln -sfn "${versioned##*/}" "${CSA_VENV}.link-new" && mv -h "${CSA_VENV}.link-new" "$CSA_VENV"; }; then
      rm -f "${CSA_VENV}.link-new"
      if [[ -n "$aside" ]]; then
        mv "$aside" "$CSA_VENV" || true
      fi
      warn "Could not link $CSA_VENV to ${versioned##*/} - left as it was; $versioned is ready"
      return 0
    fi
    case "$action" in
      create)
        success "Created $versioned; $CSA_VENV links to it"
        ;;
      migrate)
        warn "$CSA_VENV now links to ${versioned##*/}; the directory that was there$why is kept at $aside"
        ;;
      flip)
        if [[ "$old" -ef "$versioned" ]]; then
          warn "$CSA_VENV pointed at $versioned, which no longer existed; it is rebuilt"
        elif [[ -e "$old" ]]; then
          warn "$CSA_VENV now links to ${versioned##*/}; it linked to $old$why, which is kept, not deleted"
        else
          warn "$CSA_VENV now links to ${versioned##*/}; it linked to $old, which no longer exists"
        fi
        ;;
    esac
  fi

  if [[ "$action" != "create" && -d "$old" && ! "$old" -ef "$versioned" ]]; then
    extras="$(venv_extra_packages "$py" "$old" "$versioned")" || extras=""
  fi
  if [[ -n "$extras" ]]; then
    warn "Not reinstalled from $old: $extras"
    if declare -F csa_todo_add >/dev/null && csa_todo_add 43 "Reinstall what the previous ~/.default_venv had: $extras" - "$CSA_VENV/bin/python3 -m pip install $extras"; then
      :
    else
      warn "  to reinstall them: $CSA_VENV/bin/python3 -m pip install $extras"
    fi
  fi
  if [[ $active -eq 1 ]]; then
    if declare -F csa_todo_add >/dev/null && csa_todo_add 10 "Open a new terminal to use the rebuilt ~/.default_venv" - -; then
      :
    else
      warn "Open a new terminal to use the rebuilt ~/.default_venv"
    fi
  fi
  return 0
}

# ~/.default_venv: its own main() step, BEFORE update_pip. It used to be the tail of update_pip,
# after two early returns - nothing outdated, or no package names parsed - so on an up-to-date
# machine it never ran. Repairs an existing venv, never creates one and never installs a Python
# (decision D4 of #179); then refreshes CSA_DOC_PY_DEPS in it.
update_default_venv() {
  local reason
  if [[ ! -e "$CSA_VENV" && ! -L "$CSA_VENV" ]]; then
    return 0
  fi
  ensure_default_venv --no-create
  if reason="$(venv_rebuild_reason "$CSA_VENV")" && [[ "$reason" != *Cellar* ]]; then
    warn "Not refreshing the document deps: $CSA_VENV cannot take them ($reason)"
    return 0
  fi
  info "Refreshing document deps (${CSA_DOC_PY_DEPS[*]}, then ${CSA_DOC_PY_DEPS_OPTIONAL[*]}) in $CSA_VENV"
  csa_venv_pip_install "$CSA_VENV/bin/python3" "${CSA_DOC_PY_DEPS[@]}" \
    || warn "Failed to update $CSA_VENV packages; continuing"
  csa_venv_optional_install "$CSA_VENV/bin/python3"
}

update_claude_code() {
  if ! has_command claude; then return 0; fi

  info "Updating Claude Code"
  claude update || warn "claude update failed; continuing"
}

# ── Plugin marketplaces ─────────────────────────────────────────────
# Add any CSA marketplaces the user can access but hasn't registered yet,
# then refresh all registered marketplaces from their sources. Missing gh
# or gh-auth skips the add step silently — a user who isn't in CSA-Internal
# doesn't need to see chatter about repos they can't see.

sync_plugin_marketplaces() {
  has_command claude || return 0

  # If gh is available + authenticated, add any missing accessible ones
  # silently. Otherwise skip straight to the refresh pass.
  if has_command gh && gh auth status >/dev/null 2>&1; then
    local already_added
    already_added="$(claude plugin marketplace list 2>/dev/null \
      | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')" || already_added=""

    local added=() failed=() failed_errs=()
    local repo add_err
    for repo in "${CSA_MARKETPLACES[@]}"; do
      grep -qxF "$repo" <<< "$already_added" && continue
      gh api "repos/$repo" >/dev/null 2>&1 || continue

      # Capture stderr (into add_err) so a real failure shows its reason;
      # discard stdout. `2>&1 >/dev/null` inside $(...) redirects stderr to
      # the captured stdout stream, then sends original stdout to /dev/null.
      if add_err="$(claude plugin marketplace add "$repo" 2>&1 >/dev/null)"; then
        added+=("$repo")
      else
        failed+=("$repo")
        failed_errs+=("${add_err:-<no stderr output>}")
      fi
    done

    if [[ ${#added[@]} -gt 0 ]]; then
      success "Registered new plugin marketplaces:"
      printf '  + %s\n' "${added[@]}"
    fi
    if [[ ${#failed[@]} -gt 0 ]]; then
      warn "Failed to register ${#failed[@]} marketplace(s):"
      local i
      for i in "${!failed[@]}"; do
        printf '  ! %s\n      %s\n' "${failed[$i]}" "${failed_errs[$i]}"
      done
    fi
  fi

  info "Refreshing plugin marketplaces"
  claude plugin marketplace update || warn "marketplace update failed; continuing"
}

# Register the CSA MCP server (csa-mcp) with Claude Code if missing.
# See scripts/macos-ai-tools.sh setup_csa_mcp_server for full rationale —
# silent unless we actually register, gh-probed CSA-Internal access gate,
# does not clobber existing OAuth sessions.
setup_csa_mcp_server() {
  has_command claude || return 0
  has_command gh || return 0
  gh auth status >/dev/null 2>&1 || return 0

  if claude mcp list 2>/dev/null | grep -qE "^${CSA_MCP_NAME}[: ]"; then
    return 0
  fi

  gh api "repos/$CSA_MCP_GATE_REPO" >/dev/null 2>&1 || return 0

  local add_err
  if add_err="$(claude mcp add --transport http --scope user "$CSA_MCP_NAME" "$CSA_MCP_URL" 2>&1 >/dev/null)"; then
    success "Registered Claude Code MCP server: $CSA_MCP_NAME"
    info "Run /mcp inside Claude Code to authenticate with the CSA MCP server."
    info "  sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
  else
    warn "Failed to register Claude Code MCP server '$CSA_MCP_NAME':"
    printf '      %s\n' "${add_err:-<no stderr output>}"
  fi
}

# Run CSA-internal setup that cannot live in this public repo (it carries CSA's OAuth
# client). Gated the same way as setup_csa_mcp_server: gh-probe CloudSecurityAlliance-Internal,
# and silently do nothing for anyone without access — external users of this public repo see
# no chatter about it. The fetched script is idempotent and handles its own reporting.
# NOTE: keep in sync with the copies in the other scripts, as with setup_csa_mcp_server.
setup_csa_internal_tools() {
  has_command gh || return 0
  gh auth status >/dev/null 2>&1 || return 0
  gh api "repos/$CSA_MCP_GATE_REPO" >/dev/null 2>&1 || return 0

  local name script
  # What the gate repo ACTUALLY holds. The loop below does `continue` on a script it cannot
  # fetch - deliberately, so one absent server does not stop the ones after it - which makes a
  # stale list produce NO OUTPUT AT ALL. The list is copied into six scripts and has drifted
  # twice (#85, #92); both times somebody noticed a server missing days later. See #95.
  #
  # tests/test_internal_setup_lists.py asserts the six copies agree with each other and says it
  # cannot check them against the gate repo, which is private. Here we can.
  gate_has="$(gh api "repos/${CSA_MCP_GATE_REPO}/contents/internal-setup" --jq '.[].name' 2>/dev/null \
              | grep -E '^csa-.*-setup\.sh$' || true)"
  if [[ -n "$gate_has" ]]; then
    for have in $gate_has; do
      listed=""
      for want in "${CSA_INTERNAL_SETUPS[@]}"; do
        if [[ "$want" == "$have" ]]; then listed=1; break; fi
      done
      if [[ -z "$listed" ]]; then
        warn "${have} is in the gate repo but not in this installer's list - a server nobody is installing (#95)"
      fi
    done
    for want in "${CSA_INTERNAL_SETUPS[@]}"; do
      if ! printf '%s\n' "$gate_has" | grep -qxF "$want"; then
        info "${want} is listed here but not yet in the gate repo; skipping it"
      fi
    done
  fi

  for name in "${CSA_INTERNAL_SETUPS[@]}"; do
    script="$(gh api "repos/$CSA_MCP_GATE_REPO/contents/internal-setup/$name" \
                --jq '.content' 2>/dev/null | base64 --decode 2>/dev/null)" || continue
    [[ -n "$script" ]] || continue
    # `continue`, not `return`: a setup script that is absent from the gate repo - because
    # it has not been merged yet, or was renamed - must not stop the ones after it. The
    # earlier single-script form returned, so a rename would have silently disabled every
    # server that followed.
    #
    # CSA_PYTHON_PREFERRED tells it which interpreter to install the server on. All six entry
    # scripts declare it (3.14; tests/test_python_pins.py pins them), so it is never empty
    # here, and the setup script does not have to guess. Passed identically so all three
    # copies of this function stay byte-identical, which tools/check-duplication.py
    # enforces. See CSA-Plugins#133.
    # CSA_NESTED tells the fetched script that it is running inside another CSA installer, so it
    # should leave the closing summary to this one. Without it both printed "if anything above
    # went wrong, re-run with logging on", one after the other, which reads like a stutter and
    # gives two different instructions for the same thing ("<this script>" vs "the same command").
    CSA_NESTED=1 CSA_PYTHON_PREFERRED="${CSA_PYTHON_PREFERRED:-}" bash -c "$script" || warn "CSA internal setup ($name) reported a problem (see above)"
  done
}

# ── Plugin install ──────────────────────────────────────────────────
# Fetch the public and internal plugin list files from HEAD, register
# any missing marketplaces (CSA marketplaces are gh-probed first),
# then install plugins that aren't yet installed. Silent-by-default:
# already-installed entries and inaccessible CSA marketplaces produce
# no output. Only actual installs and install errors print.
#
# This function is duplicated (by design) in scripts/macos-ai-tools.sh
# and in PowerShell form in scripts/windows-ai-tools.ps1. When fixing
# bugs here, mirror the fix in both other scripts.

PLUGIN_LIST_URL_PUBLIC="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins.txt"
PLUGIN_LIST_URL_INTERNAL="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins-internal.txt"

# Return "csa" if the marketplace should be gh-probed, "public" otherwise.
plugin_marketplace_kind() {
  case "$1" in
    claude-plugins-official|anthropic-agent-skills) echo public ;;
    *) echo csa ;;
  esac
}

# Read a plugin list (via stdin), strip blanks/comments, emit one
# <plugin>@<marketplace> entry per line.
plugin_list_entries() {
  grep -v -E '^\s*(#|$)'
}

# Preflight helper: print one line summarizing what install_plugins would
# do. Fetches the list files and diffs against `claude plugin list`.
# Intentionally cheap — no gh-probes here, so the count is "up to N";
# CSA plugins the user can't access get filtered out at actual install
# time.
install_plugins_preview() {
  if ! has_command curl; then
    echo "  Plugins              (skipped: curl not available)"
    return 0
  fi

  local public_list internal_list
  public_list="$(curl -fsSL -H 'Cache-Control: no-cache' "$PLUGIN_LIST_URL_PUBLIC" 2>/dev/null || true)"
  internal_list="$(curl -fsSL -H 'Cache-Control: no-cache' "$PLUGIN_LIST_URL_INTERNAL" 2>/dev/null || true)"

  if [[ -z "$public_list" && -z "$internal_list" ]]; then
    echo "  Plugins              (skipped: couldn't fetch plugin lists)"
    return 0
  fi

  local installed_plugins=""
  if has_command claude; then
    installed_plugins="$(claude plugin list 2>/dev/null \
      | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')" || installed_plugins=""
  fi

  local total=0 already=0 line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    total=$((total + 1))
    if [[ -n "$installed_plugins" ]] && grep -qxF "$line" <<< "$installed_plugins"; then
      already=$((already + 1))
    fi
  done < <(printf '%s\n%s\n' "$public_list" "$internal_list" | plugin_list_entries)

  local new=$((total - already))
  if [[ $total -eq 0 ]]; then
    echo "  Plugins              (list files empty)"
  elif [[ $new -eq 0 ]]; then
    echo "  Plugins              all $already defaults already installed"
  elif [[ $already -eq 0 ]]; then
    echo "  Plugins              install up to $total defaults from csa-plugins*.txt"
  else
    echo "  Plugins              install up to $new new ($already already present)"
  fi
}

install_plugins() {
  has_command claude || return 0
  has_command curl || return 0

  local public_list internal_list
  public_list="$(curl -fsSL -H 'Cache-Control: no-cache' "$PLUGIN_LIST_URL_PUBLIC" 2>/dev/null || true)"
  internal_list="$(curl -fsSL -H 'Cache-Control: no-cache' "$PLUGIN_LIST_URL_INTERNAL" 2>/dev/null || true)"

  if [[ -z "$public_list" && -z "$internal_list" ]]; then
    return 0
  fi

  # Snapshot already-registered marketplaces and already-installed plugins.
  # Use [[:space:]] (portable) rather than \s (not recognized by BSD sed).
  local registered_repos installed_plugins
  registered_repos="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')" || registered_repos=""
  installed_plugins="$(claude plugin list 2>/dev/null \
    | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')" || installed_plugins=""

  local gh_authed=0
  if has_command gh && gh auth status >/dev/null 2>&1; then gh_authed=1; fi

  local added=() failed=() failed_errs=()
  local add_err inst_err

  # Track which marketplaces/plugins we've processed. Indexed arrays
  # + string-search rather than associative arrays to stay compatible
  # with macOS bash 3.2.
  local seen_markets=() market_usable=() seen_plugins=()

  # Pass 1: ensure each referenced marketplace is registered.
  local line name market repo kind
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    name="${line%@*}"
    market="${line#*@}"

    [[ " ${seen_markets[*]:-} " == *" $market "* ]] && continue
    seen_markets+=("$market")

    repo="$(plugin_marketplace_repo "$market")"
    if [[ -z "$repo" ]]; then
      # Unknown marketplace in list file — developer mistake (list/map
      # drift). Warn so it's caught quickly; this only fires for CSA
      # editors, never for external users running the public installer.
      warn "Plugin list references unknown marketplace '$market' — update plugin_marketplace_repo"
      continue
    fi

    kind="$(plugin_marketplace_kind "$market")"

    # Already registered — mark as usable, move on.
    if grep -qxF "$repo" <<< "$registered_repos"; then
      market_usable+=("$market")
      continue
    fi

    # For CSA marketplaces: require gh + authed + accessible.
    if [[ "$kind" == csa ]]; then
      [[ $gh_authed -eq 1 ]] || continue
      gh api "repos/$repo" >/dev/null 2>&1 || continue
    fi

    # Register the marketplace.
    if add_err="$(claude plugin marketplace add "$repo" 2>&1 >/dev/null)"; then
      added+=("$repo")
      market_usable+=("$market")
    else
      failed+=("marketplace $repo")
      failed_errs+=("${add_err:-<no stderr output>}")
    fi
  done < <(printf '%s\n%s\n' "$public_list" "$internal_list" | plugin_list_entries)

  if [[ ${#added[@]} -gt 0 ]]; then
    success "Registered plugin marketplaces:"
    printf '  + %s\n' "${added[@]}"
  fi

  # Pass 2: collect plugins to install (in usable marketplace, not already
  # installed, deduped across list files).
  local pending_installs=()
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    name="${line%@*}"
    market="${line#*@}"

    [[ " ${seen_plugins[*]:-} " == *" ${name}@${market} "* ]] && continue
    seen_plugins+=("${name}@${market}")

    [[ " ${market_usable[*]:-} " == *" $market "* ]] || continue
    grep -qxF "${name}@${market}" <<< "$installed_plugins" && continue

    pending_installs+=("${name}@${market}")
  done < <(printf '%s\n%s\n' "$public_list" "$internal_list" | plugin_list_entries)

  # Pass 3: announce, then install each pending plugin with per-item
  # progress so the user sees forward motion instead of a silent wait.
  if [[ ${#pending_installs[@]} -gt 0 ]]; then
    info "Installing ${#pending_installs[@]} plugin(s):"
    local plugin
    for plugin in "${pending_installs[@]}"; do
      if inst_err="$(claude plugin install "$plugin" 2>&1 >/dev/null)"; then
        printf '  + %s\n' "$plugin"
      else
        failed+=("plugin $plugin")
        failed_errs+=("${inst_err:-<no stderr output>}")
        printf '  ! %s\n      %s\n' "$plugin" "${inst_err:-<no stderr output>}"
      fi
    done
  fi

  if [[ ${#failed[@]} -gt 0 ]]; then
    warn "Plugin install finished with ${#failed[@]} failure(s) (details above)."
  fi
}

# ── Summary ─────────────────────────────────────────────────────────

summary() {
  echo ""
  success "Update complete!"
  echo ""

  # Show current versions
  info "Current versions:"
  echo ""

  if has_command brew; then
    echo "  Homebrew .......... $(brew --version 2>/dev/null | head -n1)"
  fi
  if has_command node; then
    echo "  Node.js ........... $(node --version 2>/dev/null)"
    echo "  npm ............... $(npm --version 2>/dev/null)"
  fi
  if has_command git; then
    echo "  Git ............... $(git --version 2>/dev/null)"
  fi
  if has_command python3; then
    echo "  Python ............ $(python3 --version 2>/dev/null)"
  fi
  if has_command python3; then
    echo "  pip ............... $(python3 -m pip --version 2>/dev/null | head -n1)"
  fi
  if has_command claude; then
    echo "  Claude Code ....... $(claude --version 2>/dev/null | head -n1)"
  fi
  if has_command codex; then
    echo "  Codex CLI ......... $(codex --version 2>/dev/null | head -n1)"
  fi
  if has_command gemini; then
    echo "  Gemini CLI ........ $(gemini --version 2>/dev/null | head -n1)"
  fi

  echo ""
  info "Snapshot files (for rollback):"
  echo "  $SNAPSHOT_FILE"
  [[ -f "$PIP_FREEZE_FILE" ]] && echo "  $PIP_FREEZE_FILE"
  echo ""
  echo "  Rollback examples:"
  echo "    brew install <formula>@<version>"
  echo "    npm install -g <package>@<version>"
  [[ -f "$PIP_FREEZE_FILE" ]] && echo "    python3 -m pip install -r $PIP_FREEZE_FILE"
  echo ""

  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Update ${SCRIPT_VERSION}"

  ensure_brew_in_path
  snapshot
  preflight

  if ! confirm "Proceed with updates?"; then
    abort "Aborted."
  fi

  echo ""
  update_brew
  update_npm
  update_default_venv
  update_pip
  update_claude_code
  sync_plugin_marketplaces
  install_plugins
  setup_csa_mcp_server
  summary
  # Runs LAST, after the summary, so the internal setup's own output — including the
  # "you still need to log in" banner — is the final thing on screen instead of being
  # buried under a wall of install output the user has stopped reading.
  setup_csa_internal_tools
}

main "$@"
