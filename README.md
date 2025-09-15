# DesktopSetup

Setup of desktop tools and AI support for macOS.

## macOS Install Script

The `macos-install.sh` script installs and updates a standard developer + AI toolchain on macOS:

- Homebrew (installs if missing, otherwise updates)
- pyenv and the latest Python 3.12.x (installs if missing; sets as global if not already on 3.12)
- Node.js (via Homebrew)
- AI CLIs: Claude Code (`claude-code`), Google Gemini (`gemini-cli`), and ChatGPT Codex (`codex`)
  - Tries Homebrew formula first; falls back to global npm package when no formula is available
- 1Password application (via Homebrew cask)

The script is idempotent: re-running it upgrades outdated items and leaves up‑to‑date tools unchanged.

### Run

Run directly with Bash and curl:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/macos-install.sh)"
```

To run without prompts in CI or automation, prefix with `NONINTERACTIVE=1`:

```
NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/macos-install.sh)"
```

On interactive runs, the script prints a summary of actions and prompts for confirmation `[Y/n]` before making changes. In non-interactive mode, it proceeds without prompting.

### Notes

- macOS only; the script aborts on non-macOS systems and when run as root (outside containers).
- If the AI CLIs use different names in your environment, you can override via env vars before running:
  - `CSA_CLAUDE_FORMULA`, `CSA_CLAUDE_NPM`, `CSA_CLAUDE_BIN`
  - `CSA_GEMINI_FORMULA`, `CSA_GEMINI_NPM`, `CSA_GEMINI_BIN`
  - `CSA_CODEX_FORMULA`, `CSA_CODEX_NPM`, `CSA_CODEX_BIN`
- When Homebrew is installed for the first time, PATH is set for the current session in the script. Follow Homebrew’s post‑install guidance if you need to persist PATH changes in your shell profile.
