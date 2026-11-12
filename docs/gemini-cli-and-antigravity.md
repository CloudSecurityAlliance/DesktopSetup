# Gemini CLI and Antigravity CLI: who can use which, and what DesktopSetup should install

Researched 2026-11-12 for [#171](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/171),
which blocks [#167](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/167). An
independent check of every claim followed the same day, and its corrections are applied here.
**No script has changed.** The recommendation below is the AI's; the four decisions at the end
are the CINO's.

**Every claim carries one of four labels:**

| Label | Means |
|---|---|
| **measured** | Run once on one Mac (Apple Silicon, macOS Darwin 27.2) on 2026-11-12, in a throwaway `HOME`, signed out, stdin closed. The commands are in the [measurement log](#measurement-log). |
| **reproduced** | Measured, then seen again independently: a second run on a different `agy` build the same day, or the same result reported in this repo's issues or Google's bug tracker. |
| **vendor docs** | Google's own page, repository or install script, or a package registry or manifest entry. The source number points into [Sources](#sources). |
| **inferred** | Reasoned from the above, and not confirmed. No decision should rest on an inferred row alone. |

**What could not be measured.** No Windows machine and no CSA Workspace sign-in were available.
Every Windows behaviour and every sign-in outcome below is vendor docs or inferred.

## The answer in brief

- **Gemini CLI stopped serving personal Google accounts on 2026-06-18**, free and Google AI Pro or
  Ultra alike. It still serves Gemini Code Assist Standard and Enterprise licences and paid API
  keys. Whether a CSA Workspace account without a licence is refused is not stated by Google.
- **Antigravity CLI (`agy`) is the successor.** It installs, registers MCP servers and installs
  CSA's plugins without signing in or prompting. Updating it headless works.
- **Recommendation:** install `agy` with Google's own install script on both OSes and verify its
  code signature afterwards; update it with `agy update`; stop installing Gemini CLI on new
  machines and keep existing installs current.
- **But not before the CINO decides how CSA staff sign in to it** (Decision 1). Until then the
  easiest path for a refused Workspace user, which Google's own FAQ suggests, is a personal
  account under consumer terms, where Google employees and contractors may review what is sent.

## What decides it

### Who can still sign in to Gemini CLI

| Account or method | Gemini CLI today | Evidence |
|---|---|---|
| Personal Google account, free ("Gemini Code Assist for individuals") | **No**, since 2026-06-18. Refused with: "This client is no longer supported for Gemini Code Assist for individuals. To continue using Gemini, please migrate to the Antigravity suite of products" | vendor docs [S1][S2]; reproduced: #167 (2026-10-26) and gemini-cli #29279 on 0.59.0 [S24] |
| Personal account with Google AI Pro or Ultra | **No**, the same refusal, since 2026-06-18 | vendor docs [S1]; reproduced: gemini-cli #28229 on 0.49.0, open [S24] |
| Gemini Code Assist **Standard or Enterprise** licence (Google Cloud project) | **Yes**: "your access remains unchanged", and Google keeps updating Gemini CLI for these customers | vendor docs [S1][S2] |
| **Paid** Gemini API key, or a Gemini Enterprise Agent Platform API key | **Yes**. The blog's words: "paid Gemini and Gemini Enterprise Agent Platform API keys" | vendor docs [S1] |
| Vertex AI through Application Default Credentials, with no API key | **Not stated.** The blog names API keys only | vendor docs are silent |
| Free-tier Gemini API key | **Not stated** | vendor docs are silent |
| **CSA Workspace account without a Code Assist licence** | **Not stated by Google. Expected to be refused.** Gemini CLI's own docs route Workspace sign-in through a Google Cloud project with Code Assist [S16], and Google Cloud's admin page (updated 2026-11-10) puts a Workspace user's free access under "Code Assist for individuals" [S17], the tier that was cut off | inferred |

Also about Gemini CLI:

- **It is maintained:** `@google/gemini-cli` 0.68.0 was published on 2026-11-10 (vendor docs [S21]).
- **Its own sign-in guide is stale.** Last changed 2026-09-18, it still recommends "Sign in with
  Google" to individuals and never mentions the cut-off (vendor docs [S16]).
- **Homebrew deprecated the `gemini-cli` formula** from 2026-06-18 and disables it on
  2026-12-18, naming the cask `antigravity-cli` as its replacement (vendor docs [S19]).
  DesktopSetup already moves a Homebrew `gemini-cli` to npm (`migrate_gemini`), so nothing breaks.
- It is not installed on the measurement Mac, so none of this was re-tested here.

### What Antigravity CLI is

- **Google's terminal agent, command `agy`**, announced 2026-05-19 as Gemini CLI's successor for
  consumer tiers. It keeps Agent Skills, Hooks, Subagents, and extensions (as "plugins"), with no
  1:1 parity (vendor docs [S1]).
- **Closed source.** The GitHub repository holds only the README, CHANGELOG, examples and release
  binaries (vendor docs [S13]).
- **Released about daily:** 1.4.1 on 2026-10-17 to 1.5.7 on 2026-11-12 (vendor docs [S13]).
- **Code-signed by Google, Team ID `EQHXZ8M8AV`.** Reproduced: 1.5.7 (downloaded), 1.4.12 (the
  local install) and 1.4.11 (inside Gemini.app).
- **It reads `AGENTS.md` and `GEMINI.md`** (vendor docs [S3][S8]), which fits CINO-Engineering
  DEC-033.

Where it keeps things (vendor docs; the MCP path also reproduced):

| What | Path |
|---|---|
| Binary, macOS | `~/.local/bin/agy` [S5] |
| Binary, Windows | `%LOCALAPPDATA%\agy\bin\agy.exe` [S5] |
| CLI settings | `~/.gemini/antigravity-cli/settings.json` [S7], a different file from Gemini CLI's `~/.gemini/settings.json` |
| User MCP servers | `~/.gemini/config/mcp_config.json` [S4] |
| Personal customizations | `~/.gemini/config/` (`skills/`, `plugins/`, `rules/`, `hooks.json`) [S8] |
| Updater state | `~/.gemini/antigravity-cli/updater/` [S6] |
| Sign-in token | the OS keyring: Keychain item "Antigravity CLI", Windows Credential Manager [S5][S6] |

### Where it can come from

**The vendor manifest, the Homebrew cask and the winget manifest ship the same file.** All three
name `storage.googleapis.com/antigravity-public/antigravity-cli/1.5.7-…`
(vendor docs [S15][S18][S20]).

| Channel | What it is | Evidence |
|---|---|---|
| **Google's install script** | macOS: `curl -fsSL https://antigravity.google/cli/install.sh \| bash`, to `~/.local/bin/agy`. Windows: `irm https://antigravity.google/cli/install.ps1 \| iex`, to `%LOCALAPPDATA%\agy\bin\agy.exe`. Updated by `agy`'s own updater | vendor docs [S5][S13][S14] |
| Homebrew cask `antigravity-cli` | 1.5.7, `auto_updates true`; `bin/agy` is a symlink into the Caskroom; `zap` trashes `~/.gemini/antigravity-cli` | vendor docs [S18] |
| winget `Google.AntigravityCLI` | 1.5.7, `InstallerType: portable`, Google's bucket, pinned by SHA-256. **The manifest is community-generated** (its header: "Created with YamlCreate.ps1 Dumplings Mod"); "Publisher: Google" is the manifest's own metadata, not a signature | vendor docs [S20], header read 2026-11-12 |
| Gemini.app helper | `/Applications/Gemini.app/Contents/Helpers/agy` is Antigravity CLI **1.4.11** and runs outside the bundle, but moves only when Gemini.app updates: Gemini.app was current (1.141.3.1394) while the standalone channel was at 1.5.7 | reproduced (version, and running a copy); Gemini.app's own version measured |
| Gemini Desktop for Windows | **ships no `agy`.** The 1.19.0 **x64** installer has no `agy.exe` or `antigravity` string; arm64 was not checked. Google's desktop page lists the Antigravity launcher for macOS only | measured; vendor docs [S23][S25] |
| GitHub release assets | `agy_cli_mac_{arm64,x64}.tar.gz`, `agy_cli_windows_{x64,arm64}.zip`; nothing updates them | vendor docs [S13] |
| **npm: impostors only** | There is **no `@google` package.** `antigravity-cli` (0.0.1, described "Antigravity CLI - placeholder", its binary named `kirox`), `agy` (0.0.0) and `antigravity` (0.0.0) are all published by unrelated individuals. **Never install `agy` from npm** | vendor docs [S22], registry queried 2026-11-12 |

**What the install scripts do** (vendor docs [S14], script read, unless marked):

- Fetch the vendor manifest (version, URL, SHA-512), download the binary and check it against
  that SHA-512. **This catches a corrupted download, not a compromised source:** the hash and the
  binary both come from Google's servers in the same run, so whoever could change one could change
  the other. Authenticity comes from the code signature (Decision 2).
- Clear macOS quarantine, or `Unblock-File` on Windows, then run `agy install`. That appends
  `export PATH="…/.local/bin:$PATH"` to **every existing** shell profile: `.zshrc`, `.zprofile`,
  `.bashrc` and `.bash_profile` in the test. It never prompts and exits 0 (measured).
- **No sudo and no prompt** on macOS (measured). Re-running finds the binary and exits 0 with no
  change.
- **macOS cannot skip the PATH edit.** The docs say `--skip-path` can be appended [S5], but
  `install.sh` as served on 2026-11-12 rejects it: `[ERROR] Unknown parameter: --skip-path`, exit 1
  (measured). `install.ps1` does pass extra flags to `agy install`.
- It overlaps DesktopSetup harmlessly: the macOS script already puts `~/.local/bin` on PATH for
  Claude Code, so the profiles get duplicate lines.

### How it stays current

- **`agy update` runs headless.** With stdin closed it printed "Update successful! Please restart
  agy", exited 0, and took a copy from 1.4.12 to 1.5.7. It replaces the binary at its own path and
  leaves the old one beside it as `agy.<number>.old`, the same rename-the-running-image pattern as
  Claude Code's `claude.exe.old.*` (measured; the independent check confirmed it).
- **The background updater runs only while `agy` runs.** It uses a 15-minute debounce marker and a
  lock in `~/.gemini/antigravity-cli/updater/`, and `AGY_CLI_DISABLE_AUTO_UPDATE=true` turns it off
  (vendor docs [S6]). Evidence that it needs use: the local install was put at 1.4.12 on
  2026-10-30, last checked on 2026-11-03 ("Already on the latest version"), and was still 1.4.12 on
  2026-11-12 after eight releases (reproduced). Like Claude Desktop's in-app updater, it keeps a
  machine current only if the tool is used.
- **The updater and a package manager both want to own the file.** In a simulated cask layout
  (`bin/agy` a symlink to `Caskroom/…/1.4.11/antigravity`), `agy update` replaced the symlink with
  a regular 1.5.7 file, renamed the symlink `agy.<n>.old`, and left the Caskroom copy at 1.4.11
  (measured once; the independent check could not confirm it). Real Homebrew and winget were not
  tested. Under them that would leave a binary the package manager did not put there and a stale
  receipt (inferred).

### MCP servers

- **`agy mcp add|remove|list|enable|disable` exists** since 1.1.16, 2026-08-20 (vendor docs
  [S13]). None needs sign-in (measured for `list`, `add`, `disable` and `remove` on 1.5.7;
  `list` and `add` reproduced on 1.4.12).
- **It writes `~/.gemini/config/mcp_config.json`** as `{"mcpServers": {name: {command, args, env}
  | {serverUrl, headers}, disabled}}`, and an empty env value is kept as `""` (reproduced; a URL
  becoming `serverUrl` measured). Remote servers must use Streamable HTTP (vendor docs [S4]).
- **`agy mcp add` silently overwrites an entry of the same name.** A second add of `csa-test` with
  different env replaced the first entry whole, losing its env, with no warning and exit 0
  (reproduced on 1.5.7 and 1.4.12). So any registration must check first.
- **Flags go before the name**; a flag after it is rejected. There is no `agy mcp get`;
  `agy mcp remove nosuch` exits 1 (measured).
- **`agy mcp list` shows only `mcp_config.json`.** Servers bundled in plugins, such as the secid
  plugin's, do not appear (measured).
- **#155's folder trust probably does not apply to user-level servers.** `agy mcp list` reports
  them `enabled`, with no trust caveat (measured). The docs tie workspace trust to indexing and
  workspace `.agents/` customizations [S5][S7]. What happens in a signed-in session in an
  untrusted folder is untested (inferred).

### Skills and plugins

- **`agy plugin install https://github.com/CloudSecurityAlliance/csa-plugins-official` installs all
  8 CSA plugins, signed out**, exit 0, keeping the secid plugin's MCP server
  (reproduced on 1.5.7 and 1.4.12; the command is vendor docs [S11]). The
  `…/tree/main/plugins/<name>` form installs one (measured).
- **A Claude marketplace name is refused:** `cwe-analysis@csa-plugins-official` gives
  `unknown marketplace`, exit 1 (reproduced).
- **`~/.agents/skills/`, the folder Codex and Gemini CLI share, is not documented as read.** The
  docs list `~/.gemini/config/skills/`, `~/.gemini/antigravity-cli/skills/` and `~/.gemini/skills/`
  for personal skills, and a project's `.agents/skills/` for workspace skills. A personal
  `skills.json` manifest can point anywhere (vendor docs [S8], by omission; not tested).
- Whether the installed skills load at run time needs a signed-in session: task 5 of #172.

### Machines that already have Gemini CLI

- **`agy mcp` neither reads nor changes Gemini CLI's `~/.gemini/settings.json`.** With a server in
  that file, `agy mcp list` said "No MCP servers configured.", and the file was byte-identical
  after `agy mcp add` (reproduced on 1.5.7 and 1.4.12).
- **`agy plugin import gemini` converts only `~/.gemini/extensions/`**: "No gemini extensions
  found." (measured; vendor docs [S3]). CSA ships no Gemini extensions, so the CSA servers that
  `gemini mcp add --scope user` wrote do not carry over. They must be registered with `agy`
  separately.
- `agy`'s first interactive launch offers to convert "global configurations" [S3]; whether that
  includes those servers is untested.

## What would hurt CSA staff

1. **Consumer terms become the default path.** Google's FAQ tells a Workspace user who is refused
   to "Contact your Workspace administrator to request access, or sign in with a personal Google
   Account instead" [S9]. Under the consumer terms, "Google employees and contractors may access,
   view, review and use Interactions. Please don't submit confidential information or any data you
   wouldn't want a reviewer to see" [S12]. Shipping `agy` before Decision 1 makes that the easy
   path for every refused CSA user (vendor docs, quotes re-read 2026-11-12).
2. **Impostor packages.** Three npm names a person might guess (`agy`, `antigravity`,
   `antigravity-cli`) belong to third parties, and Google publishes none (vendor docs [S22]). The
   scripts and docs must name only Google's install script.
3. **Lost MCP registrations.** Because `agy mcp add` overwrites, a registration that treats a
   failed `agy mcp list` as "not there" would replace a working entry. The sketch below adds only
   when the list succeeded.
4. **A piped install with no authenticity check.** The script's SHA-512 is not one (above).
   Checking the code signature after install and after each `agy update` is (Decision 2).

## Recommendation for #167 (AI-written)

**Sequencing.** Decision 1 gates #167. If #167 must ship first, the installer prints one line
whenever it installs `agy`: personal Google sign-in is under consumer terms, so use no CSA data
with it.

**Install route, both OSes: Google's install script**, then a signature check.

- **macOS:** `install.sh`, run only when `~/.local/bin/agy` is absent. Then require
  `codesign --verify --strict` to pass and `codesign -dv` to report `TeamIdentifier=EQHXZ8M8AV`.
- **Windows:** `install.ps1`, downloaded to a file and run with `powershell -File`, so its exit
  code counts (under `iex` it throws instead; vendor docs [S14], script read). Then require
  `Get-AuthenticodeSignature` to be `Valid` with a Google signer. **Whether `agy.exe` carries an
  Authenticode signature has not been checked**; that is the first Windows measurement to make.
- **Why:** it is the vendor's build where the vendor's updater expects it, the rule in
  [`desktop-ai-apps.md`](desktop-ai-apps.md); it is the same model as Claude Code's native
  installer; and both platforms take the same route, which `check-parity.py` wants.
- **What it costs:** a piped remote script; duplicate PATH lines in up to four macOS shell
  profiles, which cannot be turned off; no package-manager receipt.
- **Rejected: the Homebrew cask and winget.** The package manager and `agy`'s updater both claim
  the file. `brew upgrade` without `--greedy` skips `auto_updates` casks, so Homebrew would never
  update it anyway, and the winget manifest is community-generated.
- **Rejected: npm.** Impostors only.
- **Rejected: the Gemini.app helper.** It lags the standalone channel, is macOS-only (Apple
  Silicon, macOS 15+), and lives inside a signed bundle its updater should not write to.

**Updates.**

- `macos-update.sh` and `windows-update.ps1` run `agy update` when `agy` is present, as they run
  `claude update`, then repeat the signature check.
- Report the installed version against the vendor manifest (`…/manifests/<platform>.json`), as
  `desktop-ai-apps.md` advises: compare against the vendor's feed.
- On Windows, recognise `agy` by **path**, never by process name, because the updater leaves
  `agy.<n>.old`-style files (AGENTS.md's Windows trap; inferred from the macOS rename).

**MCP registration** (CloudSecurityAlliance-Internal/CSA-Plugins, `register_other_clients` in its
four `.sh` and four `.ps1` setup scripts, kept identical by `check-duplication.py` [S26]). Keep the
Gemini branch where `gemini` is present, and add an `agy` branch. A sketch, not tested:

```bash
  # ---- Antigravity CLI (agy) ----
  if has_command agy; then
    # `agy mcp add` overwrites silently, so add ONLY when the list succeeded and the exact
    # name is absent. A failed list must never fall through to an add.
    if csa_run "agy mcp list" agy mcp list; then
      if ! awk -v n="$name" 'NR>1 && $1==n {f=1} END {exit !f}' <<<"${CSA_OUT:-}"; then
        local aflags=() q
        for q in "$@"; do aflags+=(-e "$q"); done          # flags BEFORE <name>
        csa_run "agy mcp add" agy mcp add ${aflags[@]+"${aflags[@]}"} "$name" "$bin" \
          || warn "  agy mcp add failed; Antigravity will not see ${name}"
      fi
    else
      warn "  agy mcp list failed; ${name} not registered with Antigravity, nothing changed"
    fi
  fi
```

- Match the NAME column exactly. The Gemini branch's `grep -qF "$name"` also matches a longer name
  that contains `$name`, which here would skip a needed add (inferred).
- There is no `--scope` to get wrong: `agy mcp` always writes the user-level file.
- DesktopSetup's own hosted `csa-mcp` registration is Claude Code-only;
  [#176](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/176) owns widening it.

**Skills and plugins.** csa-plugins-official's README can document
`agy plugin install https://github.com/CloudSecurityAlliance/csa-plugins-official`. Its existing
copy-into-`~/.gemini/antigravity-cli/skills/` method also still matches the docs.

**Machines already set up.** Leave `~/.gemini/settings.json` alone. Don't run
`agy plugin import gemini`. Register the CSA servers with `agy` directly.

**Gemini CLI:** Decision 3, option (b).

**Docs #167 should change:** AGENTS.md (the Gemini rows and the "which clients get CSA tooling"
trap), README.md, ENGINEERING.md's AI-layer row, `docs/mcp-servers.md` (an `agy` section), and
`docs/desktop-ai-apps.md` (the Gemini.app `agy` is Antigravity CLI 1.4.11, lags, and is not used).

**An ADR in `DECISIONS-ADR.md`** should record "vendor install script over cask and winget". It
departs from how the four desktop apps are installed.

## Decisions for the CINO, one at a time (AI-written)

Ordered by the 2026-11-09 goal order: safety and privacy first.

### Decision 1: how CSA staff sign in to `agy`, and under which terms

- **Context.** A Workspace account signs in only after a Workspace admin provisions Antigravity
  [S9]. Google Cloud documents an Admin console control, "Allow access to Code Assist for
  individuals" [S17]; that it is the one the FAQ means is inferred. The terms differ by sign-in:
  - personal sign-in: consumer terms, with human review of Interactions [S12];
  - "a Google Workspace subscription on the Google Cloud Pre-GA Offering Terms", Gemini Enterprise
    or a business API key: the administrator's terms instead [S12]. Whether CSA's Workspace
    qualifies is unknown;
  - a Business account (Google Cloud): Google Cloud terms, and CLI telemetry "always off for
    business accounts" [S7][S10].
- **Options:** (a) turn on the Workspace toggle; (b) Gemini Enterprise or a Google Cloud project
  (Business account); (c) personal accounts only, with no CSA data; (d) Gemini API keys.
- **Recommendation: (b) for anyone handling CSA data**, (a) only after confirming which terms
  then apply. **#167 waits for this**, or ships with the one-line warning above.
- **Why it needs the CINO:** spend and data policy outside the repo, and only an admin can see the
  console.
- **What would let the AI decide next time:** a recorded CSA policy on which Google sign-ins are
  approved for CSA data.

### Decision 2: accept a piped install of a closed-source, daily-released, self-updating binary

- **Context.** This is a security call, not only an ADR. Every CSA machine would run a script
  fetched at install time, and then a binary that replaces itself about daily with code no one at
  CSA can read. The script's SHA-512 gives integrity, not authenticity.
- **Options:** (a) accept, with a code-signature check after install and after each `agy update`
  (Team ID `EQHXZ8M8AV` on macOS, Authenticode on Windows); (b) accept as is; (c) don't install
  `agy`, and let staff install it themselves.
- **Recommendation: (a).** It turns "trust the download" into "trust Google's signing key", the
  same trust already given to Gemini.app.
- **Why it needs the CINO:** it is risk acceptance for every machine the installers touch.
- **What would let the AI decide next time:** a standing rule for vendor self-updating binaries,
  for example "allowed if code-signed by the vendor and verified after every install or update".

### Decision 3: keep or drop Gemini CLI

- **Context.** CINO-Engineering DEC-032's supported list (amended 2026-11-06) names the Gemini
  desktop app, Antigravity (`agy`) and Gemini on the web for Google, and leaves Gemini CLI out.
  Gemini CLI now serves only Code Assist Standard or Enterprise licences and paid API keys.
- **Options:** (a) keep installing and updating it everywhere; (b) stop installing it, keep
  updating existing installs; (c) uninstall it.
- **Recommendation: (b)**, or (a) if Decision 1 finds a CSA Code Assist licence. When `gemini` is
  present, print one line: personal Google sign-in no longer works with it; use `agy`. Removing a
  tool someone may run with a paid key costs more than leaving it.
- **Why it needs the CINO:** it depends on the licence facts and changes the supported-tools list.
- **What would let the AI decide next time:** DEC-032 saying explicitly whether Gemini CLI is
  supported.

### Decision 4: the Antigravity desktop App

- **Context.** Homebrew cask `antigravity` (2.31.2) and winget `Google.Antigravity` exist (vendor
  docs). DEC-032 does not list the App.
- **Recommendation: don't install it** for now; revisit if DEC-032 adds it.
- **Why it needs the CINO:** it would add a fifth desktop app to every machine.
- **What would let the AI decide next time:** DEC-032 listing it, or not.

## Not verified

- **Any sign-in result:** a CSA Workspace account on `agy` or on Gemini CLI, and which admin
  control provisions `agy`. Needs one signed-in run on a Mac (#119 holds the Mac test list).
- **Every Windows behaviour:** `install.ps1` under Windows PowerShell 5.1, whether it edits the
  user PATH, whether `agy.exe` is Authenticode-signed, `agy update` while `agy.exe` runs, and the
  winget portable install against the updater. These can join #161 or #163.
- **Real Homebrew,** rather than a simulated cask layout.
- **Folder trust at run time** (#155) for user-level MCP servers.
- **The first interactive launch** over an existing Gemini profile.
- **The `.old` files:** whether `agy` ever removes the `agy.<n>.old` files it leaves.
- **Doc drift.** Google's pages disagree in places: Google Cloud's page still lists Gemini CLI
  under "Code Assist for individuals" [S17], against the blog [S1]; `install.sh` rejects flags the
  Authenticate page documents [S5]; Gemini CLI's auth doc predates the cut-off [S16]. This note
  prefers the dated announcement and what was measured.

## Measurement log

One Mac, Apple Silicon, 2026-11-12 UTC. Every `agy` run used
`env -i PATH=/usr/bin:/bin HOME=<mktemp> TERM=dumb AGY_CLI_DISABLE_AUTO_UPDATE=true timeout N … </dev/null`,
on a copy of the binary. Nothing that needs sign-in was run, and no model was called. The real
`~/.local/bin/agy`, `Gemini.app` and `~/.gemini` were hashed before and after, and were unchanged.

| What | Run 1 (research, 1.5.7 unless noted) | Run 2 (while writing this note, 1.4.12 and 1.4.11) |
|---|---|---|
| Versions and signing | helper: `Identifier=agy`, Team `EQHXZ8M8AV`, 198,595,680 bytes, **1.4.11**; local install **1.4.12**; downloaded 1.5.7 matched the manifest's SHA-512, Team `EQHXZ8M8AV` | the same versions and Team ID |
| `agy mcp list` / `add` / `add` again | empty list; add writes `mcp_config.json`; a second add replaces the entry and its env | the same |
| Gemini's `settings.json` | its server not listed; file byte-identical; `plugin import gemini`: "No gemini extensions found." | not listed; byte-identical |
| `agy plugin install <repo URL>` | exit 0, 8 plugins; `…@csa-plugins-official` → `unknown marketplace` | exit 0, 8 plugins; `unknown marketplace`, exit 1 |
| `agy update` | a copy of 1.4.12 became 1.5.7, exit 0, `agy.<n>.old` beside it | not re-run |
| Cask-like symlink | `bin/agy update` turned the symlink into a regular 1.5.7 file | not re-run |
| `agy install` | PATH line appended to four empty profiles; no prompt; exit 0 | not re-run |
| `bash install.sh --skip-path` | `[ERROR] Unknown parameter: --skip-path`, exit 1 | not re-run |
| Windows Gemini Desktop 1.19.0 x64 | winget's installer (SHA-256 matched the manifest), searched in ASCII and UTF-16LE: no `agy.exe`, `antigravity` or `*_mcp_server` | not re-run |
| npm and winget | — | `npm view` of `agy`, `antigravity`, `antigravity-cli`, and three `@google/…` names (all 404); winget manifest header read |

Scratch binaries, homes and the downloaded installer were deleted afterwards.

## Sources

| # | Source | Date |
|---|---|---|
| S1 | Google Developers Blog, "An important update: Transitioning Gemini CLI to Antigravity CLI": https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/ | 2026-05-19; re-read 2026-11-12 |
| S2 | gemini-cli discussion #27274, a Google product manager's post: https://github.com/google-gemini/gemini-cli/discussions/27274 (community comments not relied on) | 2026-05-19, updated 2026-10-09 |
| S3 | Antigravity docs, Migrating from Gemini CLI: https://antigravity.google/docs/cli/gcli-migration | fetched 2026-11-12 |
| S4 | Antigravity docs, MCP: https://antigravity.google/docs/mcp | fetched 2026-11-12 |
| S5 | Antigravity docs, Get started and Authenticate: https://antigravity.google/docs/getting-started, https://antigravity.google/docs/install | fetched 2026-11-12 |
| S6 | Antigravity docs, CLI troubleshooting: https://antigravity.google/docs/cli/troubleshooting | re-read 2026-11-12 |
| S7 | Antigravity docs, CLI reference and Settings: https://antigravity.google/docs/cli/reference, https://antigravity.google/docs/settings | fetched 2026-11-12 |
| S8 | Antigravity docs, Customization discovery: https://antigravity.google/docs/customization-discovery | re-read 2026-11-12 |
| S9 | Antigravity docs, FAQ: https://antigravity.google/docs/faq | re-read 2026-11-12 |
| S10 | Antigravity docs, Enterprise and Plans: https://antigravity.google/docs/enterprise, https://antigravity.google/docs/plans | fetched 2026-11-12 |
| S11 | Antigravity docs, Plugins and Marketplace: https://antigravity.google/docs/plugins, https://antigravity.google/docs/marketplace | fetched 2026-11-12 |
| S12 | Antigravity Terms: https://antigravity.google/terms | re-read 2026-11-12 |
| S13 | google-antigravity/antigravity-cli README, CHANGELOG and releases: https://github.com/google-antigravity/antigravity-cli | 1.1.16 (2026-08-20) to 1.5.7 (2026-11-12) |
| S14 | Install scripts: https://antigravity.google/cli/install.sh, https://antigravity.google/cli/install.ps1 | read 2026-11-12 |
| S15 | Vendor update manifest: https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/darwin_arm64.json (and `windows_amd64.json`) | 1.5.7, fetched 2026-11-12 |
| S16 | Gemini CLI authentication doc: https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.mdx | last commit 2026-09-18 |
| S17 | Google Cloud, "Control access to Gemini Code Assist for individuals": https://docs.cloud.google.com/gemini/docs/codeassist/control-individuals-access | updated 2026-11-10 |
| S18 | Homebrew cask `antigravity-cli`: https://formulae.brew.sh/cask/antigravity-cli | 1.5.7, 2026-11-12 |
| S19 | Homebrew formula `gemini-cli`: https://formulae.brew.sh/formula/gemini-cli | deprecated 2026-06-18; disabled 2026-12-18 |
| S20 | winget `Google.AntigravityCLI`: https://github.com/microsoft/winget-pkgs/tree/master/manifests/g/Google/AntigravityCLI | 1.5.7, 2026-11-12 |
| S21 | npm `@google/gemini-cli`: https://www.npmjs.com/package/@google/gemini-cli | 0.68.0, 2026-11-10 |
| S22 | npm `antigravity-cli`, `agy`, `antigravity`: https://www.npmjs.com/package/antigravity-cli and the same path for each | queried 2026-11-12 |
| S23 | Gemini desktop page: https://gemini.google/desktop/ | fetched 2026-11-12 |
| S24 | gemini-cli issues #28229 (2026-07-01, open), #28846 (2026-08-16), #29279 (2026-09-10): https://github.com/google-gemini/gemini-cli/issues/28229 | as dated |
| S25 | winget `Google.GeminiDesktop` 1.19.0: https://github.com/microsoft/winget-pkgs/tree/master/manifests/g/Google/GeminiDesktop | 2026-11-04 |
| S26 | Internal: CSA-Plugins `internal-setup/csa-*-setup.{sh,ps1}` (`register_other_clients`); CINO-Engineering `DECISIONS.md` DEC-032 (2026-11-06 amendment) and DEC-033 | read 2026-11-12 |
