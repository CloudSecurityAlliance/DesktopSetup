#!/usr/bin/env bash

# Cloud Security Alliance — macOS CSA Plugins and MCP Servers Install/Update
#
# Standalone script for the CSA layer: Claude Code plugins AND every
# CSA MCP server. It registers missing marketplaces (CSA ones via gh
# probe), installs any plugins from scripts/csa-plugins.txt and
# scripts/csa-plugins-internal.txt that aren't yet installed, refreshes
# all registered marketplaces, registers the CSA MCP server, and then
# installs or upgrades each internal MCP server from the gate repo.
#
# Use this when you want to get current on the CSA layer without running
# the full macos-ai-tools.sh (which also installs Homebrew apps) or
# macos-update.sh (which also upgrades Homebrew / npm / pip).
#
# The name says "plugins" for compatibility: it is in documented curl
# one-liners that fetch HEAD, and `main` is the release. See #89 - every
# string that NAMES this script now mentions MCP servers, because the
# naming was the bug: the repo's own maintainer ran the full installer to
# pick up one new MCP server, which this would have done in a fraction of
# the time.
#
# Usage:
#   bash scripts/macos-plugins.sh
#   bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-plugins.sh)"

set -euo pipefail

SCRIPT_VERSION="2026-11-14T05:43Z"

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
#   scripts/windows-update.ps1     (full updater, Windows)
# All six files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the scripts will drift.
# One entry per internal MCP server. Top-level, beside CSA_MARKETPLACES, because
# macos-ai-tools.sh's installation plan has to count it and a list local to the function that
# runs it cannot be counted from the plan. It was local, that plan named two of these four by
# hand, and two servers were installed the person had not been shown. Kept here in every script
# carrying setup_csa_internal_tools so the shared function stays byte-identical.
CSA_INTERNAL_SETUPS=(
  csa-google-workspace-setup.sh
  csa-google-gmail-calendar-setup.sh
  csa-skilljar-setup.sh
  csa-zendesk-setup.sh
)

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
#   scripts/windows-update.ps1
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
# See scripts/macos-ai-tools.sh for full rationale. Keep these constants
# and the setup_csa_mcp_server function in sync across all six scripts.
CSA_MCP_NAME="csa-mcp"
CSA_MCP_URL="https://cloudsecurityalliance.org/mcp"
CSA_MCP_GATE_REPO="CloudSecurityAlliance-Internal/CSA-Plugins"

# The interpreter the internal setup scripts install their servers on. Declared in all six
# entry scripts, and pinned equal by tests/test_python_pins.py; before that only the two
# *-ai-tools scripts declared it and -update / -plugins passed an empty value.
CSA_PYTHON_PREFERRED="3.14"

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
SCRIPT_LABEL="macos-plugins.sh"
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
    printf '\n--- %s %s ---\n' "${SCRIPT_LABEL:-desktopsetup}" "${SCRIPT_VERSION}" >> "$CSA_LOG"
  else
    CSA_LOG="${HOME}/desktopsetup-$(date +%Y%m%d-%H%M%S).log"
    ( umask 077; : > "$CSA_LOG" )      # 0600 from creation, not chmod-ed afterwards
    {
      echo "=== DesktopSetup $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
      echo "This log is REDACTED for known credential shapes, but review it before sharing."
      echo "$(uname -sr) · bash ${BASH_VERSION} · ${SCRIPT_LABEL:-desktopsetup} ${SCRIPT_VERSION}"
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
  # The registration audit's working directory (csa_registrations_dir) holds its plan file. It is
  # removed on every exit path: a declined plan and a run stopped early as well as a finished one.
  if [[ -n "${CSA_REG_DIR:-}" && -d "$CSA_REG_DIR" ]]; then
    rm -rf "$CSA_REG_DIR" || true
  fi
  csa_debug_hint
  return $status
}
# csa_on_exit removes CSA_REG_DIR with rm -rf, so it is never taken from the environment: only
# csa_registrations_dir sets it, to a directory mktemp made for this run.
unset CSA_REG_DIR
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
      | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')" || installed_plugins=""
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
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')" || registered_repos=""
  installed_plugins="$(claude plugin list 2>/dev/null \
    | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')" || installed_plugins=""

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
      | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')" || already_added=""

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
    info "  sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
  else
    warn "Failed to register Claude Code MCP server '$CSA_MCP_NAME':"
    printf '      %s\n' "${add_err:-<no stderr output>}"
  fi
}

# ── CSA MCP registrations: audited in the plan, repaired after the setups (#179, Plan 2) ──
# scripts/csa-mcp-registrations.py finds every registration of the four CSA MCP servers in Claude
# Code, Claude Desktop, Codex and Gemini. It is fetched from HEAD, as the plugin lists are, into a
# mktemp directory that lives for one run: CSA_REG_DIR, which csa_on_exit removes on every exit.
# The preflight runs its read-only `plan`, which records what it showed in plan.json. The last step
# of setup_csa_internal_tools, after the gate setups have installed or rebuilt each binary, runs
# `apply` on exactly that file, so a registration the person was not shown is reported and never
# changed (A4), then `verify`, which launches no server while D5 holds.
#
# KEEP IN SYNC: these six functions are byte-identical in macos-ai-tools.sh, macos-update.sh and
# macos-plugins.sh (tools/check-duplication.py). The Windows twins are #184's Task 4W; until they
# land, tests/test_mcp_registrations.py's wiring_windows_twin_exists reports a SKIP on every run.

# Makes this run's working directory in the CALLER's shell, so call it directly and never inside
# $(...): there it would set CSA_REG_DIR in a subshell, and lose it. Reused once made; empty when
# mktemp fails.
csa_registrations_dir() {
  if [[ -z "${CSA_REG_DIR:-}" || ! -d "$CSA_REG_DIR" ]]; then
    CSA_REG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csa-registrations.XXXXXX" 2>/dev/null)" || CSA_REG_DIR=""
  fi
  return 0
}

# Prints the csa-mcp-registrations.py to run, or nothing. It sets nothing, so it is safe inside
# $(...). CSA_REGISTRATIONS_PY names a local copy, for tests and branch runs; one that is not a
# readable file prints nothing, so a typo is said rather than quietly running HEAD's copy instead.
csa_registrations_py() {
  local dest
  if [[ -n "${CSA_REGISTRATIONS_PY:-}" ]]; then
    if [[ -f "$CSA_REGISTRATIONS_PY" && -r "$CSA_REGISTRATIONS_PY" ]]; then
      printf '%s\n' "$CSA_REGISTRATIONS_PY"
    fi
    return 0
  fi
  if [[ -z "${CSA_REG_DIR:-}" || ! -d "$CSA_REG_DIR" ]] || ! has_command curl; then
    return 0
  fi
  dest="$CSA_REG_DIR/csa-mcp-registrations.py"
  if [[ ! -s "$dest" ]]; then
    rm -f "$dest.part"
    if curl -fsSL --max-time 60 -H 'Cache-Control: no-cache' -o "$dest.part" \
        "$CSA_RAW_BASE/csa-mcp-registrations.py" 2>/dev/null && [[ -s "$dest.part" ]]; then
      mv -f "$dest.part" "$dest"
    else
      rm -f "$dest.part"
      return 0
    fi
  fi
  printf '%s\n' "$dest"
}

# Prints a Python that can run csa-mcp-registrations.py (stdlib only, 3.9 or later), or nothing.
# Self-contained, because macos-plugins.sh has no find_csa_python. The candidates, in order:
# python3 on PATH; uv's CSA Python, any build; Homebrew's python3 under each of its two prefixes;
# and Apple's, only with the Command Line Tools, because without them that stub opens an install
# dialog. Each is an absolute path that must pass -f and -x, which follow links, so a dangling one
# (a venv whose Homebrew Python was upgraded away) is never run. Then it must run, -I so neither
# the working directory nor PYTHONPATH can stand in for the stdlib, within 10 s: stock macOS has
# no `timeout`. So a dead ~/.default_venv activated by ~/.zshrc, or a dead Homebrew Python, no
# longer skips the audit: the next candidate is tried.
csa_registrations_python() {
  local apple=/usr/bin/python3 n cand pid waited
  for n in 1 2 3 4 5; do
    cand=""
    case "$n" in
      1) cand="$(command -v python3 2>/dev/null)" || cand="" ;;
      2) if has_command uv; then
           cand="$(uv python find --system "$CSA_PYTHON_PREFERRED" 2>/dev/null)" || cand=""
         fi ;;
      3) cand=/opt/homebrew/bin/python3 ;;
      4) cand=/usr/local/bin/python3 ;;
      5) cand="$apple" ;;
    esac
    if [[ "$cand" != /* || ! -f "$cand" || ! -x "$cand" ]]; then
      continue
    fi
    if [[ "$cand" == "$apple" ]] && ! xcode-select -p >/dev/null 2>&1; then
      continue
    fi
    "$cand" -I -c 'import sys, json; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1 &
    pid=$!
    waited=0
    while kill -0 "$pid" 2>/dev/null && [[ $waited -lt 100 ]]; do
      sleep 0.1
      waited=$((waited + 1))
    done
    if [[ $waited -ge 100 ]]; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    if wait "$pid" 2>/dev/null; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 0
}

# A `log` line of csa-mcp-registrations.py is for the debug log only, never the screen. It goes
# into the file through the same redactor as everything else there, and only when CSA_DEBUG made
# one: an exported CSA_LOG alone is not a debug log, and nothing is written to it.
csa_registrations_log() {
  if [[ -n "${CSA_LOG:-}" ]] && csa_debug_requested; then
    printf '  [csa-mcp-registrations] %s\n' "$1" | csa_redact >> "$CSA_LOG" 2>/dev/null || true
  fi
  return 0
}

# The plan's rows for the registrations, inside the Internal MCP servers block. Read-only: the
# .py's `plan` writes nothing but its plan file, kept for repair_csa_registrations. Past its header
# it is silent for an account without CSA-Internal access, as the block's other rows are.
csa_registrations_preview() {
  local python py out rc=0 kind text
  echo "                       then audit their registrations in Claude Code (user and local scopes), Claude Desktop, Codex and Gemini,"
  echo "                       and re-point a dead one at ~/.local/bin keeping every setting"
  if ! has_command gh || ! gh auth status >/dev/null 2>&1 \
      || ! gh api "repos/$CSA_MCP_GATE_REPO" >/dev/null 2>&1; then
    return 0
  fi
  # First, before anything reads CSA_REG_DIR: under set -u an unset one would end the run.
  csa_registrations_dir
  if [[ -z "${CSA_REG_DIR:-}" ]]; then
    echo "                       registration audit skipped: couldn't make a temporary directory; nothing will be changed"
    return 0
  fi
  python="$(csa_registrations_python)" || python=""
  if [[ -z "$python" ]]; then
    echo "                       registration audit skipped: no Python 3.9 or later was found; nothing will be changed"
    return 0
  fi
  py="$(csa_registrations_py)" || py=""
  if [[ -z "$py" && -n "${CSA_REGISTRATIONS_PY:-}" ]]; then
    echo "                       registration audit skipped: CSA_REGISTRATIONS_PY is not a readable file; nothing will be changed"
    return 0
  fi
  if [[ -z "$py" ]]; then
    echo "                       registration audit skipped: couldn't fetch csa-mcp-registrations.py; nothing will be changed"
    return 0
  fi
  # --out must be a new file. This directory is this run's own, so a leftover is ours to remove.
  rm -f "$CSA_REG_DIR/plan.json"
  out="$("$python" -I "$py" plan --out "$CSA_REG_DIR/plan.json" </dev/null)" || rc=$?
  while IFS=$'\t' read -r kind text; do
    case "$kind" in
      row) echo "                       $text" ;;
      "") ;;
      log) csa_registrations_log "$text" ;;
      *) csa_registrations_log "$kind${text:+ $text}" ;;
    esac
  done <<< "$out"
  if [[ $rc -ne 0 ]]; then
    # No plan file, so the repair acts on nothing it finds (repair_csa_registrations).
    rm -f "$CSA_REG_DIR/plan.json"
    csa_registrations_log "plan exited $rc"
    echo "                       registration audit failed; nothing will be changed"
  fi
  return 0
}

# The last step of setup_csa_internal_tools, so it runs behind the same gh gate, and after the
# gate setups have installed or rebuilt each standard binary. `apply` re-points only what the plan
# showed and is unchanged since. With no plan file (the audit was skipped or failed before the
# person agreed) it is handed a plan with no findings, so every finding is reported and none is
# acted on. Then `verify`, without --run: the .py decides, by D5, whether anything is launched.
# Each line is shown as the .py prints it, so a server check, once D5 allows one, is not a silent
# wait. It never fails the run.
repair_csa_registrations() {
  local python="" py="" why="" approved step kind text
  local args=()
  csa_registrations_dir
  if [[ -z "${CSA_REG_DIR:-}" ]]; then
    why="couldn't make a temporary directory"
  else
    python="$(csa_registrations_python)" || python=""
    if [[ -z "$python" ]]; then
      why="no Python 3.9 or later was found"
    else
      py="$(csa_registrations_py)" || py=""
      if [[ -z "$py" ]]; then
        why="couldn't get csa-mcp-registrations.py"
      fi
    fi
  fi
  if [[ -n "$why" ]]; then
    warn "CSA MCP registrations were not checked: $why; nothing was changed"
  else
    info "CSA MCP registrations: re-pointing what the plan showed, if anything (csa-mcp-registrations.py)"
    approved="$CSA_REG_DIR/plan.json"
    if [[ ! -f "$approved" ]]; then
      approved="$CSA_REG_DIR/plan-with-no-findings.json"
      printf '%s\n' '{"tool": "csa-mcp-registrations", "findings": []}' > "$approved" 2>/dev/null || true
    fi
    for step in apply verify; do
      if [[ "$step" == apply ]]; then
        args=(apply --approved "$approved")
      else
        args=(verify)
      fi
      while IFS=$'\t' read -r kind text; do
        case "$kind" in
          ok) success "$text" ;;
          info|row) info "$text" ;;
          warn) warn "$text" ;;
          exit) warn "csa-mcp-registrations.py $step exited $text" ;;
          "") ;;
          log) csa_registrations_log "$text" ;;
          *) csa_registrations_log "$kind${text:+ $text}" ;;
        esac
      done < <("$python" -I "$py" "${args[@]}" </dev/null || printf 'exit\t%s\n' "$?")
    done
  fi
  if [[ -n "${CSA_REG_DIR:-}" ]]; then
    rm -rf "$CSA_REG_DIR" || true
  fi
  unset CSA_REG_DIR
  return 0
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

  local name script
  # What the gate repo ACTUALLY holds. The loop below does `continue` on a script it cannot
  # fetch - deliberately, so one absent server does not stop the ones after it - which makes a
  # stale list produce NO OUTPUT AT ALL. The list is copied into six scripts and has drifted
  # twice (#85, #92); both times somebody noticed a server missing days later. See #95.
  #
  # tests/test_internal_setup_lists.py asserts the six copies agree with each other and says it
  # cannot check them against the gate repo, which is private. Here we can.
  gate_has="$(gh api "repos/${CSA_MCP_GATE_REPO}/contents/internal-setup" --jq '.[].name' 2>/dev/null \
              | grep -E '^csa-.*-setup\.sh$' || true)"
  if [[ -n "$gate_has" ]]; then
    for have in $gate_has; do
      listed=""
      for want in "${CSA_INTERNAL_SETUPS[@]}"; do
        if [[ "$want" == "$have" ]]; then listed=1; break; fi
      done
      if [[ -z "$listed" ]]; then
        warn "${have} is in the gate repo but not in this installer's list - a server nobody is installing (#95)"
      fi
    done
    for want in "${CSA_INTERNAL_SETUPS[@]}"; do
      if ! printf '%s\n' "$gate_has" | grep -qxF "$want"; then
        info "${want} is listed here but not yet in the gate repo; skipping it"
      fi
    done
  fi

  for name in "${CSA_INTERNAL_SETUPS[@]}"; do
    script="$(gh api "repos/$CSA_MCP_GATE_REPO/contents/internal-setup/$name" \
                --jq '.content' 2>/dev/null | base64 --decode 2>/dev/null)" || continue
    [[ -n "$script" ]] || continue
    # `continue`, not `return`: a setup script that is absent from the gate repo - because
    # it has not been merged yet, or was renamed - must not stop the ones after it. The
    # earlier single-script form returned, so a rename would have silently disabled every
    # server that followed.
    #
    # CSA_PYTHON_PREFERRED tells it which interpreter to install the server on. All six entry
    # scripts declare it (3.14; tests/test_python_pins.py pins them), so it is never empty
    # here, and the setup script does not have to guess. Passed identically so all three
    # copies of this function stay byte-identical, which tools/check-duplication.py
    # enforces. See CSA-Plugins#133.
    # CSA_NESTED tells the fetched script that it is running inside another CSA installer, so it
    # should leave the closing summary to this one. Without it both printed "if anything above
    # went wrong, re-run with logging on", one after the other, which reads like a stutter and
    # gives two different instructions for the same thing ("<this script>" vs "the same command").
    CSA_NESTED=1 CSA_PYTHON_PREFERRED="${CSA_PYTHON_PREFERRED:-}" bash -c "$script" || warn "CSA internal setup ($name) reported a problem (see above)"
  done
  # Last, behind the same gate and after every setup above: the plan's registration repairs.
  repair_csa_registrations
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
    echo "                       sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
    # DERIVED, for the reason the marketplace line is. This preview named none of the four
    # internal servers while installing all four, so a person agreed to a list that omitted
    # every one of them. Enumerated so the plan and the run cannot disagree.
    echo "  Internal MCP servers install/upgrade ${#CSA_INTERNAL_SETUPS[@]} servers on Python ${CSA_PYTHON_PREFERRED} (standard build) if your GitHub account has CSA-Internal access"
    echo "                       (installs uv's Python ${CSA_PYTHON_PREFERRED} standard build if it is missing)"
    local setup_name
    for setup_name in "${CSA_INTERNAL_SETUPS[@]}"; do
      echo "                       ${setup_name%-setup.sh}"
    done
    # Then every registration of those servers, and the dead ones it will re-point (#179, Plan 2).
    # Called directly: it sets CSA_REG_DIR, where the plan file waits for repair_csa_registrations.
    csa_registrations_preview
    echo "                       each prints what it may do before it is used"
  else
    warn "claude CLI not found — install it first via scripts/macos-ai-tools.sh"
    abort "Nothing to do without claude CLI."
  fi

  echo ""
}

# ── Main ────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS CSA Plugins and MCP Servers ${SCRIPT_VERSION}"

  preflight

  if ! confirm "Proceed with the CSA plugin and MCP server sync?"; then
    abort "Aborted."
  fi

  sync_plugin_marketplaces
  install_plugins
  setup_csa_mcp_server

  info "Refreshing plugin marketplaces"
  claude plugin marketplace update || warn "marketplace update failed; continuing"

  echo ""
  success "CSA plugins and MCP servers are up to date."
  echo ""
  echo "  To list installed plugins:"
  echo "    claude plugin list"
  echo ""
  echo "  To enable/disable individual plugins:"
  echo "    claude plugin enable <name>"
  echo "    claude plugin disable <name>"
  echo ""
  # Runs LAST, after the summary, so the internal setup's own output — including the
  # "you still need to log in" banner — is the final thing on screen instead of being
  # buried under a wall of install output the user has stopped reading.
  setup_csa_internal_tools
}

main "$@"
