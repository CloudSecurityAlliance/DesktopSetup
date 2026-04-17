#!/usr/bin/env bash

# Cloud Security Alliance — macOS AI Tools Setup
#
# Installs:
#   1. Xcode Command Line Tools
#   2. Homebrew (macOS package manager)
#   3. Node.js (via Homebrew, provides npm)
#   4. Python (via Homebrew, provides python3/pip3)
#   5. Git (via Homebrew, latest version)
#   6. GitHub CLI (gh) + authentication
#   7. 1Password CLI (via Homebrew)
#   8. Claude Desktop (via Homebrew cask, auto-updates)
#   9. ChatGPT Desktop (via Homebrew cask, auto-updates)
#  10. Claude Code (native installer, auto-updates)
#  11. OpenAI Codex CLI (via npm)
#  12. Google Gemini CLI (via npm)
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

set -euo pipefail

SCRIPT_VERSION="2026.04171300"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Plugin marketplaces to register with Claude Code. Each entry is an
# ORG/REPO on GitHub. At install time, each is probed via `gh` for
# accessibility; inaccessible ones (private org repos the user isn't a
# member of) are silently skipped.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/windows-ai-tools.ps1   (installer, Windows)
#   scripts/macos-update.sh        (updater, macOS)
# All three files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the installer and updater will drift.
CSA_MARKETPLACES=(
  "CloudSecurityAlliance-Internal/CINO-Plugins"
  "CloudSecurityAlliance-Internal/CSA-Plugins"
  "CloudSecurityAlliance-Internal/Research-Plugins"
  "CloudSecurityAlliance-Internal/Training-Plugins"
  "CloudSecurityAlliance/csa-plugins-official"
)

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
path_updated=0              # set to 1 if ~/.local/bin was added to shell config

detect_migrations() {
  ensure_brew_in_path

  # Claude: should be native installer, not brew or npm
  # Check both the original scoped package name and the bare "claude" package.
  if has_command brew && brew list --cask claude-code >/dev/null 2>&1; then
    claude_needs_migration="brew"
  elif npm list -g @anthropic-ai/claude-code >/dev/null 2>&1 \
    || npm list -g claude >/dev/null 2>&1; then
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

  # Python
  if has_command python3; then
    echo "  Python ............ installed ($(get_version python3 --version))"
  else
    echo "  Python ............ install via Homebrew"
  fi

  # Git
  if has_command git && brew list --formula git >/dev/null 2>&1; then
    echo "  Git ............... installed ($(get_version git --version))"
  elif has_command git; then
    echo "  Git ............... upgrade to Homebrew version"
  else
    echo "  Git ............... install via Homebrew"
  fi

  # GitHub CLI
  if has_command gh; then
    echo "  GitHub CLI ........ installed ($(get_version gh --version))"
  else
    echo "  GitHub CLI ........ install via Homebrew"
  fi

  # 1Password CLI
  if has_command op; then
    echo "  1Password CLI ..... installed ($(get_version op --version))"
  else
    echo "  1Password CLI ..... install via Homebrew"
  fi

  # Claude Desktop
  if brew list --cask claude >/dev/null 2>&1; then
    echo "  Claude Desktop .... installed (Homebrew cask)"
  else
    echo "  Claude Desktop .... install via Homebrew cask"
  fi

  # ChatGPT Desktop
  if brew list --cask chatgpt >/dev/null 2>&1; then
    echo "  ChatGPT Desktop ... installed (Homebrew cask)"
  else
    echo "  ChatGPT Desktop ... install via Homebrew cask"
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

  # Claude Code flicker fix
  if grep -q 'CLAUDE_CODE_NO_FLICKER' "$HOME/.zprofile" 2>/dev/null \
    && grep -q 'CLAUDE_CODE_NO_FLICKER' "$HOME/.zshrc" 2>/dev/null; then
    echo "  CLAUDE_CODE_NO_FLICKER  already set"
  else
    echo "  CLAUDE_CODE_NO_FLICKER  set (enables flicker-free terminal renderer)"
  fi

  # Plugin marketplaces
  echo "  Plugin marketplaces  probe ${#CSA_MARKETPLACES[@]} CSA repos, add any your GitHub account can access"

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
    npm uninstall -g @anthropic-ai/claude-code 2>/dev/null || true
    npm uninstall -g claude 2>/dev/null || true
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
    if brew outdated node 2>/dev/null | grep -q node; then
      info "Upgrading Node.js"
      brew upgrade node || abort "Failed to upgrade Node.js"
    else
      info "Node.js already current: $(get_version node --version)"
    fi
  elif has_command node; then
    info "Node.js already installed (non-Homebrew): $(get_version node --version)"
  else
    info "Installing Node.js"
    brew install node || abort "Failed to install Node.js"
  fi
}

install_python() {
  ensure_brew_in_path

  if has_command python3; then
    info "Python already installed: $(get_version python3 --version)"
    return 0
  fi

  info "Installing Python"
  brew install python || abort "Failed to install Python"
}

install_git() {
  ensure_brew_in_path

  if brew list --formula git >/dev/null 2>&1; then
    info "Upgrading Git"
    brew upgrade git 2>/dev/null || true
  else
    info "Installing Git via Homebrew"
    brew install git || abort "Failed to install Git"
  fi
}

install_gh() {
  ensure_brew_in_path

  if brew list --formula gh >/dev/null 2>&1; then
    info "Upgrading GitHub CLI"
    brew upgrade gh 2>/dev/null || true
  else
    info "Installing GitHub CLI"
    brew install gh || abort "Failed to install GitHub CLI"
  fi
}

setup_gh_auth() {
  if ! has_command gh; then return 0; fi
  if gh auth status >/dev/null 2>&1; then
    info "GitHub CLI already authenticated"
    return 0
  fi
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    warn "Skipping gh auth login (non-interactive mode)"
    return 0
  fi

  echo ""
  info "GitHub CLI is installed but not authenticated."
  if confirm "Run 'gh auth login' now?"; then
    gh auth login --git-protocol https || warn "gh auth login failed; you can run it manually later"
  fi
}

install_1password_cli() {
  ensure_brew_in_path

  if brew list --formula 1password-cli >/dev/null 2>&1; then
    info "Upgrading 1Password CLI"
    brew upgrade 1password-cli 2>/dev/null || true
  else
    info "Installing 1Password CLI"
    brew install 1password-cli || warn "Failed to install 1Password CLI"
  fi
}

install_claude_desktop() {
  ensure_brew_in_path

  if brew list --cask claude >/dev/null 2>&1; then
    info "Claude Desktop already installed; skipping"
    return 0
  fi

  info "Installing Claude Desktop"
  brew install --cask claude || warn "Failed to install Claude Desktop"
}

install_chatgpt() {
  ensure_brew_in_path

  if brew list --cask chatgpt >/dev/null 2>&1; then
    info "ChatGPT Desktop already installed; skipping"
    return 0
  fi

  info "Installing ChatGPT Desktop"
  brew install --cask chatgpt || warn "Failed to install ChatGPT Desktop"
}

setup_git_identity() {
  local current_name current_email
  current_name="$(git config --global user.name 2>/dev/null || true)"
  current_email="$(git config --global user.email 2>/dev/null || true)"

  if [[ -n "$current_name" && -n "$current_email" ]]; then
    info "Git identity already configured: $current_name <$current_email>"
    return 0
  fi

  # Need gh authenticated to pull profile info
  if ! has_command gh || ! gh auth status >/dev/null 2>&1; then
    if [[ -z "$current_name" || -z "$current_email" ]]; then
      warn "Git identity not configured. Run these after authenticating with GitHub:"
      [[ -z "$current_name" ]]  && echo "  git config --global user.name \"Your Name\""
      [[ -z "$current_email" ]] && echo "  git config --global user.email \"you@example.com\""
    fi
    return 0
  fi

  # Fetch name and email from GitHub profile
  local gh_name gh_email
  gh_name="$(gh api user --jq '.name // empty' 2>/dev/null || true)"
  gh_email="$(gh api user --jq '.email // empty' 2>/dev/null || true)"

  # If email is private/null, try the emails endpoint
  if [[ -z "$gh_email" ]]; then
    gh_email="$(gh api user/emails --jq '[.[] | select(.primary==true)][0].email // empty' 2>/dev/null || true)"
  fi

  # Use GitHub values only for fields not already set
  local set_name="${current_name:-$gh_name}"
  local set_email="${current_email:-$gh_email}"

  if [[ -z "$set_name" && -z "$set_email" ]]; then
    warn "Could not determine Git identity from GitHub profile."
    warn "Run: git config --global user.name \"Your Name\""
    warn "Run: git config --global user.email \"you@example.com\""
    return 0
  fi

  if [[ -n "${NONINTERACTIVE-}" ]]; then
    # In non-interactive mode, set what we can silently
    [[ -z "$current_name" && -n "$set_name" ]]   && git config --global user.name "$set_name"
    [[ -z "$current_email" && -n "$set_email" ]] && git config --global user.email "$set_email"
    info "Git identity configured from GitHub profile"
    return 0
  fi

  echo ""
  info "Git identity (user.name / user.email) is used in every commit."
  if [[ -z "$current_name" && -n "$set_name" ]]; then
    echo "  Name:  $set_name (from GitHub)"
  fi
  if [[ -z "$current_email" && -n "$set_email" ]]; then
    echo "  Email: $set_email (from GitHub)"
  fi

  if confirm "Set Git identity from your GitHub profile?"; then
    [[ -z "$current_name" && -n "$set_name" ]]   && git config --global user.name "$set_name"   && success "Set user.name to: $set_name"
    [[ -z "$current_email" && -n "$set_email" ]] && git config --global user.email "$set_email" && success "Set user.email to: $set_email"
  else
    warn "Skipped. Set manually with:"
    [[ -z "$current_name" ]]  && echo "  git config --global user.name \"Your Name\""
    [[ -z "$current_email" ]] && echo "  git config --global user.email \"you@example.com\""
  fi
}

install_claude() {
  if [[ -n "$claude_needs_migration" ]]; then
    migrate_claude
  elif has_command claude; then
    info "Claude Code already installed ($(get_version claude --version)); skipping"
    return 0
  fi
  info "Installing Claude Code (native installer)"
  curl -fsSL https://claude.ai/install.sh | bash \
    || abort "Claude Code installation failed."

  # Ensure ~/.local/bin is on PATH for this session
  export PATH="$HOME/.local/bin:$PATH"

  # Write to both shell config files so all session types pick up the PATH:
  #   .zprofile — login shells (what macOS Terminal.app opens by default)
  #   .zshrc    — interactive non-login shells
  # Uses a broad pattern to catch any existing variant.
  if ! grep -q '\.local/bin' "$HOME/.zprofile" 2>/dev/null; then
    info "Adding ~/.local/bin to PATH in ~/.zprofile"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zprofile"
    path_updated=1
  fi
  if ! grep -q '\.local/bin' "$HOME/.zshrc" 2>/dev/null; then
    info "Adding ~/.local/bin to PATH in ~/.zshrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
    path_updated=1
  fi
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

# ── Environment setup ───────────────────────────────────────────────

setup_claude_env() {
  # Enable the flicker-free renderer — eliminates the terminal redraw flicker
  # that makes Claude Code unpleasant to use for long sessions.
  export CLAUDE_CODE_NO_FLICKER=1

  local wrote=0
  if ! grep -q 'CLAUDE_CODE_NO_FLICKER' "$HOME/.zprofile" 2>/dev/null; then
    echo 'export CLAUDE_CODE_NO_FLICKER=1' >> "$HOME/.zprofile"
    wrote=1
  fi
  if ! grep -q 'CLAUDE_CODE_NO_FLICKER' "$HOME/.zshrc" 2>/dev/null; then
    echo 'export CLAUDE_CODE_NO_FLICKER=1' >> "$HOME/.zshrc"
    wrote=1
  fi

  if [[ "$wrote" == "1" ]]; then
    success "Set CLAUDE_CODE_NO_FLICKER=1 (flicker-free terminal renderer)"
    path_updated=1
  else
    info "Claude Code environment already configured"
  fi
}

# ── Plugin marketplaces ─────────────────────────────────────────────
# Register CSA plugin marketplaces with Claude Code, but only the ones
# the authenticated GitHub account can actually see. Missing preconditions
# (no claude, no gh, not authenticated) and inaccessible repos are silent —
# a user who isn't in CSA-Internal just gets the public marketplace and
# doesn't see any chatter about the internal ones.

setup_plugin_marketplaces() {
  has_command claude || return 0
  has_command gh || return 0
  gh auth status >/dev/null 2>&1 || return 0

  # Snapshot already-registered marketplaces (single call).
  # list format: "    Source: GitHub (ORG/REPO)"
  local already_added
  already_added="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"

  local added=() failed=()
  local repo
  for repo in "${CSA_MARKETPLACES[@]}"; do
    # Already registered, or not accessible to this account — silently skip.
    grep -qxF "$repo" <<< "$already_added" && continue
    gh api "repos/$repo" >/dev/null 2>&1 || continue

    if claude plugin marketplace add "$repo" >/dev/null 2>&1; then
      added+=("$repo")
    else
      failed+=("$repo")
    fi
  done

  if [[ ${#added[@]} -gt 0 ]]; then
    success "Registered Claude Code plugin marketplaces:"
    printf '  + %s\n' "${added[@]}"
  fi
  if [[ ${#failed[@]} -gt 0 ]]; then
    warn "Failed to register ${#failed[@]} marketplace(s):"
    printf '  ! %s\n' "${failed[@]}"
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
  if has_command python3; then
    echo "  Python ............ $(get_version python3 --version)"
    echo "  pip ............... $(get_version pip3 --version)"
  fi
  if has_command git; then
    echo "  Git ............... $(get_version git --version)"
  fi
  if has_command gh; then
    echo "  GitHub CLI ........ $(get_version gh --version)"
  fi
  if has_command op; then
    echo "  1Password CLI ..... $(get_version op --version)"
  fi
  if brew list --cask claude >/dev/null 2>&1; then
    echo "  Claude Desktop .... installed"
  fi
  if brew list --cask chatgpt >/dev/null 2>&1; then
    echo "  ChatGPT Desktop ... installed"
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
  if has_command gh && ! gh auth status >/dev/null 2>&1; then
    echo "  - Run 'gh auth login' to authenticate with GitHub"
  fi
  if [[ -z "$(git config --global user.name 2>/dev/null)" ]] || [[ -z "$(git config --global user.email 2>/dev/null)" ]]; then
    echo "  - Configure Git identity: git config --global user.name \"Your Name\""
    echo "    and: git config --global user.email \"you@example.com\""
  fi
  echo "  - Enable 1Password CLI integration: 1Password app → Settings → Developer → \"Integrate with 1Password CLI\", then restart 1Password"
  echo "  - Run 'claude' to start Claude Code"
  echo "  - Run 'codex' to start Codex CLI"
  echo "  - Run 'gemini' to start Gemini CLI"
  echo ""
  echo "  To update npm-installed tools later:"
  echo "    npm update -g @openai/codex @google/gemini-cli"
  echo ""
  echo "  To refresh plugin marketplaces:"
  echo "    claude plugin marketplace update"
  echo "  (auto-update per marketplace is opt-in — toggle from /plugin in Claude Code)"
  echo ""
  echo "  Claude Code updates itself automatically."
  echo ""
  info "Learn Claude Code in your terminal:"
  echo "  /powerup  — interactive lessons with animated demos, one feature at a time"
  echo "  /init     — in a project directory, first ask Claude to read all the files,"
  echo "              then type /init — creates a CLAUDE.md tailored to your codebase"
  echo ""

  # PATH reload banner — only shown when ~/.local/bin was actually added to shell config
  if [[ "${path_updated}" == "1" ]]; then
    echo ""
    printf "${YELLOW}╔══════════════════════════════════════════════════════════════╗${RESET}\n"
    printf "${YELLOW}║${RESET}${BOLD}  IMPORTANT: Your shell configuration has been updated.      ${RESET}${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}  To use the newly installed tools, either:                    ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}    ${BOLD}1.${RESET} Open a new terminal window or tab                      ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}    ${BOLD}2.${RESET} Reload your current session:                          ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}       ${GREEN}source ~/.zprofile${RESET}                                     ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}╚══════════════════════════════════════════════════════════════╝${RESET}\n"
    echo ""
  fi
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS AI Tools Setup v${SCRIPT_VERSION}"

  check_running_tools
  preflight

  if ! confirm "Proceed with installation?"; then
    abort "Aborted."
  fi

  echo ""
  install_xcode_cli_tools
  install_homebrew
  install_node
  install_python
  install_git
  install_gh
  install_1password_cli
  install_claude_desktop
  install_chatgpt
  install_claude
  install_codex
  install_gemini
  setup_claude_env
  setup_gh_auth
  setup_git_identity
  setup_plugin_marketplaces
  summary
}

main "$@"
