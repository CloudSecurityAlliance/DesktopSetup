#!/usr/bin/env bash

# Cloud Security Alliance — macOS AI Tools Setup
#
# Installs:
#   1. Xcode Command Line Tools
#   2. Homebrew (macOS package manager)
#   3. Node.js (via Homebrew, provides npm)
#   4. Claude Code (native installer, auto-updates)
#   5. OpenAI Codex CLI (via npm)
#   6. Google Gemini CLI (via npm)
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

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

# ── Running process check ────────────────────────────────────────────

check_running_tools() {
  local running=()
  pgrep -x claude >/dev/null 2>&1 && running+=("Claude Code")
  pgrep -x codex >/dev/null 2>&1 && running+=("Codex CLI")
  pgrep -x gemini >/dev/null 2>&1 && running+=("Gemini CLI")

  if [[ ${#running[@]} -gt 0 ]]; then
    warn "These tools are currently running: ${running[*]}"
    echo "  It's safe to continue, but running sessions will stay on the old version."
    echo "  For a clean migration, close them first and re-run this script."
    echo ""
    if ! confirm "Continue anyway?"; then
      abort "Aborted. Close running tools and try again."
    fi
  fi
}

# ── Helpers ─────────────────────────────────────────────────────────

has_command() { command -v "$1" >/dev/null 2>&1; }

get_version() {
  local cmd="$1"; shift
  if has_command "$cmd"; then
    "$cmd" "$@" 2>/dev/null | head -n1
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

ensure_brew_in_path() {
  if has_command brew; then return 0; fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

# ── Migration detection ─────────────────────────────────────────────
# Detect tools installed via the wrong method so we can migrate them.
# Config files (~/.claude, ~/.codex, ~/.gemini) are always preserved.

claude_needs_migration=""   # "brew" or "npm" if installed wrong
codex_needs_migration=""    # "brew" if installed via homebrew
gemini_needs_migration=""   # "brew" if installed via homebrew

detect_migrations() {
  ensure_brew_in_path

  # Claude: should be native installer, not brew or npm
  if has_command brew && brew list --cask claude-code >/dev/null 2>&1; then
    claude_needs_migration="brew"
  elif npm list -g @anthropic-ai/claude-code >/dev/null 2>&1; then
    claude_needs_migration="npm"
  fi

  # Codex: should be npm, not brew
  if has_command brew && brew list --cask codex >/dev/null 2>&1; then
    codex_needs_migration="brew"
  fi

  # Gemini: should be npm, not brew
  if has_command brew && brew list --formula gemini-cli >/dev/null 2>&1; then
    gemini_needs_migration="brew"
  elif has_command brew && brew list --cask gemini-cli >/dev/null 2>&1; then
    gemini_needs_migration="brew"
  fi
}

# ── Preflight ───────────────────────────────────────────────────────

preflight() {
  detect_migrations

  echo ""
  info "Installation plan:"
  echo ""

  # Xcode CLI Tools
  if xcode-select -p >/dev/null 2>&1; then
    echo "  Xcode CLI Tools ... installed"
  else
    echo "  Xcode CLI Tools ... install"
  fi

  # Homebrew
  if has_command brew; then
    echo "  Homebrew .......... installed (update)"
  else
    echo "  Homebrew .......... install"
  fi

  # Node.js
  if has_command node; then
    echo "  Node.js ........... installed ($(get_version node --version))"
  else
    echo "  Node.js ........... install via Homebrew"
  fi

  # Claude Code
  if [[ -n "$claude_needs_migration" ]]; then
    echo "  Claude Code ....... migrate from $claude_needs_migration → native installer (settings preserved)"
  elif has_command claude; then
    echo "  Claude Code ....... installed ($(get_version claude --version))"
  else
    echo "  Claude Code ....... install (native installer, auto-updates)"
  fi

  # Codex
  if [[ -n "$codex_needs_migration" ]]; then
    echo "  Codex CLI ......... migrate from Homebrew → npm (settings preserved)"
  elif has_command codex; then
    echo "  Codex CLI ......... installed ($(get_version codex --version))"
  else
    echo "  Codex CLI ......... install via npm"
  fi

  # Gemini
  if [[ -n "$gemini_needs_migration" ]]; then
    echo "  Gemini CLI ........ migrate from Homebrew → npm (settings preserved)"
  elif has_command gemini; then
    echo "  Gemini CLI ........ installed ($(get_version gemini --version))"
  else
    echo "  Gemini CLI ........ install via npm"
  fi

  echo ""
}

# ── Migration steps ──────────────────────────────────────────────────
# Remove tools installed via the wrong method before reinstalling.
# Config files in $HOME are never touched.

migrate_claude() {
  if [[ "$claude_needs_migration" == "brew" ]]; then
    info "Removing Claude Code from Homebrew (migrating to native installer)"
    brew uninstall --cask claude-code || warn "brew uninstall claude-code failed; continuing"
  elif [[ "$claude_needs_migration" == "npm" ]]; then
    info "Removing Claude Code from npm (migrating to native installer)"
    npm uninstall -g @anthropic-ai/claude-code || warn "npm uninstall claude-code failed; continuing"
  fi
}

migrate_codex() {
  if [[ "$codex_needs_migration" == "brew" ]]; then
    info "Removing Codex CLI from Homebrew (migrating to npm)"
    brew uninstall --cask codex || warn "brew uninstall codex failed; continuing"
  fi
}

migrate_gemini() {
  if [[ "$gemini_needs_migration" == "brew" ]]; then
    info "Removing Gemini CLI from Homebrew (migrating to npm)"
    brew uninstall --formula gemini-cli 2>/dev/null \
      || brew uninstall --cask gemini-cli 2>/dev/null \
      || warn "brew uninstall gemini-cli failed; continuing"
  fi
}

# ── Install steps ───────────────────────────────────────────────────

install_xcode_cli_tools() {
  if xcode-select -p >/dev/null 2>&1; then
    info "Xcode Command Line Tools already installed"
    return 0
  fi

  info "Installing Xcode Command Line Tools"
  xcode-select --install 2>/dev/null || true

  # Wait for installation to complete (it opens a GUI prompt)
  echo "  Waiting for Xcode Command Line Tools installation..."
  echo "  Please follow the prompts in the dialog that appeared."
  until xcode-select -p >/dev/null 2>&1; do
    sleep 5
  done
  success "Xcode Command Line Tools installed"
}

install_homebrew() {
  if has_command brew; then
    info "Updating Homebrew"
    brew update || warn "brew update failed; continuing"
    return 0
  fi

  info "Installing Homebrew"
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
      || abort "Homebrew installation failed."
  else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
      || abort "Homebrew installation failed."
  fi
  ensure_brew_in_path
}

install_node() {
  ensure_brew_in_path

  if brew list --formula node >/dev/null 2>&1; then
    info "Upgrading Node.js"
    brew upgrade node 2>/dev/null || true
  elif has_command node; then
    info "Node.js already installed (non-Homebrew): $(get_version node --version)"
  else
    info "Installing Node.js"
    brew install node || abort "Failed to install Node.js"
  fi
}

install_claude() {
  if [[ -n "$claude_needs_migration" ]]; then
    migrate_claude
  fi
  info "Installing/updating Claude Code (native installer)"
  curl -fsSL https://claude.ai/install.sh | bash \
    || abort "Claude Code installation failed."
}

install_codex() {
  if [[ -n "$codex_needs_migration" ]]; then
    migrate_codex
  fi

  if ! has_command npm; then
    warn "npm not found; skipping Codex CLI"
    return 1
  fi

  if [[ -z "$codex_needs_migration" ]] && has_command codex; then
    info "Updating Codex CLI"
    npm update -g @openai/codex || npm install -g @openai/codex || warn "Failed to update Codex CLI"
  else
    info "Installing Codex CLI"
    npm install -g @openai/codex || warn "Failed to install Codex CLI"
  fi
}

install_gemini() {
  if [[ -n "$gemini_needs_migration" ]]; then
    migrate_gemini
  fi

  if ! has_command npm; then
    warn "npm not found; skipping Gemini CLI"
    return 1
  fi

  if [[ -z "$gemini_needs_migration" ]] && has_command gemini; then
    info "Updating Gemini CLI"
    npm update -g @google/gemini-cli || npm install -g @google/gemini-cli || warn "Failed to update Gemini CLI"
  else
    info "Installing Gemini CLI"
    npm install -g @google/gemini-cli || warn "Failed to install Gemini CLI"
  fi
}

# ── Summary ─────────────────────────────────────────────────────────

summary() {
  echo ""
  success "Setup complete! Installed versions:"
  echo ""

  if has_command brew; then
    echo "  Homebrew .......... $(brew --version | head -n1)"
  fi
  if has_command node; then
    echo "  Node.js ........... $(get_version node --version)"
    echo "  npm ............... $(get_version npm --version)"
  fi
  if has_command claude; then
    echo "  Claude Code ....... $(get_version claude --version)"
  fi
  if has_command codex; then
    echo "  Codex CLI ......... $(get_version codex --version)"
  fi
  if has_command gemini; then
    echo "  Gemini CLI ........ $(get_version gemini --version)"
  fi

  echo ""
  info "Next steps:"
  echo "  - Run 'claude' to start Claude Code"
  echo "  - Run 'codex' to start Codex CLI"
  echo "  - Run 'gemini' to start Gemini CLI"
  echo ""
  echo "  To update npm-installed tools later:"
  echo "    npm update -g @openai/codex @google/gemini-cli"
  echo ""
  echo "  Claude Code updates itself automatically."
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Development Setup"

  check_running_tools
  preflight

  if ! confirm "Proceed with installation?"; then
    abort "Aborted."
  fi

  echo ""
  install_xcode_cli_tools
  install_homebrew
  install_node
  install_claude
  install_codex
  install_gemini
  summary
}

main "$@"
