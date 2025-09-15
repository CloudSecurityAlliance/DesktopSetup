#!/usr/bin/env bash

# Cloud Security Alliance macOS setup script
# - Installs/updates Homebrew
# - Installs/updates pyenv and latest Python 3.12.x
# - Installs/updates Node.js
# - Installs/updates AI CLIs (claude-code, gemini-cli, codex) via Homebrew or npm
# - Installs/updates 1Password app (Homebrew cask)
#
# Usage (recommended):
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/macos-install.sh)"

set -u

abort() { printf "%s\n" "$@" >&2; exit 1; }

# Colors if TTY
if [[ -t 1 ]]; then
  tty_escape() { printf "\033[%sm" "$1"; }
else
  tty_escape() { :; }
fi
tty_mkbold() { tty_escape "1;$1"; }
tty_blue="$(tty_mkbold 34)"
tty_red="$(tty_mkbold 31)"
tty_bold="$(tty_mkbold 39)"
tty_reset="$(tty_escape 0)"
ohai() { printf "${tty_blue}==>${tty_bold} %s${tty_reset}\n" "$*"; }
warn() { printf "${tty_red}Warning${tty_reset}: %s\n" "$*" >&2; }

# Confirmation prompt
confirm_or_exit() {
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    return 0
  fi
  echo
  ohai "This script will:"
  echo "- Install or update Homebrew"
  echo "- Install or update pyenv and Python 3.12.x"
  echo "- Install or update Node.js"
  echo "- Install or update AI CLIs: claude-code, gemini-cli, codex"
  echo "- Install or update 1Password (app)"
  echo
  read -r -p "Proceed? [Y/n] " reply
  case "${reply:-Y}" in
    [Yy]*) ;;
    [Nn]*) abort "Aborted by user." ;;
    *)     ;; # default yes
  esac
}

# Modes
if [[ -z "${NONINTERACTIVE-}" ]]; then
  if [[ -n "${CI-}" ]]; then
    warn 'Running in non-interactive mode because `$CI` is set.'
    NONINTERACTIVE=1
  elif [[ ! -t 0 ]]; then
    warn 'Running in non-interactive mode because `stdin` is not a TTY.'
    NONINTERACTIVE=1
  fi
else
  ohai 'Running in non-interactive mode because `$NONINTERACTIVE` is set.'
fi

# Preconditions
[[ "${BASH_VERSION:-}" ]] || abort "Bash is required to interpret this script."
[[ "$(uname -s)" == "Darwin" ]] || abort "This script supports macOS only."

# Refuse to run as root (except in container/CI)
if [[ "${EUID:-${UID}}" == "0" ]]; then
  if [[ ! -f /.dockerenv ]] && [[ ! -f /run/.containerenv ]]; then
    abort "Don't run this script as root."
  fi
fi

# Helper: ensure Homebrew is installed
ensure_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi

  ohai "Homebrew not found. Installing Homebrew..."
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
      abort "Homebrew installation failed."
  else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
      abort "Homebrew installation failed."
  fi

  # Add brew to PATH for current session
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

# Ensure brew is in PATH (when already installed but not exported yet)
ensure_brew_in_path() {
  if command -v brew >/dev/null 2>&1; then return 0; fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

# Brew helpers (idempotent)
BREW_VERBOSE=(--display-times --verbose)
brew_install_or_upgrade_formula() {
  local formula="$1"
  if brew list --formula "$formula" >/dev/null 2>&1; then
    ohai "Upgrading $formula (if outdated)"
    brew upgrade "${BREW_VERBOSE[@]}" "$formula" || true
  else
    ohai "Installing $formula"
    brew install "${BREW_VERBOSE[@]}" "$formula" || abort "Failed to install $formula"
  fi
}

brew_install_or_upgrade_cask() {
  local cask="$1"
  if brew list --cask "$cask" >/dev/null 2>&1; then
    ohai "Upgrading $cask (if outdated)"
    brew upgrade "${BREW_VERBOSE[@]}" --cask "$cask" || true
  else
    ohai "Installing $cask (cask)"
    brew install "${BREW_VERBOSE[@]}" --cask "$cask" || abort "Failed to install $cask"
  fi
}

# npm global install/update helper
npm_install_or_update() {
  local pkg="$1"; shift
  local bin_name="${1:-$pkg}"
  if command -v "$bin_name" >/dev/null 2>&1; then
    ohai "Updating npm package $pkg"
    npm update -g "$pkg" || npm install -g "$pkg" || warn "Failed to update $pkg"
  else
    ohai "Installing npm package $pkg"
    npm install -g "$pkg" || warn "Failed to install $pkg"
  fi
}

install_ai_tool() {
  # Tries Homebrew formula first; falls back to npm global if formula not found.
  local name="$1"; shift
  local formula="$1"; shift
  local npm_pkg="$1"; shift
  local bin_name="${1:-$npm_pkg}"

  if brew info --json=v2 "$formula" >/dev/null 2>&1; then
    brew_install_or_upgrade_formula "$formula"
  else
    warn "$name not available as Homebrew formula ($formula). Falling back to npm ($npm_pkg)."
    npm_install_or_update "$npm_pkg" "$bin_name"
  fi
}

main() {
  ohai "Starting Cloud Security Alliance macOS setup"

  confirm_or_exit

  ensure_homebrew
  ensure_brew_in_path

  ohai "Updating Homebrew"
  brew update || warn "brew update failed; continuing"

  # Core dev tools
  brew_install_or_upgrade_formula pyenv
  brew_install_or_upgrade_formula node

  # Ensure pyenv usable in this script
  export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
  export PATH="$PYENV_ROOT/bin:$PATH"
  if command -v pyenv >/dev/null 2>&1; then
    # shellcheck disable=SC1090
    eval "$(pyenv init -)"
  fi

  # Install latest Python 3.12.x with pyenv
  if command -v pyenv >/dev/null 2>&1; then
    ohai "Resolving latest Python 3.12.x"
    # Fetch list and pick latest stable 3.12.x (exclude dev/alpha/beta/rc)
    local_latest_312="$(pyenv install -l | sed 's/^ *//' | \
      grep -E '^3\.12\.[0-9]+$' | tail -1 || true)"
    if [[ -z "${local_latest_312}" ]]; then
      warn "Could not determine latest 3.12.x from pyenv; falling back to 3.12.0"
      local_latest_312="3.12.0"
    fi
    ohai "Ensuring Python ${local_latest_312} via pyenv (verbose build output)"
    pyenv install -sv "${local_latest_312}" || abort "pyenv failed to install Python ${local_latest_312}"

    # Optionally set as global if not already a 3.12.*
    current_global="$(pyenv global 2>/dev/null || true)"
    if [[ -z "${current_global}" || "${current_global}" != 3.12* ]]; then
      ohai "Setting pyenv global to ${local_latest_312}"
      pyenv global "${local_latest_312}" || warn "Failed to set pyenv global"
    else
      ohai "pyenv global already set (${current_global}); leaving as-is"
    fi
    pyenv rehash || true
  else
    warn "pyenv not found after install; skipping Python installation"
  fi

  # AI tools
  # Defaults can be overridden via env vars CSA_* if your org uses different package names.
  CLAUDE_FORMULA="${CSA_CLAUDE_FORMULA:-claude-code}"
  CLAUDE_NPM="${CSA_CLAUDE_NPM:-claude-code}"
  CLAUDE_BIN="${CSA_CLAUDE_BIN:-claude-code}"

  GEMINI_FORMULA="${CSA_GEMINI_FORMULA:-gemini-cli}"
  GEMINI_NPM="${CSA_GEMINI_NPM:-gemini-cli}"
  GEMINI_BIN="${CSA_GEMINI_BIN:-gemini}"

  CODEX_FORMULA="${CSA_CODEX_FORMULA:-codex}"
  CODEX_NPM="${CSA_CODEX_NPM:-codex}"
  CODEX_BIN="${CSA_CODEX_BIN:-codex}"

  # If brew formulae do not exist, we gracefully fall back to npm packages
  install_ai_tool "Claude Code" "$CLAUDE_FORMULA" "$CLAUDE_NPM" "$CLAUDE_BIN"
  install_ai_tool "Google Gemini CLI" "$GEMINI_FORMULA" "$GEMINI_NPM" "$GEMINI_BIN"
  install_ai_tool "ChatGPT Codex" "$CODEX_FORMULA" "$CODEX_NPM" "$CODEX_BIN"

  # 1Password (app)
  brew_install_or_upgrade_cask 1password

  ohai "All done. Summary:"
  echo "- Homebrew: $(brew --version | head -n1)"
  if command -v pyenv >/dev/null 2>&1; then
    echo "- pyenv: $(pyenv --version)"
    echo "- Python: $(python3 --version 2>/dev/null || true)"
  fi
  if command -v node >/dev/null 2>&1; then
    echo "- Node: $(node --version)"
    echo "- npm: $(npm --version)"
  fi
  echo "- 1Password: installed via Homebrew cask"
}

main "$@"
