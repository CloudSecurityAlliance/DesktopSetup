#!/usr/bin/env bash

# Cloud Security Alliance — macOS AI Tools Setup
#
# Installs:
#   1. Xcode Command Line Tools
#   2. Homebrew (macOS package manager)
#   3. Node.js (via Homebrew, provides npm)
#   4. Python (via Homebrew, provides python3/pip3)
#   5. Document toolchain: pandoc + typst (via Homebrew), plus pyyaml +
#      pymupdf in ~/.default_venv — required by the document-pipeline plugin
#   6. Git (via Homebrew, latest version)
#   7. GitHub CLI (gh) + authentication
#   8. 1Password (via Homebrew cask, GUI app — needed for biometric CLI unlock)
#   9. 1Password CLI (via Homebrew)
#  10. Claude Desktop (via Homebrew cask; app self-updates, so direct-
#      download copies are detected and left alone)
#  11. ChatGPT Desktop (via Homebrew cask; same self-update story)
#  12. Claude Code (native installer, auto-updates)
#  13. OpenAI Codex CLI (via npm)
#  14. Google Gemini CLI (via npm)
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

set -euo pipefail

SCRIPT_VERSION="2026.08241200"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Plugin marketplaces to register with Claude Code. Each entry is an
# ORG/REPO on GitHub. At install time, each is probed via `gh` for
# accessibility; inaccessible ones (private org repos the user isn't a
# member of) are silently skipped.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/windows-ai-tools.ps1   (installer, Windows)
#   scripts/macos-update.sh        (full updater, macOS)
#   scripts/macos-plugins.sh       (standalone plugins, macOS)
#   scripts/windows-plugins.ps1    (standalone plugins, Windows)
# All five files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the scripts will drift.
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
# support `declare -A`. Used by install_plugins() to register missing
# marketplaces and (for CSA marketplaces) gh-probe access.
#
# Names `accounting-plugins` and any `csa-*` are treated as CSA-internal:
# gh-probed before register, silent-skip on access denial. The two
# public names are handled separately by plugin_marketplace_kind().
#
# KEEP IN SYNC: duplicated as plugin_marketplace_repo in
#   scripts/macos-update.sh
#   scripts/macos-plugins.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-ai-tools.ps1
#   scripts/windows-plugins.ps1
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
# Registers the CSA MCP server with Claude Code (HTTP transport,
# OAuth 2.1 + PKCE). The server answers unauthenticated callers, so the
# gate is not about access — we gate registration behind a `gh`-probe of
# a canonical CSA-Internal repo because this public bootstrap should only
# auto-wire CSA tooling into CSA-eligible accounts; a stranger shouldn't
# get a CSA OAuth server added unprompted. Matches the silent-by-default
# contract used for plugin marketplaces.
#
# KEEP IN SYNC: same constants and logic in
#   scripts/windows-ai-tools.ps1
#   scripts/macos-update.sh
#   scripts/macos-plugins.sh
#   scripts/windows-plugins.ps1
CSA_MCP_NAME="csa-mcp"
CSA_MCP_URL="https://cloudsecurityalliance.org/mcp"
CSA_MCP_GATE_REPO="CloudSecurityAlliance-Internal/CSA-Plugins"

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
SCRIPT_LABEL="macos-ai-tools.sh"
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

# Read CFBundleShortVersionString from a macOS .app bundle. Echoes empty
# on any failure (missing .app, missing key, unreadable plist). Use with
# `${ver:+, v$ver}` to only append the version if one was found.
get_app_version() {
  defaults read "$1/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null
}

# Echo the .app bundle's mtime as YYYY-MM-DD, reflecting last install or
# self-update. Useful at-a-glance staleness signal alongside the version.
# Empty on failure.
get_app_mtime() {
  date -r "$1" +%Y-%m-%d 2>/dev/null
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

# Upgrade a Homebrew package and say what actually happened.
#
# `info "Upgrading Git"` printed on EVERY run whether or not anything was upgraded, then
# `brew upgrade` was silenced - so the script announced work it usually did not do, and never
# said what version resulted. The plan above already lists the version you HAVE; this is the
# missing half. Quiet when there is nothing to do, like the rest of this script.
#
# $1 formula|cask   $2 package   $3 human label
csa_brew_upgrade() {
  local kind="$1" pkg="$2" label="$3" before after
  before="$(brew list --"$kind" --versions "$pkg" 2>/dev/null || true)"
  brew upgrade --"$kind" "$pkg" >/dev/null 2>&1 || true
  after="$(brew list --"$kind" --versions "$pkg" 2>/dev/null || true)"
  if [[ "$before" != "$after" ]]; then
    success "$label upgraded: ${before#* } -> ${after#* }"
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

  # Document toolchain (document-pipeline plugin: Markdown -> tagged PDF)
  if has_command pandoc; then
    echo "  pandoc ............ installed ($(get_version pandoc --version))"
  else
    echo "  pandoc ............ install via Homebrew"
  fi
  if has_command typst; then
    echo "  typst ............. installed ($(get_version typst --version))"
  else
    echo "  typst ............. install via Homebrew"
  fi
  # `pymupdf`, not `fitz`. Same package - `fitz` is the legacy import alias, and PyMuPDF now
  # prints "The `fitz` API is deprecated and will be removed in future" on every use. It showed
  # up in a real debug log. When it is finally removed this probe starts failing, and a failing
  # probe here means the script reinstalls the dependency on every single run, forever, while
  # reporting success. Probing the name we actually install avoids both.
  if python3 -c 'import yaml, pymupdf' >/dev/null 2>&1; then
    echo "  Preflight deps .... installed (pyyaml, pymupdf)"
  else
    echo "  Preflight deps .... install pyyaml + pymupdf into ~/.default_venv"
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

  # 1Password (GUI app — needed for biometric CLI unlock)
  if [[ -d "/Applications/1Password.app" ]]; then
    local onep_ver onep_dt onep_method
    onep_ver="$(get_app_version /Applications/1Password.app)"
    onep_dt="$(get_app_mtime /Applications/1Password.app)"
    if brew list --cask 1password >/dev/null 2>&1; then
      onep_method="Homebrew cask"
    else
      onep_method="non-Homebrew"
    fi
    echo "  1Password ......... installed ($onep_method${onep_ver:+, v$onep_ver}${onep_dt:+ · $onep_dt})"
  else
    echo "  1Password ......... install via Homebrew cask"
  fi

  # 1Password CLI
  if has_command op; then
    echo "  1Password CLI ..... installed ($(get_version op --version))"
  else
    echo "  1Password CLI ..... install via Homebrew"
  fi

  # Claude Desktop
  if [[ -d "/Applications/Claude.app" ]]; then
    local claude_ver claude_dt claude_method
    claude_ver="$(get_app_version /Applications/Claude.app)"
    claude_dt="$(get_app_mtime /Applications/Claude.app)"
    if brew list --cask claude >/dev/null 2>&1; then
      claude_method="Homebrew cask"
    else
      claude_method="non-Homebrew"
    fi
    echo "  Claude Desktop .... installed ($claude_method${claude_ver:+, v$claude_ver}${claude_dt:+ · $claude_dt})"
  else
    echo "  Claude Desktop .... install via Homebrew cask"
  fi

  # ChatGPT Desktop
  if [[ -d "/Applications/ChatGPT.app" ]]; then
    local chatgpt_ver chatgpt_dt chatgpt_method
    chatgpt_ver="$(get_app_version /Applications/ChatGPT.app)"
    chatgpt_dt="$(get_app_mtime /Applications/ChatGPT.app)"
    if brew list --cask chatgpt >/dev/null 2>&1; then
      chatgpt_method="Homebrew cask"
    else
      chatgpt_method="non-Homebrew"
    fi
    echo "  ChatGPT Desktop ... installed ($chatgpt_method${chatgpt_ver:+, v$chatgpt_ver}${chatgpt_dt:+ · $chatgpt_dt})"
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
  install_plugins_preview
  echo "  CSA MCP server       register $CSA_MCP_NAME if your GitHub account has CSA-Internal access"
  # Announced, because it was not: setup_csa_internal_tools installs and upgrades
  # csa-google-workspace, and a plan that does not mention it means somebody reading the plan
  # cannot tell whether their Google Workspace server was touched. Same gh-probe gate as the
  # line above, so it says "if ... access" for the same reason.
  echo "  Google Workspace     install/upgrade csa-google-workspace if your GitHub account has CSA-Internal access"

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

# ── Document toolchain ──────────────────────────────────────────────
# pandoc and typst render Markdown into CSA-branded, PDF/UA-1 tagged
# PDFs; the document-pipeline plugin's build script hard-requires both
# on PATH and exits 1 without them. pyyaml + pymupdf back its preflight
# checks.
#
# The deps go in a venv, not brew's python3: Homebrew Python is PEP 668
# externally-managed, so `pip install` into it fails outright. We use
# ~/.default_venv because document-pipeline's own launcher already probes
# it (after $CSA_PYTHON and any PATH python3 that already has the deps),
# so no PATH or env wiring is needed on our side.
CSA_VENV="$HOME/.default_venv"
CSA_DOC_PY_DEPS=(pyyaml pymupdf)

install_doc_toolchain() {
  ensure_brew_in_path

  local f
  for f in pandoc typst; do
    if brew list --formula "$f" >/dev/null 2>&1; then
      info "$f already installed: $(get_version "$f" --version)"
    else
      info "Installing $f"
      brew install "$f" \
        || warn "Failed to install $f — document rendering stays broken until it is installed"
    fi
  done
}

install_doc_python_deps() {
  if ! has_command python3; then
    warn "No python3 — skipping document preflight deps"
    return 0
  fi

  # Some other python3 on PATH may already satisfy them. Leave it alone.
  if python3 -c 'import yaml, pymupdf' >/dev/null 2>&1; then
    info "Document preflight deps already available to python3"
    return 0
  fi

  if [[ ! -x "$CSA_VENV/bin/python3" ]]; then
    info "Creating Python venv at $CSA_VENV"
    python3 -m venv "$CSA_VENV" || {
      warn "Could not create $CSA_VENV — skipping document preflight deps"
      return 0
    }
  fi

  info "Installing document preflight deps (${CSA_DOC_PY_DEPS[*]}) into $CSA_VENV"
  "$CSA_VENV/bin/python3" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  "$CSA_VENV/bin/python3" -m pip install --quiet --upgrade "${CSA_DOC_PY_DEPS[@]}" \
    || warn "Failed to install ${CSA_DOC_PY_DEPS[*]} — csa-preflight will print its own install hint"
}

install_git() {
  ensure_brew_in_path

  if brew list --formula git >/dev/null 2>&1; then
    csa_brew_upgrade formula git "Git"
  else
    info "Installing Git via Homebrew"
    brew install git || abort "Failed to install Git"
  fi
}

install_gh() {
  ensure_brew_in_path

  if brew list --formula gh >/dev/null 2>&1; then
    csa_brew_upgrade formula gh "GitHub CLI"
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
    # --scopes user:email: lets setup_git_identity read the user's primary
    # email via `gh api user/emails` when it's not public on the user
    # profile. Without it that endpoint returns HTTP 404.
    gh auth login --git-protocol https --scopes user:email || warn "gh auth login failed; you can run it manually later"
  fi
}

install_1password() {
  ensure_brew_in_path

  if brew list --cask 1password >/dev/null 2>&1; then
    info "1Password already installed; skipping"
    return 0
  fi

  if [[ -d "/Applications/1Password.app" ]]; then
    info "1Password already installed (non-Homebrew); skipping"
    return 0
  fi

  info "Installing 1Password"
  brew install --cask 1password || warn "Failed to install 1Password"
}

# Does the 1Password CLI still need its desktop-app integration turned on?
#
# Read from op's config rather than by running `op`: a real command can trigger a biometric
# prompt, and a setup script should never make somebody's laptop ask for a fingerprint. Once
# the app integration has been used, `system_auth_latest_signin` in ~/.config/op/config holds
# a token id; before that it is absent or empty.
#
# Defaults to SAYING SOMETHING when it cannot tell. A hint shown unnecessarily is mildly
# annoying; a hint withheld leaves `op` unusable for somebody who does not know why.
needs_1password_integration() {
  has_command op || return 1
  local config="${HOME}/.config/op/config"
  [[ -f "$config" ]] || return 0
  python3 -c '
import json, sys
try:
    with open(sys.argv[1]) as handle:
        signed_in = json.load(handle).get("system_auth_latest_signin") or ""
except Exception:
    sys.exit(0)          # unreadable: say something rather than assume it is set up
sys.exit(0 if not signed_in else 1)
' "$config"
}

install_1password_cli() {
  ensure_brew_in_path

  # `--cask`, not `--formula`. 1password-cli is a CASK, so the formula check never matched -
  # every run announced "Installing 1Password CLI" and then brew replied "Not upgrading, the
  # latest version is already installed". Two lines of output saying opposite things, on every
  # run, for something that had been installed for months.
  if brew list --cask 1password-cli >/dev/null 2>&1; then
    # Silent when there is nothing to do, like the rest of this script. `brew upgrade` on a
    # current cask writes its "Not upgrading" notice to stderr, which is not news.
    csa_brew_upgrade cask 1password-cli "1Password CLI"
  else
    info "Installing 1Password CLI"
    brew install --cask 1password-cli || warn "Failed to install 1Password CLI"
  fi
}

install_claude_desktop() {
  ensure_brew_in_path

  if brew list --cask claude >/dev/null 2>&1; then
    info "Claude Desktop already installed; skipping"
    return 0
  fi

  if [[ -d "/Applications/Claude.app" ]]; then
    info "Claude Desktop already installed (non-Homebrew); skipping"
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

  if [[ -d "/Applications/ChatGPT.app" ]]; then
    info "ChatGPT Desktop already installed (non-Homebrew); skipping"
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
      [[ -z "$current_email" ]] && echo "  git config --global user.email \"you@example.com\"" || true
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
      [[ -z "$set_email" ]] && echo "  user.email (run: git config --global user.email \"you@example.com\")" || true
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
    [[ -z "$current_email" ]] && echo "  git config --global user.email \"you@example.com\"" || true
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

  local added=() failed=() failed_errs=()
  local repo add_err
  for repo in "${CSA_MARKETPLACES[@]}"; do
    # Already registered, or not accessible to this account — silently skip.
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
    success "Registered Claude Code plugin marketplaces:"
    printf '  + %s\n' "${added[@]}"
  fi
  if [[ ${#failed[@]} -gt 0 ]]; then
    warn "Failed to register ${#failed[@]} marketplace(s):"
    local i
    for i in "${!failed[@]}"; do
      printf '  ! %s\n      %s\n' "${failed[$i]}" "${failed_errs[$i]}"
    done
  fi
}

# Register the CSA MCP server (csa-mcp) with Claude Code if missing.
# Silent-by-default: returns silently when claude/gh is unavailable, gh
# is unauthenticated, csa-mcp is already registered, or the user lacks
# CSA-Internal access. The server uses OAuth 2.1 + PKCE, so the user
# must run /mcp inside Claude Code to complete the browser sign-in —
# we print that reminder only on a fresh registration.
setup_csa_mcp_server() {
  has_command claude || return 0
  has_command gh || return 0
  gh auth status >/dev/null 2>&1 || return 0

  # Already registered? Don't clobber — would invalidate the OAuth session.
  if claude mcp list 2>/dev/null | grep -qE "^${CSA_MCP_NAME}[: ]"; then
    return 0
  fi

  # CSA-membership gate via gh probe of a canonical CSA-Internal repo.
  gh api "repos/$CSA_MCP_GATE_REPO" >/dev/null 2>&1 || return 0

  local add_err
  if add_err="$(claude mcp add --transport http --scope user "$CSA_MCP_NAME" "$CSA_MCP_URL" 2>&1 >/dev/null)"; then
    success "Registered Claude Code MCP server: $CSA_MCP_NAME"
    info "Run /mcp inside Claude Code to authenticate with the CSA MCP server."
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

  local script
  script="$(gh api "repos/$CSA_MCP_GATE_REPO/contents/internal-setup/csa-google-workspace-setup.sh" \
              --jq '.content' 2>/dev/null | base64 --decode 2>/dev/null)" || return 0
  [[ -n "$script" ]] || return 0
  # CSA_NESTED tells the fetched script that it is running inside another CSA installer, so it
  # should leave the closing summary to this one. Without it both printed "if anything above
  # went wrong, re-run with logging on", one after the other, which reads like a stutter and
  # gives two different instructions for the same thing ("<this script>" vs "the same command").
  CSA_NESTED=1 bash -c "$script" || warn "CSA internal setup reported a problem (see above)"
}

# ── Plugin install ──────────────────────────────────────────────────
# Fetch the public and internal plugin list files from HEAD, register
# any missing marketplaces (CSA marketplaces are gh-probed first),
# then install plugins that aren't yet installed. Silent-by-default:
# already-installed entries and inaccessible CSA marketplaces produce
# no output. Only actual installs and install errors print.

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
      | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')"
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
  local registered_repos installed_plugins
  registered_repos="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"
  installed_plugins="$(claude plugin list 2>/dev/null \
    | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')"

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
  if has_command pandoc; then
    echo "  pandoc ............ $(get_version pandoc --version)"
  fi
  if has_command typst; then
    echo "  typst ............. $(get_version typst --version)"
  fi
  if has_command git; then
    echo "  Git ............... $(get_version git --version)"
  fi
  if has_command gh; then
    echo "  GitHub CLI ........ $(get_version gh --version)"
  fi
  if brew list --cask 1password >/dev/null 2>&1 || [[ -d "/Applications/1Password.app" ]]; then
    echo "  1Password ......... installed"
  fi
  if has_command op; then
    echo "  1Password CLI ..... $(get_version op --version)"
  fi
  if brew list --cask claude >/dev/null 2>&1 || [[ -d "/Applications/Claude.app" ]]; then
    echo "  Claude Desktop .... installed"
  fi
  if brew list --cask chatgpt >/dev/null 2>&1 || [[ -d "/Applications/ChatGPT.app" ]]; then
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
  # Only what somebody has to DO, and only when they have to do it. Three lines telling
  # people to run a command named after the tool ("Run 'claude' to start Claude Code") are
  # not next steps, and the npm-update advice competed with the answer that actually
  # matters: re-run this script, which updates everything it installed.
  if has_command gh && ! gh auth status >/dev/null 2>&1; then
    echo "  - Run 'gh auth login' to authenticate with GitHub"
  fi
  if [[ -z "$(git config --global user.name 2>/dev/null)" ]] || [[ -z "$(git config --global user.email 2>/dev/null)" ]]; then
    echo "  - Configure Git identity: git config --global user.name \"Your Name\""
    echo "    and: git config --global user.email \"you@example.com\""
  fi
  if needs_1password_integration; then
    echo "  - Turn on the 1Password CLI integration: 1Password -> Settings -> Developer ->"
    echo "    \"Integrate with 1Password CLI\", then restart 1Password"
  fi
  echo "  - Re-run this script any time to update everything it installed"
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
    printf "${YELLOW}║${RESET}${BOLD}  IMPORTANT: Your shell configuration has been updated.       ${RESET}${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}  To use the newly installed tools, either:                   ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}    ${BOLD}1.${RESET} Open a new terminal window or tab                      ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}    ${BOLD}2.${RESET} Reload your current session:                           ${YELLOW}║${RESET}\n"
    printf "${YELLOW}║${RESET}                                                              ${YELLOW}║${RESET}\n"
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
  install_doc_toolchain
  install_doc_python_deps
  install_git
  install_gh
  setup_gh_auth
  setup_git_identity
  install_1password
  install_1password_cli
  install_claude_desktop
  install_chatgpt
  install_claude
  install_codex
  install_gemini
  setup_claude_env
  setup_plugin_marketplaces
  install_plugins
  setup_csa_mcp_server
  summary
  # Runs LAST, after the summary, so the internal setup's own output — including the
  # "you still need to log in" banner — is the final thing on screen instead of being
  # buried under a wall of install output the user has stopped reading.
  setup_csa_internal_tools
}

main "$@"
