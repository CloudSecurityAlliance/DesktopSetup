# Default plugin install — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install a curated default set of Claude Code plugins on every CSA machine that runs the AI tools installer (and keep them aligned on updater runs), driven by two shared plain-text list files.

**Architecture:** Two list files (`scripts/csa-plugins.txt` public, `scripts/csa-plugins-internal.txt` CSA-access-probed) are the single source of truth for plugin names and their marketplaces. Each of the three scripts (`macos-ai-tools.sh`, `windows-ai-tools.ps1`, `macos-update.sh`) gains an `install_plugins` / `Install-Plugins` function that curl/irm-fetches both lists, registers any missing marketplaces, then installs any missing plugins — silent on skip, loud on install or error.

**Tech Stack:** Bash (with `curl`, `sed`, `grep`, `gh`, `claude` CLI). PowerShell 5.1 (with `Invoke-RestMethod`, `claude` CLI, existing `Invoke-NativeQuiet` / `Invoke-NativeCapture` helpers). No new dependencies.

**Dependency:** This plan assumes PR #11 (fix/marketplace-add-stderr) has merged to `main` — the new install code reuses its stderr-capture pattern and the `Invoke-NativeCapture` PowerShell helper introduced there. Rebase `feat/default-plugin-install` on `origin/main` before starting Task 1.

---

## File structure

**Create:**
- `scripts/csa-plugins.txt` — public plugin list, 29 entries, fetched at runtime.
- `scripts/csa-plugins-internal.txt` — CSA-internal plugin list, 11 entries, access-probed.

**Modify:**
- `scripts/macos-ai-tools.sh` — add `PLUGIN_MARKETPLACE_REPOS` map, `install_plugins` function, wire into `main()` and `preflight()`, bump `SCRIPT_VERSION`.
- `scripts/windows-ai-tools.ps1` — add `$PluginMarketplaceRepos` map, `Install-Plugins` function, wire into `main` flow and plan display, bump `$ScriptVersion`.
- `scripts/macos-update.sh` — add `PLUGIN_MARKETPLACE_REPOS` map, `install_plugins` function, wire into the update flow, bump `SCRIPT_VERSION`.
- `README.md` — add **Plugins installed** section with five groups.
- `CLAUDE.md` — add **Plugin install contract** subsection under "Conventions", extend the **Shared boilerplate** paragraph to reference the two list files.

Plugin list parser duplicates across all three scripts (matching the existing `CSA_MARKETPLACES` duplication pattern). KEEP-IN-SYNC comment blocks on both the list files and the parser function.

---

## Task 1: Create the public plugin list file

**Files:**
- Create: `scripts/csa-plugins.txt`

- [ ] **Step 1: Write the file**

```text
# CSA default plugin list — public marketplaces.
# One plugin per line in <plugin>@<marketplace> form. Blank lines and
# lines starting with # are ignored.
#
# Read by the install_plugins / Install-Plugins functions in:
#   scripts/macos-ai-tools.sh
#   scripts/windows-ai-tools.ps1
#   scripts/macos-update.sh
#
# These entries are public — no access probe; always installed.

agent-sdk-dev@claude-plugins-official
chrome-devtools-mcp@claude-plugins-official
claude-code-setup@claude-plugins-official
claude-md-management@claude-plugins-official
cloudflare@claude-plugins-official
code-review@claude-plugins-official
commit-commands@claude-plugins-official
explanatory-output-style@claude-plugins-official
feature-dev@claude-plugins-official
frontend-design@claude-plugins-official
github@claude-plugins-official
greptile@claude-plugins-official
learning-output-style@claude-plugins-official
mcp-server-dev@claude-plugins-official
playground@claude-plugins-official
playwright@claude-plugins-official
plugin-dev@claude-plugins-official
pr-review-toolkit@claude-plugins-official
pydantic-ai@claude-plugins-official
security-guidance@claude-plugins-official
semgrep@claude-plugins-official
session-report@claude-plugins-official
skill-creator@claude-plugins-official
slack@claude-plugins-official
superpowers@claude-plugins-official
typescript-lsp@claude-plugins-official

claude-api@anthropic-agent-skills
document-skills@anthropic-agent-skills
example-skills@anthropic-agent-skills
```

- [ ] **Step 2: Verify line count matches spec (29 non-blank non-comment lines)**

Run:
```bash
grep -cv -E '^\s*(#|$)' scripts/csa-plugins.txt
```
Expected: `29`

- [ ] **Step 3: Commit**

```bash
git add scripts/csa-plugins.txt
git commit -m "feat(plugins): add public plugin list (29 entries)"
```

---

## Task 2: Create the CSA-internal plugin list file

**Files:**
- Create: `scripts/csa-plugins-internal.txt`

- [ ] **Step 1: Write the file**

```text
# CSA default plugin list — private CSA marketplaces.
# Each entry's marketplace is gh-probed before install; marketplaces the
# user's GitHub account can't access are silently skipped along with all
# their plugins. External users of the public DesktopSetup repo see
# zero chatter about these.
#
# Read by the install_plugins / Install-Plugins functions in:
#   scripts/macos-ai-tools.sh
#   scripts/windows-ai-tools.ps1
#   scripts/macos-update.sh

cwe-analysis@csa-plugins-official
incident-analysis@csa-plugins-official
nist-ir-8477-mapping@csa-plugins-official
security-knowledge-ingestion@csa-plugins-official

cino-project-tracker@csa-cino-plugins

audience-lens@csa-research-plugins
research-initiative-tracker@csa-research-plugins
writing-style-forge@csa-research-plugins

csa-certification-development@csa-training-plugins
csa-training-content-development@csa-training-plugins
csa-training-design-system@csa-training-plugins
```

- [ ] **Step 2: Verify line count (11 non-blank non-comment lines)**

Run:
```bash
grep -cv -E '^\s*(#|$)' scripts/csa-plugins-internal.txt
```
Expected: `11`

- [ ] **Step 3: Commit**

```bash
git add scripts/csa-plugins-internal.txt
git commit -m "feat(plugins): add CSA-internal plugin list (11 entries)"
```

---

## Task 3: Add marketplace-repo map to `macos-ai-tools.sh`

The new `install_plugins` function needs to translate a marketplace **name** (as it appears in the list files) into the underlying GitHub **repo** (for the `gh api` access probe on CSA marketplaces, and for `claude plugin marketplace add` when not already registered). The existing `CSA_MARKETPLACES` array only stores repo paths — no name mapping. Add a single-source-of-truth map covering every marketplace referenced by either list file.

**Files:**
- Modify: `scripts/macos-ai-tools.sh` — add the map immediately below the `CSA_MARKETPLACES` array declaration (around line 46).

- [ ] **Step 1: Insert the map after `CSA_MARKETPLACES`**

Edit the block right after the closing `)` of `CSA_MARKETPLACES`, inserting:

```bash
# Marketplace name → GitHub repo. Maps every marketplace referenced by
# scripts/csa-plugins.txt and scripts/csa-plugins-internal.txt. Used by
# install_plugins() to register missing marketplaces and (for CSA
# marketplaces) gh-probe access.
#
# Keys prefixed with `csa-` or matching `accounting-plugins` are
# treated as CSA-internal: gh-probed before register, silent-skip on
# access denial. All other keys are public: register unconditionally.
#
# KEEP IN SYNC: duplicated as PLUGIN_MARKETPLACE_REPOS in
#   scripts/macos-update.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-ai-tools.ps1
declare -A PLUGIN_MARKETPLACE_REPOS=(
  # Public
  [claude-plugins-official]="anthropics/claude-plugins-official"
  [anthropic-agent-skills]="anthropics/skills"
  # CSA-internal
  [accounting-plugins]="CloudSecurityAlliance-Internal/Accounting-Plugins"
  [csa-cino-plugins]="CloudSecurityAlliance-Internal/CINO-Plugins"
  [csa-plugins]="CloudSecurityAlliance-Internal/CSA-Plugins"
  [csa-research-plugins]="CloudSecurityAlliance-Internal/Research-Plugins"
  [csa-training-plugins]="CloudSecurityAlliance-Internal/Training-Plugins"
  [csa-plugins-official]="CloudSecurityAlliance/csa-plugins-official"
)
```

- [ ] **Step 2: Syntax check**

Run:
```bash
bash -n scripts/macos-ai-tools.sh
```
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add scripts/macos-ai-tools.sh
git commit -m "refactor(macos-ai-tools): add PLUGIN_MARKETPLACE_REPOS name→repo map"
```

---

## Task 4: Add `install_plugins` function to `macos-ai-tools.sh`

The function fetches both list files from HEAD, parses them, ensures the referenced marketplaces are registered (silently skipping inaccessible CSA ones), then installs any plugins that aren't already installed. Silent on skip, one-line success on install, warn-with-stderr on error (same pattern as PR #11's marketplace-add fix).

**Files:**
- Modify: `scripts/macos-ai-tools.sh` — add function immediately after the existing `setup_plugin_marketplaces()` function.

- [ ] **Step 1: Insert the function**

Add this block right after `setup_plugin_marketplaces()` (so it lives in the same "Plugin marketplaces" section):

```bash
# ── Plugin install ──────────────────────────────────────────────────
# Fetch the public and internal plugin list files from HEAD, register
# any missing marketplaces (CSA marketplaces are gh-probed first),
# then install plugins that aren't yet installed. Silent-by-default:
# already-installed entries and inaccessible CSA marketplaces produce
# no output. Only actual installs and install errors print.

PLUGIN_LIST_URL_PUBLIC="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins.txt"
PLUGIN_LIST_URL_INTERNAL="https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins-internal.txt"

# Return "csa" if the marketplace should be gh-probed, "public" otherwise.
plugin_marketplace_kind() {
  case "$1" in
    claude-plugins-official|anthropic-agent-skills) echo public ;;
    *) echo csa ;;
  esac
}

# Read a plugin list (via stdin), strip blanks/comments, emit one
# <plugin>@<marketplace> entry per line.
plugin_list_entries() {
  grep -v -E '^\s*(#|$)'
}

install_plugins() {
  has_command claude || return 0
  has_command curl || return 0

  local public_list internal_list
  public_list="$(curl -fsSL -H 'Cache-Control: no-cache' "$PLUGIN_LIST_URL_PUBLIC" 2>/dev/null || true)"
  internal_list="$(curl -fsSL -H 'Cache-Control: no-cache' "$PLUGIN_LIST_URL_INTERNAL" 2>/dev/null || true)"

  if [[ -z "$public_list" && -z "$internal_list" ]]; then
    return 0
  fi

  # Snapshot already-registered marketplaces and already-installed plugins.
  local registered_repos installed_plugins
  registered_repos="$(claude plugin marketplace list 2>/dev/null \
    | sed -n 's/.*GitHub (\([^)]*\)).*/\1/p')"
  installed_plugins="$(claude plugin list 2>/dev/null \
    | sed -n 's/^\s*❯\s*\(.*\)$/\1/p')"

  local gh_authed=0
  if has_command gh && gh auth status >/dev/null 2>&1; then gh_authed=1; fi

  local added=() installed=() failed=() failed_errs=()
  local add_err inst_err

  # Track which marketplaces we've processed so we don't re-probe.
  declare -A seen_markets=()
  declare -A market_usable=()   # [name]=1 if we should install from it

  # Pass 1: ensure each referenced marketplace is registered.
  local line name market repo kind
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    name="${line%@*}"
    market="${line#*@}"

    if [[ -n "${seen_markets[$market]:-}" ]]; then continue; fi
    seen_markets[$market]=1

    repo="${PLUGIN_MARKETPLACE_REPOS[$market]:-}"
    if [[ -z "$repo" ]]; then
      # Unknown marketplace — not in our map. Skip silently; this
      # shouldn't happen if list files are kept in sync with the map.
      continue
    fi

    kind="$(plugin_marketplace_kind "$market")"

    # Already registered — mark as usable, move on.
    if grep -qxF "$repo" <<< "$registered_repos"; then
      market_usable[$market]=1
      continue
    fi

    # For CSA marketplaces: require gh + authed + accessible.
    if [[ "$kind" == csa ]]; then
      [[ $gh_authed -eq 1 ]] || continue
      gh api "repos/$repo" >/dev/null 2>&1 || continue
    fi

    # Register the marketplace.
    if add_err="$(claude plugin marketplace add "$repo" 2>&1 >/dev/null)"; then
      added+=("$repo")
      market_usable[$market]=1
    else
      failed+=("marketplace $repo")
      failed_errs+=("${add_err:-<no stderr output>}")
    fi
  done < <(printf '%s\n%s\n' "$public_list" "$internal_list" | plugin_list_entries)

  # Pass 2: install each plugin whose marketplace is usable and that
  # isn't already installed.
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    name="${line%@*}"
    market="${line#*@}"

    [[ -n "${market_usable[$market]:-}" ]] || continue
    grep -qxF "${name}@${market}" <<< "$installed_plugins" && continue

    if inst_err="$(claude plugin install "${name}@${market}" 2>&1 >/dev/null)"; then
      installed+=("${name}@${market}")
    else
      failed+=("plugin ${name}@${market}")
      failed_errs+=("${inst_err:-<no stderr output>}")
    fi
  done < <(printf '%s\n%s\n' "$public_list" "$internal_list" | plugin_list_entries)

  if [[ ${#added[@]} -gt 0 ]]; then
    success "Registered plugin marketplaces:"
    printf '  + %s\n' "${added[@]}"
  fi
  if [[ ${#installed[@]} -gt 0 ]]; then
    success "Installed plugins:"
    printf '  + %s\n' "${installed[@]}"
  fi
  if [[ ${#failed[@]} -gt 0 ]]; then
    warn "Failed on ${#failed[@]} item(s):"
    local i
    for i in "${!failed[@]}"; do
      printf '  ! %s\n      %s\n' "${failed[$i]}" "${failed_errs[$i]}"
    done
  fi
}
```

- [ ] **Step 2: Syntax check and shellcheck**

Run:
```bash
bash -n scripts/macos-ai-tools.sh && echo OK
shellcheck scripts/macos-ai-tools.sh 2>&1 | grep -E 'install_plugins|plugin_list_entries|plugin_marketplace_kind' || echo "no new findings"
```
Expected: `OK`, then `no new findings` (pre-existing SC2016/SC2059 are outside this function).

- [ ] **Step 3: Smoke test the parser**

Run (standalone in a terminal, copy-paste the parser helper):
```bash
printf '# comment\n\nfoo@bar\nbaz@qux\n\n#another\n' | grep -v -E '^\s*(#|$)'
```
Expected output:
```
foo@bar
baz@qux
```

- [ ] **Step 4: Commit**

```bash
git add scripts/macos-ai-tools.sh
git commit -m "feat(macos-ai-tools): add install_plugins fetching csa-plugins*.txt"
```

---

## Task 5: Wire `install_plugins` into `macos-ai-tools.sh` flow

**Files:**
- Modify: `scripts/macos-ai-tools.sh` — call the new function from `main()`, add a plan line in `preflight()`, bump `SCRIPT_VERSION`.

- [ ] **Step 1: Bump version**

Find the line `SCRIPT_VERSION="2026.04212115"` (near line 25). Replace with today's timestamp, e.g.:

```bash
SCRIPT_VERSION="2026.04222100"
```

- [ ] **Step 2: Add preflight plan line**

In `preflight()`, find the line that displays the marketplaces probe (look for `Plugin marketplaces  probe ${#CSA_MARKETPLACES[@]} CSA repos`). Immediately after it, add:

```bash
  echo "  Plugins              install defaults from csa-plugins.txt (+ csa-plugins-internal.txt if accessible)"
```

- [ ] **Step 3: Call install_plugins from main**

Find the `main()` function. After the line that calls `setup_plugin_marketplaces`, add:

```bash
  install_plugins
```

- [ ] **Step 4: Syntax check**

Run:
```bash
bash -n scripts/macos-ai-tools.sh && echo OK
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/macos-ai-tools.sh
git commit -m "feat(macos-ai-tools): wire install_plugins into main and preflight"
```

---

## Task 6: Add `PLUGIN_MARKETPLACE_REPOS` map and `install_plugins` to `macos-update.sh`

**Files:**
- Modify: `scripts/macos-update.sh` — same map and same function as in `macos-ai-tools.sh`, plus bump `SCRIPT_VERSION`.

- [ ] **Step 1: Insert the map after `CSA_MARKETPLACES`**

Same content as Task 3, but with a KEEP-IN-SYNC comment that references the other two files instead of this one. Insert after the `CSA_MARKETPLACES` closing `)` (around line 40):

```bash
# Marketplace name → GitHub repo. See the matching block in
# scripts/macos-ai-tools.sh for the full rationale.
#
# KEEP IN SYNC: duplicated as PLUGIN_MARKETPLACE_REPOS in
#   scripts/macos-ai-tools.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-ai-tools.ps1
declare -A PLUGIN_MARKETPLACE_REPOS=(
  [claude-plugins-official]="anthropics/claude-plugins-official"
  [anthropic-agent-skills]="anthropics/skills"
  [accounting-plugins]="CloudSecurityAlliance-Internal/Accounting-Plugins"
  [csa-cino-plugins]="CloudSecurityAlliance-Internal/CINO-Plugins"
  [csa-plugins]="CloudSecurityAlliance-Internal/CSA-Plugins"
  [csa-research-plugins]="CloudSecurityAlliance-Internal/Research-Plugins"
  [csa-training-plugins]="CloudSecurityAlliance-Internal/Training-Plugins"
  [csa-plugins-official]="CloudSecurityAlliance/csa-plugins-official"
)
```

- [ ] **Step 2: Insert the `install_plugins` function**

Add the identical function from Task 4 Step 1 into `macos-update.sh`, immediately after the existing `sync_plugin_marketplaces()` function. The function body is the same; the only difference is context (the updater may be called repeatedly over time, so plugin-list drift is expected behavior, not a migration).

Copy the entire block from Task 4 Step 1 (starting at `PLUGIN_LIST_URL_PUBLIC=...` through the closing `}` of `install_plugins`) and paste it.

- [ ] **Step 3: Call `install_plugins` from the update flow**

Find the `main()` function near the bottom of `macos-update.sh`. After the call to `sync_plugin_marketplaces`, add:

```bash
  install_plugins
```

- [ ] **Step 4: Bump version**

Change:
```bash
SCRIPT_VERSION="2026.04212115"
```
to today's timestamp:
```bash
SCRIPT_VERSION="2026.04222100"
```

- [ ] **Step 5: Syntax check and shellcheck**

Run:
```bash
bash -n scripts/macos-update.sh && echo OK
shellcheck scripts/macos-update.sh 2>&1 | grep -E 'install_plugins|plugin_list_entries|plugin_marketplace_kind' || echo "no new findings"
```
Expected: `OK`, then `no new findings`.

- [ ] **Step 6: Commit**

```bash
git add scripts/macos-update.sh
git commit -m "feat(macos-update): sync default plugins alongside marketplaces"
```

---

## Task 7: Add PowerShell map + `Install-Plugins` to `windows-ai-tools.ps1`

**Files:**
- Modify: `scripts/windows-ai-tools.ps1` — add the hashtable, the function, wire into the main flow, add a plan line, bump `$ScriptVersion`.

- [ ] **Step 1: Insert the hashtable after `$CSA_MARKETPLACES`**

Find the closing `)` of `$CSA_MARKETPLACES` (around line 42). Insert immediately after:

```powershell
# Marketplace name -> GitHub repo. See the matching block in
# scripts/macos-ai-tools.sh for the full rationale.
#
# KEEP IN SYNC: duplicated as PLUGIN_MARKETPLACE_REPOS in
#   scripts/macos-ai-tools.sh
#   scripts/macos-update.sh
$PluginMarketplaceRepos = @{
    'claude-plugins-official'  = 'anthropics/claude-plugins-official'
    'anthropic-agent-skills'   = 'anthropics/skills'
    'accounting-plugins'       = 'CloudSecurityAlliance-Internal/Accounting-Plugins'
    'csa-cino-plugins'         = 'CloudSecurityAlliance-Internal/CINO-Plugins'
    'csa-plugins'              = 'CloudSecurityAlliance-Internal/CSA-Plugins'
    'csa-research-plugins'     = 'CloudSecurityAlliance-Internal/Research-Plugins'
    'csa-training-plugins'     = 'CloudSecurityAlliance-Internal/Training-Plugins'
    'csa-plugins-official'     = 'CloudSecurityAlliance/csa-plugins-official'
}
```

- [ ] **Step 2: Insert the `Install-Plugins` function**

Immediately after the existing `Setup-PluginMarketplaces` function, add:

```powershell
# ── Plugin install ──────────────────────────────────────────────────
# Fetch the public and internal plugin list files from HEAD, register
# any missing marketplaces (CSA ones are gh-probed first), then
# install plugins that aren't yet installed. Silent on skip, loud on
# actual install or error. Mirrors install_plugins() in the bash
# scripts.

$PluginListUrlPublic   = 'https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins.txt'
$PluginListUrlInternal = 'https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins-internal.txt'

function Get-PluginMarketplaceKind {
    param([string]$Name)
    if ($Name -eq 'claude-plugins-official' -or $Name -eq 'anthropic-agent-skills') {
        return 'public'
    }
    return 'csa'
}

function Get-PluginListEntries {
    param([string]$Text)
    if (-not $Text) { return @() }
    return $Text -split "`r?`n" | Where-Object {
        $_ -and ($_ -notmatch '^\s*(#|$)')
    }
}

function Install-Plugins {
    if (-not (Has-Command claude)) { return }

    try {
        $publicList   = Invoke-RestMethod -Uri $PluginListUrlPublic   -Headers @{ 'Cache-Control' = 'no-cache' } -ErrorAction Stop
    } catch { $publicList = '' }
    try {
        $internalList = Invoke-RestMethod -Uri $PluginListUrlInternal -Headers @{ 'Cache-Control' = 'no-cache' } -ErrorAction Stop
    } catch { $internalList = '' }

    if (-not $publicList -and -not $internalList) { return }

    # Already-registered marketplaces and already-installed plugins.
    $registeredRepos = @()
    $listing = claude plugin marketplace list 2>$null
    foreach ($line in $listing) {
        if ($line -match 'GitHub \(([^)]+)\)') { $registeredRepos += $matches[1] }
    }
    $installedPlugins = @()
    $pluginListing = claude plugin list 2>$null
    foreach ($line in $pluginListing) {
        if ($line -match '^\s*❯\s*(.*)$') { $installedPlugins += $matches[1].Trim() }
    }

    $ghAuthed = (Has-Command gh) -and ((Invoke-NativeQuiet { gh auth status }) -eq 0)

    $added = @()
    $installed = @()
    $failed = @()

    $allEntries = @()
    $allEntries += Get-PluginListEntries $publicList
    $allEntries += Get-PluginListEntries $internalList

    $seenMarkets   = @{}
    $marketUsable  = @{}

    # Pass 1: ensure each referenced marketplace is registered.
    foreach ($entry in $allEntries) {
        $parts = $entry -split '@', 2
        if ($parts.Count -ne 2) { continue }
        $market = $parts[1]

        if ($seenMarkets.ContainsKey($market)) { continue }
        $seenMarkets[$market] = $true

        $repo = $PluginMarketplaceRepos[$market]
        if (-not $repo) { continue }

        if ($registeredRepos -contains $repo) {
            $marketUsable[$market] = $true
            continue
        }

        if ((Get-PluginMarketplaceKind $market) -eq 'csa') {
            if (-not $ghAuthed) { continue }
            if ((Invoke-NativeQuiet { gh api "repos/$repo" }) -ne 0) { continue }
        }

        $result = Invoke-NativeCapture { claude plugin marketplace add $repo }
        if ($result.ExitCode -eq 0) {
            $added += $repo
            $marketUsable[$market] = $true
        } else {
            $failed += [pscustomobject]@{
                What   = "marketplace $repo"
                Output = if ($result.Output) { $result.Output } else { '<no stderr output>' }
            }
        }
    }

    # Pass 2: install plugins.
    foreach ($entry in $allEntries) {
        $parts = $entry -split '@', 2
        if ($parts.Count -ne 2) { continue }
        $name = $parts[0]
        $market = $parts[1]

        if (-not $marketUsable.ContainsKey($market)) { continue }
        if ($installedPlugins -contains "$name@$market") { continue }

        $result = Invoke-NativeCapture { claude plugin install "$name@$market" }
        if ($result.ExitCode -eq 0) {
            $installed += "$name@$market"
        } else {
            $failed += [pscustomobject]@{
                What   = "plugin $name@$market"
                Output = if ($result.Output) { $result.Output } else { '<no stderr output>' }
            }
        }
    }

    if ($added.Count -gt 0) {
        Write-Success "Registered plugin marketplaces:"
        $added | ForEach-Object { Write-Host "  + $_" }
    }
    if ($installed.Count -gt 0) {
        Write-Success "Installed plugins:"
        $installed | ForEach-Object { Write-Host "  + $_" }
    }
    if ($failed.Count -gt 0) {
        Write-Warn "Failed on $($failed.Count) item(s):"
        foreach ($f in $failed) {
            Write-Host "  ! $($f.What)"
            Write-Host "      $($f.Output)"
        }
    }
}
```

- [ ] **Step 3: Wire into the main flow**

Find where `Setup-PluginMarketplaces` is called in the main execution flow. Immediately after that call, add:

```powershell
Install-Plugins
```

- [ ] **Step 4: Add preflight plan line**

Find the block in the preflight display that lists `Plugin marketplaces  probe $($CSA_MARKETPLACES.Count) CSA repos...`. Immediately after it, add:

```powershell
Write-Host "  Plugins              install defaults from csa-plugins.txt (+ csa-plugins-internal.txt if accessible)"
```

- [ ] **Step 5: Bump version**

Change:
```powershell
$ScriptVersion = "2026.04212115"
```
to today's timestamp:
```powershell
$ScriptVersion = "2026.04222100"
```

- [ ] **Step 6: PowerShell lint (optional, if PSScriptAnalyzer is available)**

```powershell
Invoke-ScriptAnalyzer -Path scripts/windows-ai-tools.ps1 -Severity Warning,Error
```
Expected: no new findings related to the new function (pre-existing results are unchanged).

- [ ] **Step 7: Commit**

```bash
git add scripts/windows-ai-tools.ps1
git commit -m "feat(windows-ai-tools): install default plugins from shared lists"
```

---

## Task 8: Update `README.md` with the Plugins section

**Files:**
- Modify: `README.md` — insert new section **"Plugins installed"** after the existing "Work tools" section and before the final repository/contributing block.

- [ ] **Step 1: Find the insertion point**

The existing "Work tools (productivity apps)" section ends with the Windows work-tools code block. Directly after the closing triple-backtick of that block (before the `---` and the `## Repository contents` heading), insert the new section.

- [ ] **Step 2: Insert the section**

```markdown
## Plugins installed

The AI tools installers (and the macOS updater) install a curated set of
Claude Code plugins so CSA staff can use them right away and explore
what's possible. Public plugins install for everyone; CSA-marketplace
plugins install only if your GitHub account can access the private CSA
marketplaces.

### Process & planning
- **superpowers** — brainstorming, writing-plans, TDD, systematic-debugging, code review, verification, dispatching-parallel-agents, using-git-worktrees
- **feature-dev** — `/brainstorm`, `/write-plan`, `/execute-plan`, `/implement`, `/finish-branch`
- **claude-code-setup** — claude-automation-recommender (scan a repo, recommend hooks/agents/skills)
- **claude-md-management** — `/init` improvements, claude-md-improver
- **session-report** — HTML report of tokens, cache, skills, expensive prompts
- **explanatory-output-style** — toggle: add educational explanations to responses
- **learning-output-style** — toggle: interactive learning with contribution requests

### Software development
- **commit-commands** — `/commit`, `/commit-push-pr`, `/clean_gone`
- **code-review** — `/review`
- **pr-review-toolkit** — `/review-pr`, multi-agent PR review (silent-failure-hunter, type-design-analyzer, pr-test-analyzer, comment-analyzer, code-simplifier)
- **github** — GitHub MCP (issues, PRs, code search, releases, reviews)
- **greptile** — Greptile code intelligence
- **frontend-design** — polished UI code that avoids generic AI aesthetics
- **playwright** — browser automation and UI testing via Playwright MCP
- **chrome-devtools-mcp** — Chrome DevTools MCP (debugging, performance, a11y, LCP)
- **playground** — single-file interactive HTML explorers
- **typescript-lsp** — TypeScript language server integration
- **semgrep** — Semgrep security scanning (requires `semgrep` CLI)
- **security-guidance** — security review and guidance
- **cloudflare** — Workers, Pages, D1/R2/KV, Durable Objects, Agents SDK, Wrangler

### Building Claude apps
- **claude-api** — Claude API / Anthropic SDK (migrations, caching, tool use, batching)
- **agent-sdk-dev** — `/new-sdk-app`, Agent SDK verifiers
- **mcp-server-dev** — build-mcp-server, build-mcp-app, build-mcpb (local .mcpb bundles)
- **plugin-dev** — `/create-plugin`, plugin-structure, command/agent/skill/hook development
- **skill-creator** — create, edit, and benchmark skills
- **pydantic-ai** — Pydantic AI framework

### Business & productivity
- **slack** — `/standup`, `/find-discussions`, `/summarize-channel`, `/draft-announcement`, `/channel-digest`
- **document-skills** — docx, pptx, pdf, xlsx, canvas-design, brand-guidelines, internal-comms, theme-factory, webapp-testing
- **example-skills** — reference implementations of the document skills above

### CSA-specific (installed if you're on CSA-Internal teams)
- **cwe-analysis** — CWE assignment, chains, AI relevance
- **incident-analysis** — OSINT, timeline, impact, defensive recs for cloud/AI incidents
- **nist-ir-8477-mapping** — map between frameworks using NIST IR 8477
- **security-knowledge-ingestion** — convert standards/regs into structured data
- **cino-project-tracker** — CINO Airtable project registry
- **audience-lens** — build audience profiles for writing tasks
- **writing-style-forge** — generate writing-style plugins from samples
- **research-initiative-tracker** — CSA research initiative tracking
- **csa-certification-development**, **csa-training-content-development**, **csa-training-design-system** — training & certification workflows

The plugin lists live in [`scripts/csa-plugins.txt`](scripts/csa-plugins.txt)
and [`scripts/csa-plugins-internal.txt`](scripts/csa-plugins-internal.txt)
— edit those to change what gets installed by default. Users can
disable any individual plugin locally with `claude plugin disable <name>`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document default plugin set grouped by purpose"
```

---

## Task 9: Update `CLAUDE.md` with the plugin-install contract

**Files:**
- Modify: `CLAUDE.md` — extend "Shared boilerplate" paragraph, add new "Plugin install contract" subsection under "Conventions" (right after the existing "Plugin marketplace registration" subsection).

- [ ] **Step 1: Extend the "Shared boilerplate" paragraph**

Find the paragraph starting `All scripts (both platforms) duplicate their output helpers...`. At the end of that paragraph (after the final sentence), append:

```
The `PLUGIN_MARKETPLACE_REPOS` / `$PluginMarketplaceRepos` map is similarly duplicated across `macos-ai-tools.sh`, `windows-ai-tools.ps1`, and `macos-update.sh`. The actual plugin lists, however, are single-source: `scripts/csa-plugins.txt` and `scripts/csa-plugins-internal.txt` are fetched from HEAD at runtime, so list-only changes do **not** require a script edit or `SCRIPT_VERSION` bump.
```

- [ ] **Step 2: Add the "Plugin install contract" subsection**

Immediately after the "Plugin marketplace registration" subsection (which ends with the bullet about the updater's `Refreshing plugin marketplaces` info line), insert:

```markdown
### Plugin install contract
`macos-ai-tools.sh`, `windows-ai-tools.ps1`, and `macos-update.sh` share a silent-by-default plugin-install contract — similar shape to marketplace registration, but driven by list files:
1. Fetch `scripts/csa-plugins.txt` (public) and `scripts/csa-plugins-internal.txt` (CSA-internal) from HEAD via `curl` / `Invoke-RestMethod`. If both fetches fail or `claude`/`curl` is missing, the whole step is a silent no-op.
2. Each entry is `<plugin>@<marketplace>`. Blank lines and `#`-prefixed lines are ignored.
3. Pass 1: ensure each referenced marketplace is registered. Public marketplaces (`claude-plugins-official`, `anthropic-agent-skills`) register unconditionally. CSA marketplaces (`csa-plugins`, `csa-cino-plugins`, `csa-research-plugins`, `csa-training-plugins`, `csa-plugins-official`, `accounting-plugins`) are `gh`-probed first via their underlying repo — inaccessible ones silently skip every plugin from that marketplace, matching the existing CSA-marketplace registration contract.
4. Pass 2: for each plugin whose marketplace is usable, skip if already installed (silent); otherwise `claude plugin install <entry>`.
5. Output: one success line per marketplace registered + one success line per plugin installed + one warn line per failure with the captured stderr indented under it. Already-installed entries and inaccessible CSA entries produce no output.
6. List-only changes (adding or removing a plugin from either `.txt` file) require a single commit to `main` and propagate to existing users on their next installer or `macos-update.sh` run — no script edit or `SCRIPT_VERSION` bump.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude-md): document plugin install contract and shared map"
```

---

## Task 10: End-to-end smoke test and open PR

**Files:**
- None (verification only).

- [ ] **Step 1: Dry-run smoke test on local macOS**

On the current machine (which already has most plugins installed), run the updater to verify the new `install_plugins` path is idempotent and silent when nothing needs doing:

```bash
bash scripts/macos-update.sh
```

Expected: output shows the existing marketplace-refresh info line and no new plugin-install lines (because everything is already installed). Any failures print with stderr visible. If a plugin appears on the list but isn't installed locally, expect one success line like:
```
==> Installed plugins:
  + <plugin>@<marketplace>
```

- [ ] **Step 2: Dry-run on a teammate's fresh Windows machine (or a clean VM)**

Have Hannah (or anyone with a fresh Windows setup) rerun:
```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
```

Expected: after the existing marketplace-registration step, a new pass that registers any missing marketplaces (from the plugin list) and installs the default plugin set. Failures print with captured stderr.

- [ ] **Step 3: Push the branch and open PR**

```bash
git push -u origin feat/default-plugin-install
gh pr create --base main --head feat/default-plugin-install \
  --title "feat(ai-tools): install default plugins from shared lists" \
  --body-file docs/default-plugin-install-design.md
```

(Body can be refined after creation — the design doc is a reasonable first-draft body.)

- [ ] **Step 4: Link the PR back to the design and plan docs**

In the PR description (via web UI or `gh pr edit`), add a header:
```
Spec: docs/default-plugin-install-design.md
Plan: docs/default-plugin-install-plan.md
```

---

## Self-review

**Spec coverage:**
- Two list files (public + internal) — Tasks 1–2 ✅
- `install_plugins` in `macos-ai-tools.sh` + wiring — Tasks 3–5 ✅
- `install_plugins` in `macos-update.sh` + wiring — Task 6 ✅
- `Install-Plugins` in `windows-ai-tools.ps1` + wiring — Task 7 ✅
- README "Plugins installed" section with 5 groups — Task 8 ✅
- CLAUDE.md plugin install contract + shared-boilerplate extension — Task 9 ✅
- E2E verification + PR — Task 10 ✅
- Silent-by-default contract (skip on missing `claude`/`curl`, already-installed, inaccessible CSA) — baked into Task 4 function body and documented in Task 9 contract ✅
- List fetched from HEAD so one-file updates propagate — Task 4 Step 1 `PLUGIN_LIST_URL_*` constants ✅
- `gh`-probe only for CSA marketplaces — Task 4 Step 1 `plugin_marketplace_kind` function + conditional probe ✅
- Captured stderr on install error — Task 4 Step 1 `2>&1 >/dev/null` pattern; Task 7 Step 2 `Invoke-NativeCapture` usage ✅

**Placeholder scan:** no "TBD", "implement later", or similar in any task. Every step has exact code or exact commands.

**Type consistency:**
- Bash: `install_plugins`, `plugin_list_entries`, `plugin_marketplace_kind`, `PLUGIN_MARKETPLACE_REPOS`, `PLUGIN_LIST_URL_PUBLIC`, `PLUGIN_LIST_URL_INTERNAL` — names consistent across Tasks 3–6.
- PowerShell: `Install-Plugins`, `Get-PluginListEntries`, `Get-PluginMarketplaceKind`, `$PluginMarketplaceRepos`, `$PluginListUrlPublic`, `$PluginListUrlInternal` — names consistent across Task 7.
- URL values identical in bash and PowerShell, pointing at `HEAD` of the public repo.

**Scope:** single feature, one PR, ~10 commits. Appropriate size for a single plan.
