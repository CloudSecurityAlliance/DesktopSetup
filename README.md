# CSA DesktopSetup

Automated setup for Cloud Security Alliance development environments. Get from a bare Mac to productive in a few commands.

## Quick Start

### Work tools (everyone)

1Password, Slack, Zoom, Chrome, Microsoft Office, Git, GitHub CLI. Optional dev profile adds VS Code, AWS CLI, and Wrangler.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"
```

### AI tools

Claude Code, Codex CLI, Gemini CLI.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```

Both scripts are interactive — they show you what they plan to do and ask for confirmation. Both install the shared base layer (Xcode CLI Tools, Homebrew, Node.js/npm) if not already present. Run either one first, or both.

## What This Repo Contains

### `scripts/`

macOS setup scripts. Each is self-contained and idempotent (safe to re-run):

- **`macos-work-tools.sh`** — Core work apps + optional developer tools
- **`macos-ai-tools.sh`** — AI coding assistants (with migration from Homebrew/npm to recommended install methods)

### `catalog/`

Reference catalog of MCP servers and AI agent skills that CSA projects use. Each entry describes what it does, when a project needs it, and how to install it. The actual skill implementations live in separate repositories — this is the index.

- **`catalog/mcp-servers/`** — MCP server documentation and setup instructions
- **`catalog/skills/`** — AI agent skill references and detection criteria

### `archives/`

Previous versions of scripts preserved for reference.

## Updating

```bash
# Update AI tools (Codex, Gemini — Claude auto-updates)
npm update -g

# Update Homebrew-managed tools and apps
brew upgrade
```

## Per-Project Setup

This repo solves the bootstrap problem — getting your machine ready. But each project also needs its own AI tooling configured (the right MCP servers, the right skills). Rather than installing everything globally, we configure tools per-project so your AI assistant has the right context without noise.

When you open a CSA project, check its README for a **Development Setup** section that lists which MCP servers and skills to install.

## macOS Only (For Now)

We currently support macOS only. Windows support may come later.

## Contributing

Found a problem? Want to add an MCP server or skill to the catalog? Have a suggestion?

[Open an issue](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/new/choose) — we have templates for common requests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
