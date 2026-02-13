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

### `archives/`

Previous versions of scripts preserved for reference.

## Updating

```bash
# Update AI tools (Codex, Gemini — Claude auto-updates)
npm update -g

# Update Homebrew-managed tools and apps
brew upgrade
```

## macOS Only (For Now)

We currently support macOS only. Windows support may come later.

## Contributing

Found a problem? Have a suggestion?

[Open an issue](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/new/choose) — we have templates for common requests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
