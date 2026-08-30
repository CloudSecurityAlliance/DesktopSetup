# TODO — Code Audit Findings

Audit performed 2026-02-24. Issues grouped by priority.

---

## Critical

- [x] **C1 — Claude Code re-installs on every run** (`macos-ai-tools.sh:286–287`)
  Added `has_command claude` guard to skip the installer when already installed and no migration is needed.

- [ ] **C2 — Word-splitting in pip upgrade loop** (`macos-update.sh:274`)
  `for pkg in $pkg_names` — unquoted variable is split on whitespace. Blank lines in the Python JSON output silently pass empty/malformed strings to `pip install --upgrade`. Replace with `mapfile -t pkg_names < <(...)` and iterate with `"${pkg_names[@]}"`.

---

## High

- [ ] **H1 — `pgrep -x claude` may not detect running Claude Code** (`macos-ai-tools.sh:63`)
  Needs verification on macOS: if the native installer puts a real binary at `~/.local/bin/claude`, `-x` works fine. If it runs as a Node.js process, the process name would be `node` and the check misses it. If broken, fix is `pgrep -f "\.local/bin/claude"`.
  To verify: start a `claude` session, then in another terminal run `ps aux | grep claude` and check the process name in column 11 (the COMMAND column). If it shows `node` rather than `claude`, apply the fix.

- [ ] **H2 — Missing `has_command brew` guard in Git plan display** (`macos-work-tools.sh:166`)
  On a fresh machine, `brew list --formula git` is called before Homebrew is installed, causing the plan to show "upgrade to Homebrew version" instead of "install via Homebrew". Add `has_command brew &&` to the condition.

- [ ] **H3 — Preflight shows outdated packages from stale Homebrew index** (`macos-update.sh:168–169`)
  `brew outdated` runs in `preflight()` before `brew update`, so the plan shown to the user may not match what actually gets upgraded. Run `brew update` before the preflight display, or add a note that the list is cache-based.

- [ ] **H4 — Codex cask migration detection is dead code** (`macos-ai-tools.sh:127–128`)
  No Homebrew cask named `codex` exists for the OpenAI Codex CLI. `brew list --cask codex` never matches, so migration never fires. Also missing: a `brew list --formula codex` check for a formula install.

- [ ] **H5 — `.zshrc` PATH modification not idempotent** (`macos-ai-tools.sh:291–294`)
  Exact-string grep `'export PATH="$HOME/.local/bin:$PATH"'` misses quoting variants, causing a duplicate `export PATH=` line to be appended on every re-run. Change to `grep -qF '.local/bin'`.

---

## Medium

- [x] **M1 — Uses `python` instead of `python3`** (`macos-update.sh:270`, `macos-update.sh:128,144`)
  macOS 12.3+ removed the `python` shim. If the user only has `python3`/`pip3`, JSON parsing silently fails (`|| true`) and all pip upgrades are skipped with no warning. Try `python3` first, fall back to `python`.

- [x] **M2 — Wrong banner text in `macos-ai-tools.sh`** (`macos-ai-tools.sh:375`)
  Banner reads "macOS Development Setup" — should be "macOS AI Tools Setup" to match the script header comment on line 2. Copy-paste error.

- [x] **M3 — `brew upgrade node` runs unconditionally** (both install scripts, ~line 268)
  Prints "Upgrading Node.js" even when Node is already current. Minor UX issue; `brew upgrade` on a current package just warns and exits cleanly.

---

## Security Audit Findings

Audit performed 2026-02-24.

### Critical (Security)

- **SEC-C1 — `curl | bash` for Claude Code installer** (`macos-ai-tools.sh:286`) — WONT FIX
  Following the official Claude Code install pattern. Same trust model as the Homebrew installer.

- **SEC-C2 — Homebrew installer fetched from `HEAD` with no integrity check** (`macos-work-tools.sh:258`, `macos-ai-tools.sh:261`) — DOCUMENTED CONCERN
  Using the official command from https://brew.sh/. Risk acknowledged: a compromise of the Homebrew GitHub repo or GitHub's raw CDN would affect all machines running this script. Keep `main` branch reviewed and avoid merging untested code.

### High (Security)

- **SEC-H1 — `eval "$(brew shellenv)"` trusts output of an unverified binary** (all three scripts, `ensure_brew_in_path`) — WONT FIX
  If a local binary has been replaced, the machine is already fully compromised.

- **SEC-H2 — `~/.local/bin` prepended to PATH before directory integrity is verified** (`macos-ai-tools.sh:290–294`) — WONT FIX
  If a malicious binary is already in the user's home directory, the machine is already compromised.

### Medium (Security)

- **SEC-M1 — Bootstrap commands fetch from `HEAD`** (all three script headers) — DOCUMENTED CONCERN
  Following the same pattern as the official Homebrew docs. Keep `HEAD` in sync with tested/reviewed commits; avoid merging untested code to `main`.

- **SEC-M2 — Root check bypassable via `/.dockerenv` file** (all three scripts, ~line 51) — WONT FIX
  Creating `/.dockerenv` requires root — if an attacker has root, the machine is already compromised.

- **SEC-M3 — Snapshot log files are world-readable** (`macos-update.sh:86–150`) — DOCUMENTED CONCERN
  macOS home directory permissions protect these files on a standard single-user machine. Only a concern on shared multi-user systems, which is not the target environment.
