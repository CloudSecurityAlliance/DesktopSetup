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

SCRIPT_VERSION="2026.0932215"

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
SCRIPT_LABEL="macos-work-tools.sh"
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
  [[ -z "$CSA_LOG_INHERITED" ]] && info "debug logging to $CSA_LOG"
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

# ── Post-install setup ─────────────────────────────────────────────

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
    # --scopes user:email: lets setup_git_identity read the user's primary
    # email via `gh api user/emails` when it's not public on the user
    # profile. Without it that endpoint returns HTTP 404.
    gh auth login --git-protocol https --scopes user:email || warn "gh auth login failed; you can run it manually later"
  fi
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
    if [[ -n "$set_name" && -n "$set_email" ]]; then
      info "Git identity configured from GitHub profile"
    else
      warn "Git identity partially configured from GitHub profile. Still missing:"
      [[ -z "$set_name" ]]  && echo "  user.name  (run: git config --global user.name \"Your Name\")"
      [[ -z "$set_email" ]] && echo "  user.email (run: git config --global user.email \"you@example.com\")"
    fi
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

    # Catch partial success: GitHub didn't expose everything we needed
    # (common cause: existing gh token lacks the user:email scope, so the
    # email fallback returns 404 and we have no email to set).
    if [[ -z "$set_name" || -z "$set_email" ]]; then
      warn "GitHub didn't expose everything. Set manually:"
      [[ -z "$set_name" ]] && echo "  git config --global user.name \"Your Name\""
      if [[ -z "$set_email" ]]; then
        echo "  git config --global user.email \"you@example.com\""
        echo "  (or run 'gh auth refresh --scopes user:email' and re-run this script to pull it from GitHub)"
      fi
    fi
  else
    warn "Skipped. Set manually with:"
    [[ -z "$current_name" ]]  && echo "  git config --global user.name \"Your Name\""
    [[ -z "$current_email" ]] && echo "  git config --global user.email \"you@example.com\""
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
  if has_command gh && ! gh auth status >/dev/null 2>&1; then
    echo "  - Run 'gh auth login' to authenticate with GitHub"
  fi
  if [[ -z "$(git config --global user.name 2>/dev/null)" ]] || [[ -z "$(git config --global user.email 2>/dev/null)" ]]; then
    echo "  - Configure Git identity: git config --global user.name \"Your Name\""
    echo "    and: git config --global user.email \"you@example.com\""
  fi
  if [[ "$INSTALL_DEV" == true ]]; then
    echo "  - Run 'aws configure' to set up AWS credentials"
  fi
  echo ""
  echo "  To install AI tools (Claude Code, Codex, Gemini):"
  echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)\""
  echo ""

  # PATH reload banner
  echo ""
  printf "${YELLOW}╔══════════════════════════════════════════════════════════════╗${RESET}\n"
  printf "${YELLOW}║${RESET}${BOLD}  IMPORTANT: Your PATH has been updated.                     ${RESET}${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}  To use the newly installed tools, either:                    ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}    ${BOLD}1.${RESET} Open a new terminal window or tab                      ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}    ${BOLD}2.${RESET} Reload your current session:                          ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}       ${GREEN}source ~/.zshrc${RESET}                                        ${YELLOW}║${RESET}\n"
  printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
  printf "${YELLOW}╚══════════════════════════════════════════════════════════════╝${RESET}\n"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Work Tools Setup v${SCRIPT_VERSION}"

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

  setup_gh_auth
  setup_git_identity
  summary
}

main "$@"

csa_debug_hint
