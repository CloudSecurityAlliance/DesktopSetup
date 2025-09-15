# DesktopSetup

Setup of desktop tools and AI support for macOS.

## macOS Install Script

The `macos-install.sh` script installs and updates a standard developer + AI toolchain on macOS:

- Homebrew (installs if missing, otherwise updates)
- pyenv and the latest Python 3.12.x (installs if missing; sets as global if not already on 3.12)
- Node.js (via Homebrew)
- AI CLIs: Claude Code (`claude-code` cask), Google Gemini (`gemini-cli`), and ChatGPT Codex (`codex`)
  - Installed strictly via Homebrew (formula or cask). If a package is not available in Homebrew, the script aborts so it can be fixed rather than silently falling back.
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
The summary is a preflight plan that shows, per tool, whether it will be installed, upgraded (Homebrew‑managed), or skipped if already present (non‑Homebrew).

### Notes

- macOS only; the script aborts on non-macOS systems and when run as root (outside containers).
- If the AI CLIs use different names in your environment, you can override via env vars before running (Homebrew-only):
  - `CSA_CLAUDE_FORMULA`, `CSA_CLAUDE_BIN` (default formula: `claude-code`, bin: `claude`)
  - `CSA_GEMINI_FORMULA`, `CSA_GEMINI_BIN` (default formula: `gemini-cli`, bin: `gemini`)
  - `CSA_CODEX_FORMULA`, `CSA_CODEX_BIN` (default formula: `codex`, bin: `codex`)
  - Note: There is no npm fallback; ensure the Homebrew formula/cask names are valid or add a tap.
- When Homebrew is installed for the first time, PATH is set for the current session in the script. Follow Homebrew’s post‑install guidance if you need to persist PATH changes in your shell profile.
