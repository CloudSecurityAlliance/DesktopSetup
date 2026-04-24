#!/usr/bin/env bash

# Cloud Security Alliance — macOS Update Script
#
# Updates all tools managed by macos-work-tools.sh and macos-ai-tools.sh:
#   1. Homebrew formulas and casks (Git, Node.js, apps, etc.)
#   2. Global npm packages (Codex, Gemini, Wrangler)
#   3. pip + all pip packages (in active venv or system Python)
#   4. Claude Code — updated via `claude update`
#
# Before updating, saves a snapshot of all installed versions to:
#   ~/Library/Logs/CSA-DesktopSetup/pre-update-<timestamp>.txt
#
# Usage:
#   bash scripts/macos-update.sh
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"

set -euo pipefail

SCRIPT_VERSION="2026.04242300"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Each update run will add any entries from this list that aren't yet
# registered (and that the user's gh account can access), then refresh
# all registered marketplaces.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/macos-ai-tools.sh      (installer, macOS)
#   scripts/windows-ai-tools.ps1   (installer, Windows)
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
# support `declare -A`. See the matching block in
# scripts/macos-ai-tools.sh for full rationale.
#
# KEEP IN SYNC: duplicated as plugin_marketplace_repo in
#   scripts/macos-ai-tools.sh
#   scripts/macos-plugins.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-ai-tools.ps1
#   scripts/windows-plugins.ps1
plugin_marketplace_repo() {
  case "$1" in
    claude-plugins-official) echo "anthropics/claude-plugins-official" ;;
    anthropic-agent-skills)  echo "anthropics/skills" ;;
    accounting-plugins)      echo "CloudSecurityAlliance-Internal/Accounting-Plugins" ;;
    csa-cino-plugins)        echo "CloudSecurityAlliance-Internal/CINO-Plugins" ;;
    csa-plugins)             echo "CloudSecurityAlliance-Internal/CSA-Plugins" ;;
    csa-research-plugins)    echo "CloudSecurityAlliance-Internal/Research-Plugins" ;;
    csa-training-plugins)    echo "CloudSecurityAlliance-Internal/Training-Plugins" ;;
    csa-plugins-official)    echo "CloudSecurityAlliance/csa-plugins-official" ;;
    *) ;;
  esac
}

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
    if has_command python3; then
      echo "Python: $(python3 --version 2>/dev/null || echo unknown)"
      [[ -n "${VIRTUAL_ENV:-}" ]] && echo "venv: $VIRTUAL_ENV"
      echo ""
      python3 -m pip list 2>/dev/null || echo "(none)"
    else
      echo "(Python not available)"
    fi
    echo ""
  } > "$SNAPSHOT_FILE"

  # Save pip freeze separately for easy rollback
  if has_command python3; then
    {
      echo "# CSA DesktopSetup pip snapshot — $(date)"
      echo "# Python: $(python3 --version 2>/dev/null || echo unknown)"
      [[ -n "${VIRTUAL_ENV:-}" ]] && echo "# venv: $VIRTUAL_ENV"
      echo "# Restore with: python3 -m pip install -r $(basename "$PIP_FREEZE_FILE")"
      echo ""
      python3 -m pip freeze 2>/dev/null
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
  if has_command python3; then
    local outdated_pip venv_note=""
    outdated_pip=$(python3 -m pip list --outdated --format=columns 2>/dev/null || true)
    [[ -n "${VIRTUAL_ENV:-}" ]] && venv_note=" (venv: $(basename "$VIRTUAL_ENV"))"

    if [[ -n "$outdated_pip" ]]; then
      echo "  pip packages to update${venv_note}:"
      echo "$outdated_pip" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  pip packages${venv_note}: all up to date"
    fi
  else
    echo "  Python: not available (skipping pip)"
  fi
  echo ""

  # Claude Code
  if has_command claude; then
    echo "  Claude Code: will run \`claude update\`"
  else
    echo "  Claude Code: not installed (skipping)"
  fi
  echo ""

  # Plugin marketplaces
  if has_command claude; then
    echo "  Plugin marketplaces: refresh registered, add accessible CSA repos"
    install_plugins_preview
    echo ""
  fi
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
  if ! has_command python3; then return 0; fi

  local venv_note=""
  [[ -n "${VIRTUAL_ENV:-}" ]] && venv_note=" (venv: $(basename "$VIRTUAL_ENV"))"

  info "Updating pip itself${venv_note}"
  python3 -m pip install --upgrade pip || warn "pip upgrade failed; continuing"

  info "Updating pip packages${venv_note}"
  local outdated
  outdated=$(python3 -m pip list --outdated --format=json 2>/dev/null || echo "[]")

  if [[ "$outdated" == "[]" ]] || [[ -z "$outdated" ]]; then
    echo "  All pip packages are up to date"
    return 0
  fi

  # Extract package names and upgrade them one at a time
  local pkg_names
  pkg_names=$(echo "$outdated" | python3 -c "import sys, json; print(' '.join(p['name'] for p in json.load(sys.stdin)))" 2>/dev/null || true)

  if [[ -z "$pkg_names" ]]; then return 0; fi

  for pkg in $pkg_names; do
    info "  Upgrading $pkg"
    python3 -m pip install --upgrade "$pkg" 2>/dev/null || warn "Failed to upgrade $pkg; continuing"
  done
}

update_claude_code() {
  if ! has_command claude; then return 0; fi

  info "Updating Claude Code"
  claude update || warn "claude update failed; continuing"
}

# ── Plugin marketplaces ─────────────────────────────────────────────
# Add any CSA marketplaces the user can access but hasn't registered yet,
# then refresh all registered marketplaces from their sources. Missing gh
# or gh-auth skips the add step silently — a user who isn't in CSA-Internal
# doesn't need to see chatter about repos they can't see.

sync_plugin_marketplaces() {
  has_command claude || return 0

  # If gh is available + authenticated, add any missing accessible ones
  # silently. Otherwise skip straight to the refresh pass.
  if has_command gh && gh auth status >/dev/null 2>&1; then
    local already_added
    already_added="$(claude plugin marketplace list 2>/dev/null \
      | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"

    local added=() failed=() failed_errs=()
    local repo add_err
    for repo in "${CSA_MARKETPLACES[@]}"; do
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
      success "Registered new plugin marketplaces:"
      printf '  + %s\n' "${added[@]}"
    fi
    if [[ ${#failed[@]} -gt 0 ]]; then
      warn "Failed to register ${#failed[@]} marketplace(s):"
      local i
      for i in "${!failed[@]}"; do
        printf '  ! %s\n      %s\n' "${failed[$i]}" "${failed_errs[$i]}"
      done
    fi
  fi

  info "Refreshing plugin marketplaces"
  claude plugin marketplace update || warn "marketplace update failed; continuing"
}

# ── Plugin install ──────────────────────────────────────────────────
# Fetch the public and internal plugin list files from HEAD, register
# any missing marketplaces (CSA marketplaces are gh-probed first),
# then install plugins that aren't yet installed. Silent-by-default:
# already-installed entries and inaccessible CSA marketplaces produce
# no output. Only actual installs and install errors print.
#
# This function is duplicated (by design) in scripts/macos-ai-tools.sh
# and in PowerShell form in scripts/windows-ai-tools.ps1. When fixing
# bugs here, mirror the fix in both other scripts.

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
      | sed -n 's/^[[:space:]]*❯[[:space:]]*\(.*\)$/\1/p')"
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
  # Use [[:space:]] (portable) rather than \s (not recognized by BSD sed).
  local registered_repos installed_plugins
  registered_repos="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"
  installed_plugins="$(claude plugin list 2>/dev/null \
    | sed -n 's/^[[:space:]]*❯[[:space:]]*\(.*\)$/\1/p')"

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
  if has_command python3; then
    echo "  Python ............ $(python3 --version 2>/dev/null)"
  fi
  if has_command python3; then
    echo "  pip ............... $(python3 -m pip --version 2>/dev/null | head -n1)"
  fi
  if has_command claude; then
    echo "  Claude Code ....... $(claude --version 2>/dev/null | head -n1)"
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
  [[ -f "$PIP_FREEZE_FILE" ]] && echo "    python3 -m pip install -r $PIP_FREEZE_FILE"
  echo ""

  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Update v${SCRIPT_VERSION}"

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
  update_claude_code
  sync_plugin_marketplaces
  install_plugins
  summary
}

main "$@"
