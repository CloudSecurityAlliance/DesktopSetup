# Default plugin install — design

**Status:** Approved design, pending implementation plan.
**Date:** 2026-04-21

## Goal

Install a curated set of Claude Code plugins by default on every CSA machine
that runs the AI tools installer, and keep that set aligned as the list
evolves. Encourage CSA staff to explore skills and build their own plugins
by making the full ecosystem available out of the box.

## Scope

- **In scope:** installing plugins during `macos-ai-tools.sh`,
  `windows-ai-tools.ps1`, and `macos-update.sh`; documenting the plugin set
  in `README.md` grouped by purpose.
- **Out of scope:** uninstall when a plugin is removed from the list;
  enable/disable management; a separate stand-alone plugin-install script;
  the currently-broken `secid` plugin (excluded until its manifest is
  fixed upstream).

## Design

### Two plugin list files

Source of truth for which plugins to install lives in two plain-text files
under `scripts/`:

- **`scripts/csa-plugins.txt`** — public plugins (29 entries from
  `claude-plugins-official` and `anthropic-agent-skills`). Installed
  unconditionally on every run.
- **`scripts/csa-plugins-internal.txt`** — CSA-marketplace plugins
  (11 entries across `csa-plugins-official`, `csa-cino-plugins`,
  `csa-research-plugins`, `csa-training-plugins`). Each entry's
  marketplace is `gh`-probed; inaccessible marketplaces silently skip.

**File format:** one entry per line in `<plugin>@<marketplace>` form.
Blank lines and lines starting with `#` are ignored. This form is what
`claude plugin install` already accepts, and it lets scripts derive the
required marketplaces from the list itself — no separate marketplace
array to keep in sync.

**Rationale for the split:** the two lists have different access
contracts. Public plugins always resolve; CSA plugins need a `gh` probe.
Keeping them in separate files makes the access contract obvious from
the filename and avoids per-line annotations. The internal file is
effectively invisible to external users of the public repo since they
fail every access probe.

### Install logic (duplicated across the 3 scripts)

Each of `macos-ai-tools.sh`, `windows-ai-tools.ps1`, and
`macos-update.sh` gains an `install_plugins` function (or PowerShell
equivalent) with the same behavior:

1. If `claude` is not in `PATH`, silently skip. No warning — consistent
   with the existing marketplace-registration contract for users running
   the installer outside a CSA environment.
2. Fetch both list files via `curl` / `Invoke-RestMethod` from the
   `HEAD` ref of the public repo. This means updating the list requires
   exactly one commit to `main` on the list file; no script change, no
   `SCRIPT_VERSION` bump needed for list-only changes.
3. For the public list: for each `<plugin>@<marketplace>` entry, ensure
   the marketplace is registered (add if missing — no `gh` probe);
   skip any plugin already installed (silent); otherwise
   `claude plugin install <plugin>@<marketplace>` and print a one-line
   success or warn.
4. For the internal list: the marketplace *name* in each entry
   (e.g. `csa-research-plugins`) maps to an underlying GitHub repo
   (e.g. `CloudSecurityAlliance-Internal/Research-Plugins`) — this
   mapping is the already-existing `CSA_MARKETPLACES` array extended
   to carry both sides, or an equivalent dict derived from it. For
   each unique marketplace referenced in the list, probe access with
   `gh api repos/<org>/<repo>`; on non-zero exit, silently skip every
   plugin from that marketplace. Otherwise register the marketplace
   (if not already), then install each plugin the same way as the
   public list.
5. Inaccessible plugins, already-installed plugins, and missing `claude`
   produce no output — only actual installs or errors print anything.

**Integration points:**

- `macos-ai-tools.sh` — new `install_plugins()` called after the existing
  marketplace-registration step in `main()`. Adds a plan line in
  `preflight()`: `Plugins  install N public + probe M CSA plugins`.
- `windows-ai-tools.ps1` — mirror structure in PowerShell.
- `macos-update.sh` — same function added in parallel with the existing
  marketplace refresh, so new plugins added to the list propagate to
  existing machines on the next update run.

The existing `CSA_MARKETPLACES` array stays. It still ensures
CSA marketplaces are registered for accessible users even when no plugin
from that marketplace is in the install list.

### README changes

New section **"Plugins installed"** in `README.md`, placed after
"Work tools". Five groups, each a subsection with a short bulleted
list of plugins and their notable commands or skills:

1. **Process & planning** — superpowers, feature-dev, claude-code-setup,
   claude-md-management, session-report, explanatory-output-style,
   learning-output-style
2. **Software development** — commit-commands, code-review,
   pr-review-toolkit, github, greptile, frontend-design, playwright,
   chrome-devtools-mcp, playground, typescript-lsp, semgrep,
   security-guidance, cloudflare
3. **Building Claude apps** — claude-api, agent-sdk-dev, mcp-server-dev,
   plugin-dev, skill-creator, pydantic-ai
4. **Business & productivity** — slack, document-skills, example-skills
5. **CSA-specific (installed if you're on CSA-Internal teams)** —
   cwe-analysis, incident-analysis, nist-ir-8477-mapping,
   security-knowledge-ingestion, cino-project-tracker, audience-lens,
   writing-style-forge, research-initiative-tracker,
   csa-certification-development, csa-training-content-development,
   csa-training-design-system

The CSA-specific group includes a one-line note that those plugins only
install for users whose GitHub account can access the private CSA
marketplaces.

### CLAUDE.md changes

- Add a subsection **"Plugin install contract"** under "Conventions"
  describing the silent-by-default behavior and the public/internal
  list split.
- Extend the existing **"Shared boilerplate"** paragraph: note that the
  plugin list now lives in two dedicated files
  (`scripts/csa-plugins.txt`, `scripts/csa-plugins-internal.txt`), but
  the parsing/install logic is duplicated three ways — same KEEP IN
  SYNC discipline as `CSA_MARKETPLACES`.
- Bump each touched script's `SCRIPT_VERSION` to the implementation
  date.

## Non-decisions

- **List format:** plain text with `#` comments was chosen over JSON or
  TOML because neither bash nor PowerShell needs an external parser
  for it, and the list is a flat sequence of strings.
- **Fetched via curl instead of embedded:** scripts already run via
  curl bootstrap, so list changes propagate without a script release.
- **Public plugins don't need a `gh` probe:** `claude-plugins-official`
  and `anthropic-agent-skills` are public Anthropic marketplaces —
  access always succeeds. Probing would be waste.
- **No separate stand-alone plugin script:** considered and rejected.
  Would have added a Git Bash invocation path on Windows and complicated
  the curl-bootstrap case. The data-file approach keeps each platform
  idiomatic while still making list updates a one-file change.

## Things that could go wrong

- **Network / rate-limit failures on list fetch.** If the curl step
  fails, the script treats it as "no plugin list available" and skips
  the install step silently, same as missing `claude`. An explicit
  warn on curl failure would be noisier than the existing silent
  contract allows; skipping keeps it consistent.
- **Plugin install command changes.** `claude plugin install
  <name>@<marketplace>` is the current form. If the CLI renames or
  restructures the subcommand, the duplicated install logic in three
  scripts all need an update at once. The KEEP IN SYNC note is the
  mitigation.
- **`secid` re-breaks or another plugin's manifest becomes invalid.**
  `claude plugin install` will error on a broken manifest. The scripts
  print the error line but don't abort — the rest of the list still
  installs.
- **Plugin count grows large enough to slow install.** Each plugin is a
  separate `claude plugin install` call today. If the default list
  grows past a few dozen, batching or parallelism may be worth
  revisiting — not now.
