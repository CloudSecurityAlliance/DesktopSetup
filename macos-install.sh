#!/usr/bin/env bash

# Cloud Security Alliance macOS setup script
# - Installs/updates Homebrew
# - Installs/updates pyenv and latest Python 3.12.x
# - Installs/updates Node.js
# - Installs/updates AI CLIs (claude-code, gemini-cli, codex, mcpb) via Homebrew/npm/pip
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
  ohai "Preflight plan (detected actions):"
  preflight_plan
  echo
  read -r -p "Proceed? [Y/n] " reply
  case "${reply:-Y}" in
    [Yy]*) ;;
    [Nn]*) abort "Aborted by user." ;;
    *)     ;; # default yes
  esac
}

# Helper: locate a binary via PATH or common Homebrew paths
find_bin_relaxed() {
  local name="$1"
  local p
  if p="$(command -v "$name" 2>/dev/null)"; then
    printf "%s" "$p"
    return 0
  fi
  for p in "/opt/homebrew/bin/$name" "/usr/local/bin/$name"; do
    if [[ -x "$p" ]]; then
      printf "%s" "$p"
      return 0
    fi
  done
  return 1
}

# Get version string by invoking a binary with args; prints empty on failure
get_version() {
  local bin="$1"; shift
  local args=("$@")
  if [[ -x "$bin" ]] || command -v "$bin" >/dev/null 2>&1; then
    "$bin" "${args[@]}" 2>/dev/null | head -n1 | sed 's/^ *//;s/ *$//'
    return 0
  fi
  return 1
}

# Brew JSON helpers (best-effort). Return empty if brew/python3 unavailable.
brew_json() {
  local id="$1"; shift
  if ! command -v brew >/dev/null 2>&1; then return 1; fi
  brew info --json=v2 "$id" 2>/dev/null
}

brew_formula_stable_version() {
  local id="$1"
  if ! command -v python3 >/dev/null 2>&1; then return 1; fi
  brew_json "$id" | python3 - <<'PY' 2>/dev/null || true
import sys, json
data=json.load(sys.stdin)
f=data.get('formulae', [{}])[0]
print((f.get('versions') or {}).get('stable',''))
PY
}

brew_cask_version() {
  local id="$1"
  if ! command -v python3 >/dev/null 2>&1; then return 1; fi
  brew_json "$id" | python3 - <<'PY' 2>/dev/null || true
import sys, json
data=json.load(sys.stdin)
c=data.get('casks', [{}])[0]
print(c.get('version',''))
PY
}

# Get app bundle version via mdls (macOS)
get_app_version_mdls() {
  local app_path="$1"
  if [[ -d "$app_path" ]] && command -v mdls >/dev/null 2>&1; then
    mdls -name kMDItemVersion -raw "$app_path" 2>/dev/null | head -n1
    return 0
  fi
  return 1
}

# Print a one-line plan for a Homebrew formula with an expected binary
plan_formula() {
  # Args: <label> <formula> <bin>
  local label="$1" formula="$2" bin="$3"
  local brew_present=1
  if command -v brew >/dev/null 2>&1; then brew_present=0; fi
  local bin_path
  bin_path="$(find_bin_relaxed "$bin" 2>/dev/null || true)"
  local current_v latest_v
  current_v=""
  latest_v=""

  if [[ $brew_present -ne 0 ]]; then
    if [[ -n "$bin_path" ]]; then
      current_v="$(get_version "$bin_path" --version || true)"
      echo "- ${label}: skip (already present at ${bin_path}${current_v:+, current: ${current_v}}; Homebrew not installed yet)"
    else
      echo "- ${label}: install via Homebrew (after installing Homebrew)"
    fi
    return 0
  fi

  if brew list --formula "$formula" >/dev/null 2>&1; then
    latest_v="$(brew_formula_stable_version "$formula" || true)"
    current_v="$(get_version "$bin" --version || true)"
    echo "- ${label}: upgrade (Homebrew-managed)${current_v:+, current: ${current_v}}${latest_v:+, latest: ${latest_v}}"
  else
    if [[ -n "$bin_path" ]]; then
      current_v="$(get_version "$bin_path" --version || true)"
      echo "- ${label}: skip (already present at ${bin_path}, non-Homebrew${current_v:+, current: ${current_v}})"
    else
      latest_v="$(brew_formula_stable_version "$formula" || true)"
      echo "- ${label}: install${latest_v:+, latest: ${latest_v}}"
    fi
  fi
}

# Print a one-line plan for an AI tool (formula or cask) with expected binary
plan_ai() {
  # Args: <label> <brew_name> <bin>
  local label="$1" brew_name="$2" bin="$3"
  local brew_present=1
  if command -v brew >/dev/null 2>&1; then brew_present=0; fi
  local bin_path
  bin_path="$(find_bin_relaxed "$bin" 2>/dev/null || true)"
  local current_v latest_v
  current_v=""
  latest_v=""

  if [[ $brew_present -ne 0 ]]; then
    if [[ -n "$bin_path" ]]; then
      current_v="$(get_version "$bin_path" --version || true)"
      echo "- ${label}: skip (already present at ${bin_path}${current_v:+, current: ${current_v}}; Homebrew not installed yet)"
      return 0
    fi
    echo "- ${label}: install via Homebrew (after installing Homebrew)"
    return 0
  fi

  local t
  t="$(brew_item_type "$brew_name" || true)"
  if [[ -z "$t" ]]; then
    echo "- ${label}: ERROR (not found in Homebrew as '${brew_name}', will abort)"
    return 0
  fi

  if brew list --"$t" "$brew_name" >/dev/null 2>&1; then
    if [[ "$t" == "formula" ]]; then
      latest_v="$(brew_formula_stable_version "$brew_name" || true)"
    else
      latest_v="$(brew_cask_version "$brew_name" || true)"
    fi
    current_v="$(get_version "$bin" --version || true)"
    echo "- ${label}: upgrade (Homebrew-managed, $t)${current_v:+, current: ${current_v}}${latest_v:+, latest: ${latest_v}}"
  else
    if [[ -n "$bin_path" ]]; then
      current_v="$(get_version "$bin_path" --version || true)"
      echo "- ${label}: skip (already present at ${bin_path}, non-Homebrew${current_v:+, current: ${current_v}})"
    else
      if [[ "$t" == "formula" ]]; then
        latest_v="$(brew_formula_stable_version "$brew_name" || true)"
      else
        latest_v="$(brew_cask_version "$brew_name" || true)"
      fi
      echo "- ${label}: install ($t)${latest_v:+, latest: ${latest_v}}"
    fi
  fi
}

plan_1password() {
  local brew_present=1
  if command -v brew >/dev/null 2>&1; then brew_present=0; fi
  local app_paths=("/Applications/1Password.app" "$HOME/Applications/1Password.app")

  if [[ $brew_present -ne 0 ]]; then
    for p in "${app_paths[@]}"; do
      [[ -d "$p" ]] && { echo "- 1Password: skip (already installed at $p)"; return 0; }
    done
    echo "- 1Password: install via Homebrew cask (after installing Homebrew)"
    return 0
  fi

  if brew list --cask 1password >/dev/null 2>&1; then
    local latest_v
    latest_v="$(brew_cask_version 1password || true)"
    echo "- 1Password: upgrade (Homebrew-managed cask)${latest_v:+, latest: ${latest_v}}"
    return 0
  fi
  for p in "${app_paths[@]}"; do
    if [[ -d "$p" ]]; then
      local current_v
      current_v="$(get_app_version_mdls "$p" || true)"
      echo "- 1Password: skip (already installed at $p${current_v:+, current: ${current_v}})"
      return 0
    fi
  done
  local latest_v
  latest_v="$(brew_cask_version 1password || true)"
  echo "- 1Password: install (cask)${latest_v:+, latest: ${latest_v}}"
}

preflight_plan() {
  # Homebrew
  if command -v brew >/dev/null 2>&1; then
    echo "- Homebrew: already installed"
  else
    echo "- Homebrew: install"
  fi

  # Core formulas
  plan_formula "pyenv" "pyenv" "pyenv"
  plan_formula "Node.js" "node" "node"
  plan_formula "Python 3.12.x (via pyenv)" "pyenv" "python3" >/dev/null 2>&1 || true

  # AI tools
  plan_ai "Claude Code" "claude-code" "claude"
  plan_ai "Google Gemini CLI" "gemini-cli" "gemini"
  plan_ai "ChatGPT Codex" "codex" "codex"
  plan_tool "MCPB CLI" "npm" "@anthropic-ai/mcpb" "mcpb"

  # 1Password
  plan_1password
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
    brew upgrade "${BREW_VERBOSE[@]}" --cask "$cask" || warn "Failed to upgrade $cask (cask); continuing"
  else
    ohai "Installing $cask (cask)"
    brew install "${BREW_VERBOSE[@]}" --cask "$cask" || warn "Failed to install $cask (cask); continuing"
  fi
}

# Package manager helpers
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

pip_install_or_update() {
  local pkg="$1"; shift
  local bin_name="${1:-$pkg}"
  # Try pip3 first, then pip
  local pip_cmd=""
  if command -v pip3 >/dev/null 2>&1; then
    pip_cmd="pip3"
  elif command -v pip >/dev/null 2>&1; then
    pip_cmd="pip"
  else
    warn "Neither pip nor pip3 found; skipping $pkg"
    return 1
  fi

  if command -v "$bin_name" >/dev/null 2>&1; then
    ohai "Updating pip package $pkg"
    "$pip_cmd" install --upgrade "$pkg" || warn "Failed to update $pkg"
  else
    ohai "Installing pip package $pkg"
    "$pip_cmd" install "$pkg" || warn "Failed to install $pkg"
  fi
}

# Print a one-line plan for a tool installation
plan_tool() {
  # Args: <label> <pkg_manager> <package_name> <bin>
  local label="$1" pkg_manager="$2" package_name="$3" bin="$4"
  local bin_path
  bin_path="$(find_bin_relaxed "$bin" 2>/dev/null || true)"
  local current_v latest_v
  current_v=""
  latest_v=""

  case "$pkg_manager" in
    "brew")
      if command -v brew >/dev/null 2>&1; then
        if brew list --formula "$package_name" >/dev/null 2>&1; then
          latest_v="$(brew_formula_stable_version "$package_name" || true)"
          current_v="$(get_version "$bin" --version || true)"
          echo "- ${label}: upgrade (Homebrew formula)${current_v:+, current: ${current_v}}${latest_v:+, latest: ${latest_v}}"
        elif [[ -n "$bin_path" ]]; then
          current_v="$(get_version "$bin_path" --version || true)"
          echo "- ${label}: skip (already present at ${bin_path}${current_v:+, current: ${current_v}})"
        else
          latest_v="$(brew_formula_stable_version "$package_name" || true)"
          echo "- ${label}: install (Homebrew formula)${latest_v:+, latest: ${latest_v}}"
        fi
      else
        if [[ -n "$bin_path" ]]; then
          current_v="$(get_version "$bin_path" --version || true)"
          echo "- ${label}: skip (already present at ${bin_path}${current_v:+, current: ${current_v}})"
        else
          echo "- ${label}: install (after installing Homebrew)"
        fi
      fi
      ;;
    "cask")
      if command -v brew >/dev/null 2>&1; then
        if brew list --cask "$package_name" >/dev/null 2>&1; then
          latest_v="$(brew_cask_version "$package_name" || true)"
          echo "- ${label}: upgrade (Homebrew cask)${latest_v:+, latest: ${latest_v}}"
        else
          latest_v="$(brew_cask_version "$package_name" || true)"
          echo "- ${label}: install (Homebrew cask)${latest_v:+, latest: ${latest_v}}"
        fi
      else
        echo "- ${label}: install (after installing Homebrew)"
      fi
      ;;
    "npm")
      if command -v npm >/dev/null 2>&1; then
        if [[ -n "$bin_path" ]]; then
          current_v="$(get_version "$bin_path" --version || true)"
          echo "- ${label}: update (npm)${current_v:+, current: ${current_v}}"
        else
          echo "- ${label}: install (npm)"
        fi
      else
        echo "- ${label}: install (after installing Node.js)"
      fi
      ;;
    "pip")
      if command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
        if [[ -n "$bin_path" ]]; then
          current_v="$(get_version "$bin_path" --version || true)"
          echo "- ${label}: update (pip)${current_v:+, current: ${current_v}}"
        else
          echo "- ${label}: install (pip)"
        fi
      else
        echo "- ${label}: install (after installing Python)"
      fi
      ;;
  esac
}

install_tool() {
  # Install or upgrade a tool via its designated package manager.
  # Args: <display_name> <pkg_manager> <package_name> <bin_name>
  local name="$1" pkg_manager="$2" package_name="$3" bin_name="$4"

  case "$pkg_manager" in
    "brew")
      install_or_upgrade_formula_checked "$package_name" "$bin_name"
      ;;
    "cask")
      brew_install_or_upgrade_cask "$package_name"
      ;;
    "npm")
      if command -v npm >/dev/null 2>&1; then
        npm_install_or_update "$package_name" "$bin_name"
      else
        warn "$name requires npm but npm not found; skipping"
      fi
      ;;
    "pip")
      if command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
        pip_install_or_update "$package_name" "$bin_name"
      else
        warn "$name requires pip but pip not found; skipping"
      fi
      ;;
    *)
      abort "Unknown package manager: $pkg_manager"
      ;;
  esac
}

install_or_upgrade_formula_checked() {
  # Args: <formula> <bin_name>
  local formula="$1"; local bin_name="$2"
  local existing_bin
  existing_bin="$(command -v "$bin_name" 2>/dev/null || true)"
  if [[ -n "$existing_bin" ]]; then
    if brew list --formula "$formula" >/dev/null 2>&1; then
      ohai "Upgrading $formula (Homebrew-managed, if outdated)"
      brew upgrade "${BREW_VERBOSE[@]}" "$formula" || warn "Failed to upgrade $formula; continuing"
    else
      ohai "$formula already present at $existing_bin; skipping Homebrew install to avoid conflicts"
    fi
    return 0
  fi

  brew_install_or_upgrade_formula "$formula"
}

brew_item_type() {
  # Echoes 'formula' or 'cask' if found, empty otherwise
  local name="$1"
  if brew info --formula "$name" >/dev/null 2>&1; then
    echo formula; return 0
  elif brew info --cask "$name" >/dev/null 2>&1; then
    echo cask; return 0
  else
    return 1
  fi
}

brew_try_install_or_upgrade() {
  # Try install/upgrade via brew for a given name and type; never abort.
  local name="$1"; local type="$2"
  if [[ "$type" == "formula" ]]; then
    if brew list --formula "$name" >/dev/null 2>&1; then
      ohai "Upgrading $name (if outdated)"
      brew upgrade "${BREW_VERBOSE[@]}" "$name" || return 1
    else
      ohai "Installing $name"
      brew install "${BREW_VERBOSE[@]}" "$name" || return 1
    fi
  elif [[ "$type" == "cask" ]]; then
    if brew list --cask "$name" >/dev/null 2>&1; then
      ohai "Upgrading $name (cask, if outdated)"
      brew upgrade "${BREW_VERBOSE[@]}" --cask "$name" || return 1
    else
      ohai "Installing $name (cask)"
      brew install "${BREW_VERBOSE[@]}" --cask "$name" || return 1
    fi
  else
    return 1
  fi
}

install_ai_tool() {
  # Install or upgrade an AI tool strictly via Homebrew. No npm fallback.
  # Args: <display_name> <brew_name> <unused_npm_pkg> <bin_name>
  local name="$1"; shift
  local brew_name="$1"; shift
  local _unused_npm="$1"; shift
  local bin_name="${1:-$brew_name}"

  local existing_bin
  existing_bin="$(command -v "$bin_name" 2>/dev/null || true)"
  # Also check common Homebrew bin paths in case PATH isn't updated yet
  if [[ -z "$existing_bin" ]]; then
    for p in "/opt/homebrew/bin/$bin_name" "/usr/local/bin/$bin_name"; do
      if [[ -x "$p" ]]; then existing_bin="$p"; break; fi
    done
  fi

  # If the binary already exists but is not Brew-managed, skip to avoid conflicts
  local t
  t="$(brew_item_type "$brew_name" || true)"
  if [[ -z "$t" ]]; then
    abort "$name not available in Homebrew as '$brew_name'. Please add/tap a formula or fix the package name."
  fi

  if [[ -n "$existing_bin" ]] && ! brew list --"$t" "$brew_name" >/dev/null 2>&1; then
    warn "$name detected at $existing_bin but not Homebrew-managed; leaving as-is and skipping for now"
    return 0
  fi

  # Install or upgrade via Homebrew
  if ! brew_try_install_or_upgrade "$brew_name" "$t"; then
    abort "Failed to install/upgrade $name via Homebrew."
  fi
}

install_or_report_1password() {
  ONEPASSWORD_STATUS="not installed"
  local app_paths=("/Applications/1Password.app" "$HOME/Applications/1Password.app")

  if brew list --cask 1password >/dev/null 2>&1; then
    ohai "Upgrading 1Password (cask, if outdated)"
    if brew upgrade "${BREW_VERBOSE[@]}" --cask 1password; then
      ONEPASSWORD_STATUS="installed via Homebrew cask"
      return 0
    else
      warn "Failed to upgrade 1password (cask); continuing"
      ONEPASSWORD_STATUS="installed via Homebrew cask (upgrade failed)"
      return 0
    fi
  fi

  # Not managed by Homebrew cask; see if app already exists
  for p in "${app_paths[@]}"; do
    if [[ -d "$p" ]]; then
      ohai "1Password already installed at $p; skipping cask installation"
      ONEPASSWORD_STATUS="already installed at $p"
      return 0
    fi
  done

  # Try to install via cask
  ohai "Installing 1Password (cask)"
  if brew install "${BREW_VERBOSE[@]}" --cask 1password; then
    ONEPASSWORD_STATUS="installed via Homebrew cask"
  else
    # If installation failed but app now exists, treat as installed
    for p in "${app_paths[@]}"; do
      if [[ -d "$p" ]]; then
        ohai "Detected 1Password at $p after cask attempt; marking as installed"
        ONEPASSWORD_STATUS="already installed at $p"
        return 0
      fi
    done
    warn "Failed to install 1password (cask); continuing"
    ONEPASSWORD_STATUS="installation failed"
  fi
}

main() {
  ohai "Starting Cloud Security Alliance macOS setup"

  confirm_or_exit

  ensure_homebrew
  ensure_brew_in_path

  ohai "Updating Homebrew"
  brew update || warn "brew update failed; continuing"

  # Core dev tools (avoid conflicts if already present outside Homebrew)
  install_or_upgrade_formula_checked pyenv pyenv
  install_or_upgrade_formula_checked node node

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

  # AI tools configuration - each tool has its preferred package manager and can be overridden
  CLAUDE_PKG_MGR="${CSA_CLAUDE_PKG_MGR:-brew}"
  CLAUDE_PACKAGE="${CSA_CLAUDE_PACKAGE:-claude-code}"
  CLAUDE_BIN="${CSA_CLAUDE_BIN:-claude}"

  GEMINI_PKG_MGR="${CSA_GEMINI_PKG_MGR:-brew}"
  GEMINI_PACKAGE="${CSA_GEMINI_PACKAGE:-gemini-cli}"
  GEMINI_BIN="${CSA_GEMINI_BIN:-gemini}"

  CODEX_PKG_MGR="${CSA_CODEX_PKG_MGR:-brew}"
  CODEX_PACKAGE="${CSA_CODEX_PACKAGE:-codex}"
  CODEX_BIN="${CSA_CODEX_BIN:-codex}"

  MCPB_PKG_MGR="${CSA_MCPB_PKG_MGR:-npm}"
  MCPB_PACKAGE="${CSA_MCPB_PACKAGE:-@anthropic-ai/mcpb}"
  MCPB_BIN="${CSA_MCPB_BIN:-mcpb}"

  # AI tools - install using each tool's designated package manager
  install_ai_tool "Claude Code" "claude-code" "claude-code" "claude"
  install_ai_tool "Google Gemini CLI" "gemini-cli" "gemini-cli" "gemini"
  install_ai_tool "ChatGPT Codex" "codex" "codex" "codex"
  install_tool "MCPB CLI" "$MCPB_PKG_MGR" "$MCPB_PACKAGE" "$MCPB_BIN"

  # 1Password (app)
  install_or_report_1password

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
  # AI CLIs versions (best-effort)
  local v
  v="$(get_version claude --version || true)"; [[ -n "$v" ]] && echo "- Claude Code: $v"
  v="$(get_version gemini --version || true)"; [[ -n "$v" ]] && echo "- Gemini CLI: $v"
  v="$(get_version codex --version || true)"; [[ -n "$v" ]] && echo "- Codex: $v"
  v="$(get_version mcpb --version || true)"; [[ -n "$v" ]] && echo "- MCPB CLI: $v"

  # 1Password status and version (best-effort)
  if [[ "${ONEPASSWORD_STATUS:-}" == already* ]]; then
    local app_path
    app_path="${ONEPASSWORD_STATUS#already installed at }"
    app_path="${app_path%% *}"
    v="$(get_app_version_mdls "$app_path" || true)"
    echo "- 1Password: ${ONEPASSWORD_STATUS}${v:+, version: ${v}}"
  else
    # If installed via cask, print cask version
    if brew list --cask 1password >/dev/null 2>&1; then
      v="$(brew_cask_version 1password || true)"
      echo "- 1Password: ${ONEPASSWORD_STATUS:-installed via Homebrew cask}${v:+, version: ${v}}"
    else
      echo "- 1Password: ${ONEPASSWORD_STATUS:-not installed}"
    fi
  fi
}

main "$@"
