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
DEFAULT_DIR="$HOME/GitHub/$ORG/$REPO"

# ── Check prerequisites ─────────────────────────────────────────────

info "Cloud Security Alliance — Clone & Claude"
echo ""
echo "  Repository: $REPO_SLUG"
echo ""

# ── Choose location ─────────────────────────────────────────────────

DEFAULT_BASE="$HOME/GitHub/$ORG"

echo "  The repo will be cloned into a folder named '$REPO' inside a base directory."
echo ""
echo "  Default: $DEFAULT_BASE/$REPO"
echo ""
if [[ -t 0 ]]; then
  while true; do
    read -r -p "  Use default location? [Y/n] " reply
    reply_lower="$(echo "$reply" | tr '[:upper:]' '[:lower:]')"
    case "$reply_lower" in
      y|yes|"")
        BASE_DIR="$DEFAULT_BASE"
        break
        ;;
      n|no)
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
  echo "  Install them with the CSA AI tools setup script:"
  echo ""
  echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)\""
  echo ""
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
