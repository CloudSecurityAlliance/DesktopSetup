#!/usr/bin/env bash

# Cloud Security Alliance — macOS Update Script
#
# Updates all tools managed by macos-work-tools.sh and macos-ai-tools.sh:
#   1. Homebrew formulas and casks (Git, Node.js, apps, etc.)
#   2. Global npm packages (Codex, Gemini, Wrangler)
#   3. pip + all pip packages (in active venv or system Python)
#   4. Claude Code — skipped (auto-updates via native installer)
#
# Before updating, saves a snapshot of all installed versions to:
#   ~/Library/Logs/CSA-DesktopSetup/pre-update-<timestamp>.txt
#
# Usage:
#   bash scripts/macos-update.sh
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"

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

confirm() {
  if [[ -n "${NONINTERACTIVE-}" ]]; then return 0; fi
  local reply
  read -r -p "$1 [Y/n] " reply
  case "${reply:-Y}" in
    [Yy]*) return 0 ;;
    *)     return 1 ;;
  esac
}

ensure_brew_in_path() {
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
    if has_command pip; then
      echo "Python: $(python --version 2>/dev/null || echo unknown)"
      [[ -n "${VIRTUAL_ENV:-}" ]] && echo "venv: $VIRTUAL_ENV"
      echo ""
      pip list 2>/dev/null || echo "(none)"
    else
      echo "(pip not available)"
    fi
    echo ""
  } > "$SNAPSHOT_FILE"

  # Save pip freeze separately for easy rollback
  if has_command pip; then
    {
      echo "# CSA DesktopSetup pip snapshot — $(date)"
      echo "# Python: $(python --version 2>/dev/null || echo unknown)"
      [[ -n "${VIRTUAL_ENV:-}" ]] && echo "# venv: $VIRTUAL_ENV"
      echo "# Restore with: pip install -r $(basename "$PIP_FREEZE_FILE")"
      echo ""
      pip freeze 2>/dev/null
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

  # pip
  if has_command pip; then
    local outdated_pip venv_note=""
    outdated_pip=$(pip list --outdated --format=columns 2>/dev/null || true)
    [[ -n "${VIRTUAL_ENV:-}" ]] && venv_note=" (venv: $(basename "$VIRTUAL_ENV"))"

    if [[ -n "$outdated_pip" ]]; then
      echo "  pip packages to update${venv_note}:"
      echo "$outdated_pip" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  pip packages${venv_note}: all up to date"
    fi
  else
    echo "  pip: not available (skipping)"
  fi
  echo ""

  # Claude Code
  echo "  Claude Code: skipped (auto-updates)"
  echo ""
}

# ── Update steps ────────────────────────────────────────────────────

update_brew() {
  if ! has_command brew; then return 0; fi

  info "Updating Homebrew"
  brew update || warn "brew update failed; continuing"

  info "Upgrading Homebrew packages"
  brew upgrade || warn "brew upgrade failed; continuing"

  info "Cleaning up old versions"
  brew cleanup || true
}

update_npm() {
  if ! has_command npm; then return 0; fi

  info "Updating global npm packages"
  npm update -g || warn "npm update -g failed; continuing"
}

update_pip() {
  if ! has_command pip; then return 0; fi

  local venv_note=""
  [[ -n "${VIRTUAL_ENV:-}" ]] && venv_note=" (venv: $(basename "$VIRTUAL_ENV"))"

  info "Updating pip itself${venv_note}"
  pip install --upgrade pip || warn "pip upgrade failed; continuing"

  info "Updating pip packages${venv_note}"
  local outdated
  outdated=$(pip list --outdated --format=json 2>/dev/null || echo "[]")

  if [[ "$outdated" == "[]" ]] || [[ -z "$outdated" ]]; then
    echo "  All pip packages are up to date"
    return 0
  fi

  # Extract package names and upgrade them one at a time
  local pkg_names
  pkg_names=$(echo "$outdated" | python -c "import sys, json; print(' '.join(p['name'] for p in json.load(sys.stdin)))" 2>/dev/null || true)

  if [[ -z "$pkg_names" ]]; then return 0; fi

  for pkg in $pkg_names; do
    info "  Upgrading $pkg"
    pip install --upgrade "$pkg" 2>/dev/null || warn "Failed to upgrade $pkg; continuing"
  done
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
  if has_command python; then
    echo "  Python ............ $(python --version 2>/dev/null)"
  fi
  if has_command pip; then
    echo "  pip ............... $(pip --version 2>/dev/null | head -n1)"
  fi
  if has_command claude; then
    echo "  Claude Code ....... $(claude --version 2>/dev/null | head -n1) (auto-updates)"
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
  [[ -f "$PIP_FREEZE_FILE" ]] && echo "    pip install -r $PIP_FREEZE_FILE"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Update"

  ensure_brew_in_path
  snapshot
  preflight

  if ! confirm "Proceed with updates?"; then
    abort "Aborted."
  fi

  echo ""
  update_brew
  update_npm
  update_pip
  summary
}

main "$@"
