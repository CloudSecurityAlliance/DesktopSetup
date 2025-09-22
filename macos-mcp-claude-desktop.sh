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
  local missing=()

  if ! command -v python3 >/dev/null 2>&1; then
    missing+=("python3")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing required dependencies: ${missing[*]}"
    echo "Please install them first:"
    for dep in "${missing[@]}"; do
      case "$dep" in
        python3) echo "  Install Python 3 via: brew install python3" ;;
      esac
    done
    exit 1
  fi
}

# Validate and manipulate JSON using Python
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

# Read user input securely
read_secret() {
  local prompt="$1"
  local var_name="$2"
  local value=""

  echo -n "$prompt"
  read -rs value
  echo

  if [[ -z "$value" ]]; then
    warn "Empty value provided"
    return 1
  fi

  declare -g "$var_name=$value"
}

# Simple menu that works reliably on macOS bash
show_server_menu() {
  echo
  ohai "Cloud Security Alliance - Claude Desktop MCP Server Setup"
  echo
  echo "Available MCP Servers:"
  echo "  1) Tableau - Business Intelligence and Analytics"
  echo
  echo -n "Select server to configure [1]: "
  read -r selection
  selection="${selection:-1}"

  case "$selection" in
    1)
      echo "tableau"
      ;;
    *)
      abort "Invalid selection: $selection"
      ;;
  esac
}

# Show Tableau setup instructions
show_tableau_instructions() {
  echo
  echo "You selected: Tableau"
  echo
  ohai "Setting up Tableau MCP Server"
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
}

# Check if Tableau is already configured and handle existing config
handle_existing_tableau_config() {
  local server_status
  server_status=$(json_operation check_server "$CLAUDE_CONFIG_FILE" "tableau")

  if [[ "$server_status" == "exists" ]]; then
    echo
    success "Tableau MCP Server is already configured"
    echo
    echo "Current configuration:"
    json_operation get_server_info "$CLAUDE_CONFIG_FILE" "tableau" | sed 's/^/  /'
    echo
    echo "What would you like to do?"
    echo "  1) Keep existing configuration (do nothing)"
    echo "  2) Update PAT token only (rotate credentials)"
    echo "  3) Reconfigure completely (change server/site/credentials)"
    echo
    echo -n "Choose an option [1-3]: "
    read -r choice

    case "$choice" in
      1|"")
        echo "Keeping existing configuration."
        return 1  # Skip configuration
        ;;
      2)
        update_tableau_pat_only
        return 1  # Skip full configuration
        ;;
      3)
        echo "Proceeding with full reconfiguration..."
        return 0  # Continue with full configuration
        ;;
      *)
        abort "Invalid choice: $choice"
        ;;
    esac
  fi

  return 0  # Continue with configuration (not already configured)
}

# Update only PAT credentials for existing Tableau config
update_tableau_pat_only() {
  echo
  ohai "Updating Tableau PAT Credentials"
  echo
  echo "Please create a new PAT token following the same steps as before:"
  echo "  1. Go to: https://us-west-2b.online.tableau.com/#/site/cloudsecurityalliance/"
  echo "  2. Login with your CSA credentials"
  echo "  3. Click on your initials (top right corner)"
  echo "  4. Select \"My Account Settings\""
  echo "  5. Scroll down to \"Personal Access Tokens\""
  echo "  6. Click \"Create New Token\" (or update existing)"
  echo "  7. Give it a name like \"Claude Desktop\""
  echo "  8. Copy both the token name and the secret value"
  echo
  echo -n "Ready to update PAT credentials? [Y/n] "
  read -r ready
  case "${ready:-Y}" in
    [Yy]*) ;;
    [Nn]*) echo "PAT update cancelled."; return ;;
    *) ;;
  esac

  echo

  # Get current config to preserve server and site
  local current_info
  current_info=$(json_operation get_server_info "$CLAUDE_CONFIG_FILE" "tableau")
  local current_server current_site
  current_server=$(echo "$current_info" | grep "Server:" | cut -d' ' -f2-)
  current_site=$(echo "$current_info" | grep "Site:" | cut -d' ' -f2-)

  # Get new PAT credentials
  local pat_name pat_value
  echo -n "New PAT Token Name: "
  read -r pat_name

  if [[ -z "$pat_name" ]]; then
    abort "PAT Token Name is required"
  fi

  if ! read_secret "New PAT Token Value (hidden): " pat_value; then
    abort "PAT Token Value is required"
  fi

  # Create updated config with existing server/site but new PAT
  create_and_save_tableau_config "$current_server" "$current_site" "$pat_name" "$pat_value"
  success "Tableau PAT credentials updated successfully"
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

# Configure Tableau MCP Server
configure_tableau() {
  # Check if already configured and handle accordingly
  if ! handle_existing_tableau_config; then
    return 0  # Configuration was handled (kept existing, updated PAT, etc.)
  fi

  show_tableau_instructions

  echo -n "Ready to continue? [Y/n] "
  read -r ready
  case "${ready:-Y}" in
    [Yy]*) ;;
    [Nn]*) abort "Setup cancelled by user" ;;
    *) ;;
  esac

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
  ohai "Starting Claude Desktop MCP Server Configuration"

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

  # Show menu and get selection
  local selected_server
  selected_server=$(show_server_menu)

  # Create backup before making changes
  backup_config

  # Configure selected server
  case "$selected_server" in
    tableau)
      configure_tableau
      ;;
    *)
      abort "Unknown server: $selected_server"
      ;;
  esac

  # Final success message
  echo
  success "Configuration saved to: ${CLAUDE_CONFIG_FILE##*/}"
  echo
  ohai "Setup Complete!"
  echo "Restart Claude Desktop to use the new MCP server."
}

main "$@"