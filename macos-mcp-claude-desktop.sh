#!/usr/bin/env bash

# Cloud Security Alliance Claude Desktop MCP Server Configuration Script
# Configures MCP servers for Claude Desktop by editing claude_desktop_config.json
#
# Usage (recommended):
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/macos-mcp-claude-desktop.sh)"

set -euo pipefail

# Colors and formatting
if [[ -t 1 ]]; then
  tty_escape() { printf "\033[%sm" "$1"; }
else
  tty_escape() { :; }
fi
tty_mkbold() { tty_escape "1;$1"; }
tty_blue="$(tty_mkbold 34)"
tty_green="$(tty_mkbold 32)"
tty_red="$(tty_mkbold 31)"
tty_yellow="$(tty_mkbold 33)"
tty_bold="$(tty_mkbold 39)"
tty_reset="$(tty_escape 0)"

ohai() { printf "${tty_blue}==>${tty_bold} %s${tty_reset}\n" "$*"; }
success() { printf "${tty_green}✓${tty_reset} %s\n" "$*"; }
warn() { printf "${tty_yellow}Warning${tty_reset}: %s\n" "$*" >&2; }
error() { printf "${tty_red}Error${tty_reset}: %s\n" "$*" >&2; }
abort() { error "$@"; exit 1; }

# Configuration
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

# Ensure required tools are available
check_dependencies() {
  if ! command -v python3 >/dev/null 2>&1; then
    error "Missing required dependency: python3"
    echo "Please install Python 3 via: brew install python3"
    exit 1
  fi
}

# JSON operations using Python (compatible with all Python 3 versions)
json_operation() {
  local operation="$1"; shift

  case "$operation" in
    validate)
      local json_file="$1"
      python3 -c "
import json, sys
try:
    with open('$json_file', 'r') as f:
        json.load(f)
    print('valid')
except json.JSONDecodeError as e:
    print(f'invalid: {e}', file=sys.stderr)
    sys.exit(1)
except FileNotFoundError:
    print('missing')
"
      ;;
    check_server)
      local config_file="$1" server_name="$2"
      python3 -c "
import json, sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
    if 'mcpServers' in config and '$server_name' in config['mcpServers']:
        print('exists')
    else:
        print('missing')
except (FileNotFoundError, json.JSONDecodeError):
    print('missing')
"
      ;;
    get_server_info)
      local config_file="$1" server_name="$2"
      python3 -c "
import json, sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
    server = config.get('mcpServers', {}).get('$server_name', {})
    env = server.get('env', {})
    print(f\"Server: {env.get('SERVER', 'N/A')}\")
    print(f\"Site: {env.get('SITE_NAME', 'N/A')}\")
    print(f\"PAT Name: {env.get('PAT_NAME', 'N/A')}\")
except (FileNotFoundError, json.JSONDecodeError):
    print('Error reading configuration')
"
      ;;
    add_server)
      local config_file="$1" server_name="$2" server_config="$3"
      python3 -c "
import json, sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

config['mcpServers']['$server_name'] = json.loads('$server_config')

with open('$config_file', 'w') as f:
    json.dump(config, f, indent=2)
print('success')
" || echo "failed"
      ;;
    remove_server)
      local config_file="$1" server_name="$2"
      python3 -c "
import json, sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
    if 'mcpServers' in config and '$server_name' in config['mcpServers']:
        del config['mcpServers']['$server_name']
        with open('$config_file', 'w') as f:
            json.dump(config, f, indent=2)
        print('success')
    else:
        print('not_found')
except (FileNotFoundError, json.JSONDecodeError):
    print('failed')
"
      ;;
  esac
}

# Create backup of config file
backup_config() {
  if [[ -f "$CLAUDE_CONFIG_FILE" ]]; then
    local backup_file="${CLAUDE_CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CLAUDE_CONFIG_FILE" "$backup_file"
    success "Backup created: ${backup_file##*/}"
  fi
}

# Ensure config directory exists
ensure_config_dir() {
  if [[ ! -d "$CLAUDE_CONFIG_DIR" ]]; then
    mkdir -p "$CLAUDE_CONFIG_DIR"
    success "Created Claude config directory"
  fi
}

# Initialize empty config if it doesn't exist
init_config_if_needed() {
  if [[ ! -f "$CLAUDE_CONFIG_FILE" ]]; then
    echo '{"mcpServers": {}}' > "$CLAUDE_CONFIG_FILE"
    success "Created new Claude config file"
  fi
}

# Read user input securely for passwords/tokens
read_secret() {
  local prompt="$1"
  local var_name="$2"
  local value=""

  echo -n "$prompt"
  read -s value
  echo

  if [[ -z "$value" ]]; then
    warn "Empty value provided"
    return 1
  fi

  declare -g "$var_name=$value"
}

# Ask yes/no question
ask_yn() {
  local prompt="$1"
  local default="${2:-n}"
  local reply

  if [[ "$default" == "y" ]]; then
    echo -n "$prompt [Y/n]: "
  else
    echo -n "$prompt [y/N]: "
  fi

  read -r reply
  reply="${reply:-$default}"

  case "$reply" in
    [Yy]*) return 0 ;;
    [Nn]*) return 1 ;;
    *) return 1 ;;
  esac
}

# Create and save Tableau configuration
create_and_save_tableau_config() {
  local server_url="$1" site_name="$2" pat_name="$3" pat_value="$4"

  # Create server configuration (escape for JSON)
  local escaped_server_url escaped_site_name escaped_pat_name escaped_pat_value
  escaped_server_url=$(printf '%s\n' "$server_url" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')
  escaped_site_name=$(printf '%s\n' "$site_name" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')
  escaped_pat_name=$(printf '%s\n' "$pat_name" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')
  escaped_pat_value=$(printf '%s\n' "$pat_value" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')

  local tableau_config
  tableau_config="{
  \"command\": \"npx\",
  \"args\": [\"-y\", \"@tableau/mcp-server@latest\"],
  \"env\": {
    \"SERVER\": $escaped_server_url,
    \"SITE_NAME\": $escaped_site_name,
    \"PAT_NAME\": $escaped_pat_name,
    \"PAT_VALUE\": $escaped_pat_value
  }
}"

  # Add to config
  local result
  result=$(json_operation add_server "$CLAUDE_CONFIG_FILE" "tableau" "$tableau_config")
  if [[ "$result" != "success" ]]; then
    abort "Failed to update configuration"
  fi
}

# Handle Tableau MCP Server
handle_tableau() {
  local server_status
  server_status=$(json_operation check_server "$CLAUDE_CONFIG_FILE" "tableau")

  if [[ "$server_status" == "exists" ]]; then
    echo
    success "Tableau MCP Server is already configured"
    echo
    echo "Current configuration:"
    json_operation get_server_info "$CLAUDE_CONFIG_FILE" "tableau" | sed 's/^/  /'
    echo

    if ask_yn "Do you want to update the Tableau MCP Server configuration?"; then
      update_tableau_config
    elif ask_yn "Do you want to remove the Tableau MCP Server?"; then
      remove_tableau_config
    else
      echo "Keeping existing Tableau configuration."
    fi
  else
    if ask_yn "Do you want to install the Tableau MCP Server for Claude Desktop?" "y"; then
      install_tableau_config
    else
      echo "Skipping Tableau MCP Server installation."
    fi
  fi
}

# Install new Tableau configuration
install_tableau_config() {
  echo
  ohai "Installing Tableau MCP Server"
  echo
  echo "This will connect Claude Desktop to your Tableau instance for data analysis."
  echo "You'll need a Personal Access Token (PAT) from Tableau."
  echo
  echo "Please follow these steps to create your PAT:"
  echo "  1. Go to: https://us-west-2b.online.tableau.com/#/site/cloudsecurityalliance/"
  echo "  2. Login with your CSA credentials"
  echo "  3. Click on your initials (top right corner)"
  echo "  4. Select \"My Account Settings\""
  echo "  5. Scroll down to \"Personal Access Tokens\""
  echo "  6. Click \"Create New Token\""
  echo "  7. Give it a name like \"Claude Desktop\""
  echo "  8. Copy both the token name and the secret value"
  echo

  if ! ask_yn "Ready to continue?"; then
    echo "Installation cancelled."
    return
  fi

  get_tableau_config_and_save
}

# Update existing Tableau configuration
update_tableau_config() {
  echo
  ohai "Updating Tableau MCP Server Configuration"
  echo
  echo "You can update your PAT credentials or change server/site settings."
  echo

  get_tableau_config_and_save
}

# Remove Tableau configuration
remove_tableau_config() {
  echo
  ohai "Removing Tableau MCP Server"

  local result
  result=$(json_operation remove_server "$CLAUDE_CONFIG_FILE" "tableau")

  case "$result" in
    success)
      success "Tableau MCP Server configuration removed"
      ;;
    not_found)
      warn "Tableau MCP Server was not found in configuration"
      ;;
    failed)
      abort "Failed to remove Tableau MCP Server configuration"
      ;;
  esac
}

# Get Tableau configuration from user and save it
get_tableau_config_and_save() {
  echo

  # Get server URL with default
  echo -n "Tableau Server URL [https://us-west-2b.online.tableau.com]: "
  read -r server_url
  server_url="${server_url:-https://us-west-2b.online.tableau.com}"

  # Get site name with default
  echo -n "Site Name [cloudsecurityalliance]: "
  read -r site_name
  site_name="${site_name:-cloudsecurityalliance}"

  # Get PAT credentials securely
  local pat_name pat_value
  echo -n "PAT Token Name: "
  read -r pat_name

  if [[ -z "$pat_name" ]]; then
    abort "PAT Token Name is required"
  fi

  if ! read_secret "PAT Token Value (hidden): " pat_value; then
    abort "PAT Token Value is required"
  fi

  create_and_save_tableau_config "$server_url" "$site_name" "$pat_name" "$pat_value"
  success "Tableau MCP Server configured successfully"
}

# Main function
main() {
  ohai "Cloud Security Alliance - Claude Desktop MCP Server Setup"

  # Preconditions
  [[ "$(uname -s)" == "Darwin" ]] || abort "This script supports macOS only"
  [[ "${EUID:-${UID}}" != "0" ]] || abort "Don't run this script as root"

  check_dependencies
  ensure_config_dir
  init_config_if_needed

  # Validate existing config
  local validation_result
  validation_result=$(json_operation validate "$CLAUDE_CONFIG_FILE")
  case "$validation_result" in
    valid) ;;
    invalid*) abort "Existing config file is invalid JSON: ${validation_result#invalid: }" ;;
    missing) init_config_if_needed ;;
  esac

  # Create backup before making any changes
  backup_config

  # Handle each MCP server one at a time
  handle_tableau

  # Final message
  echo
  success "Configuration saved to: ${CLAUDE_CONFIG_FILE##*/}"
  echo
  ohai "Setup Complete!"
  echo "Restart Claude Desktop to use any new or updated MCP servers."
}

main "$@"