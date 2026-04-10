# MCP Server Configuration Reference

This document covers how to configure MCP servers for the three AI coding CLIs: Claude Code, Codex CLI, and Gemini CLI. It is the research basis for `macos-mcp-setup.sh`.

## How each tool handles MCP

| Tool | Add command | Config file | Scope flag |
|---|---|---|---|
| Claude Code | `claude mcp add --transport http <name> <url> --header "..."` | Managed internally | `--scope user` (global) or default (project) |
| Codex CLI | `codex mcp add <name> --url <url>` | `~/.codex/config.toml` | Global only |
| Gemini CLI | `gemini mcp add --transport http <name> <url> --header "..."` | `~/.gemini/settings.json` | `-s user` (global) or default (project) |

**Key Codex limitation:** `codex mcp add --url` only accepts `--bearer-token-env-var ENV_VAR_NAME` (the name of an env var, not the token value). Inline tokens require editing `~/.codex/config.toml` directly using the `http_headers` key.

**Gemini env var expansion:** Gemini expands `$VAR` and `${VAR}` in header values in `settings.json`, so tokens can reference shell env vars rather than being inlined.

Official MCP docs per tool:
- Claude Code: https://code.claude.com/docs/en/mcp
- Codex CLI: https://developers.openai.com/codex/mcp
- Gemini CLI: https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html

---

## Airtable

**Hosted MCP URL:** `https://mcp.airtable.com/mcp`  
**Maintained by:** Airtable  
**Auth:** Personal Access Token (PAT)  
**Get token:** https://airtable.com/account/security → Personal Access Tokens → Create token  
**Official docs:** https://support.airtable.com/docs/using-the-airtable-mcp-server  
**Claude connector page:** https://claude.com/connectors/airtable  

### Claude Code

```bash
claude mcp add --transport http airtable https://mcp.airtable.com/mcp \
  --header "Authorization: Bearer YOUR_AIRTABLE_PAT" \
  --scope user
```

### Codex CLI

No clean CLI path — token cannot be inlined via `codex mcp add`. Write directly to `~/.codex/config.toml`:

```toml
[mcp_servers.airtable]
url = "https://mcp.airtable.com/mcp"
http_headers = { "Authorization" = "Bearer YOUR_AIRTABLE_PAT" }
enabled = true
```

### Gemini CLI

```bash
gemini mcp add --transport http \
  --header "Authorization: Bearer YOUR_AIRTABLE_PAT" \
  -s user \
  airtable https://mcp.airtable.com/mcp
```

Or manually in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "airtable": {
      "httpUrl": "https://mcp.airtable.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_AIRTABLE_PAT"
      }
    }
  }
}
```

---

## GitHub

**Hosted MCP URL:** `https://api.githubcopilot.com/mcp`  
**Maintained by:** GitHub (Microsoft)  
**Auth:** GitHub Personal Access Token (PAT) — auto-fetchable via `gh auth token`  
**Get token:** Run `gh auth token` if already authenticated, or https://github.com/settings/tokens  
**Official docs:** https://github.com/github/github-mcp-server  
**Installation guides:** https://github.com/github/github-mcp-server/tree/main/docs/installation-guides  
**Claude Code guide:** https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-claude.md  
**Codex guide:** https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-codex.md  
**Gemini guide:** https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-gemini-cli.md  

> **Note:** The old `@modelcontextprotocol/server-github` npm package was deprecated April 2025. Use the hosted URL above.

### Claude Code

```bash
claude mcp add --transport http github https://api.githubcopilot.com/mcp \
  --header "Authorization: Bearer $(gh auth token)" \
  --scope user
```

### Codex CLI

Via CLI (token read from env var at runtime):

```bash
codex mcp add github --url https://api.githubcopilot.com/mcp/ \
  --bearer-token-env-var GITHUB_PAT_TOKEN
```

Also requires the env var to be set in `~/.zprofile`:

```bash
export GITHUB_PAT_TOKEN="$(gh auth token)"
```

Or write directly to `~/.codex/config.toml` with the token inlined:

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
http_headers = { "Authorization" = "Bearer YOUR_GITHUB_PAT" }
enabled = true
```

### Gemini CLI

```bash
gemini mcp add --transport http \
  --header "Authorization: Bearer $(gh auth token)" \
  -s user \
  github https://api.githubcopilot.com/mcp/
```

Or manually in `~/.gemini/settings.json` (using env var expansion):

```json
{
  "mcpServers": {
    "github": {
      "httpUrl": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer $GITHUB_PAT_TOKEN"
      }
    }
  }
}
```

---

## Slack

**Hosted MCP URL:** `https://mcp.slack.com/mcp`  
**Maintained by:** Slack (Salesforce)  
**Auth:** OAuth 2.0 — requires a registered Slack app (internal or directory-published)  
**Official docs:** https://docs.slack.dev/ai/slack-mcp-server/  
**Help article:** https://slack.com/help/articles/48855576908307-Guide-to-the-Slack-MCP-server  
**Claude connector page:** https://claude.com/connectors/slack  
**Announced:** February 2026  

> **Status: Not included in v1 of `macos-mcp-setup.sh`**
>
> Slack's MCP server requires:
> 1. A registered Slack app at https://api.slack.com/apps (internal or directory-published — unlisted apps not allowed)
> 2. OAuth 2.0 flow with `client_id` + `client_secret`
> 3. User tokens (not bot tokens) via `https://slack.com/oauth/v2_user/authorize`
>
> This is not scriptable in the same way as Airtable and GitHub. Options for a future version:
> - CSA creates a single shared internal Slack app and distributes `client_id`/`client_secret` to users
> - Script prompts for credentials and opens the OAuth flow in a browser, then captures the resulting user token

> **Note:** The old `@modelcontextprotocol/server-slack` npm package was archived May 2025. Do not use it.

---

## Gmail (Claude Code only)

**Server:** `workspace-mcp` — community package by taylorwilsdon covering Gmail, Drive, Calendar, Docs, Sheets, and more  
**Transport:** Runs locally on `http://localhost:8000`, Claude Code connects via HTTP  
**Auth:** Google OAuth 2.0 — requires a Google Cloud project with OAuth credentials  
**Package:** `workspace-mcp` (via `uvx`, no global install needed)  
**Source:** https://github.com/taylorwilsdon/google_workspace_mcp  
**Docs:** https://workspacemcp.com/quick-start  

> **Claude Code only.** Codex and Gemini do not have an equivalent path at this time.  
> No hosted MCP URL exists for Gmail — Google's Cloud MCP program excludes Workspace apps.  
> The `@modelcontextprotocol/server-gdrive` npm package was archived May 2025. Do not use it.

### Prerequisites

- Python 3.10+ (`python3 --version` to check — installed by `macos-ai-tools.sh`)
- `uv` / `uvx` package manager:
  ```bash
  brew install uv
  ```

### Step 1 — Create a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Click the project dropdown → **New Project** → give it a name (e.g. `csa-workspace-mcp`) → **Create**
3. Make sure the new project is selected in the dropdown

### Step 2 — Enable the Gmail API (and any other services you want)

1. Go to **APIs & Services → Library**
2. Search for and enable each API you want:
   - **Gmail API** — for email read/search/draft/send
   - **Google Drive API** — for file access
   - **Google Calendar API** — for calendar events
   - **Google Docs API**, **Google Sheets API** — if needed

### Step 3 — Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. If prompted to configure the consent screen: choose **External**, fill in app name (e.g. `workspace-mcp`), add your Google account as a test user, save
4. Application type: **Web application**
5. Under **Authorized redirect URIs**, add: `http://localhost:8000/oauth2callback`
6. Click **Create** — copy the **Client ID** and **Client Secret**

### Step 4 — Set environment variables

Add to `~/.zprofile` (persists across sessions):

```bash
export GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_OAUTH_CLIENT_SECRET="your-client-secret"
```

Then reload:

```bash
source ~/.zprofile
```

### Step 5 — Start the server

```bash
uvx workspace-mcp --transport streamable-http
```

The server starts on `http://localhost:8000`. **It must be running for Claude Code to use Gmail.**

To run it in the background (so it persists after closing the terminal):

```bash
uvx workspace-mcp --transport streamable-http &
```

Or add a macOS Launch Agent for auto-start on login — see the Launch Agent section below.

### Step 6 — Register with Claude Code

In a new terminal (while the server is running):

```bash
claude mcp add --transport http workspace-mcp http://localhost:8000/mcp --scope user
```

### Step 7 — Authenticate with Google

1. Start Claude Code: `claude`
2. Run `/mcp` inside the session
3. Select `workspace-mcp` → follow the browser OAuth flow
4. Grant the requested Gmail (and any other) scopes
5. Tokens are cached — you won't need to re-authenticate unless you revoke access

### Verify it works

Inside a Claude Code session:

```
Search my Gmail for unread emails from the last 7 days
```

### Optional: auto-start with macOS Launch Agent

To have the server start automatically at login, create `~/Library/LaunchAgents/com.csa.workspace-mcp.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.csa.workspace-mcp</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-c</string>
    <string>uvx workspace-mcp --transport streamable-http</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>GOOGLE_OAUTH_CLIENT_ID</key>
    <string>YOUR_CLIENT_ID</string>
    <key>GOOGLE_OAUTH_CLIENT_SECRET</key>
    <string>YOUR_CLIENT_SECRET</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/workspace-mcp.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/workspace-mcp-error.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.csa.workspace-mcp.plist
```

---

## Script requirements summary

What `macos-mcp-setup.sh` needs to handle:

| Requirement | Detail |
|---|---|
| Check tool is installed | Skip configuration if `claude`, `codex`, or `gemini` not found |
| Check if already configured | Run `claude mcp list`, `codex mcp list`, `gemini mcp list` and skip or offer update |
| Prompt for tokens securely | Read without echo for PATs |
| GitHub token auto-fetch | Use `gh auth token` if `gh` is installed and authenticated; fall back to manual prompt |
| Claude Code: use CLI | `claude mcp add --transport http --header ... --scope user` |
| Codex: edit TOML | No clean CLI path for inline tokens — use Python or a TOML-aware tool to write `~/.codex/config.toml` |
| Gemini: use CLI | `gemini mcp add --transport http --header ... -s user` |
| Config backups | Back up `~/.codex/config.toml` and `~/.gemini/settings.json` before editing |
| Idempotent | Safe to re-run — detect existing entries and offer to skip or update |
| Gmail | Manual-only — script prints setup instructions and links, does not automate OAuth or GCP project creation |
