#!/usr/bin/env bash

# Cloud Security Alliance — macOS MCP Setup
#
# Configures MCP servers for installed AI coding CLIs:
#   - Claude Code  (~/.claude.json,          via `claude mcp add`)
#   - Codex CLI    (~/.codex/config.toml,    direct TOML write)
#   - Gemini CLI   (~/.gemini/settings.json, direct JSON write)
#
# Services:
#   - Airtable  (hosted MCP: mcp.airtable.com)
#   - GitHub    (hosted MCP: api.githubcopilot.com, token auto-fetched via gh)
#   - Gmail     (prints manual setup instructions only — requires OAuth/GCP)
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-mcp-setup.sh)"

set -euo pipefail

SCRIPT_VERSION="2026.04090100"

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

[[ -n "${BASH_VERSION:-}" ]]          || abort "Bash is required."
[[ "$(uname -s)" == "Darwin" ]]       || abort "This script supports macOS only."

if [[ "${EUID:-${UID}}" == "0" ]]; then
  if [[ ! -f /.dockerenv ]] && [[ ! -f /run/.containerenv ]]; then
    abort "Don't run this as root."
  fi
fi

has_command() { command -v "$1" >/dev/null 2>&1; }
to_lower()    { echo "$1" | tr '[:upper:]' '[:lower:]'; }

has_command python3 || abort "Python 3 is required. Run macos-ai-tools.sh first."

if [[ -z "${NONINTERACTIVE-}" ]]; then
  if [[ -n "${CI-}" ]]; then
    warn "Non-interactive mode: \$CI is set."
    NONINTERACTIVE=1
  elif [[ ! -t 0 ]]; then
    warn "Non-interactive mode: stdin is not a TTY."
    NONINTERACTIVE=1
  fi
fi

confirm() {
  if [[ -n "${NONINTERACTIVE-}" ]]; then return 0; fi
  local reply
  read -r -p "$1 [Y/n] " reply
  case "${reply:-Y}" in
    [Yy]*) return 0 ;;
    *)     return 1 ;;
  esac
}

# ── Token primitives ─────────────────────────────────────────────────

# Show first 8 + ... + last 4 characters of a token
mask_token() {
  local t="$1"
  if [[ ${#t} -le 12 ]]; then
    printf '%s...' "${t:0:4}"
  else
    printf '%s...%s' "${t:0:8}" "${t: -4}"
  fi
}

# Extract a Bearer token already stored in ~/.claude.json for a named MCP server
get_claude_configured_token() {
  local service="$1"
  python3 - <<PYEOF 2>/dev/null
import json, os
try:
    path = os.path.expanduser("~/.claude.json")
    d = json.load(open(path))
    auth = (d.get("mcpServers", {})
             .get("${service}", {})
             .get("headers", {})
             .get("Authorization", ""))
    if auth.startswith("Bearer "):
        print(auth[7:])
except Exception:
    pass
PYEOF
}

# Extract a Bearer token from ~/.codex/config.toml for a named MCP server
get_codex_configured_token() {
  local service="$1"
  python3 - <<PYEOF 2>/dev/null
import os, re
try:
    path = os.path.expanduser("~/.codex/config.toml")
    content = open(path).read()
    m = re.search(r'\[mcp_servers\.${service}\](.*?)(?=\n\[|\Z)',
                  content, re.DOTALL)
    if m:
        t = re.search(r'Bearer\s+([^\s"\'\\\\]+)', m.group(1))
        if t:
            print(t.group(1))
except Exception:
    pass
PYEOF
}

# Extract a Bearer token from ~/.gemini/settings.json for a named MCP server
get_gemini_configured_token() {
  local service="$1"
  python3 - <<PYEOF 2>/dev/null
import json, os
try:
    path = os.path.expanduser("~/.gemini/settings.json")
    d = json.load(open(path))
    auth = (d.get("mcpServers", {})
             .get("${service}", {})
             .get("headers", {})
             .get("Authorization", ""))
    if auth.startswith("Bearer "):
        print(auth[7:])
except Exception:
    pass
PYEOF
}

# Parallel arrays populated by find_tokens()
FOUND_TOKEN_NAMES=()
FOUND_TOKEN_VALUES=()
_seen_token_values=()

_token_add() {
  local name="$1" value="$2"
  local v
  for v in "${_seen_token_values[@]}"; do
    [[ "$v" == "$value" ]] && return 0
  done
  _seen_token_values+=("$value")
  FOUND_TOKEN_NAMES+=("$name")
  FOUND_TOKEN_VALUES+=("$value")
}

# Scan live environment and shell config files for tokens matching
# a name substring and a value regex pattern.
find_tokens() {
  local name_pat; name_pat=$(to_lower "$1")
  local value_pat="$2"
  FOUND_TOKEN_NAMES=()
  FOUND_TOKEN_VALUES=()

  while IFS=$'\t' read -r name value; do
    [[ "$(to_lower "$name")" == *"${name_pat}"* ]] || continue
    [[ "$value" =~ $value_pat ]]                   || continue
    _token_add "$name" "$value"
  done < <(python3 -c "
import os
for k, v in os.environ.items():
    print(k + '\t' + v)
" 2>/dev/null)

  local f
  for f in ~/.zshenv ~/.zprofile ~/.zshrc; do
    [[ -f "$f" ]] || continue
    while IFS= read -r line; do
      line="${line#"${line%%[![:space:]]*}"}"
      line="${line#export }"
      [[ "$line" == *=* ]] || continue
      local name="${line%%=*}"
      local value="${line#*=}"
      value="${value#\"}" ; value="${value%\"}"
      value="${value#\'}" ; value="${value%\'}"
      [[ -z "$value" ]]                               && continue
      [[ "$(to_lower "$name")" == *"${name_pat}"* ]] || continue
      [[ "$value" =~ $value_pat ]]                   || continue
      _token_add "$name" "$value"
    done < <(grep -E "^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=." \
               "$f" 2>/dev/null || true)
  done
}

# Test a token against the service's API.
# On success: prints identity string, returns 0. On failure: prints reason, returns 1.
validate_token() {
  local service="$1" token="$2"
  local url identity_key

  case "$service" in
    airtable) url="https://api.airtable.com/v0/meta/whoami"; identity_key="email"  ;;
    github)   url="https://api.github.com/user";             identity_key="login"  ;;
    *)        printf "unknown service"; return 1 ;;
  esac

  local response http_code body
  response=$(curl -s -w $'\n''%{http_code}' \
    -H "Authorization: Bearer $token" \
    -H "User-Agent: CSA-DesktopSetup/${SCRIPT_VERSION}" \
    "$url" 2>/dev/null) || { printf "network error"; return 1; }

  http_code="${response##*$'\n'}"
  body="${response%$'\n'*}"

  if [[ "$http_code" != "200" ]]; then
    printf "invalid (HTTP %s)" "$http_code"
    return 1
  fi

  local identity
  identity=$(RESPONSE_BODY="$body" IDENTITY_KEY="$identity_key" python3 -c "
import os, json
key = os.environ['IDENTITY_KEY']
try:
    d = json.loads(os.environ['RESPONSE_BODY'])
    print(d.get(key, 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null) || identity="unknown"

  printf "%s" "$identity"
  return 0
}

# ── Token catalog ─────────────────────────────────────────────────────
#
# Each unique token value gets a letter label (A, B, C...).
# Parallel arrays — one slot per unique value:
CATALOG_LABELS=()      # "A", "B", "C"...
CATALOG_VALUES=()      # deduplicated token values
CATALOG_VALID=()       # "1" valid / "0" invalid
CATALOG_IDENTITIES=()  # identity string from API (or error reason)
CATALOG_SOURCES=()     # where found, comma-joined ("claude, codex, AIRTABLE_API_KEY")

# Track every successful write this run: "display_name|masked_token|tool|file"
CHANGES_MADE=()

# Convert 0-based index to letter label: 0→A, 1→B, ..., 25→Z, 26→AA ...
_idx_to_label() {
  local idx=$1 alpha="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
  if [[ $idx -lt 26 ]]; then
    echo "${alpha:$idx:1}"
  else
    echo "${alpha:$(( idx/26 - 1 )):1}${alpha:$(( idx%26 )):1}"
  fi
}

# Add a source+value pair to the catalog; merges sources if value already present
_catalog_add() {
  local src="$1" val="$2"
  local i
  for i in "${!CATALOG_VALUES[@]}"; do
    if [[ "${CATALOG_VALUES[$i]}" == "$val" ]]; then
      CATALOG_SOURCES[i]="${CATALOG_SOURCES[i]}, $src"
      return 0
    fi
  done
  local idx=${#CATALOG_VALUES[@]}
  CATALOG_LABELS+=("$(_idx_to_label "$idx")")
  CATALOG_VALUES+=("$val")
  CATALOG_VALID+=("0")
  CATALOG_IDENTITIES+=("")
  CATALOG_SOURCES+=("$src")
}

# Discover and validate all tokens for a service; populates CATALOG_* arrays.
# extra_name/extra_value: optional pre-fetched token (e.g. gh auth)
build_catalog() {
  local service="$1" name_pat="$2" value_pat="$3"
  local extra_name="${4:-}" extra_value="${5:-}"

  CATALOG_LABELS=()
  CATALOG_VALUES=()
  CATALOG_VALID=()
  CATALOG_IDENTITIES=()
  CATALOG_SOURCES=()

  # Already-configured tokens (one per tool — may be the same value)
  local t
  t=$(get_claude_configured_token "$service"); [[ -n "$t" ]] && _catalog_add "claude" "$t"
  t=$(get_codex_configured_token  "$service"); [[ -n "$t" ]] && _catalog_add "codex"  "$t"
  t=$(get_gemini_configured_token "$service"); [[ -n "$t" ]] && _catalog_add "gemini" "$t"

  # Pre-fetched extra token (e.g. gh auth)
  [[ -n "$extra_value" ]] && _catalog_add "$extra_name" "$extra_value"

  # Env vars and shell config files (skip values already in catalog)
  _seen_token_values=("${CATALOG_VALUES[@]}")
  find_tokens "$name_pat" "$value_pat"
  local i
  for i in "${!FOUND_TOKEN_NAMES[@]}"; do
    _catalog_add "${FOUND_TOKEN_NAMES[$i]}" "${FOUND_TOKEN_VALUES[$i]}"
  done

  # Validate each unique token
  for i in "${!CATALOG_VALUES[@]}"; do
    local identity
    if identity=$(validate_token "$service" "${CATALOG_VALUES[$i]}" 2>/dev/null); then
      CATALOG_VALID[i]="1"
      CATALOG_IDENTITIES[i]="$identity"
    else
      CATALOG_VALID[i]="0"
      CATALOG_IDENTITIES[i]="$identity"
    fi
  done
}

# Return the catalog label for a token value (empty string if not found)
catalog_label_for_value() {
  local val="$1"
  [[ -z "$val" ]] && return
  local i
  for i in "${!CATALOG_VALUES[@]}"; do
    [[ "${CATALOG_VALUES[$i]}" == "$val" ]] && { echo "${CATALOG_LABELS[$i]}"; return; }
  done
}

# Print the catalog table
show_catalog() {
  if [[ ${#CATALOG_VALUES[@]} -eq 0 ]]; then
    echo "  No tokens found."
    echo ""
    return
  fi
  echo "  Token catalog:"
  echo ""
  local i masked valid_line
  for i in "${!CATALOG_VALUES[@]}"; do
    masked=$(mask_token "${CATALOG_VALUES[$i]}")
    if [[ "${CATALOG_VALID[i]}" == "1" ]]; then
      valid_line="${GREEN}✔ valid${RESET} · ${CATALOG_IDENTITIES[i]}"
    else
      valid_line="${RED}✗ invalid${RESET} (${CATALOG_IDENTITIES[i]})"
    fi
    printf "    %s)  %-22s  " "${CATALOG_LABELS[$i]}" "$masked"
    printf "%b" "$valid_line"
    printf "  [%s]\n" "${CATALOG_SOURCES[i]}"
  done
  echo ""
}

# Print current per-tool configuration using catalog labels (A, B, ?)
show_current_config() {
  local service="$1"
  local any=0
  local tool tool_name current_val lbl
  for tool in claude codex gemini; do
    has_command "$tool" || continue
    any=1
    case "$tool" in
      claude) tool_name="Claude Code" ;;
      codex)  tool_name="Codex CLI"   ;;
      gemini) tool_name="Gemini CLI"  ;;
    esac
    current_val=$(get_${tool}_configured_token "$service" 2>/dev/null || echo "")
    if [[ -z "$current_val" ]]; then
      printf "    %-12s  (not configured)\n" "$tool_name"
    else
      lbl=$(catalog_label_for_value "$current_val")
      [[ -z "$lbl" ]] && lbl="?"
      printf "    %-12s  %s  %s\n" "$tool_name" "$lbl" "$(mask_token "$current_val")"
    fi
  done
  [[ $any -eq 1 ]] && echo ""
}

# ── MCP config writers ────────────────────────────────────────────────

# Claude Code: remove existing entry (if any) then add fresh
mcp_claude_add() {
  local name="$1" url="$2" token="$3"
  claude mcp remove "$name" --scope user 2>/dev/null || true
  claude mcp add --transport http "$name" "$url" \
    --header "Authorization: Bearer $token" \
    --scope user
}

# Gemini CLI: merge into ~/.gemini/settings.json
mcp_gemini_add() {
  local name="$1" url="$2" token="$3"
  python3 - <<PYEOF 2>/dev/null
import json, os, sys

path = os.path.expanduser("~/.gemini/settings.json")
os.makedirs(os.path.dirname(path), exist_ok=True)

try:
    with open(path) as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

config.setdefault("mcpServers", {})
config["mcpServers"]["${name}"] = {
    "httpUrl": "${url}",
    "headers": {"Authorization": "Bearer ${token}"}
}

try:
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
except Exception:
    sys.exit(1)
PYEOF
}

# Codex CLI: add or replace [mcp_servers.<name>] section in ~/.codex/config.toml
mcp_codex_add() {
  local name="$1" url="$2" token="$3"
  python3 - <<PYEOF 2>/dev/null
import os, re, sys

path = os.path.expanduser("~/.codex/config.toml")
os.makedirs(os.path.dirname(path), exist_ok=True)

try:
    with open(path) as f:
        content = f.read()
except FileNotFoundError:
    content = ""

new_block = (
    '[mcp_servers.${name}]\n'
    'url = "${url}"\n'
    'http_headers = { "Authorization" = "Bearer ${token}" }\n'
    'enabled = true\n'
)

pattern = r'\[mcp_servers\.${name}\][^\[]*'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_block, content, flags=re.DOTALL)
else:
    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n" + new_block

try:
    with open(path, "w") as f:
        f.write(content)
except Exception:
    sys.exit(1)
PYEOF
}

# ── Service handler ───────────────────────────────────────────────────

# Apply one token to every installed tool, printing per-tool status
_apply_to_all() {
  local service_key="$1" mcp_url="$2" token="$3"
  local masked; masked=$(mask_token "$token")
  echo ""
  if has_command claude; then
    printf "  Claude Code ... "
    if mcp_claude_add "$service_key" "$mcp_url" "$token" 2>/dev/null; then
      printf "${GREEN}✔ configured${RESET}\n"
      CHANGES_MADE+=("$service_key|$masked|Claude Code|$HOME/.claude.json")
    else
      printf "${RED}✗ failed${RESET}\n"
    fi
  fi
  if has_command gemini; then
    printf "  Gemini CLI  ... "
    if mcp_gemini_add "$service_key" "$mcp_url" "$token" 2>/dev/null; then
      printf "${GREEN}✔ configured${RESET}\n"
      CHANGES_MADE+=("$service_key|$masked|Gemini CLI|$HOME/.gemini/settings.json")
    else
      printf "${RED}✗ failed${RESET}\n"
    fi
  fi
  if has_command codex; then
    printf "  Codex CLI   ... "
    if mcp_codex_add "$service_key" "$mcp_url" "$token" 2>/dev/null; then
      printf "${GREEN}✔ configured${RESET}\n"
      CHANGES_MADE+=("$service_key|$masked|Codex CLI|$HOME/.codex/config.toml")
    else
      printf "${RED}✗ failed${RESET}\n"
    fi
  fi
}

# Apply one token to a single tool
_apply_to_tool() {
  local tool="$1" service_key="$2" mcp_url="$3" token="$4"
  local masked; masked=$(mask_token "$token")
  case "$tool" in
    claude)
      printf "      Claude Code ... "
      if mcp_claude_add "$service_key" "$mcp_url" "$token" 2>/dev/null; then
        printf "${GREEN}✔${RESET}\n"
        CHANGES_MADE+=("$service_key|$masked|Claude Code|$HOME/.claude.json")
      else
        printf "${RED}✗ failed${RESET}\n"
      fi
      ;;
    gemini)
      printf "      Gemini CLI  ... "
      if mcp_gemini_add "$service_key" "$mcp_url" "$token" 2>/dev/null; then
        printf "${GREEN}✔${RESET}\n"
        CHANGES_MADE+=("$service_key|$masked|Gemini CLI|$HOME/.gemini/settings.json")
      else
        printf "${RED}✗ failed${RESET}\n"
      fi
      ;;
    codex)
      printf "      Codex CLI   ... "
      if mcp_codex_add "$service_key" "$mcp_url" "$token" 2>/dev/null; then
        printf "${GREEN}✔${RESET}\n"
        CHANGES_MADE+=("$service_key|$masked|Codex CLI|$HOME/.codex/config.toml")
      else
        printf "${RED}✗ failed${RESET}\n"
      fi
      ;;
  esac
}

# Prompt to enter and validate a new token; echoes the token on success
_prompt_new_token() {
  local service="$1" create_url="$2"
  printf "  Create a token at: %s\n" "$create_url"
  echo ""
  while true; do
    local tok=""
    read -r -s -p "  Paste token (hidden): " tok; echo ""
    [[ -z "$tok" ]] && { warn "Token cannot be empty."; continue; }
    printf "  Testing... "
    local identity
    if identity=$(validate_token "$service" "$tok" 2>/dev/null); then
      printf "${GREEN}✔ valid${RESET} · %s\n" "$identity"
      # Add to catalog so it can be reused in per-tool mode
      _catalog_add "new" "$tok"
      local idx=$(( ${#CATALOG_VALUES[@]} - 1 ))
      CATALOG_VALID[idx]="1"
      CATALOG_IDENTITIES[idx]="$identity"
      echo "$tok"
      return 0
    else
      printf "${RED}✗ %s${RESET} — try again.\n" "$identity"
    fi
  done
}

# Prompt for a token choice (letter/+/keep/skip) for one tool in per-tool mode
_prompt_tool_choice() {
  local tool="$1" service_key="$2" mcp_url="$3" create_url="$4"
  local tool_name current_val lbl current_display

  case "$tool" in
    claude) tool_name="Claude Code" ;;
    codex)  tool_name="Codex CLI"   ;;
    gemini) tool_name="Gemini CLI"  ;;
  esac

  current_val=$(get_${tool}_configured_token "$service_key" 2>/dev/null || echo "")
  lbl=$(catalog_label_for_value "$current_val")
  [[ -z "$lbl" && -n "$current_val" ]] && lbl="?"

  if [[ -z "$current_val" ]]; then
    current_display="not configured"
  else
    current_display="${lbl} ($(mask_token "$current_val"))"
  fi

  # Build valid-label list for the prompt hint
  local valid_opts="" i
  for i in "${!CATALOG_VALID[@]}"; do
    [[ "${CATALOG_VALID[i]}" == "1" ]] && valid_opts="${valid_opts}${CATALOG_LABELS[$i]}/"
  done
  local opts_hint="${valid_opts}+/keep/skip"

  while true; do
    printf "    %-12s  (currently: %-22s)  [%s]: " \
      "$tool_name" "$current_display" "$opts_hint"
    local choice
    read -r choice
    choice="${choice:-keep}"

    case "$(to_lower "$choice")" in
      keep|"")
        return 0  # leave unchanged
        ;;
      skip)
        return 0  # also leave unchanged — skip means "don't touch this tool"
        ;;
      +|new)
        echo ""
        local new_tok
        if new_tok=$(_prompt_new_token "$service_key" "$create_url"); then
          _apply_to_tool "$tool" "$service_key" "$mcp_url" "$new_tok"
        fi
        return 0
        ;;
      *)
        # Match against a catalog label
        local matched=0
        for i in "${!CATALOG_LABELS[@]}"; do
          if [[ "$(to_lower "$choice")" == "$(to_lower "${CATALOG_LABELS[$i]}")" ]]; then
            matched=1
            if [[ "${CATALOG_VALID[i]}" == "1" ]]; then
              _apply_to_tool "$tool" "$service_key" "$mcp_url" "${CATALOG_VALUES[$i]}"
            else
              warn "Token ${CATALOG_LABELS[$i]} is not valid — choose another."
              matched=0  # force retry
            fi
            break
          fi
        done
        [[ $matched -eq 0 ]] && warn "Enter a letter (${valid_opts}), +, keep, or skip."
        [[ $matched -eq 1 ]] && return 0
        ;;
    esac
  done
}

# Generic service handler: discover tokens, show catalog + current state, prompt.
#
#   display_name  — shown to user ("Airtable", "GitHub")
#   service_key   — MCP server name and config key ("airtable", "github")
#   name_pat      — token name pattern for env/shell discovery ("airtable")
#   value_pat     — ERE matched against token values ("^pat")
#   create_url    — where to create a new token
#   mcp_url       — the MCP server endpoint URL
#   extra_name    — optional pre-fetched candidate display name (e.g. "gh auth")
#   extra_value   — optional pre-fetched candidate token value
handle_service() {
  local display_name="$1" service_key="$2"
  local name_pat="$3" value_pat="$4"
  local create_url="$5" mcp_url="$6"
  local extra_name="${7:-}" extra_value="${8:-}"

  echo ""
  info "────────────────────────────── $display_name"
  echo ""

  build_catalog "$service_key" "$name_pat" "$value_pat" "$extra_name" "$extra_value"

  show_catalog
  echo "  Currently configured:"
  show_current_config "$service_key"

  # NONINTERACTIVE: use first valid token for all tools, or skip
  if [[ -n "${NONINTERACTIVE-}" ]]; then
    local i first_valid=""
    for i in "${!CATALOG_VALID[@]}"; do
      if [[ "${CATALOG_VALID[i]}" == "1" ]]; then
        first_valid="${CATALOG_VALUES[$i]}"
        break
      fi
    done
    if [[ -z "$first_valid" ]]; then
      warn "No valid $display_name token found — skipping."
      return 0
    fi
    _apply_to_all "$service_key" "$mcp_url" "$first_valid"
    return 0
  fi

  # Build the prompt options line
  local valid_labels=() i
  for i in "${!CATALOG_VALID[@]}"; do
    [[ "${CATALOG_VALID[i]}" == "1" ]] && valid_labels+=("${CATALOG_LABELS[$i]}")
  done

  echo "  Options:"
  for lbl in "${valid_labels[@]}"; do
    printf "    [%s]  Apply token %s to all tools\n" "$lbl" "$lbl"
  done
  echo "    [t]  Configure each tool separately (different token per tool)"
  printf "    [+]  Enter a new token  (%s)\n" "$create_url"
  echo "    [s]  Skip — keep current configuration"
  echo ""

  local valid_opts_str
  if [[ ${#valid_labels[@]} -gt 0 ]]; then
    valid_opts_str="$(IFS="/"; echo "${valid_labels[*]}")/t/+/s"
  else
    valid_opts_str="t/+/s"
  fi

  while true; do
    local choice
    read -r -p "  Choice [$valid_opts_str]: " choice
    choice="${choice:-s}"

    case "$(to_lower "$choice")" in
      s|skip)
        info "Skipping $display_name — existing config left unchanged."
        return 0
        ;;
      t)
        echo ""
        echo "  Configure each tool (letter to apply that token, [keep] to leave unchanged):"
        echo ""
        local tool
        for tool in claude codex gemini; do
          has_command "$tool" || continue
          _prompt_tool_choice "$tool" "$service_key" "$mcp_url" "$create_url"
        done
        echo ""
        return 0
        ;;
      +|new)
        echo ""
        local new_tok
        if new_tok=$(_prompt_new_token "$service_key" "$create_url"); then
          _apply_to_all "$service_key" "$mcp_url" "$new_tok"
        fi
        return 0
        ;;
      *)
        local matched=0
        for i in "${!CATALOG_LABELS[@]}"; do
          if [[ "$(to_lower "$choice")" == "$(to_lower "${CATALOG_LABELS[$i]}")" ]]; then
            matched=1
            if [[ "${CATALOG_VALID[i]}" == "1" ]]; then
              _apply_to_all "$service_key" "$mcp_url" "${CATALOG_VALUES[$i]}"
            else
              warn "Token ${CATALOG_LABELS[$i]} is not valid — choose another."
              matched=0
            fi
            break
          fi
        done
        [[ $matched -eq 0 ]] && warn "Enter one of: $valid_opts_str"
        [[ $matched -eq 1 ]] && return 0
        ;;
    esac
  done
}

# ── Service handlers ──────────────────────────────────────────────────

handle_airtable() {
  handle_service \
    "Airtable" "airtable" \
    "airtable" "^pat" \
    "https://airtable.com/account/security" \
    "https://mcp.airtable.com/mcp"
}

handle_github() {
  local gh_token=""
  has_command gh && gh_token=$(gh auth token 2>/dev/null || true)
  handle_service \
    "GitHub" "github" \
    "github" "^gh[pos]_|^github_pat_" \
    "https://github.com/settings/tokens" \
    "https://api.githubcopilot.com/mcp" \
    "gh auth (current session)" "$gh_token"
}

handle_gmail_instructions() {
  echo ""
  info "────────────────────────────── Gmail (manual setup — Claude Code only)"
  echo ""
  cat <<'INSTRUCTIONS'
  Gmail requires OAuth 2.0 via a Google Cloud project. No scriptable
  token path exists. Follow these steps once:

  1. Create a GCP project
       https://console.cloud.google.com/ → New Project

  2. Enable the Gmail API
       APIs & Services → Library → search "Gmail API" → Enable
       (also enable Drive, Calendar, Sheets if wanted)

  3. Create OAuth 2.0 credentials
       APIs & Services → Credentials → Create Credentials → OAuth client ID
       Type: Web application
       Redirect URI: http://localhost:8000/oauth2callback
       → copy Client ID and Client Secret

  4. Add to ~/.zprofile:
       export GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
       export GOOGLE_OAUTH_CLIENT_SECRET="your-client-secret"
       source ~/.zprofile

  5. Start the server (must be running for Claude Code to use Gmail):
       uvx workspace-mcp --transport streamable-http

  6. Register with Claude Code (one time):
       claude mcp add --transport http workspace-mcp \
         http://localhost:8000/mcp --scope user

  7. Inside Claude Code, run /mcp → select workspace-mcp → complete OAuth

  Full docs: https://workspacemcp.com/quick-start
  Auto-start on login: see docs/mcp-servers.md (Launch Agent instructions)
INSTRUCTIONS
}

# ── Legacy MCP detection ──────────────────────────────────────────────

# Scan all three config files for old npm/npx/stdio-based MCP entries.
# Prints a report and removes them if confirmed.
check_legacy_mcp() {
  local legacy_report
  legacy_report=$(python3 - <<'PYEOF' 2>/dev/null
import json, os, re, sys

def check_claude():
    path = os.path.expanduser("~/.claude.json")
    try:
        d = json.load(open(path))
        for name, cfg in d.get("mcpServers", {}).items():
            if "command" in cfg:
                args = " ".join(cfg.get("args", []))
                print(f"claude|{name}|command={cfg['command']} {args}")
    except Exception:
        pass

def check_codex():
    path = os.path.expanduser("~/.codex/config.toml")
    try:
        content = open(path).read()
        # Malformed section headers: ones that start with a quoted string directly
        # (e.g. ["-y", "airtable-mcp-server"]) — valid paths like
        # [plugins."name"] start with an unquoted identifier before any quote.
        for m in re.finditer(r'\[("(?:[^"\\]|\\.)*"(?:\s*,\s*"(?:[^"\\]|\\.)*")*)\]', content):
            print(f"codex|malformed [{m.group(1)}]|invalid TOML section header")
        # command-based mcp_servers entries
        for m in re.finditer(r'\[mcp_servers\.(\w+)\](.*?)(?=\n\[|\Z)', content, re.DOTALL):
            if re.search(r'command\s*=', m.group(2)):
                print(f"codex|{m.group(1)}|command-based (not HTTP)")
    except Exception:
        pass

def check_gemini():
    path = os.path.expanduser("~/.gemini/settings.json")
    try:
        d = json.load(open(path))
        for name, cfg in d.get("mcpServers", {}).items():
            if "command" in cfg:
                args = " ".join(cfg.get("args", []))
                print(f"gemini|{name}|command={cfg['command']} {args}")
    except Exception:
        pass

check_claude()
check_codex()
check_gemini()
PYEOF
)

  [[ -z "$legacy_report" ]] && return 0

  warn "Old-style MCP entries found (npm/npx/stdio-based — these don't work with hosted MCP):"
  echo ""
  local tool name reason
  while IFS='|' read -r tool name reason; do
    local file
    case "$tool" in
      claude) file="$HOME/.claude.json" ;;
      codex)  file="$HOME/.codex/config.toml" ;;
      gemini) file="$HOME/.gemini/settings.json" ;;
    esac
    printf "    %-28s  %-30s  %s\n" "$file" "$name" "$reason"
  done <<< "$legacy_report"
  echo ""

  if ! confirm "  Remove these old entries before proceeding?"; then
    warn "Leaving old entries in place — they may cause errors in the tools."
    return 0
  fi

  # Remove them
  python3 - <<'PYEOF' 2>/dev/null
import json, os, re

# Claude: remove command-based entries
path = os.path.expanduser("~/.claude.json")
try:
    d = json.load(open(path))
    servers = d.get("mcpServers", {})
    removed = [k for k, v in servers.items() if "command" in v]
    for k in removed:
        del servers[k]
    if removed:
        with open(path, "w") as f:
            json.dump(d, f, indent=2)
        print(f"  ~/.claude.json: removed {', '.join(removed)}")
except Exception:
    pass

# Codex: remove malformed sections and command-based mcp_servers
path = os.path.expanduser("~/.codex/config.toml")
try:
    content = open(path).read()
    orig = content
    # Remove malformed section headers that start with a quoted string
    # (e.g. ["-y", "airtable-mcp-server"]) — leaves valid paths like
    # [plugins."name"] and [projects."/path"] untouched.
    content = re.sub(
        r'\n\["(?:[^"\\]|\\.)*"(?:\s*,\s*"(?:[^"\\]|\\.)*")*\][^\[]*',
        '\n', content, flags=re.DOTALL)
    # Remove command-based mcp_servers sections
    def strip_cmd(m):
        if re.search(r'command\s*=', m.group(2)):
            return ''
        return m.group(0)
    content = re.sub(
        r'\n\[mcp_servers\.(\w+)\](.*?)(?=\n\[|\Z)', strip_cmd, content, flags=re.DOTALL)
    if content != orig:
        with open(path, "w") as f:
            f.write(content)
        print("  ~/.codex/config.toml: removed old entries")
except Exception:
    pass

# Gemini: remove command-based entries
path = os.path.expanduser("~/.gemini/settings.json")
try:
    d = json.load(open(path))
    servers = d.get("mcpServers", {})
    removed = [k for k, v in servers.items() if "command" in v]
    for k in removed:
        del servers[k]
    if removed:
        with open(path, "w") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        print(f"  ~/.gemini/settings.json: removed {', '.join(removed)}")
except Exception:
    pass
PYEOF

  success "Old entries removed."
  echo ""
}

# ── Preflight ────────────────────────────────────────────────────────

preflight() {
  echo ""
  info "Plan:"
  echo ""

  echo "  AI tools detected:"
  has_command claude && echo "    ✔ Claude Code" || echo "    ✗ Claude Code (not installed — run macos-ai-tools.sh)"
  has_command codex  && echo "    ✔ Codex CLI"   || echo "    ✗ Codex CLI   (not installed)"
  has_command gemini && echo "    ✔ Gemini CLI"  || echo "    ✗ Gemini CLI  (not installed)"
  echo ""

  echo "  Services:"
  echo "    • Airtable  — hosted MCP, PAT required"
  echo "    • GitHub    — hosted MCP, token auto-fetched via gh if available"
  echo "    • Gmail     — manual setup instructions printed (Claude Code only)"
  echo ""

  echo "  Config files that may be written:"
  echo "    ~/.claude.json"
  has_command codex  && echo "    ~/.codex/config.toml"
  has_command gemini && echo "    ~/.gemini/settings.json"
  echo ""
}

# ── Summary ──────────────────────────────────────────────────────────

summary() {
  echo ""
  success "Done!"
  echo ""

  if [[ ${#CHANGES_MADE[@]} -gt 0 ]]; then
    info "What was written:"
    echo ""
    local last_svc="" entry svc masked tool file
    for entry in "${CHANGES_MADE[@]}"; do
      IFS='|' read -r svc masked tool file <<< "$entry"
      if [[ "$svc" != "$last_svc" ]]; then
        printf "  %s\n" "$svc"
        last_svc="$svc"
      fi
      printf "    %-12s  %-28s  token: %s\n" "$tool" "$file" "$masked"
    done
    echo ""
  fi

  info "Verify:"
  echo ""
  has_command claude && echo "  claude mcp list"
  has_command codex  && echo "  codex mcp list"
  has_command gemini && echo "  gemini mcp list"
  echo ""
  echo "  Inside Claude Code, run /mcp to confirm servers are connected."
  echo ""
}

# ── Main ─────────────────────────────────────────────────────────────

main() {
  info "Cloud Security Alliance — macOS MCP Setup v${SCRIPT_VERSION}"

  preflight
  check_legacy_mcp

  if ! confirm "Proceed?"; then
    abort "Aborted."
  fi

  handle_airtable
  handle_github
  handle_gmail_instructions

  summary
}

main "$@"
