# CSA DesktopSetup

**One command takes a CSA laptop from bare to AI-capable** — on macOS and Windows.

Not just the apps. By the time a run finishes, the AI can reach CSA's actual work: your
Zendesk tickets, your Gmail and Calendar, comments on a Google Doc, courses and learners in
Skilljar. That is the point — so the question stops being *"can the AI do this?"* and becomes
*"should we?"* (see [`BUSINESS-CASE.md`](BUSINESS-CASE.md)).

---

## Which script do I run?

Start here. Most people need the first row once, and the third row from then on.

| I want to… | Run | Takes |
|---|---|---|
| **Set up a new machine** | `*-ai-tools` | 10–30 min |
| …and the productivity apps too | `*-work-tools` as well | +10 min |
| **Pick up a new or updated CSA MCP server, or new plugins** | `*-plugins` | under a minute |
| **Update everything** — Homebrew/winget, npm, pip, Claude Code, *and* the CSA layer | `*-update` | 5–20 min |
| **Clone a CSA repo and start working in it** | `clone-and-claude` | seconds |

> **`*-plugins` is named badly, and we know.** It installs and upgrades **every CSA MCP server**
> as well as plugins — it is the fast path for "there's a new MCP server, get it". The filename
> stays because it is in one-liners people have already saved; see
> [ADR-003](DECISIONS-ADR.md).

Everything is **idempotent** — safe to re-run, any number of times. Each script shows you its
plan and asks before it changes anything.

---

## Quick start — AI tools

**You get:** Claude Desktop and ChatGPT Desktop; the Claude Code, Codex and Gemini CLIs;
1Password (app + CLI); Git and GitHub CLI with your identity configured from your GitHub
profile; Node, Python (via uv), `pandoc` and `typst`; a curated set of Claude Code plugins; and
**four CSA MCP servers** if your GitHub account has CSA-Internal access:

| Server | What the AI can then do |
|---|---|
| `csa-zendesk` | read, triage, comment on and solve support tickets |
| `csa-google-gmail-calendar` | read and send mail, manage calendar events |
| `csa-google-workspace` | read and write Docs, Sheets and Slides, and their comment threads |
| `csa-skilljar` | manage courses, lessons, quizzes, learners and enrolment |

The installer also detects tools installed the wrong way — Claude Code via Homebrew or npm, for
instance — and migrates them to the correct installer, preserving settings.

### macOS

```bash
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```

Installs a base layer first if it is missing — Xcode CLI Tools, Homebrew, Node/npm, uv, Python —
plus the document toolchain (`pandoc`, `typst`, and `pyyaml`/`pymupdf` in `~/.default_venv`)
that the **document-pipeline** plugin needs to render CSA PDFs.

> **Why `-H 'Cache-Control: no-cache'`?** It forces a fresh download. Without it a stale copy
> can sit in GitHub's CDN edge cache for a few minutes after a fix ships. Keep the header.

### Windows

Windows needs a one-time PowerShell setup before any script in this repo will run.

> **Not your personal machine?** The execution policy is a security setting. If this is a work
> laptop managed by your IT department, ask them before changing it.

**Step 1 — Check your current policy.** Open PowerShell as Administrator (Windows key, type
`powershell`, right-click **Windows PowerShell**, **Run as administrator**):

```powershell
Get-ExecutionPolicy
```

Note what it says — usually `Restricted` on a fresh install. You will restore this in Step 4.

**Step 2 — Temporarily allow script execution:**

```powershell
Set-ExecutionPolicy RemoteSigned
```

Answer `Y` when it asks.

**Step 3 — Run it.** Close the Administrator window and open a **regular** PowerShell window:

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

Installs Git, GitHub CLI, Python, Node.js, `pandoc` and `typst` via winget alongside the AI apps
and CLIs, plus `pyyaml` and `pymupdf` for **document-pipeline**. Needs Windows 10/11 and winget.

**Step 4 — Restore the original policy.** Re-open PowerShell as Administrator and set it back to
whatever Step 1 reported:

```powershell
Set-ExecutionPolicy Restricted
```

If you expect to run PowerShell scripts regularly, leaving it at `RemoteSigned` is reasonable.

---

## What happens at the end of a run

The last thing on screen is a short numbered list of what still needs *you*. It is the only part
you have to act on, and it is deliberately last — it used to be buried under ~140 lines of
install output.

Three kinds of item show up:

1. **Restart Claude Desktop.** A newly registered MCP server is invisible to it until then.
2. **Sign in.** Three of the four servers can do this *in the conversation* — just say
   "sign me in to Gmail" in Claude Code and follow the link. A terminal command is listed as the
   fallback.
3. **Something only another person can do** — for example, Skilljar needs a credential issued to
   you.

If a server does not appear in Claude Code afterwards, the usual cause is item 1.

---

## Clone a repo and start Claude

Replace `ORG/REPO` with the real org and repository.

```bash
# macOS
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

```powershell
# Windows
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

Checks prerequisites, clones to `~/GitHub/OrgName/RepoName`, and tells you how to launch Claude
Code. Safe to re-run: if the repo is already there it pulls instead of cloning.

---

## Updating

### Just the CSA layer — plugins and MCP servers

**This is the one to reach for** when there is a new or updated CSA MCP server. No Homebrew,
winget, npm or pip; it finishes in well under a minute.

```bash
# macOS
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-plugins.sh)"
```

```powershell
# Windows
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-plugins.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

### Everything

Homebrew/winget, npm globals, pip, Claude Code, and then the CSA layer. Takes a snapshot of every
installed version first, so you can see what changed if something breaks.

```bash
# macOS
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"
```

```powershell
# Windows
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-update.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

Snapshots land in `~/Library/Logs/CSA-DesktopSetup/` (macOS) or
`%LOCALAPPDATA%\CSA-DesktopSetup\` (Windows), timestamped.

### Or by hand

```bash
# macOS
brew update && brew upgrade     # Homebrew formulas and casks
npm update -g                   # npm globals (Codex, Gemini, Wrangler)
pip install --upgrade pip
claude update                   # Claude Code
```

```powershell
# Windows
winget upgrade --all; npm update -g; python -m pip install --upgrade pip; claude update
```

Note that doing it by hand skips the CSA layer entirely — no plugins, no MCP servers.

---

## Work tools (productivity apps)

Optional, and independent of the AI tools.

**macOS** — 1Password, Slack, Zoom, Chrome, Microsoft Office, Git, GitHub CLI. An optional dev
profile adds VS Code, AWS CLI and Wrangler.

```bash
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"
```

**Windows** — Git, GitHub CLI, 1Password, Slack, Zoom, Chrome, Microsoft Office, with the same
optional dev profile. Needs the execution policy from Step 2 above.

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

The profile is chosen interactively. A non-interactive run always installs core only.

---

## Plugins installed

The AI tools installers and the updaters install a curated set of Claude Code plugins, so CSA
staff can use them immediately and see what is possible. Public plugins install for everyone;
CSA-marketplace plugins install only if your GitHub account can reach the private CSA
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
- **frontend-design** — polished UI code that avoids generic AI aesthetics
- **playwright** — browser automation and UI testing via Playwright MCP
- **chrome-devtools-mcp** — Chrome DevTools MCP (debugging, performance, a11y, LCP)
- **playground** — single-file interactive HTML explorers
- **typescript-lsp** — TypeScript language server integration
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

### CSA-specific (installed if you are on CSA-Internal teams)
- **cwe-analysis** — CWE assignment, chains, AI relevance
- **incident-analysis** — OSINT, timeline, impact, defensive recs for cloud/AI incidents
- **nist-ir-8477-mapping** — map between frameworks using NIST IR 8477
- **security-knowledge-ingestion** — convert standards/regs into structured data
- **document-pipeline** — Markdown to a branded, accessible CSA PDF (render, preflight, copy edit, design review). Needs `pandoc` and `typst` — see its README
- **vendor-research** — guided vendor evaluation and procurement decisions
- **csa-spreadsheets** — parse CCM/AICM spreadsheets into JSON, CSV, or Markdown
- **cino-project-tracker** — CINO Airtable project registry
- **audience-lens** — build audience profiles for writing tasks
- **writing-style-forge** — generate writing-style plugins from samples
- **research-initiative-tracker** — CSA research initiative tracking
- **csa-certification-development**, **csa-training-content-development**, **csa-training-design-system** — training & certification workflows

The lists live in [`scripts/csa-plugins.txt`](scripts/csa-plugins.txt) and
[`scripts/csa-plugins-internal.txt`](scripts/csa-plugins-internal.txt) — edit those to change
what installs by default. A list-only change reaches everyone on their next run, with no script
update needed. Disable any single plugin locally with `claude plugin disable <name>`.

---

## Debug mode — when something goes wrong

Re-run the same command with `CSA_DEBUG` set. Everything still prints to screen, and a full
transcript — every command, its output, its exit code, and what the machine looked like — is
written to a file in your home directory. Works on **every** script here.

### macOS

```bash
CSA_DEBUG=1 bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```

`CSA_DEBUG=1` goes **before** `bash`, as a prefix on the same line. That is what makes it reach
the script.

### Windows

> **Paste these one at a time.** Copying both lines together into the console has been observed
> to close the window immediately, before either line runs. Two separate pastes — or the
> single-line form below — both avoid it.

Turn logging on:

```powershell
$env:CSA_DEBUG = '1'
```

Then run the script:

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

The variable stays set for the rest of that window, so a second run also logs. To stop:

```powershell
Remove-Item Env:\CSA_DEBUG
```

**Or as a single line**, if you would rather paste once:

```powershell
$env:CSA_DEBUG = '1'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

**There is no `-Debug` switch, and both obvious guesses go wrong:**

| what you might type | what actually happens |
|---|---|
| `irm ... --Debug ... \| iex` | fails immediately — *"a positional parameter cannot be found that accepts argument '--Debug'"* |
| `irm ... -Debug ... \| iex` | **runs, and logs nothing.** `-Debug` is a real parameter *on `irm`* — it applies to the download, not to the script `iex` then executes |

Why there is no switch: `irm … | iex` fetches text and executes it, so the script never receives
an argument vector for a flag to arrive in. An environment variable is the only thing that
crosses that boundary — which is also how `NONINTERACTIVE` works.

Either spelling is accepted, since `$env:` is easy to forget. These are **alternatives, not a
sequence** — use one:

```powershell
$env:CSA_DEBUG = '1'
```

```powershell
$CSA_DEBUG = '1'
```

So is any of `1`, `true`, `yes` or `on`, in any case.

### The log

The path is printed at the start and again at the end:

```
~/desktopsetup-YYYYMMDD-HHMMSS.log                 (macOS)
C:\Users\<you>\desktopsetup-YYYYMMDD-HHMMSS.log    (Windows)
```

Readable only by you (mode 0600, or an ACL granting just your account). **One file covers the
whole run**, including the CSA-internal setup that runs as a separate process — so there is only
ever one file to send.

It exists even if the run stops early. A script that refuses to proceed — wrong platform,
running as Administrator, a missing prerequisite — still leaves a log saying which check
refused, because that is exactly when you want one.

Known credential shapes (tokens, client secrets, bearer headers, refresh tokens) are replaced
with `<redacted>` before anything is written, the CSA OAuth client is never captured at all, and
the snapshot records *key names* rather than values. That is a safety net, not a guarantee:
**read the file before you send it to anyone.** The first line of every log says the same.

---

## Retired: MCP token setup (macOS)

`macos-mcp-setup.sh` discovered Airtable and GitHub personal access tokens and wrote them into
the Claude Code, Codex and Gemini configs. It is **retired** — those services are now reachable
as hosted connectors over OAuth, with no long-lived token stored on disk. The script is kept in
[`archives/`](archives/) for reference.

**If you ran it, you may still have tokens on disk.** Look for `airtable` or `github` MCP entries
carrying a bearer token in `~/.claude.json`, `~/.codex/config.toml` and `~/.gemini/settings.json`,
remove any you no longer use, then revoke the token at the service. Nothing removes them for you.

---

## Repository contents

### Project documents

The CINO standard file set. Written after reading the repository rather than from a template, and
where something does not apply it says so and says why — per
[`a-standard-file-filled-from-the-template-is-worse-than-a-missing-one`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/a-standard-file-filled-from-the-template-is-worse-than-a-missing-one.md).

- **[`ENGINEERING.md`](ENGINEERING.md)** — **start here if you are changing anything.** The
  repository's facts: the ten scripts, why `main` is the release, the PowerShell 5.1 behaviour
  the wrappers exist for, the parity contract, the guard layer
- **[`BUSINESS-CASE.md`](BUSINESS-CASE.md)** — why this exists: moving the question from *can the
  AI do this* to *should we*
- **[`GOALS.md`](GOALS.md)** — what success looks like, read off this repository's record with
  the evidence linked inline
- **[`RACI.md`](RACI.md)** — who is accountable, and the bus factor of one
- **[`DECISIONS-ADR.md`](DECISIONS-ADR.md)** — six local technical decisions and what each
  rejected
- **[`FRICTION.md`](FRICTION.md)** — work that is harder than it should be, for a human or an AI
- **[`WAITING-FOR.md`](WAITING-FOR.md)** — blocked work, each entry with an observable trigger
- **[`TODO.md`](TODO.md)** — open work, one line per item
- **[`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md)** — no running service; the runtime
  dependencies that exist anyway, two of them CSA's own
- **[`BACKUP-RESOURCES.md`](BACKUP-RESOURCES.md)** — no state of our own; the backups these
  scripts write onto *user* machines, and the retention gap
- **[`CLAUDE.md`](CLAUDE.md)** / **[`AGENTS.md`](AGENTS.md)** — thin pointers to
  `ENGINEERING.md` plus what is specific to each AI coding tool

### `scripts/`

Ten scripts, five macOS/Windows pairs — each self-contained and idempotent.

- **`macos-ai-tools.sh`** / **`windows-ai-tools.ps1`** — the AI layer: desktop apps, coding CLIs,
  plugins, and every CSA MCP server
- **`macos-work-tools.sh`** / **`windows-work-tools.ps1`** — core work apps plus an optional dev
  profile
- **`macos-update.sh`** / **`windows-update.ps1`** — update everything, with a version snapshot
  first
- **`macos-plugins.sh`** / **`windows-plugins.ps1`** — CSA plugins **and MCP servers** only; the
  fast path
- **`clone-and-claude.sh`** / **`clone-and-claude.ps1`** — clone a CSA repo and start Claude Code
- **`csa-claude-connectors.py`** — disable chosen claude.ai connectors so the CSA Google MCP
  servers are used instead. Report-only unless `--apply`
- **`csa-plugins.txt`** / **`csa-plugins-internal.txt`** — the plugin lists, fetched at runtime

### `tools/` and `tests/`

Eleven repo-specific checks and ten test files. **`./tools/check-all.sh` mirrors CI exactly** —
run it before opening a pull request. See [`ENGINEERING.md`](ENGINEERING.md) for what it proves
and what it does not.

### `docs/` and `archives/`

Design notes, the weekly source-sweep runbook, and previous script versions for reference.

---

## Contributing

Found a problem? Have a suggestion?

[Open an issue](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/new/choose) — there
are templates for common requests. If you are sending a bug report, a
[debug-mode](#debug-mode--when-something-goes-wrong) log is the single most useful thing to
attach — read it first.

Changing the scripts? [`ENGINEERING.md`](ENGINEERING.md) first, and run `./tools/check-all.sh`.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
