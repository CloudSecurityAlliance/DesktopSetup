#!/usr/bin/env bash

# Cloud Security Alliance — Clone Repo & Launch Claude
#
# Clones a CSA GitHub repo into ~/GitHub/OrgName/RepoName and prints
# instructions to launch Claude Code.  Safe to re-run — skips clone
# if the directory already exists.
#
# Prerequisites: git, gh (authenticated), claude
# Missing tools?  Run the AI tools installer first:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
#
# Example:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- CloudSecurityAlliance-Internal/Training-Documentation

set -euo pipefail

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
SCRIPT_LABEL="clone-and-claude.sh"

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
# Line-buffered if this sed can be. Without it the parent's output sits in the pipe while a
# child process writing straight to the same file gets there first, so the log reads with the
# CSA-internal section ahead of the banner that preceded it by seconds. BSD sed spells it -l,
# GNU sed -u, and some have neither - so ask, once, rather than assume.
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

CSA_LOG_INHERITED=""
if [[ "${CSA_DEBUG:-}" == "1" ]]; then
  if [[ -n "${CSA_LOG:-}" ]]; then
    CSA_LOG_INHERITED=1
    printf '\n--- %s ---\n' "${SCRIPT_LABEL:-desktopsetup}" >> "$CSA_LOG"
  else
    CSA_LOG="${HOME}/desktopsetup-$(date +%Y%m%d-%H%M%S).log"
    ( umask 077; : > "$CSA_LOG" )      # 0600 from creation, not chmod-ed afterwards
    {
      echo "=== DesktopSetup $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
      echo "This log is REDACTED for known credential shapes, but review it before sharing."
      echo "$(uname -sr) · bash ${BASH_VERSION} · ${SCRIPT_LABEL:-desktopsetup}"
    } >> "$CSA_LOG"
  fi
  export CSA_DEBUG CSA_LOG
  # Verified on bash 3.2.57 (macOS): all output survives, including on `exit N` and on an
  # uncaught failure under `set -e`. The flush race that process substitution is known for
  # did not appear in 500-line bursts through either exit path.
  exec > >(csa_redact | tee -a "$CSA_LOG") 2>&1
  [[ -z "$CSA_LOG_INHERITED" ]] && info "debug logging to $CSA_LOG"
fi

# Printed at the end of every run, either way: the moment somebody needs the logging
# incantation is the moment the run went wrong, not later in a README they are not reading.
csa_debug_hint() {
  if [[ -n "${CSA_LOG:-}" && -z "${CSA_LOG_INHERITED:-}" ]]; then
    info "debug log: $CSA_LOG  (redacted, but review before sharing)"
  elif [[ -z "${CSA_LOG:-}" ]]; then
    printf '  if anything above went wrong, re-run with logging on:\n'
    printf '    CSA_DEBUG=1 <the same command>\n'
  fi
}


has_command() { command -v "$1" >/dev/null 2>&1; }

# ── Preconditions ───────────────────────────────────────────────────

[[ -n "${BASH_VERSION:-}" ]] || abort "Bash is required."
[[ "$(uname -s)" == "Darwin" ]] || abort "This script supports macOS only. For Windows, use the PowerShell version."

# ── Parse argument ──────────────────────────────────────────────────

REPO_SLUG="${1:-}"

if [[ -z "$REPO_SLUG" ]]; then
  echo ""
  error "No repository specified."
  echo ""
  echo "  Usage:"
  echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)\" -- ORG/REPO"
  echo ""
  echo "  Example:"
  echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)\" -- CloudSecurityAlliance-Internal/Training-Documentation"
  echo ""
  exit 1
fi

# Validate format
if [[ "$REPO_SLUG" != */* ]]; then
  abort "Repository must be in ORG/REPO format (e.g., CloudSecurityAlliance-Internal/Training-Documentation)"
fi

ORG="${REPO_SLUG%%/*}"
REPO="${REPO_SLUG##*/}"

info "Cloud Security Alliance — Clone & Claude"
echo ""
echo "  Repository: $REPO_SLUG"
echo ""

# ── Check prerequisites ─────────────────────────────────────────────

MISSING=()

if ! has_command git; then
  MISSING+=("git")
fi

if ! has_command gh; then
  MISSING+=("gh (GitHub CLI)")
fi

if ! has_command claude; then
  MISSING+=("claude (Claude Code)")
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
  error "Missing required tools: ${MISSING[*]}"
  echo ""
  if ! has_command git || ! has_command gh; then
    echo "  First, install work tools (Git, GitHub CLI, and more):"
    echo ""
    echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)\""
    echo ""
  fi
  if ! has_command claude; then
    echo "  Install AI tools (Claude Code, Codex, Gemini):"
    echo ""
    echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)\""
    echo ""
  fi
  echo "  Then re-run this script."
  exit 1
fi

# Check gh authentication
if ! gh auth status >/dev/null 2>&1; then
  error "GitHub CLI is not authenticated."
  echo ""
  echo "  Run this to log in:"
  echo ""
  echo "    gh auth login --git-protocol https"
  echo ""
  echo "  Then re-run this script."
  exit 1
fi

info "All prerequisites OK"
echo ""

# ── Choose location ─────────────────────────────────────────────────

DEFAULT_BASE="$HOME/GitHub/$ORG"

echo "  The repo will be cloned into a folder named '$REPO' inside a base directory."
echo ""
echo "  Default: $DEFAULT_BASE/$REPO"
echo ""
if [[ -t 0 ]]; then
  while true; do
    read -r -p "  Clone to default location, or choose your own? [yes/No] " reply
    reply_lower="$(echo "$reply" | tr '[:upper:]' '[:lower:]')"
    case "$reply_lower" in
      y|yes)
        BASE_DIR="$DEFAULT_BASE"
        break
        ;;
      n|no|"")
        echo ""
        echo "  Enter the path where you want the repo."
        echo "  Example: ~/Projects or /Users/yourname/work"
        echo ""
        read -r -p "  Path: " custom_path
        if [[ -z "$custom_path" ]]; then
          abort "No path entered."
        fi
        # Expand ~ if user typed it
        custom_path="${custom_path/#\~/$HOME}"
        # Strip trailing slashes
        custom_path="${custom_path%/}"
        # If the path already ends with the repo name, use it as-is
        if [[ "$(basename "$custom_path")" == "$REPO" ]]; then
          BASE_DIR="$(dirname "$custom_path")"
        else
          BASE_DIR="$custom_path"
        fi
        break
        ;;
      *)
        echo "  Please enter yes or no."
        ;;
    esac
  done
else
  BASE_DIR="$DEFAULT_BASE"
fi

TARGET_DIR="$BASE_DIR/$REPO"

# ── Safety check ────────────────────────────────────────────────────
# The final target must be a new directory. Refuse to clone into an
# existing non-git directory (e.g., /usr, /tmp, /Applications).

if [[ -d "$TARGET_DIR" && ! -d "$TARGET_DIR/.git" ]]; then
  abort "Directory already exists and is not a git repo: $TARGET_DIR\n  Refusing to clone into an existing directory. Choose a different location."
fi

if [[ -t 0 ]]; then
  echo ""
  echo "  Will clone to: $TARGET_DIR"
  echo ""
  while true; do
    read -r -p "  Proceed? [y/N] " confirm_reply
    confirm_lower="$(echo "$confirm_reply" | tr '[:upper:]' '[:lower:]')"
    case "$confirm_lower" in
      y|yes) break ;;
      n|no|"") abort "Aborted." ;;
      *) echo "  Please enter yes or no." ;;
    esac
  done
fi

echo ""

# ── Clone ───────────────────────────────────────────────────────────

if [[ -d "$TARGET_DIR/.git" ]]; then
  success "Already cloned: $TARGET_DIR"
  echo "  Pulling latest changes..."
  git -C "$TARGET_DIR" pull --ff-only 2>/dev/null || warn "Pull failed (you may have local changes); continuing"
else
  info "Cloning $REPO_SLUG"
  mkdir -p "$(dirname "$TARGET_DIR")"
  gh repo clone "$REPO_SLUG" "$TARGET_DIR" || abort "Clone failed. Check that you have access to $REPO_SLUG."
  success "Cloned to $TARGET_DIR"
fi

# ── Done ────────────────────────────────────────────────────────────

echo ""
success "Ready! Run these commands to start working:"
echo ""
echo "    cd $TARGET_DIR && claude"
echo ""

csa_debug_hint
