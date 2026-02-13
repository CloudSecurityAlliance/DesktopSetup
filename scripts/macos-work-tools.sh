#!/usr/bin/env bash

# Cloud Security Alliance — macOS Work Tools Setup
#
# Core profile (everyone):
#   1. Xcode Command Line Tools
#   2. Homebrew (macOS package manager)
#   3. Node.js (via Homebrew, provides npm)
#   4. Git (via Homebrew, latest version)
#   5. GitHub CLI (gh)
#   6. 1Password
#   7. Slack
#   8. Zoom
#   9. Google Chrome
#  10. Microsoft Office (Word, Excel, PowerPoint, Outlook, Teams + AutoUpdate)
#
# Dev profile (core + these):
#  11. Visual Studio Code
#  12. AWS CLI
#  13. Wrangler (Cloudflare CLI, via npm)
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"

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

has_cask() { brew list --cask "$1" >/dev/null 2>&1; }

has_app() {
  [[ -d "/Applications/$1.app" ]] || [[ -d "$HOME/Applications/$1.app" ]]
}

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

# ── Profile selection ───────────────────────────────────────────────

INSTALL_DEV=false

select_profile() {
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    # Default to core only in non-interactive mode
    return 0
  fi

  echo ""
  info "Select a profile:"
  echo ""
  echo "  1) Core — 1Password, Slack, Zoom, Chrome, Microsoft Office, Git, GitHub CLI"
  echo "  2) Core + Developer — adds VS Code, AWS CLI, Wrangler"
  echo ""

  local reply
  read -r -p "Profile [1/2]: " reply
  case "${reply:-1}" in
    2) INSTALL_DEV=true ;;
    *) INSTALL_DEV=false ;;
  esac
}

# ── Preflight ───────────────────────────────────────────────────────

plan_line() {
  # Usage: plan_line "Label" "status"
  printf "  %-22s %s\n" "$1" "$2"
}

preflight() {
  ensure_brew_in_path

  echo ""
  info "Installation plan:"
  echo ""

  # Base layer
  if xcode-select -p >/dev/null 2>&1; then
    plan_line "Xcode CLI Tools" "installed"
  else
    plan_line "Xcode CLI Tools" "install"
  fi

  if has_command brew; then
    plan_line "Homebrew" "installed (update)"
  else
    plan_line "Homebrew" "install"
  fi

  if has_command node; then
    plan_line "Node.js" "installed ($(get_version node --version))"
  else
    plan_line "Node.js" "install via Homebrew"
  fi

  # Core tools
  echo ""
  echo "  ── Core ──"

  if has_command git && brew list --formula git >/dev/null 2>&1; then
    plan_line "Git" "installed ($(get_version git --version))"
  elif has_command git; then
    plan_line "Git" "upgrade to Homebrew version"
  else
    plan_line "Git" "install via Homebrew"
  fi

  if has_command gh; then
    plan_line "GitHub CLI" "installed ($(get_version gh --version))"
  else
    plan_line "GitHub CLI" "install via Homebrew"
  fi

  # Cask apps — check both brew cask and /Applications
  local -a cask_apps=(
    "1Password:1password:1Password"
    "Slack:slack:Slack"
    "Zoom:zoom:zoom.us"
    "Google Chrome:google-chrome:Google Chrome"
    "Microsoft Office:microsoft-office:Microsoft Word"
  )

  for entry in "${cask_apps[@]}"; do
    IFS=: read -r label cask app_name <<< "$entry"
    if has_command brew && has_cask "$cask"; then
      plan_line "$label" "installed (Homebrew)"
    elif has_app "$app_name"; then
      plan_line "$label" "installed"
    else
      plan_line "$label" "install via Homebrew"
    fi
  done

  # Dev tools
  if [[ "$INSTALL_DEV" == true ]]; then
    echo ""
    echo "  ── Developer ──"

    if has_app "Visual Studio Code"; then
      plan_line "VS Code" "installed"
    else
      plan_line "VS Code" "install via Homebrew"
    fi

    if has_command aws; then
      plan_line "AWS CLI" "installed ($(get_version aws --version))"
    else
      plan_line "AWS CLI" "install via Homebrew"
    fi

    if has_command wrangler; then
      plan_line "Wrangler" "installed ($(get_version wrangler --version))"
    else
      plan_line "Wrangler" "install via npm"
    fi
  fi

  echo ""
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

install_formula() {
  # Usage: install_formula <label> <formula>
  local label="$1" formula="$2"
  if brew list --formula "$formula" >/dev/null 2>&1; then
    info "Upgrading $label"
    brew upgrade "$formula" 2>/dev/null || true
  else
    info "Installing $label"
    brew install "$formula" || warn "Failed to install $label"
  fi
}

install_cask() {
  # Usage: install_cask <label> <cask> <app_name>
  local label="$1" cask="$2" app_name="$3"

  if has_cask "$cask"; then
    info "Upgrading $label"
    brew upgrade --cask "$cask" 2>/dev/null || true
  elif has_app "$app_name"; then
    info "$label already installed (non-Homebrew); skipping"
  else
    info "Installing $label"
    brew install --cask "$cask" || warn "Failed to install $label"
  fi
}

install_npm_package() {
  # Usage: install_npm_package <label> <package> <bin>
  local label="$1" package="$2" bin="$3"

  if ! has_command npm; then
    warn "npm not found; skipping $label"
    return 1
  fi

  if has_command "$bin"; then
    info "Updating $label"
    npm update -g "$package" || npm install -g "$package" || warn "Failed to update $label"
  else
    info "Installing $label"
    npm install -g "$package" || warn "Failed to install $label"
  fi
}

install_core() {
  info "Installing core tools"
  echo ""

  install_formula "Git" "git"
  install_formula "GitHub CLI" "gh"
  install_cask "1Password" "1password" "1Password"
  install_cask "Slack" "slack" "Slack"
  install_cask "Zoom" "zoom" "zoom.us"
  install_cask "Google Chrome" "google-chrome" "Google Chrome"
  install_cask "Microsoft Office" "microsoft-office" "Microsoft Word"
}

install_dev() {
  echo ""
  info "Installing developer tools"
  echo ""

  install_cask "Visual Studio Code" "visual-studio-code" "Visual Studio Code"
  install_formula "AWS CLI" "awscli"
  install_npm_package "Wrangler" "wrangler" "wrangler"
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
  if has_command git; then
    echo "  Git ............... $(get_version git --version)"
  fi
  if has_command gh; then
    echo "  GitHub CLI ........ $(get_version gh --version)"
  fi

  # Check apps
  local -a check_apps=("1Password" "Slack" "zoom.us:Zoom" "Google Chrome" "Microsoft Word:Microsoft Office")
  for entry in "${check_apps[@]}"; do
    IFS=: read -r app_name label <<< "$entry"
    label="${label:-$app_name}"
    if has_app "$app_name"; then
      echo "  $label ............ installed"
    fi
  done

  if [[ "$INSTALL_DEV" == true ]]; then
    if has_app "Visual Studio Code"; then
      echo "  VS Code ........... installed"
    fi
    if has_command aws; then
      echo "  AWS CLI ........... $(get_version aws --version)"
    fi
    if has_command wrangler; then
      echo "  Wrangler .......... $(get_version wrangler --version)"
    fi
  fi

  echo ""
  info "Next steps:"
  echo "  - Sign in to 1Password, Slack, Zoom, Chrome, and Microsoft Office"
  echo "  - Run 'gh auth login' to authenticate with GitHub"
  if [[ "$INSTALL_DEV" == true ]]; then
    echo "  - Run 'aws configure' to set up AWS credentials"
  fi
  echo ""
  echo "  To install AI tools (Claude Code, Codex, Gemini):"
  echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)\""
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Work Tools Setup"

  select_profile
  preflight

  if ! confirm "Proceed with installation?"; then
    abort "Aborted."
  fi

  echo ""
  install_xcode_cli_tools
  install_homebrew
  install_node
  install_core

  if [[ "$INSTALL_DEV" == true ]]; then
    install_dev
  fi

  summary
}

main "$@"
