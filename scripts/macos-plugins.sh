#!/usr/bin/env bash

# Cloud Security Alliance — macOS Plugin Install/Update
#
# Standalone script that just handles Claude Code plugins: register
# missing marketplaces (CSA ones via gh probe), install any plugins
# from scripts/csa-plugins.txt and scripts/csa-plugins-internal.txt
# that aren't yet installed, then refresh all registered marketplaces.
#
# Use this when you want to get current on plugins without running
# the full macos-ai-tools.sh (which also installs Homebrew apps) or
# macos-update.sh (which also upgrades Homebrew / npm / pip).
#
# Usage:
#   bash scripts/macos-plugins.sh
#   bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-plugins.sh)"

set -euo pipefail

SCRIPT_VERSION="2026.04271200"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Registered in sync_plugin_marketplaces() regardless of whether
# install_plugins() pulls anything from them. Keeps zero-plugin
# marketplaces (e.g. accounting-plugins) browsable after this script
# runs.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/macos-ai-tools.sh      (installer, macOS)
#   scripts/windows-ai-tools.ps1   (installer, Windows)
#   scripts/macos-update.sh        (full updater, macOS)
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
# support `declare -A`. See scripts/macos-ai-tools.sh for full
# rationale.
#
# KEEP IN SYNC: duplicated as plugin_marketplace_repo in
#   scripts/macos-ai-tools.sh
#   scripts/macos-update.sh
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

# ── CSA MCP server ──────────────────────────────────────────────────
# See scripts/macos-ai-tools.sh for full rationale. Keep these constants
# and the setup_csa_mcp_server function in sync across all five scripts.
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

# ── Plugin install ──────────────────────────────────────────────────
# Same logic as the bundled install_plugins() in macos-ai-tools.sh /
# macos-update.sh — fetch lists from HEAD, register missing
# marketplaces (CSA gh-probed), install plugins that aren't yet
# installed. Silent-by-default on skips.

PLUGIN_LIST_URL_PUBLIC="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins.txt"
PLUGIN_LIST_URL_INTERNAL="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins-internal.txt"

plugin_marketplace_kind() {
  case "$1" in
    claude-plugins-official|anthropic-agent-skills) echo public ;;
    *) echo csa ;;
  esac
}

plugin_list_entries() {
  grep -v -E '^\s*(#|$)'
}

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

  local registered_repos installed_plugins
  registered_repos="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"
  installed_plugins="$(claude plugin list 2>/dev/null \
    | sed -n 's/^[[:space:]]*❯[[:space:]]*\(.*\)$/\1/p')"

  local gh_authed=0
  if has_command gh && gh auth status >/dev/null 2>&1; then gh_authed=1; fi

  local added=() failed=() failed_errs=()
  local add_err inst_err

  local seen_markets=() market_usable=() seen_plugins=()

  local line name market repo kind
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    name="${line%@*}"
    market="${line#*@}"

    [[ " ${seen_markets[*]:-} " == *" $market "* ]] && continue
    seen_markets+=("$market")

    repo="$(plugin_marketplace_repo "$market")"
    if [[ -z "$repo" ]]; then
      warn "Plugin list references unknown marketplace '$market' — update plugin_marketplace_repo"
      continue
    fi

    kind="$(plugin_marketplace_kind "$market")"

    if grep -qxF "$repo" <<< "$registered_repos"; then
      market_usable+=("$market")
      continue
    fi

    if [[ "$kind" == csa ]]; then
      [[ $gh_authed -eq 1 ]] || continue
      gh api "repos/$repo" >/dev/null 2>&1 || continue
    fi

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

# ── CSA marketplace registration ────────────────────────────────────
# Register any CSA_MARKETPLACES entries the user can access but hasn't
# registered yet. This is independent of the plugin list — it keeps
# zero-plugin marketplaces (like accounting-plugins) registered so the
# user can browse them from within Claude Code.

sync_plugin_marketplaces() {
  has_command claude || return 0

  if has_command gh && gh auth status >/dev/null 2>&1; then
    local already_added
    already_added="$(claude plugin marketplace list 2>/dev/null \
      | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"

    local added=() failed=() failed_errs=()
    local repo add_err
    for repo in "${CSA_MARKETPLACES[@]}"; do
      grep -qxF "$repo" <<< "$already_added" && continue
      gh api "repos/$repo" >/dev/null 2>&1 || continue

      if add_err="$(claude plugin marketplace add "$repo" 2>&1 >/dev/null)"; then
        added+=("$repo")
      else
        failed+=("$repo")
        failed_errs+=("${add_err:-<no stderr output>}")
      fi
    done

    if [[ ${#added[@]} -gt 0 ]]; then
      success "Registered new CSA plugin marketplaces:"
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
}

# Register the CSA MCP server (csa-mcp) with Claude Code if missing.
# See scripts/macos-ai-tools.sh setup_csa_mcp_server for full rationale —
# silent unless we actually register, gh-probed CSA-Internal access gate,
# does not clobber existing OAuth sessions.
setup_csa_mcp_server() {
  has_command claude || return 0
  has_command gh || return 0
  gh auth status >/dev/null 2>&1 || return 0

  if claude mcp list 2>/dev/null | grep -qE "^${CSA_MCP_NAME}[: ]"; then
    return 0
  fi

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

# ── Preflight ───────────────────────────────────────────────────────

preflight() {
  echo ""
  info "Plugin sync plan:"
  echo ""

  if has_command claude; then
    echo "  Plugin marketplaces: refresh registered, add accessible CSA repos"
    install_plugins_preview
    echo "  CSA MCP server     : register $CSA_MCP_NAME if your GitHub account has CSA-Internal access"
  else
    warn "claude CLI not found — install it first via scripts/macos-ai-tools.sh"
    abort "Nothing to do without claude CLI."
  fi

  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS Plugin Sync v${SCRIPT_VERSION}"

  preflight

  if ! confirm "Proceed with plugin sync?"; then
    abort "Aborted."
  fi

  sync_plugin_marketplaces
  install_plugins
  setup_csa_mcp_server

  info "Refreshing plugin marketplaces"
  claude plugin marketplace update || warn "marketplace update failed; continuing"

  echo ""
  success "Plugin sync complete."
  echo ""
  echo "  To list installed plugins:"
  echo "    claude plugin list"
  echo ""
  echo "  To enable/disable individual plugins:"
  echo "    claude plugin enable <name>"
  echo "    claude plugin disable <name>"
  echo ""
}

main "$@"
