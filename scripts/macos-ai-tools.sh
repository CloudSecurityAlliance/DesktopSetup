#!/usr/bin/env bash

# Cloud Security Alliance — macOS AI Tools Setup
#
# Installs:
#   1. Xcode Command Line Tools
#   2. Homebrew (macOS package manager)
#   3. Node.js (via Homebrew, provides npm)
#   4. uv (kept current) and Python 3.14, the standard build, uv-managed
#      (Homebrew python@3.14 as fallback); other Pythons are left alone
#   5. Document toolchain: pandoc + typst (via Homebrew), plus pyyaml,
#      pymupdf 1.x and csa-google-workspace in ~/.default_venv, a link to
#      ~/.default_venv-3.14 built on that Python — required by the
#      document-pipeline plugin
#   6. Git (via Homebrew, latest version)
#   7. GitHub CLI (gh) + authentication
#   8. 1Password (via Homebrew cask, GUI app — needed for biometric CLI unlock)
#   9. 1Password CLI (via Homebrew)
#  10. Claude Desktop (via Homebrew cask; app self-updates, so direct-
#      download copies are detected and left alone)
#  11. ChatGPT Desktop (via Homebrew cask; same self-update story)
#  12. Gemini Desktop (via Homebrew cask `google-gemini`, NOT `gemini`; Apple
#      Silicon and macOS 15 only; Google's updater keeps it current)
#  13. Copilot Desktop (Microsoft's own .pkg, NOT the `microsoft-365-copilot`
#      cask; Edge's updater keeps it current) — see docs/desktop-ai-apps.md
#  14. Claude Code (native installer, auto-updates)
#  15. OpenAI Codex CLI (via npm)
#  16. Google Gemini CLI (via npm)
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

set -euo pipefail

SCRIPT_VERSION="2026-11-14T05:43Z"

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
#   scripts/windows-update.ps1     (full updater, Windows)
# All six files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the scripts will drift.
# One entry per internal MCP server. Top-level, beside CSA_MARKETPLACES, because the
# installation plan has to count it and a list local to the function that runs it cannot be
# counted from the plan. It was local, the plan named two of these four by hand, and two
# servers were installed that the person had not been shown. Appending here is now the whole
# change needed to add a server.
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
#   scripts/windows-update.ps1
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

# The to-do ledger lives for one run. Created before anything can discover a to-do, and
# EXPORTED so the nested setup scripts - separate processes here, `bash -c "$script"` - append
# to the same file. Removed by csa_show_todo_list after it renders.
if [[ -z "${CSA_TODO_FILE:-}" ]]; then
  CSA_TODO_FILE="${TMPDIR:-/tmp}/csa-todo-$$.tsv"
  export CSA_TODO_FILE
fi
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

# npm 11.19+ ends a global install with an `npm warn install-scripts` block: native dependencies
# (node-pty and @github/keytar, under the Gemini CLI) declare install scripts that a future npm
# will run only from an allowlist. Measured on npm 11.19.0 / node 26.8.1 (Homebrew's unversioned
# node, which is what a clean machine got before #74 pinned node@24) — the scripts still RUN: `node-pty/build/` holds the node-gyp
# Makefiles afterwards and both modules load. It is a pre-announcement, not a failure.
#
# It does not read like one (issue #51). This installer is run by people who do not use npm, on
# a machine they were handed an hour ago, and five lines of `npm warn` under "Updating Gemini
# CLI" is indistinguishable from something breaking. The funding footer goes for the same
# reason. Both are kept verbatim under CSA_DEBUG=1, where anyone debugging npm needs them.
#
# sed, not `grep -v`: `set -o pipefail` is on and a grep matching nothing exits 1, so on the day
# npm stops printing this block a clean run would start reporting failure — an `npm install -g
# X@latest` that worked reported as "Failed to update X", and macos-update.sh warning about an
# update that worked. sed exits 0 whatever it matches, so npm's own status propagates.
# tests/test_npm_output_filter.py holds that case, and the `grep -v` control proving it is real.
csa_npm() {
  if csa_debug_requested; then
    npm "$@"
  else
    # Deliberately NOT $CSA_SED_UNBUF. BSD sed spells line-buffering -l as a bare flag; GNU
    # sed spells -l N and takes an argument, so on GNU it swallows the first -e and treats
    # '/^npm warn install-scripts/d' as an input FILENAME: stdin is never read, npm's summary
    # vanishes, and the "no such file" error quotes the pattern back. csa_redact gets away
    # with the same variable only because -E follows it and absorbs the argument. Buffering
    # buys nothing here anyway - npm prints its summary once, at the end.
    npm "$@" 2>&1 | sed \
      -e '/^npm warn install-scripts/d' \
      -e '/looking for funding$/d' \
      -e '/run `npm fund` for details$/d'
  fi
}

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

# Echo the .app bundle's CFBundleIdentifier. Empty on failure. The name on disk is not the
# identity: `brew install --cask gemini` puts MacPaw's duplicate-file cleaner in /Applications,
# and Google's Gemini is also "Gemini.app" - only the identifier tells them apart.
get_app_bundle_id() {
  defaults read "$1/Contents/Info.plist" CFBundleIdentifier 2>/dev/null
}

# ── Desktop apps that are running ───────────────────────────────────
#
# A desktop app must not be replaced while it runs: its files are swapped underneath it, and a
# pkg or cask install over a live app leaves it half-old until it crashes or is relaunched.
#
# "Running" means the app's MAIN executable - the thing the person quits - runs as THIS user.
# Nothing else in the bundle counts, because nothing else is reliably gone once they have quit:
#   - the vendor's launchd jobs: Copilot's Library/LoginItems/CopilotAppHost, Gemini's
#     Helpers/GeminiAppLauncher, updaters in Library/LaunchServices (seen in `launchctl list`
#     beside the running apps, 2026-10-24); launchd may keep them alive or relaunch them;
#   - even under Frameworks: on 2026-10-25 three of Copilot's crash handlers there had launchd,
#     not Copilot, as their parent (ppid 1), so they may outlive it.
# A wait that counted any of those might never end. The window and renderer processes exit with
# the main one; the vendor's own installer stops and restarts the rest.
#
# Identified by PATH, not by name, for the reason Get-RunningAiClients gives on Windows: a name
# says what somebody called a file. `ps -o comm=` prints the full executable path for an app
# LaunchServices started - all four main executables did, 2026-10-25 - but a RELATIVE one for
# some launchd jobs (`Contents/Library/LoginItems/...`), which therefore never match here.
app_running() {
  local bundle="$1"
  ps -x -U "$(id -u)" -o comm= 2>/dev/null \
    | awk -v main="$bundle/Contents/MacOS/" 'index($0, main) == 1 { found = 1 } END { exit !found }'
}

# Wait for the person to quit an app fully before it is replaced. Returns 0 once it has exited
# (or was never running), 1 when it is still running and the caller must leave it alone.
#
# Never quits the app on the person's behalf: an app can hold unsaved work, and only they know.
# With nobody at the keyboard (NONINTERACTIVE) there is nobody to quit it, so it does not wait
# at all - waiting would hang a headless run forever. Interactively it polls, and every minute
# asks whether to keep waiting, so an app that will not exit cannot trap the run either.
wait_for_app_exit() {
  local name="$1" bundle="$2" waited=0
  app_running "$bundle" || return 0

  if [[ -n "${NONINTERACTIVE-}" ]]; then
    warn "$name is running, and nobody is here to quit it - leaving it as it is."
    return 1
  fi

  warn "$name is running. Quit it fully so it can be replaced:"
  echo "  choose Quit from its menu, or press ⌘Q while it is in front - closing its window"
  echo "  is not enough, it keeps running in the menu bar."
  echo "  Waiting for it to exit..."
  while app_running "$bundle"; do
    if [[ $waited -ge 60 ]]; then
      if ! confirm "$name is still running. Keep waiting?"; then
        # Asked again, not assumed: they may have quit it while the question was on screen.
        if app_running "$bundle"; then
          return 1
        fi
        break
      fi
      waited=0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  success "$name has exited"
  return 0
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

# An unaccepted Xcode license makes EVERY Homebrew command fail with the same error, and
# `xcode-select -p` cannot see it: "the tools are installed" and "the license is accepted" are
# independent states, and a machine fresh from `xcode-select --install` has the first without
# the second.
#
# Without this gate one root cause became five symptoms (#87): `brew update`, pandoc, typst and
# the document preflight deps each warned and continued, and only the fifth - Git - aborted. So
# the one actionable line, which Homebrew itself printed, scrolled past four CSA messages that
# each described a consequence ("document rendering stays broken") instead of the cause.
#
# Keyed on the literal refusal text, not on a predictive probe of the license state: a state
# probe has to special-case CLT-only machines against ones with full Xcode (`xcodebuild -version`
# answers differently on each) and goes stale as Xcode changes, whereas a string this specific
# cannot stop a run that would otherwise have worked.
#
# `/usr/bin/git` is the probe because it is a Command Line Tools shim present on every Mac, so it
# refuses in exactly the way every `brew` subprocess is about to - no extra dependency, and no
# assumption that Homebrew is installed yet.
csa_xcode_license_checked=0
csa_require_xcode_license() {
  if [[ "$csa_xcode_license_checked" == 1 ]]; then return 0; fi
  csa_xcode_license_checked=1
  local probe
  probe="$(/usr/bin/git --version 2>&1 || true)"
  case "$probe" in
    *"agreed to the Xcode"*|*"Xcode/iOS license"*) ;;
    *) return 0 ;;
  esac
  error "The Xcode license has not been accepted, so Homebrew cannot install anything."
  printf '  Run this, then re-run this script:\n    sudo xcodebuild -license accept\n' >&2
  exit 1
}

ensure_brew_in_path() {
  csa_require_xcode_license
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
copilot_needs_migration=""  # "brew" if the microsoft-365-copilot cask is installed
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

  # Copilot: should be Microsoft's unified app, not the cask. `microsoft-365-copilot` installs
  # what Microsoft now calls "the former Microsoft 365 Copilot app" (the AutoUpdate build, 1.x)
  # with AutoUpdate deselected, and the cask had not moved since 2026-09-30 when this was
  # written. A Copilot from anywhere else is left alone: its own updater owns it.
  if has_command brew && brew list --cask microsoft-365-copilot >/dev/null 2>&1; then
    copilot_needs_migration="brew"
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

  # Node.js. The unversioned formula is REPLACED by node@24, and a plan that does not say so
  # is a plan that hides the only destructive step in this script - `has_command brew` guard
  # because preflight runs before install_homebrew on a fresh machine (TODO H2's class).
  if has_command brew && brew list --formula node >/dev/null 2>&1; then
    echo "  Node.js ........... $(get_version node --version) — replace with the LTS line: install node@24, remove the unversioned formula"
  elif has_command node; then
    echo "  Node.js ........... installed ($(get_version node --version))"
  else
    echo "  Node.js ........... install node@24 (LTS) via Homebrew"
  fi

  # uv. install_uv keeps an installed uv current, by whichever route owns it.
  if has_command uv; then
    if has_command brew && brew list --formula uv >/dev/null 2>&1; then
      echo "  uv ................ installed ($(get_version uv --version)) — keep current via Homebrew"
    else
      echo "  uv ................ installed ($(get_version uv --version)) — keep current via uv self update"
    fi
  else
    echo "  uv ................ install via Homebrew"
  fi

  # Python
  # Reporting "installed" for any python3 is what made #53 invisible: on a stock Mac this
  # printed a green line for Apple's 3.9.6 and the run carried on. And reporting any 3.14 is
  # what hid #179: uv's 3.14t answered to "3.14". find_csa_python, which never installs, names
  # the one interpreter that counts; install_python runs `uv python install` whatever it finds.
  local py_found
  if py_found="$(find_csa_python)"; then
    echo "  Python ............ installed ($(get_version "$py_found" --version), standard build, $py_found) — ensure uv's ${CSA_PYTHON_PREFERRED}"
  else
    echo "  Python ............ install ${CSA_PYTHON_PREFERRED}, standard build, via uv (Homebrew python@${CSA_PYTHON_PREFERRED} as fallback); other Pythons left as they are"
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
  # ~/.default_venv: this machine's repair and its reason, from the same classifier the step acts
  # on (default_venv_state). It used to probe PATH's python3, which is not where the deps go.
  echo "  Preflight deps .... $(default_venv_plan)"

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

  # Gemini Desktop and Copilot Desktop. Each row is printed from the same *_state function the
  # install step acts on, so the plan and the run cannot describe two different decisions.
  local gemini_app_ver gemini_app_dt
  case "$(gemini_desktop_state)" in
    cask|direct)
      gemini_app_ver="$(get_app_version "$GEMINI_DESKTOP_APP")" || gemini_app_ver=""
      gemini_app_dt="$(get_app_mtime "$GEMINI_DESKTOP_APP")" || gemini_app_dt=""
      echo "  Gemini Desktop .... installed${gemini_app_ver:+ (v$gemini_app_ver${gemini_app_dt:+ · $gemini_app_dt})}"
      ;;
    other)
      echo "  Gemini Desktop .... skip — $GEMINI_DESKTOP_APP is a different app, not Google's"
      ;;
    unsupported)
      echo "  Gemini Desktop .... skip — needs Apple Silicon and macOS 15 or later"
      ;;
    *)
      echo "  Gemini Desktop .... install via Homebrew cask (google-gemini)"
      ;;
  esac

  local copilot_app copilot_app_ver copilot_app_dt
  case "$(copilot_desktop_state)" in
    migrate)
      echo "  Copilot Desktop ... replace the Homebrew cask (Microsoft's former app) with Microsoft's own — quit Copilot first"
      ;;
    installed)
      copilot_app="$(copilot_app_path)"
      copilot_app_ver="$(get_app_version "$copilot_app")" || copilot_app_ver=""
      copilot_app_dt="$(get_app_mtime "$copilot_app")" || copilot_app_dt=""
      echo "  Copilot Desktop ... installed${copilot_app_ver:+ (v$copilot_app_ver${copilot_app_dt:+ · $copilot_app_dt})}"
      ;;
    unsupported)
      echo "  Copilot Desktop ... skip — needs macOS 14 or later"
      ;;
    *)
      echo "  Copilot Desktop ... install Microsoft's .pkg (a download of several hundred MB; asks for your password)"
      ;;
  esac

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
    echo "  Codex CLI ......... installed ($(get_version codex --version)); update to latest via npm"
  else
    echo "  Codex CLI ......... install via npm"
  fi

  # Gemini
  if [[ -n "$gemini_needs_migration" ]]; then
    echo "  Gemini CLI ........ migrate from Homebrew → npm (settings preserved)"
  elif has_command gemini; then
    echo "  Gemini CLI ........ installed ($(get_version gemini --version)); update to latest via npm"
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
  echo "                       sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
  # Announced, because it was not: setup_csa_internal_tools installs and upgrades these, and a
  # plan that does not mention one means somebody reading the plan cannot tell whether that
  # server was touched. Same gh-probe gate as the line above, so it says "if ... access" for
  # the same reason.
  #
  # DERIVED from CSA_INTERNAL_SETUPS, not typed out, for the reason the marketplace line above
  # is derived: the hand-written version named Google Workspace and Skilljar, then Gmail/Calendar
  # and Zendesk were appended to the list and installed without ever appearing in the plan a
  # person agreed to. A consent surface that is a second copy of the list is a consent surface
  # that will eventually describe a different installation from the one that runs.
  echo "  Internal MCP servers install/upgrade ${#CSA_INTERNAL_SETUPS[@]} servers on Python ${CSA_PYTHON_PREFERRED} (standard build) if your GitHub account has CSA-Internal access"
  echo "                       (installs uv's Python ${CSA_PYTHON_PREFERRED} standard build if it is missing)"
  local setup_name
  for setup_name in "${CSA_INTERNAL_SETUPS[@]}"; do
    echo "                       ${setup_name%-setup.sh}"
  done
  # Each CSA tool already installed on an interpreter that must be replaced, and why (#179 item
  # 6) - the setup scripts above rebuild it on the CSA Python. Read-only, like the rest of the plan.
  local tool_repairs tool_fix
  tool_repairs="$(csa_tool_repairs)" || tool_repairs=""
  while IFS= read -r tool_fix; do
    if [[ -n "$tool_fix" ]]; then
      echo "                       rebuild ${tool_fix%%: *} on Python ${CSA_PYTHON_PREFERRED} (standard build): ${tool_fix#*: }"
    fi
  done <<< "$tool_repairs"
  # Then every registration of those servers, and the dead ones it will re-point (#179, Plan 2).
  # Called directly: it sets CSA_REG_DIR, where the plan file waits for repair_csa_registrations.
  csa_registrations_preview
  echo "                       each prints what it may do before it is used"

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

# Same class of bug as install_python, narrower blast radius: a stock Mac has no node at
# all, so the `else` branch below installs one and it is fine. This only bites a machine that
# already had an old node - an abandoned nvm install, say - which `has_command node` would
# otherwise accept.
#
# The floor comes from the consumer that asks for most, not from a number we picked - the same
# rule as CSA_PYTHON_MIN. Measured 2026-09-06: wrangler >= 22.0.0, gemini-cli >= 20, typescript
# >= 16.20, codex >= 16. Wrangler binds, because Node here is not just an AI-CLI dependency:
# it is the runtime for building Cloudflare Workers and TypeScript.
CSA_NODE_MIN=22

node_meets_floor() {
  local min="$CSA_NODE_MIN" major
  # `|| major=""` is not decoration: under pipefail a missing or broken `node` makes this
  # pipeline non-zero, the assignment inherits it, and set -e kills the caller. That is the
  # #51 class, and tools/check-pipeline-assignments.py now fails on it.
  major="$(node --version 2>/dev/null | sed 's/^v//; s/\..*//')" || major=""
  if [[ ! "$major" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  (( major >= min ))
}

install_node() {
  ensure_brew_in_path

  # Pin the LTS line so both platforms run the same Node major; Windows installs
  # OpenJS.NodeJS.LTS (#56). node@24 is a versioned, keg-only formula, so rather than reason
  # about what that means, three things were measured on a macos-latest runner (2026-09-16):
  #   - `brew install node@24` exits 1 even when it succeeds, so its status cannot be trusted;
  #   - keg-only is literal: immediately after a successful install there is NO `node` on PATH
  #     at all, so the force-link below is required rather than defensive;
  #   - npm's global prefix is the Homebrew prefix in every one of those states, so wrangler,
  #     codex and gemini installed with `npm -g` keep working across the switch. Verified by
  #     installing wrangler first and checking it still ran afterwards.
  # The unversioned formula is removed rather than merely left unlinked: `brew upgrade` in
  # macos-update.sh upgrades and relinks whatever is installed, so leaving it would flip the
  # machine back to Current on the next update run, silently.
  if brew list --formula node >/dev/null 2>&1; then
    info "Replacing the unversioned Homebrew Node.js with the LTS line (node@24)"
    brew uninstall --ignore-dependencies node >/dev/null 2>&1 \
      || warn "Could not remove the unversioned node formula; continuing"
  fi

  if brew list --formula node@24 >/dev/null 2>&1; then
    if brew outdated node@24 2>/dev/null | grep -q node@24; then
      info "Upgrading Node.js"
      # Same reasoning as the install below: do not trust this exit status for a keg-only
      # formula, and an out-of-date Node is not a reason to stop the whole installer anyway.
      brew upgrade node@24 || warn "Could not upgrade Node.js; continuing with the installed version"
    else
      info "Node.js already current: $(get_version node --version)"
    fi
  elif has_command node && node_meets_floor; then
    info "Node.js already installed (non-Homebrew): $(get_version node --version)"
    return 0
  else
    if has_command node; then
      info "Node.js is $(get_version node --version), below the v${CSA_NODE_MIN} Wrangler needs - installing Homebrew Node.js"
    fi
    info "Installing Node.js LTS (node@24)"
    # Measured on macos-latest 2026-09-16: `brew install node@24` exits **1** even when it
    # succeeds - it installs the formula, prints its Summary, then the keg-only caveat, and
    # returns non-zero. `|| abort` on that exit status aborts a working install, which is
    # exactly what the first version of this did. Check the outcome, not the status.
    brew install node@24 || true
    brew list --formula node@24 >/dev/null 2>&1 || abort "Failed to install Node.js"
  fi

  # REQUIRED, not belt-and-braces: node@24 is keg-only, so Homebrew deliberately does not
  # symlink it into the prefix. Measured - immediately after a successful install there is no
  # `node` on PATH at all until this runs.
  brew link --overwrite --force node@24 >/dev/null 2>&1 \
    || warn "Could not link node@24 - run: brew link --overwrite --force node@24"
  return 0
}

# The floor is not ours to choose. CSA-Document-Pipeline's pyproject.toml declares
# requires-python = ">=3.10", and csa-google-workspace - which document-pipeline's register
# tools import - refuses to install below it.
# Raised 3.10 -> 3.14 because the CONSUMERS raised theirs, which is the only reason this
# number ever moves (DEC-012: "version floors are read from what the consumer declares
# (requires-python), never invented by the installer"). All four CSA MCP servers now declare
# `requires-python = ">=3.14"`, and install_doc_python_deps puts csa_google_workspace into
# ~/.default_venv - so a venv built on 3.10 would be one this script cannot populate.
#
# CSA-Document-Pipeline still declares >=3.10 and is satisfied by 3.14, so the maximum across
# consumers is 3.14. Nothing on macOS measures against it any more: ~/.default_venv must now BE
# CSA_PYTHON_PREFERRED (venv_rebuild_reason), not merely clear a floor. It stays declared, pinned
# equal to Windows' $CsaPythonMin (tests/test_python_pins.py), which Windows still resolves by
# until #184, and tools/sweep-csa-sources.sh compares it with upstream's requires-python. Those
# read it from this file, so this script itself does not (SC2034).
# shellcheck disable=SC2034
CSA_PYTHON_MIN="3.14"
# The CSA Python: the one minor version find_csa_python accepts and install_python always
# ensures, standard (GIL) build only. A floor says what breaks; this says what runs, and pinning
# it is what stops macOS and Windows drifting apart the way brew's python (3.14) and winget's
# Python.Python.3.13 already had.
CSA_PYTHON_PREFERRED="3.14"

# ── The CSA Python ───────────────────────────────────────────────────
# ONE interpreter, named by one resolver, verified by running it (#179). The resolver it
# replaces returned the first PATH or uv interpreter that cleared a floor, and on a real Mac
# that was Homebrew's 3.15 (PATH python3) or uv's free-threaded python3.14t: when 3.14t is the
# only uv-managed 3.14, `uv python find 3.14` returns it (measured, uv 0.13.7). All four CSA
# servers landed on 3.14t that way. So nothing here trusts a name, a version string or
# `uv tool list --show-python` (which prints the same thing for both builds): every candidate
# is run and asked.
#
# KEEP SELF-CONTAINED: these three functions depend only on has_command, info, warn and
# CSA_PYTHON_PREFERRED, so they can be shared byte-identically with another script.

# $1 interpreter. Exit 0 iff it runs, is CSA_PYTHON_PREFERRED, and is the standard build
# (sysconfig Py_GIL_DISABLED falsy - it is 1 on 3.14t). Silent. -I so neither the caller's
# working directory nor PYTHONPATH can shadow sysconfig.
python_is_csa_build() {
  local got
  [[ -n "${1:-}" ]] || return 1
  got="$("$1" -I -c 'import sys, sysconfig; print("%d.%d" % sys.version_info[:2], 1 if sysconfig.get_config_var("Py_GIL_DISABLED") else 0)' 2>/dev/null)" || return 1
  if [[ "$got" == "${CSA_PYTHON_PREFERRED} 0" ]]; then
    return 0
  fi
  return 1
}

# Prints the CSA Python's path, or exits 1. NEVER installs anything: the preflight calls this
# before the person has agreed to anything.
#
#   1. `uv python find --system --managed-python`. --system is REQUIRED: measured on uv 0.13.7,
#      with VIRTUAL_ENV set it otherwise returns the active venv's python, which would make a
#      venv the base of everything built on this.
#   2. every `variant == "default"` CPython in uv's JSON listing. Parsed by Python, not awk,
#      because a path may contain a space. uv 0.13.7 may report its ~/.local/bin shim as `path`
#      with the managed interpreter as `symlink`; the managed one is tried first, and either
#      is accepted only if it verifies, so nothing depends on whether a shim exists.
#   3. Homebrew's opt/python@X.Y, which is stable across `brew upgrade` (its Cellar target is not).
#
# Both uv calls run in a subshell with UV_PYTHON_PREFERENCE unset. Measured on uv 0.13.7: with it
# exported, at any value, `--managed-python` is refused ("cannot be used with
# `--python-preference`", exit 2) by both `find` and `list`, so this found nothing even with the
# standard 3.14 installed, and ensure_csa_python went on to Homebrew. A subshell, not `env -u`:
# the variable is dropped for those two calls only, and the tests' PATH has no /usr/bin/env.
# An empty listing (`[]`) spawns no parser: /usr/bin/python3 on a Mac without the Command Line
# Tools opens an install dialog, and the preflight runs this before anyone has agreed to anything.
#
# A path is returned as uv printed it - the minor-version directory cpython-3.14-<platform>,
# a link uv points at the current patch release - never resolved to the patch directory
# (cpython-3.14.10-<platform>), which a patch upgrade replaces.
find_csa_python() {
  local first="" listed="" cands="" parser cand prefix
  local parse='import json, sys
for e in json.loads(sys.argv[1]):
    if e.get("variant") == "default" and e.get("implementation") == "cpython":
        for p in (e.get("symlink"), e.get("path")):
            if p:
                print(p)'
  if has_command uv; then
    first="$( (unset UV_PYTHON_PREFERENCE; uv python find --system --managed-python "$CSA_PYTHON_PREFERRED") 2>/dev/null)" || first=""
    if [[ -n "$first" ]] && python_is_csa_build "$first"; then
      printf '%s\n' "$first"
      return 0
    fi
    listed="$( (unset UV_PYTHON_PREFERENCE; uv python list --only-installed --managed-python "$CSA_PYTHON_PREFERRED" --output-format json) 2>/dev/null)" || listed=""
    if [[ -n "$listed" && "$listed" != "[]" ]]; then
      # Any Python that runs can parse JSON, including a 3.14t that failed the check above.
      for parser in "$first" /usr/bin/python3; do
        [[ -n "$parser" ]] || continue
        if cands="$("$parser" -I -c "$parse" "$listed" 2>/dev/null)"; then
          break
        fi
        cands=""
      done
      while IFS= read -r cand; do
        if [[ -n "$cand" ]] && python_is_csa_build "$cand"; then
          printf '%s\n' "$cand"
          return 0
        fi
      done <<< "$cands"
    fi
  fi
  if has_command brew; then
    prefix="$(brew --prefix 2>/dev/null)" || prefix=""
    cand="${prefix}/opt/python@${CSA_PYTHON_PREFERRED}/bin/python${CSA_PYTHON_PREFERRED}"
    if [[ -n "$prefix" ]] && python_is_csa_build "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  fi
  return 1
}

# Provisions the CSA Python and prints its path - ONLY the path goes to stdout, so a caller can
# write py="$(ensure_csa_python)"; every other line goes to stderr. Exits 1, with a warning,
# when neither uv nor Homebrew could provide one.
#
# `uv python install` runs even when a 3.14 is already there, because "a 3.14" may be only the
# free-threaded one and installing the standard build beside it is the fix: once both exist,
# uv's own resolution prefers the standard build (measured, uv 0.13.7). A no-op when present.
# Never `3.14+gil`: uv 0.13.7 never downloads for a +gil request, so it fails on a clean machine.
ensure_csa_python() {
  local found
  if has_command uv; then
    info "Ensuring Python ${CSA_PYTHON_PREFERRED} (uv-managed, standard build)" >&2
    uv python install "$CSA_PYTHON_PREFERRED" >&2 \
      || warn "uv could not install Python ${CSA_PYTHON_PREFERRED}"
  fi
  if found="$(find_csa_python)"; then
    printf '%s\n' "$found"
    return 0
  fi
  if has_command brew; then
    info "Installing python@${CSA_PYTHON_PREFERRED} via Homebrew, the fallback" >&2
    brew install "python@${CSA_PYTHON_PREFERRED}" >&2 \
      || warn "Homebrew could not install python@${CSA_PYTHON_PREFERRED}"
    if found="$(find_csa_python)"; then
      printf '%s\n' "$found"
      return 0
    fi
  fi
  warn "No Python ${CSA_PYTHON_PREFERRED} standard build: neither uv nor Homebrew could provide one"
  return 1
}

# uv is the CSA Python toolchain standard (CINO-Engineering DEC-012). Installed here
# for two jobs: provisioning interpreters (below), and later `uv tool install` for CSA's own
# Python CLIs once they are packaged. Chosen over pipx because it also provisions the
# interpreter - pipx needs a working Python first, which is the bootstrap problem one layer up.
#
# Kept current, because the measured uv behaviour the resolver above relies on is version-bound.
# A Homebrew-owned uv is upgraded through Homebrew, because `uv self update` fails on a Homebrew
# install; any other uv updates itself. A failed update only warns - an older uv still works.
install_uv() {
  ensure_brew_in_path

  if has_command uv; then
    if has_command brew && brew list --formula uv >/dev/null 2>&1; then
      csa_brew_upgrade formula uv "uv"
    else
      local before after out
      before="$(get_version uv --version)" || before=""
      if out="$(uv self update 2>&1)"; then
        after="$(get_version uv --version)" || after=""
        if [[ "$before" != "$after" ]]; then
          success "uv upgraded: ${before#uv } -> ${after#uv }"
        fi
      else
        warn "Could not update uv (${before:-version unknown}); continuing with it. uv said:"
        printf '%s\n' "$out" >&2
      fi
    fi
    info "uv already installed: $(get_version uv --version)"
    return 0
  fi

  info "Installing uv"
  brew install uv || warn "Failed to install uv - falling back to Homebrew's python@${CSA_PYTHON_PREFERRED}"
}

# ALWAYS ensures the uv-managed CSA Python, even when another Python is present - decision D3
# of #179: uv is the one provider (DEC-012). It adds an interpreter and changes nothing else:
# PATH's python3, Homebrew's Pythons and every other uv interpreter are left as they were.
# Not an abort when it fails: the AI tools below do not need Python, and #51 is what an
# optional step taking the whole installer down looks like.
install_python() {
  ensure_brew_in_path

  local found
  if found="$(ensure_csa_python)"; then
    info "Python ready: $(get_version "$found" --version) ($found)"
  fi
  return 0
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
# csa-google-workspace is what document-pipeline's csa-register-{format,merge,verify}
# probe for; it pulls google-api-python-client transitively, so one entry covers both.
# Without it those three launchers fail their own dep probe and exit 2 naming a package
# nothing installed. It requires >= 3.10, which is why CSA_PYTHON_MIN exists.
# These must install: a venv without them is not a replacement for one that has them.
#
# Nothing here may bring in onnxruntime (#179's final review, 2026-11-10): its official macOS and
# Linux builds from 1.29 on ship Microsoft 1DS telemetry that is ON by default - a device id and
# an event cache under ~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime, sent
# to mobile.events.data.microsoft.com, off only with ORT_DISABLE_TELEMETRY=1 set before it loads.
#   * pymupdf is pinned below 2: pymupdf 2.x requires onnxruntime, pymupdf-layout and
#     pymupdf4llm unconditionally, and publishes no macOS x86_64 wheel; 1.28.2 has no
#     dependencies at all and has Intel wheels. Quoted, because `<2` is a redirection.
#   * markitdown (#157) is NOT installed, for the same reason: markitdown -> magika ->
#     onnxruntime.
# tools/check-doc-deps-resolve.py resolves this list with real uv and fails on onnxruntime.
CSA_DOC_PY_DEPS=(pyyaml "pymupdf>=1.24.3,<2" csa-google-workspace)

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

# Install packages into a venv that may not contain pip.
#
# `"$venv/bin/python3" -m pip` assumed pip was there and failed with "No module named pip" on a
# real machine (#86), leaving csa-preflight broken while the warning named the packages rather
# than the cause. A venv created by `uv venv` has NO pip - uv omits it by design - and this
# script installs uv itself a few steps earlier, so a uv-made venv is an ordinary state here,
# not an exotic one. The `[[ ! -x ... ]]` guard above exists precisely to accept a venv this
# script did not create, which is the case that has no pip.
#
# `uv pip install --python <interpreter>` targets an existing venv without needing pip inside it,
# and is substantially faster. `--upgrade`, as the pip fallback has always passed: without it uv
# leaves an installed package that satisfies the request exactly as it is (measured, uv 0.13.7:
# "Would make no changes" for an outdated idna), so nothing would keep the document deps current -
# update_pip leaves them to update_default_venv. The deps' own pins still hold: `--upgrade` with
# "pymupdf>=1.24.3,<2" moved 1.27.1 to 1.28.2, never to 2.x.
# `ensurepip` is the fallback for a machine where the uv install
# failed; a venv built by `python3 -m venv` already has pip and takes neither path.
#
# $1 venv python   $2... packages
csa_venv_pip_install() {
  local vpy="$1"; shift
  if has_command uv; then
    if uv pip install --quiet --upgrade --python "$vpy" "$@"; then return 0; fi
    warn "uv could not install into $vpy - falling back to pip"
  fi
  if ! "$vpy" -m pip --version >/dev/null 2>&1; then
    if ! "$vpy" -m ensurepip --upgrade >/dev/null 2>&1; then
      warn "$vpy has no pip and ensurepip failed - cannot install $*"
      return 1
    fi
  fi
  "$vpy" -m pip install --quiet --upgrade "$@"
}

# ── ~/.default_venv: a link to a versioned venv ─────────────────────
# document-pipeline's bash launchers probe $HOME/.default_venv/bin/python3. It is a RELATIVE link
# to a versioned directory, ${CSA_VENV}-${CSA_PYTHON_PREFERRED} (the CINO's decision, 2026-11-10,
# #179): a repair builds the new directory and flips the link, so every old directory is kept
# for rollback and the one an active shell is using never moves (D1). Before that it was a real
# directory built on whatever python3 PATH offered - Homebrew's 3.15, a 3.13, uv's free-threaded
# 3.14t, or a Homebrew Cellar path the next `brew upgrade` deletes.
#
# KEEP IN SYNC: CSA_VENV, CSA_DOC_PY_DEPS, the three CSA-Python functions above and every
# function from venv_cfg_get to default_venv_leftovers are duplicated byte-identically in
# macos-update.sh (tools/check-duplication.py; tests/test_python_pins.py for the array).
# tests/test_venv_replacement.py runs them.

# $1 pyvenv.cfg, $2 key. Prints the value - everything after the first "=", trimmed, inner
# spaces kept, because a home path may contain one - or exits 1. `uv venv` writes version_info,
# `python -m venv` writes version.
venv_cfg_get() {
  local line key val
  if [[ ! -f "$1" ]]; then
    return 1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" != *=* ]]; then
      continue
    fi
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#"${key%%[![:space:]]*}"}"
    if [[ "$key" == "$2" ]]; then
      val="${line#*=}"
      val="${val#"${val%%[![:space:]]*}"}"
      val="${val%"${val##*[![:space:]]}"}"
      printf '%s\n' "$val"
      return 0
    fi
  done < "$1"
  return 1
}

# $1 a venv directory. Prints the ONE reason it must be rebuilt and exits 0; exits 1, silently,
# when it is absent or sound. Sound: bin/python3 runs, is CSA_PYTHON_PREFERRED, is the standard
# build, and was not recorded on a Homebrew Cellar path.
#
# A dangling bin/python3 - its interpreter deleted, so -L is true and -x false - is BROKEN, never
# absent. The Cellar test reads the RECORDED path, never realpath: the first symlink hop out of
# the venv, or pyvenv.cfg's home. Homebrew's opt/python@X.Y is stable across `brew upgrade` though
# its realpath is in the Cellar; only a recorded path containing /Cellar/ is deleted by the next
# upgrade.
venv_rebuild_reason() {
  local dir="${1%/}" got cur hop rec="" home="" n=0
  if [[ ! -e "$dir" && ! -L "$dir" ]]; then
    return 1
  fi
  if [[ ! -x "$dir/bin/python3" ]]; then
    echo "its Python no longer exists"
    return 0
  fi
  got="$("$dir/bin/python3" -I -c 'import sys, sysconfig; print("%d.%d" % sys.version_info[:2], 1 if sysconfig.get_config_var("Py_GIL_DISABLED") else 0)' 2>/dev/null)" || got=""
  case "$got" in
    [0-9]*.[0-9]*" "[01]) ;;
    *)
      echo "its Python does not run"
      return 0
      ;;
  esac
  if [[ "${got% *}" != "$CSA_PYTHON_PREFERRED" ]]; then
    echo "it is Python ${got% *}, not ${CSA_PYTHON_PREFERRED}"
    return 0
  fi
  if [[ "${got#* }" != "0" ]]; then
    echo "it is the free-threaded build"
    return 0
  fi
  cur="$dir/bin/python3"
  while [[ -L "$cur" && $n -lt 16 ]]; do
    hop="$(readlink "$cur")" || break
    case "$hop" in
      /*) ;;
      *) hop="${cur%/*}/$hop" ;;
    esac
    case "$hop" in
      "$dir"/*) cur="$hop" ;;
      *)
        rec="$hop"
        break
        ;;
    esac
    n=$((n + 1))
  done
  home="$(venv_cfg_get "$dir/pyvenv.cfg" home)" || home=""
  if [[ "$rec" == */Cellar/* || "$home" == */Cellar/* ]]; then
    echo "it is built on a Homebrew Cellar path, which the next brew upgrade deletes"
    return 0
  fi
  return 1
}

# $1 a venv directory, $2 a suffix for a name collision. Prints where the directory goes when it
# is moved aside: ${CSA_VENV}-<X.Y> from pyvenv.cfg (version_info, or version), or
# ${CSA_VENV}-unknown, plus -<$2> when that name is taken. ${CSA_VENV}-${CSA_PYTHON_PREFERRED} is
# always taken: it is the venv being built.
venv_aside_name() {
  local v="" major minor name
  v="$(venv_cfg_get "$1/pyvenv.cfg" version_info)" || v="$(venv_cfg_get "$1/pyvenv.cfg" version)" || v=""
  name="${CSA_VENV}-unknown"
  if [[ "$v" == [0-9]*.[0-9]* ]]; then
    major="${v%%.*}"
    minor="${v#*.}"
    minor="${minor%%.*}"
    if [[ -n "$minor" && "$major$minor" != *[!0-9]* ]]; then
      name="${CSA_VENV}-${major}.${minor}"
    fi
  fi
  if [[ -e "$name" || -L "$name" || "$name" == "${CSA_VENV}-${CSA_PYTHON_PREFERRED}" ]]; then
    name="${name}-$2"
  fi
  printf '%s\n' "$name"
}

# $1 a Python to run, $2 the old venv, $3 the new one. Prints, on one line, the top-level
# packages the old venv had that the new one lacks - what a rebuild did not bring back. Read
# from the old venv's metadata, so it works when the old venv's own interpreter is gone.
# Top-level means nothing in the OLD venv required it - not just nothing that is gone: pymupdf
# 2.x required pymupdf-layout and pymupdf4llm, and the new venv has pymupdf 1.x, so judging by
# the gone packages alone reported them as the person's own and told them to reinstall them -
# which brings onnxruntime back.
venv_extra_packages() {
  local code='import glob, os, re, sys
from importlib import metadata
def norm(s):
    return re.sub(r"[-_.]+", "-", s).lower()
def dists(venv):
    found = dict()
    for d in metadata.distributions(path=glob.glob(os.path.join(venv, "lib", "python*", "site-packages"))):
        try:
            name = d.metadata["Name"]
        except Exception:
            name = None
        if name:
            found.setdefault(norm(name), (name, d))
    return found
old, new = dists(sys.argv[1]), dists(sys.argv[2])
gone = dict((k, v) for k, v in old.items() if k not in new and k not in ("pip", "setuptools", "wheel"))
needed = set()
for name, d in old.values():
    for r in d.requires or []:
        m = re.match(r"[A-Za-z0-9._-]+", r)
        if m:
            needed.add(norm(m.group(0)))
print(" ".join(sorted(v[0] for k, v in gone.items() if k not in needed)))'
  "$1" -I -c "$code" "$2" "$3" 2>/dev/null
}

# Classifies $CSA_VENV and changes nothing. Prints "<state>TAB<path>TAB<reason>", "-" for none:
#   ok          a link to a sound ${CSA_VENV}-${CSA_PYTHON_PREFERRED}
#   rebuild     a link to ${CSA_VENV}-${CSA_PYTHON_PREFERRED}, which is not sound
#   flip        a link to anything else that will not do: an older or newer ${CSA_VENV}-<X.Y>, a
#               target that no longer exists, or a broken venv of the person's own (<path>)
#   foreign-ok  a link this installer did not make, to a sound venv: left alone
#   migrate     a real directory, from before the versioned layout
#   create      nothing there
#   other       neither a directory nor a link
# One classifier, so the plan row (default_venv_plan) and the repair (ensure_default_venv) cannot
# describe two different decisions.
default_venv_state() {
  local versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}" raw target name reason
  local xy='^[0-9]+[.][0-9]+$'
  if [[ -L "$CSA_VENV" ]]; then
    raw="$(readlink "$CSA_VENV")" || raw=""
    case "$raw" in
      /*) target="$raw" ;;
      *) target="${CSA_VENV%/*}/$raw" ;;
    esac
    if [[ -e "$versioned" && "$CSA_VENV" -ef "$versioned" ]]; then
      if reason="$(venv_rebuild_reason "$versioned")"; then
        printf 'rebuild\t%s\t%s\n' "$versioned" "$reason"
      else
        printf 'ok\t%s\t-\n' "$versioned"
      fi
      return 0
    fi
    if [[ ! -e "$target" ]]; then
      printf 'flip\t%s\t%s\n' "$target" "it no longer exists"
      return 0
    fi
    name="${target##*/}"
    if reason="$(venv_rebuild_reason "$target")"; then
      printf 'flip\t%s\t%s\n' "$target" "$reason"
    elif [[ "$name" == "${CSA_VENV##*/}-"* && "${name#"${CSA_VENV##*/}"-}" =~ $xy && "${target%/*}" -ef "${CSA_VENV%/*}" ]]; then
      printf 'flip\t%s\t%s\n' "$target" "it is not ${versioned##*/}"
    else
      printf 'foreign-ok\t%s\t-\n' "$target"
    fi
    return 0
  fi
  if [[ -d "$CSA_VENV" ]]; then
    reason="$(venv_rebuild_reason "$CSA_VENV")" || reason="-"
    printf 'migrate\t%s\t%s\n' "$CSA_VENV" "$reason"
    return 0
  fi
  if [[ -e "$CSA_VENV" ]]; then
    printf 'other\t%s\t-\n' "$CSA_VENV"
    return 0
  fi
  printf 'create\t%s\t-\n' "$versioned"
}

# The plan row: what ensure_default_venv will do on this machine, and why. Changes nothing.
# $1 --no-create gives the wording for -update, which never creates a venv and installs no Python.
#
# It asks find_csa_python, as the run does first, because the Python decides the outcome: -update
# with none found changes nothing, and a Cellar-pinned venv is not rebuilt onto a Python that is on
# a Cellar path too. A plan that said "rebuild" there named a step that never runs. find_csa_python
# never installs, so the plan can ask it before anyone has agreed to anything.
# Only macos-update.sh passes --no-create; macos-ai-tools.sh calls it with no argument, which
# older ShellCheck (0.9, not the pinned 0.11) reports as SC2120. The optional argument is the design.
# shellcheck disable=SC2120
default_venv_plan() {
  local versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}"
  local deps="${CSA_DOC_PY_DEPS[*]}"
  local state action old reason build="" vr aside fix kept="" py="" leave=""
  state="$(default_venv_state)" || state=""
  IFS=$'\t' read -r action old reason <<< "$state"
  if [[ "$reason" == "-" ]]; then
    reason=""
  fi
  if [[ ! -e "$versioned" && ! -L "$versioned" ]]; then
    build="build $versioned on Python ${CSA_PYTHON_PREFERRED}"
  elif vr="$(venv_rebuild_reason "$versioned")"; then
    build="rebuild $versioned ($vr), keeping the old one beside it"
  fi
  case "$action" in
    ok)
      printf '%s\n' "install/refresh $deps in $CSA_VENV (Python ${CSA_PYTHON_PREFERRED}, standard build)"
      return 0
      ;;
    foreign-ok)
      printf '%s\n' "install/refresh $deps in $CSA_VENV, your own link to $old (sound, left as it is)"
      return 0
      ;;
    other)
      printf '%s\n' "skip: $CSA_VENV is not a directory or a link to one, and is left as it is"
      return 0
      ;;
    create)
      if [[ "${1:-}" == "--no-create" ]]; then
        printf '%s\n' "none at $CSA_VENV - this script never creates one (macos-ai-tools.sh does)"
        return 0
      fi
      fix="${build:-use $versioned}, link $CSA_VENV to it"
      ;;
    migrate)
      aside="$(venv_aside_name "$CSA_VENV" "<timestamp>")" || aside="${CSA_VENV}-<X.Y>"
      fix="${build:+$build, }move the directory $CSA_VENV to $aside${reason:+ ($reason)}, link $CSA_VENV to ${versioned##*/}"
      ;;
    flip)
      if [[ -e "$old" ]]; then
        kept=", which is kept"
      fi
      fix="${build:+$build, }link $CSA_VENV to ${versioned##*/} instead of $old ($reason)$kept"
      ;;
    rebuild)
      fix="rebuild $versioned ($reason), keeping the old one beside it"
      ;;
    *)
      return 0
      ;;
  esac
  py="$(find_csa_python)" || py=""
  if [[ -z "$py" && "${1:-}" == "--no-create" ]]; then
    # This step installs no Python, but the same -update run may: a CSA-internal member's
    # Internal MCP servers step (the gate repo's setup scripts) installs uv's standard build, and
    # the next -update then repairs the venv (measured in the Task 6 acceptance run).
    leave="there is no Python ${CSA_PYTHON_PREFERRED} standard build installed, and this step installs none. For CSA-internal members the Internal MCP servers step installs one and the next update repairs this; otherwise run macos-ai-tools.sh"
  elif [[ -n "$py" && "$reason" == *Cellar* && "$py" == */Cellar/* ]]; then
    leave="the only Python ${CSA_PYTHON_PREFERRED} is on a Cellar path too"
  fi
  if [[ -n "$leave" ]]; then
    # The same test the callers apply before installing the deps: sound, or Cellar-pinned (which
    # still runs today).
    if [[ -z "$reason" || "$reason" == *Cellar* ]]; then
      printf '%s\n' "leave $CSA_VENV as it is${reason:+ ($reason)}; install/refresh $deps in it: $leave"
    else
      printf '%s\n' "leave $CSA_VENV as it is ($reason); nothing is installed into it: $leave"
    fi
    return 0
  fi
  if [[ -z "$py" ]]; then
    fix="on the Python ${CSA_PYTHON_PREFERRED} the Python row installs: $fix"
  fi
  printf '%s\n' "$fix; install/refresh $deps in it"
}

# Makes ${CSA_VENV}-${CSA_PYTHON_PREFERRED} a sound venv on $1 (the CSA Python), with
# CSA_DOC_PY_DEPS installed. Prints the path a broken one was moved to, if any - ONLY that goes to
# stdout. Exits 1, with a warning and nothing changed, when it cannot.
#
#   absent  `uv venv --seed` straight at the final path (`python -m venv` without uv).
#   broken  BUILD FIRST, SWAP LAST: `uv venv --seed --relocatable` at .new-$$, the deps with
#           `uv pip` only, then the broken one renamed to .broken-<ts> and the new one into place.
#           Measured: a venv built at one path and renamed breaks `activate` and every console
#           script, which hardcode the creation path. --relocatable survives the rename for the
#           seed scripts and for scripts `uv pip` installs, but NOT for one the venv's own pip
#           installs (exit 127) - so csa_venv_pip_install, whose fallback is that pip, is never
#           used here. Without uv there is no relocatable build: the broken one is renamed away
#           first and `python -m venv` builds at the final path, and a failure puts it back.
# A build whose deps failed is removed: a replacement that cannot do the job is not one, and the
# venv it would replace may still serve csa-preflight.
default_venv_build() {
  local py="$1" versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}" reason new broken
  if [[ ! -e "$versioned" && ! -L "$versioned" ]]; then
    info "Building $versioned on $py" >&2
    if has_command uv; then
      if uv venv --quiet --seed --python "$py" "$versioned" >&2 \
        && csa_venv_pip_install "$versioned/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
        return 0
      fi
    elif "$py" -m venv "$versioned" >&2 \
      && csa_venv_pip_install "$versioned/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
      return 0
    fi
    rm -rf "$versioned"
    warn "Could not build $versioned - nothing else was changed"
    return 1
  fi
  if ! reason="$(venv_rebuild_reason "$versioned")"; then
    return 0
  fi
  broken="${versioned}.broken-$(date +%Y%m%d%H%M%S)"
  info "Rebuilding $versioned on $py: $reason" >&2
  if has_command uv; then
    new="${versioned}.new-$$"
    rm -rf "$new"
    if ! uv venv --quiet --seed --relocatable --python "$py" "$new" >&2 \
      || ! uv pip install --quiet --python "$new/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
      rm -rf "$new"
      warn "Could not build a replacement for $versioned - leaving it exactly as it was"
      return 1
    fi
    if ! mv "$versioned" "$broken"; then
      rm -rf "$new"
      warn "Could not move $versioned aside - leaving it exactly as it was"
      return 1
    fi
    if ! mv "$new" "$versioned"; then
      mv "$broken" "$versioned" || true
      rm -rf "$new"
      warn "Could not move the replacement into place - $versioned is as it was"
      return 1
    fi
  else
    if ! mv "$versioned" "$broken"; then
      warn "Could not move $versioned aside - leaving it exactly as it was"
      return 1
    fi
    if ! "$py" -m venv "$versioned" >&2 \
      || ! csa_venv_pip_install "$versioned/bin/python3" "${CSA_DOC_PY_DEPS[@]}" >&2; then
      rm -rf "$versioned"
      mv "$broken" "$versioned" || true
      warn "Could not rebuild $versioned - the old one is back, exactly as it was"
      return 1
    fi
  fi
  warn "$versioned rebuilt on $py ($reason); the previous one is kept at $broken"
  printf '%s\n' "$broken"
}

# Leaves $CSA_VENV a RELATIVE link to a sound ${CSA_VENV}-${CSA_PYTHON_PREFERRED} on the CSA
# Python, repairing whatever default_venv_state found and keeping every old directory. Returns 0
# always: document deps are never worth the rest of the run.
#   --no-create  (-update) repair what exists, never create one, never install a Python:
#                find_csa_python only, so no Homebrew fallback either (D4).
# Otherwise find_csa_python first and ensure_csa_python only when it finds nothing, because
# install_python has just run ensure_csa_python and a second install would announce itself twice.
#
# The flip is `ln -sfn` then `mv -h`. -h is REQUIRED: measured on macOS, a plain `mv` onto a link
# to a directory exits 0, leaves the link unchanged and drops the new link INSIDE the old target.
# `ln -sfn` overwrites a leftover .link-new. A real directory is renamed aside first, so the gap is
# one rename. ~/.zshrc is never edited: its `[ ! -d "$HOME/.default_venv" ]` follows the link.
#
# Rebuilt even when it is the active venv (D1). $VIRTUAL_ENV is compared with -ef, never as a
# string: `activate` records the creation path (~/.default_venv-3.14), and shells opened before
# the migration hold ~/.default_venv. The active shell's directory never moves - or, for a real
# directory, its path now resolves through the link - so nothing it holds dangles; it gets a
# to-do to open a new terminal.
# Only macos-update.sh passes --no-create; macos-ai-tools.sh calls it with no argument, which
# older ShellCheck (0.9, not the pinned 0.11) reports as SC2120. The optional argument is the design.
# shellcheck disable=SC2120
ensure_default_venv() {
  local create=1 versioned="${CSA_VENV}-${CSA_PYTHON_PREFERRED}" state action old reason
  local what py="" broken="" aside="" why="" active=0 v extras=""
  if [[ "${1:-}" == "--no-create" ]]; then
    create=0
  fi
  state="$(default_venv_state)" || state=""
  IFS=$'\t' read -r action old reason <<< "$state"
  if [[ "$reason" != "-" ]]; then
    why=" ($reason)"
  fi
  case "$action" in
    ok)
      return 0
      ;;
    foreign-ok)
      info "$CSA_VENV links to $old, which this installer did not make; it is a sound Python ${CSA_PYTHON_PREFERRED} venv, so it is left as it is"
      return 0
      ;;
    other)
      warn "$CSA_VENV is not a directory or a link to one - left as it is"
      return 0
      ;;
    create)
      if [[ $create -eq 0 ]]; then
        return 0
      fi
      what="$CSA_VENV"
      ;;
    rebuild)
      what="$versioned$why"
      ;;
    flip)
      what="$CSA_VENV, a link to $old$why,"
      ;;
    migrate)
      what="$CSA_VENV, a directory from before the versioned layout$why,"
      ;;
    *)
      return 0
      ;;
  esac

  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    if [[ "$VIRTUAL_ENV" -ef "$CSA_VENV" ]]; then
      active=1
    fi
    for v in "$CSA_VENV"-*; do
      if [[ "$VIRTUAL_ENV" -ef "$v" ]]; then
        active=1
      fi
    done
  fi

  if ! py="$(find_csa_python)"; then
    py=""
    if [[ $create -eq 1 ]]; then
      py="$(ensure_csa_python)" || py=""
    fi
  fi
  if [[ -z "$py" ]]; then
    warn "$what needs a Python ${CSA_PYTHON_PREFERRED} standard build to build on, and there is no Python ${CSA_PYTHON_PREFERRED} standard build - left as it is"
    return 0
  fi
  if [[ "$reason" == *Cellar* && "$py" == */Cellar/* ]]; then
    warn "$what but the only Python ${CSA_PYTHON_PREFERRED} is on a Cellar path too - left as it is"
    return 0
  fi

  if ! broken="$(default_venv_build "$py")"; then
    return 0
  fi

  if [[ "$action" == "migrate" ]]; then
    aside="$(venv_aside_name "$CSA_VENV" "$(date +%Y%m%d%H%M%S)")" || aside=""
    if [[ -z "$aside" ]] || ! mv "$CSA_VENV" "$aside"; then
      warn "Could not move $CSA_VENV aside - left as it is; $versioned is ready and the next run links it"
      return 0
    fi
    old="$aside"
  fi
  if [[ "$action" == "rebuild" ]]; then
    old="$broken"
  else
    if ! { ln -sfn "${versioned##*/}" "${CSA_VENV}.link-new" && mv -h "${CSA_VENV}.link-new" "$CSA_VENV"; }; then
      rm -f "${CSA_VENV}.link-new"
      if [[ -n "$aside" ]]; then
        mv "$aside" "$CSA_VENV" || true
      fi
      warn "Could not link $CSA_VENV to ${versioned##*/} - left as it was; $versioned is ready"
      return 0
    fi
    case "$action" in
      create)
        success "Created $versioned; $CSA_VENV links to it"
        ;;
      migrate)
        warn "$CSA_VENV now links to ${versioned##*/}; the directory that was there$why is kept at $aside"
        ;;
      flip)
        if [[ "$old" -ef "$versioned" ]]; then
          warn "$CSA_VENV pointed at $versioned, which no longer existed; it is rebuilt"
        elif [[ -e "$old" ]]; then
          warn "$CSA_VENV now links to ${versioned##*/}; it linked to $old$why, which is kept, not deleted"
        else
          warn "$CSA_VENV now links to ${versioned##*/}; it linked to $old, which no longer exists"
        fi
        ;;
    esac
  fi

  if [[ "$action" != "create" && -d "$old" && ! "$old" -ef "$versioned" ]]; then
    extras="$(venv_extra_packages "$py" "$old" "$versioned")" || extras=""
  fi
  if [[ -n "$extras" ]]; then
    warn "Not reinstalled from $old: $extras"
    if declare -F csa_todo_add >/dev/null && csa_todo_add 43 "Reinstall what the previous ~/.default_venv had: $extras" - "$CSA_VENV/bin/python3 -m pip install $extras"; then
      :
    else
      warn "  to reinstall them: $CSA_VENV/bin/python3 -m pip install $extras"
    fi
  fi
  if [[ $active -eq 1 ]]; then
    if declare -F csa_todo_add >/dev/null && csa_todo_add 10 "Open a new terminal to use the rebuilt ~/.default_venv" - -; then
      :
    else
      warn "Open a new terminal to use the rebuilt ~/.default_venv"
    fi
  fi
  return 0
}

# What pymupdf 2.x brought into $CSA_VENV and pinning it below 2 leaves behind: onnxruntime
# (whose official macOS builds send Microsoft telemetry by default), pymupdf-layout and
# pymupdf4llm. Installing pymupdf 1.x does not remove them, and this never uninstalls anything
# itself - they may be the person's own - so it warns, names them, and adds the exact command as a
# to-do, or prints it when there is no ledger. Only once the pin holds (pymupdf below 2): while
# pymupdf 2 is still there, removing what it requires would break it. Read from the venv's
# metadata. Returns 0 always.
default_venv_leftovers() {
  local vpy="$CSA_VENV/bin/python3" found="" cmd
  local code='import glob, os, re, sys
from importlib import metadata
def norm(s):
    return re.sub(r"[-_.]+", "-", s).lower()
have = dict()
for d in metadata.distributions(path=glob.glob(os.path.join(sys.argv[1], "lib", "python*", "site-packages"))):
    try:
        have[norm(d.metadata["Name"])] = d.version or ""
    except Exception:
        pass
major = re.match(r"\d+", have.get("pymupdf", "0")) or re.match(r"\d+", "0")
if int(major.group(0)) < 2:
    print(" ".join(n for n in ("onnxruntime", "pymupdf-layout", "pymupdf4llm") if n in have))'
  if [[ ! -x "$vpy" ]]; then
    return 0
  fi
  found="$("$vpy" -I -c "$code" "$CSA_VENV" 2>/dev/null)" || found=""
  if [[ -z "$found" ]]; then
    return 0
  fi
  cmd="uv pip uninstall --python \"$vpy\" $found"
  warn "$CSA_VENV still has $found, which pymupdf 2 brought in. onnxruntime's official macOS builds send Microsoft telemetry by default; nothing was uninstalled"
  if declare -F csa_todo_add >/dev/null && csa_todo_add 44 "Remove what pymupdf 2 left in ~/.default_venv: $found (onnxruntime sends Microsoft telemetry by default)" - "$cmd"; then
    :
  else
    warn "  to remove them: $cmd"
  fi
  return 0
}

# The tools the CSA_INTERNAL_SETUPS own (each setup's name without -setup.sh, under
# `uv tool dir`) whose interpreter must be replaced, one "<tool>: <reason>" line each, for the
# Internal MCP servers plan row (#179 item 6). Only those: the row says their setups rebuild them,
# and a setup rebuilds nothing but its own tool, so another csa-* tool is not listed. Read-only:
# the private gate repo's setup scripts do the rebuilding. The test is the venv's, by the same
# recorded-path rule, in the tool's wording.
csa_tool_repairs() {
  local dir setup tool reason
  if ! has_command uv; then
    return 0
  fi
  dir="$(uv tool dir 2>/dev/null)" || dir=""
  if [[ -z "$dir" || ! -d "$dir" ]]; then
    return 0
  fi
  for setup in "${CSA_INTERNAL_SETUPS[@]}"; do
    tool="$dir/${setup%-setup.sh}"
    if [[ ! -e "$tool" && ! -L "$tool" ]]; then
      continue
    fi
    if reason="$(venv_rebuild_reason "$tool")"; then
      case "$reason" in
        "it is Python "*) reason="${reason%%,*}" ;;
        *Cellar*) reason="it is on a Homebrew Cellar path" ;;
      esac
      printf '%s: %s\n' "${tool##*/}" "$reason"
    fi
  done
  return 0
}

# The document preflight deps go into ~/.default_venv, which ensure_default_venv first makes a
# link to a sound ~/.default_venv-3.14 on the CSA Python. They used to be skipped whenever PATH's
# python3 happened to import them - but document-pipeline's launchers probe the venv, not PATH.
install_doc_python_deps() {
  local reason
  ensure_default_venv
  if reason="$(venv_rebuild_reason "$CSA_VENV")" && [[ "$reason" != *Cellar* ]]; then
    warn "Skipping document preflight deps: $CSA_VENV cannot take them ($reason)"
    return 0
  fi
  if [[ ! -x "$CSA_VENV/bin/python3" ]]; then
    warn "Skipping document preflight deps: there is no $CSA_VENV"
    return 0
  fi
  info "Installing document preflight deps (${CSA_DOC_PY_DEPS[*]}) into $CSA_VENV"
  csa_venv_pip_install "$CSA_VENV/bin/python3" "${CSA_DOC_PY_DEPS[@]}" \
    || warn "Failed to install ${CSA_DOC_PY_DEPS[*]} into $CSA_VENV — csa-preflight will print its own install hint"
  default_venv_leftovers
  return 0
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

# ── Gemini Desktop and Copilot Desktop ──────────────────────────────
# Both update themselves through a vendor service that runs whether the app is open or not -
# Google's updater and Edge's updater - so this installs once and then stays out of the way.
# Why each source was chosen, and the look-alike packages that were rejected:
# docs/desktop-ai-apps.md.

GEMINI_DESKTOP_APP="/Applications/Gemini.app"
GEMINI_DESKTOP_ID="com.google.GeminiMacOS"

COPILOT_APP="/Applications/Copilot.app"
COPILOT_RECEIPT="com.microsoft.m365copilot"
# Microsoft's per-architecture links for the unified Copilot app, from
# learn.microsoft.com/windows/client-management/deploy-unified-copilot-app. Sizes move with each
# release: 413 MB (arm64) on 2026-10-24, 531 MB (arm64) and 576 MB (Intel) on 2026-10-25.
COPILOT_PKG_ARM64="https://go.microsoft.com/fwlink/?linkid=2375510"
COPILOT_PKG_X64="https://go.microsoft.com/fwlink/?linkid=2375509"
# Read off the arm64 package on 2026-10-24 with `pkgutil --check-signature` and `spctl`
# (notarized). A package not signed by this identity is not installed - this file runs
# `sudo installer` on it.
COPILOT_SIGNER="Developer ID Installer: Microsoft Corporation (UBF8T346G9)"
# A fixed path rather than mktemp: this file's EXIT trap belongs to csa_on_exit, so an
# interrupted download cannot be cleaned up by a second trap. At a fixed path it is at worst one
# file in Caches, overwritten next run, instead of one more half-gigabyte in $TMPDIR per attempt.
COPILOT_PKG_CACHE="$HOME/Library/Caches/csa-desktopsetup/Copilot.pkg"

macos_major() {
  local v
  v="$(sw_vers -productVersion 2>/dev/null)" || v=""
  echo "${v%%.*}"
}

# hw.optional.arm64, not `uname -m`: a shell running under Rosetta reports x86_64 on Apple
# Silicon, and would pick the Intel package on an arm64 Mac.
is_apple_silicon() {
  local arm
  arm="$(sysctl -n hw.optional.arm64 2>/dev/null)" || arm=""
  [[ "$arm" == "1" ]]
}

# One answer for the plan and the install: cask | direct | other | unsupported | absent.
gemini_desktop_state() {
  if has_command brew && brew list --cask google-gemini >/dev/null 2>&1; then
    echo "cask"
    return 0
  fi
  if [[ -d "$GEMINI_DESKTOP_APP" ]]; then
    local id
    id="$(get_app_bundle_id "$GEMINI_DESKTOP_APP")" || id=""
    if [[ "$id" == "$GEMINI_DESKTOP_ID" ]]; then
      echo "direct"
    else
      # Not Google's. Installing over it would fail anyway - the cask's app is also Gemini.app.
      echo "other"
    fi
    return 0
  fi
  local major
  major="$(macos_major)"
  if ! is_apple_silicon || [[ -z "$major" ]] || [[ "$major" -lt 15 ]]; then
    echo "unsupported"
    return 0
  fi
  echo "absent"
}

install_gemini_desktop() {
  ensure_brew_in_path

  case "$(gemini_desktop_state)" in
    cask)
      info "Gemini Desktop already installed; skipping"
      return 0
      ;;
    direct)
      info "Gemini Desktop already installed (non-Homebrew); skipping"
      return 0
      ;;
    other)
      warn "$GEMINI_DESKTOP_APP is not Google's Gemini; leaving it alone and not installing Gemini Desktop"
      return 0
      ;;
    unsupported)
      info "Gemini Desktop needs Apple Silicon and macOS 15 or later; skipping"
      return 0
      ;;
  esac

  # `google-gemini`, never `gemini`: that cask is MacPaw's duplicate-file cleaner.
  info "Installing Gemini Desktop"
  brew install --cask google-gemini || warn "Failed to install Gemini Desktop"
}

# Where the installed Copilot lives, or nothing. Asked of the package receipt first, because
# the former app and the unified one share the receipt id but are not known to share a name,
# and the receipt records where it installed (`volume: /`, `location: Applications`) rather
# than leaving that to be assumed. A receipt survives an app dragged to the Trash, hence the -d
# test on what it names.
copilot_app_path() {
  local info files volume location app path
  # Captured whole, then parsed: a reader that stopped early could SIGPIPE pkgutil, and under
  # pipefail the `|| x=""` would then throw away the line that was found.
  info="$(pkgutil --pkg-info "$COPILOT_RECEIPT" 2>/dev/null)" || info=""
  files="$(pkgutil --files "$COPILOT_RECEIPT" 2>/dev/null)" || files=""
  volume="$(printf '%s\n' "$info" | awk -F': ' '$1 == "volume" { print $2 }')" || volume=""
  location="$(printf '%s\n' "$info" | awk -F': ' '$1 == "location" { print $2 }')" || location=""
  app="$(printf '%s\n' "$files" | awk -F/ 'NF == 1 && /\.app$/ && !seen { print; seen = 1 }')" || app=""
  if [[ -n "$app" ]] && [[ -n "$volume" ]]; then
    path="${volume%/}/${location:+$location/}$app"
    if [[ -d "$path" ]]; then
      echo "$path"
      return 0
    fi
  fi
  if [[ -d "$COPILOT_APP" ]]; then
    echo "$COPILOT_APP"
  fi
  return 0
}

# One answer for the plan and the install: migrate | installed | unsupported | absent.
copilot_desktop_state() {
  if [[ "$copilot_needs_migration" == "brew" ]]; then
    echo "migrate"
    return 0
  fi
  if [[ -n "$(copilot_app_path)" ]]; then
    echo "installed"
    return 0
  fi
  local major
  major="$(macos_major)"
  if [[ -z "$major" ]] || [[ "$major" -lt 14 ]]; then
    echo "unsupported"
    return 0
  fi
  echo "absent"
}

# The cask's Copilot is replaced, not left beside the new one: both claim the same receipt, and
# the cask installs it with Microsoft AutoUpdate deselected, so it would sit at whatever version
# Homebrew last recorded.
#
# Finds the Homebrew Copilot and waits for the person to quit it. Returns 1, having changed
# nothing, when it cannot be found or is still running. Refusing when it cannot be FOUND is the
# point: the receipt layout was measured for the unified app only, and a wait that silently
# skipped because it had no path to watch would replace an app that is open.
copilot_ready_to_replace() {
  local bundle
  bundle="$(copilot_app_path)"
  if [[ -z "$bundle" ]]; then
    warn "Homebrew lists microsoft-365-copilot, but its app could not be found; leaving it alone"
    return 1
  fi
  if ! wait_for_app_exit "Copilot" "$bundle"; then
    warn "Left the Homebrew Copilot in place."
    if ! csa_todo_add 43 "Quit Copilot fully (Quit from its menu, not just its window), then re-run this installer to replace the Homebrew Copilot with Microsoft's own" - -; then
      echo "  Quit Copilot fully, then re-run this installer to replace it."
    fi
    return 1
  fi
  return 0
}

# Nothing is removed until its replacement is on disk and verified. The cask's own uninstall
# deletes the app (`pkgutil: com.microsoft.m365copilot`), so removing it first and then failing
# to download, verify or get sudo would leave the person with no Copilot at all.
install_copilot_desktop() {
  ensure_brew_in_path

  local migrating=0
  case "$(copilot_desktop_state)" in
    installed)
      info "Copilot Desktop already installed; it updates itself"
      return 0
      ;;
    unsupported)
      info "Copilot Desktop needs macOS 14 or later; skipping"
      return 0
      ;;
    migrate)
      migrating=1
      info "Replacing the Homebrew Copilot (Microsoft's former Microsoft 365 Copilot app) with Microsoft's own Copilot"
      copilot_ready_to_replace || return 0
      ;;
  esac

  # Asked BEFORE a half-gigabyte download, not after: with nobody at the keyboard, a password
  # prompt nobody answers is a certain failure, and only `sudo -n` says so in advance.
  if [[ -n "${NONINTERACTIVE-}" ]] && ! sudo -n true 2>/dev/null; then
    warn "Installing Copilot Desktop needs an administrator password, and nobody is here to type it; skipping"
    return 0
  fi

  local url pkg sig gatekeeper
  if is_apple_silicon; then url="$COPILOT_PKG_ARM64"; else url="$COPILOT_PKG_X64"; fi
  pkg="$COPILOT_PKG_CACHE"
  if ! mkdir -p "$(dirname "$pkg")"; then
    warn "Could not create $(dirname "$pkg"); skipping Copilot Desktop"
    return 0
  fi

  info "Downloading Copilot Desktop from Microsoft (several hundred MB)"
  # --speed-limit/--speed-time: give up on a stalled transfer instead of hanging the run.
  if ! curl -fL --progress-bar --speed-limit 1024 --speed-time 60 -o "$pkg" "$url"; then
    warn "Failed to download Copilot Desktop"
    rm -f "$pkg"
    return 0
  fi

  # Three conditions, because a name alone is a string anyone can put in a certificate: pkgutil
  # must say Apple issued the certificate for distribution, the chain must name Microsoft's
  # installer identity, and Gatekeeper must accept the package (which also checks notarization).
  sig="$(pkgutil --check-signature "$pkg" 2>&1)" || sig=""
  gatekeeper="$(spctl -a -vv -t install "$pkg" 2>&1)" || gatekeeper=""
  if [[ "$sig" != *"Status: signed by a developer certificate issued by Apple for distribution"* ]] \
    || [[ "$sig" != *"$COPILOT_SIGNER"* ]] \
    || [[ "$gatekeeper" != *"origin=$COPILOT_SIGNER"* ]]; then
    warn "The downloaded Copilot package is not signed and notarized as Microsoft's; not installing it"
    rm -f "$pkg"
    return 0
  fi

  if [[ $migrating -eq 1 ]]; then
    # Again, because the download took minutes and Copilot may have been reopened meanwhile.
    if ! copilot_ready_to_replace; then
      rm -f "$pkg"
      return 0
    fi
    # The password is asked for HERE, before the cask is removed: a prompt mistyped three times
    # after the uninstall would leave no Copilot at all. (Non-interactive runs already passed
    # `sudo -n` above.)
    if [[ -z "${NONINTERACTIVE-}" ]] && ! sudo -v; then
      warn "Could not get administrator rights; leaving the Homebrew Copilot in place"
      rm -f "$pkg"
      return 0
    fi
    if ! brew uninstall --cask microsoft-365-copilot; then
      warn "Could not remove the Homebrew Copilot; leaving it in place"
      rm -f "$pkg"
      return 0
    fi
  fi

  info "Installing Copilot Desktop (macOS asks for your password)"
  # -n with nobody at the keyboard: fail at once rather than wait on a password nobody types.
  local installed=0
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    if sudo -n installer -pkg "$pkg" -target /; then installed=1; fi
  else
    if sudo installer -pkg "$pkg" -target /; then installed=1; fi
  fi
  rm -f "$pkg"
  if [[ $installed -eq 1 ]]; then
    success "Copilot Desktop installed; Edge's updater keeps it current"
  else
    warn "Failed to install Copilot Desktop"
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

  # `install -g <pkg>@latest`, never `update -g <pkg>`: under Homebrew's node@24 the update
  # failed with EACCES writing npm's own npmrc into the read-only keg, on every re-run (#153).
  if [[ -z "$codex_needs_migration" ]] && has_command codex; then
    info "Updating Codex CLI"
    csa_npm install -g @openai/codex@latest || warn "Failed to update Codex CLI"
  else
    info "Installing Codex CLI"
    csa_npm install -g @openai/codex@latest || warn "Failed to install Codex CLI"
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

  # @latest, never `update -g`, for the reason install_codex gives (#153).
  if [[ -z "$gemini_needs_migration" ]] && has_command gemini; then
    info "Updating Gemini CLI"
    csa_npm install -g @google/gemini-cli@latest || warn "Failed to update Gemini CLI"
  else
    info "Installing Gemini CLI"
    csa_npm install -g @google/gemini-cli@latest || warn "Failed to install Gemini CLI"
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
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')" || already_added=""

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
    # CSA_PYTHON_PREFERRED tells it which interpreter this installer provisioned, so
    # `uv tool install --python` lands the server on it. Measured 2026-09-29: with no
    # --python, uv picks its OWN managed default and ignores both PATH and anything this
    # script installed - which is how four CSA servers ended up on 3.10.20. All six entry
    # scripts now declare a preference (tests/test_python_pins.py pins them), so the setup
    # scripts never fall back to their own default from here. See CSA-Plugins#133.
    # CSA_NESTED tells the fetched script that it is running inside another CSA installer, so it
    # should leave the closing summary to this one. Without it both printed "if anything above
    # went wrong, re-run with logging on", one after the other, which reads like a stutter and
    # gives two different instructions for the same thing ("<this script>" vs "the same command").
    CSA_NESTED=1 CSA_PYTHON_PREFERRED="${CSA_PYTHON_PREFERRED:-}" bash -c "$script" || warn "CSA internal setup ($name) reported a problem (see above)"
  done
  # Last, behind the same gate and after every setup above: the plan's registration repairs.
  repair_csa_registrations
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

  # Snapshot already-registered marketplaces and already-installed plugins.
  local registered_repos installed_plugins
  registered_repos="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')" || registered_repos=""
  installed_plugins="$(claude plugin list 2>/dev/null \
    | grep -oE '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')" || installed_plugins=""

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

# ── The to-do ledger ────────────────────────────────────────────────
#
# What a person must do after an install, collected from every script that discovers one, and
# rendered ONCE at the very bottom. The Windows twin carries the measurement that prompted it:
# nine lines of "Next steps" that were not steps, ~140 lines of per-server output printed
# after them, and up to four separate "restart Claude Desktop" instructions.
#
# One record per line, tab-separated, four fields:
#
#   <order>\t<title>\t<in-claude>\t<terminal>
#
# order     10 restart, 20 sign in, 30 needs somebody else, 40+ the installer's own. Dependency
#           order is a property of the record, so a writer does not have to know what else
#           exists. Restart is first because until it happens nothing below it exists.
# title     the imperative line a person reads.
# in-claude what to say to Claude, or '-'.
# terminal  the command, or '-'.
#
# Tab-separated and single-line because the writers are bash AND PowerShell and either may be
# the reader; anything richer means a parser in two languages that must agree.
#
# CSA_TODO_FILE unset means "running standalone" - the caller returns non-zero and prints its
# own line exactly as it always did, so nothing regresses for somebody running one setup
# script by hand.
csa_todo_add() {
  local order="$1" title="$2" in_claude="${3:--}" terminal="${4:--}"
  if [[ -z "${CSA_TODO_FILE:-}" ]]; then
    return 1
  fi
  # Never fail the run over the to-do list: an install that worked matters more than the note
  # about it. `|| true` because this file runs under `set -e`.
  printf '%s\t%s\t%s\t%s\n' "$order" "$title" "$in_claude" "$terminal" >> "$CSA_TODO_FILE" 2>/dev/null || true
  return 0
}

# Renders the ledger and removes it. Called dead last - nothing may print after it, or the list
# stops being the final thing on screen, which was the original defect.
csa_show_todo_list() {
  if [[ -z "${CSA_TODO_FILE:-}" ]] || [[ ! -f "$CSA_TODO_FILE" ]]; then
    return 0
  fi

  # Dedup on the whole record keeping the FIRST occurrence - which is what collapses four
  # "restart Claude Desktop" into one, keyed on the item rather than on who emitted it. Then a
  # sort on (order, read-position), so the order within a tier is the order the servers ran and
  # therefore the order the person just watched. `sort -s` is not relied on: the position is an
  # explicit key, which is also how the PowerShell half does it, because Sort-Object is not a
  # stable sort on Windows PowerShell 5.1.
  local rendered
  rendered="$(awk -F'\t' 'NF >= 4 && !seen[$0]++ { printf "%05d\t%06d\t%s\n", $1, NR, $0 }' \
              "$CSA_TODO_FILE" | sort -k1,1n -k2,2n | cut -f3-)" || rendered=""
  rm -f "$CSA_TODO_FILE"

  if [[ -z "$rendered" ]]; then
    echo ""
    success "Nothing left to do — everything is installed and signed in."
    echo ""
    return 0
  fi

  local count
  count="$(printf '%s\n' "$rendered" | grep -c . || true)"
  local plural="s"
  if [[ "$count" == "1" ]]; then plural=""; fi

  echo ""
  printf "${BLUE}  What you need to do — %s thing%s${RESET}\n" "$count" "$plural"
  echo "  ---------------------------------------------------------------"
  local n=0
  while IFS=$'\t' read -r order title in_claude terminal; do
    if [[ -z "$title" ]]; then continue; fi
    n=$((n + 1))
    printf '  %s. %s\n' "$n" "$title"
    # "In Claude" leads. Three of the four servers ship an `authenticate` tool that delivers
    # the sign-in link in the conversation, and no setup script mentioned it — the CLI
    # fallback was printed as the only route, to an audience that is mostly not CLI people.
    # The command stays second because that path can be refused by the client.
    if [[ "$in_claude" != "-" ]]; then
      printf "     In Claude, say:    ${GREEN}%s${RESET}\n" "$in_claude"
    fi
    if [[ "$terminal" != "-" ]]; then
      printf '     Or in a terminal:  %s\n' "$terminal"
    fi
    echo ""
  done <<< "$rendered"
  echo "  Re-run this installer any time; it updates everything it installed."
  echo ""
}

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
  # Resolved, not probed. `python3` and `pip3` each resolve off PATH independently, so these
  # two rows could describe different installations - and on a real run they did (#100):
  # Python 3.13.1 from ~/.default_venv next to pip 26.2.1 from Homebrew's python3.14
  # site-packages, printed adjacently and read as one interpreter.
  #
  # find_csa_python names the interpreter install_python ensured, so the summary reports the
  # CSA Python, and pip through that interpreter rather than beside it. Re-resolved here rather
  # than carried from install_python: the summary describes the machine as it is at the end,
  # not what was decided earlier. find_csa_python never installs, so this cannot either.
  local summary_py summary_pip
  if summary_py="$(find_csa_python)"; then
    echo "  Python ............ $(get_version "$summary_py" --version), standard build ($summary_py)"
    # `|| summary_pip=""` is load-bearing, not defensive dressing. `set -o pipefail` is on, so
    # an interpreter with no pip makes this pipeline exit non-zero and `set -e` kills the script
    # HERE - at the summary, after everything succeeded - and the "not available" branch below
    # would never run. check-pipeline-assignments.py caught exactly this on the first run.
    summary_pip="$("$summary_py" -m pip --version 2>/dev/null | head -n1)" || summary_pip=""
    if [[ -n "$summary_pip" ]]; then
      echo "  pip ............... $summary_pip"
    else
      # Deliberately NOT falling back to `pip3`. A pip belonging to a different interpreter is
      # not a substitute for the missing one, and an absent pip for the Python in use is
      # precisely what somebody debugging a package that "did not install" needs to see.
      echo "  pip ............... not available for $summary_py"
    fi
  else
    echo "  Python ............ no ${CSA_PYTHON_PREFERRED} standard build (see the warnings above)"
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
  case "$(gemini_desktop_state)" in
    cask|direct) echo "  Gemini Desktop .... installed" ;;
  esac
  if [[ -n "$(copilot_app_path)" ]]; then
    echo "  Copilot Desktop ... installed"
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
  # The real to-dos go to the ledger, which renders ONE ordered list dead last - after the
  # nested setup scripts, which print their own output between here and the end of the run.
  # 40+ so the servers' items (10 restart, 20 sign in, 30 needs somebody else) come first:
  # those are what a person installed this for. The re-run line is printed by the renderer.
  if has_command gh && ! gh auth status >/dev/null 2>&1; then
    csa_todo_add 40 "Sign in to GitHub" - "gh auth login" || true
  fi
  if [[ -z "$(git config --global user.name 2>/dev/null)" ]] || [[ -z "$(git config --global user.email 2>/dev/null)" ]]; then
    csa_todo_add 41 "Tell Git who you are" - 'git config --global user.name "Your Name"   (then user.email)' || true
  fi
  if needs_1password_integration; then
    csa_todo_add 42 "Turn on the 1Password CLI integration" -       "1Password > Settings > Developer > \"Integrate with 1Password CLI\", then restart it" || true
  fi
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
  info "Cloud Security Alliance — macOS AI Tools Setup ${SCRIPT_VERSION}"

  check_running_tools
  preflight

  if ! confirm "Proceed with installation?"; then
    abort "Aborted."
  fi

  echo ""
  install_xcode_cli_tools
  install_homebrew
  install_node
  install_uv
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
  install_gemini_desktop
  install_copilot_desktop
  install_claude
  install_codex
  install_gemini
  setup_claude_env
  setup_plugin_marketplaces
  install_plugins
  setup_csa_mcp_server
  summary
  # Runs before the to-do list, because this is where the servers discover theirs. Their own
  # banners still print here - gmail's two-directory explanation is a GRANT NOTICE, so it stays
  # where it is read. What moved out is the ACTION: the banner explains, the ledger instructs.
  setup_csa_internal_tools
  # Dead last. Nothing may print after this, or the list stops being the final thing on screen -
  # which was the original defect.
  csa_show_todo_list
}

main "$@"
