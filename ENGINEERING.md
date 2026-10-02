# Engineering notes

**The repository's facts, for whoever is editing it** — human, Claude Code, Codex, Gemini or
anything else. [`CLAUDE.md`](CLAUDE.md) and [`AGENTS.md`](AGENTS.md) are short pointers to this
file plus whatever is specific to their reader; see
[ADR-004](DECISIONS-ADR.md) for why there is one copy rather than two.

Read [`BUSINESS-CASE.md`](BUSINESS-CASE.md) first if you want to know *why* any of this exists.
This file is *how*.

---

## What is in here

| Section | Read it when |
|---|---|
| [`main` IS the release](#main-is-the-release) | before merging anything |
| [What the scripts are](#what-the-scripts-are) | orienting; ten scripts, five pairs |
| [Script versioning](#script-versioning) | you changed a script — the format is `YYYY.MMDDHHMM` |
| [The target runtime is Windows PowerShell 5.1](#the-target-runtime-is-windows-powershell-51) | touching any `.ps1`. The `Invoke-Native*` tables are here |
| [Conventions](#conventions) | writing new code in either language |
| [Duplicated state: the six-script lists](#duplicated-state-the-six-script-lists) | adding a marketplace, plugin or MCP server |
| [The guard layer](#the-guard-layer) | adding a check, or wondering what `check-all.sh` proves |
| [Script execution flow, and the plan](#script-execution-flow-and-the-plan) | adding a step to `main()`. The to-do ledger is here |
| [Debug mode](#debug-mode) | diagnosing a user's run, or adding output |
| [The CSA contracts](#the-csa-contracts) | anything touching plugins or MCP servers |
| [Periodic source sweep](#periodic-source-sweep) | weekly, by hand |
| [Bootstrap commands](#bootstrap-commands) | copying a one-liner — keep the `no-cache` header |
| [Three habits](#three-habits-that-would-have-prevented-most-of-this-repos-defects) | always |

---

## `main` IS the release

Every documented install path fetches `HEAD`:

```
raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/...
```

and the internal-setup fetch (`gh api repos/.../contents/internal-setup/$name`) pins no ref
either. **A merge is live to the next person who runs the one-liner.** There is no staging
branch and deliberately so ([ADR-001](DECISIONS-ADR.md)).

Consequences you have to work with:

- CI on the pull request is the only gate. `main` once carried a red test suite for six commits
  ([#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132)).
- Every script carries a version so a person can say what they ran (below), and CI refuses a
  changed script that did not bump it.
- Bootstrap one-liners all send `Cache-Control: no-cache`, because the
  `raw.githubusercontent.com` edge cache otherwise serves a stale copy for a few minutes after a
  fix ships. **Keep that header in every documented command**, README included.

---

## What the scripts are

Ten scripts, five macOS/Windows pairs. Each is self-contained and idempotent.

| macOS | Windows | What |
|---|---|---|
| `macos-work-tools.sh` | `windows-work-tools.ps1` | Core work apps (1Password, Slack, Zoom, Chrome, Office, Git, GitHub CLI) plus an optional dev profile (VS Code, AWS CLI, Wrangler) |
| `macos-ai-tools.sh` | `windows-ai-tools.ps1` | The AI layer: Claude Desktop and ChatGPT Desktop; Claude Code, Codex and Gemini CLIs; uv, Python, Node; the doc toolchain; plugin marketplaces; the CSA MCP server; and every internal CSA MCP server |
| `macos-update.sh` | `windows-update.ps1` | Update everything — Homebrew/winget, npm globals, pip, `claude update` — then the plugin and MCP sync. Snapshots versions first, for rollback |
| `macos-plugins.sh` | `windows-plugins.ps1` | **The CSA layer only**: plugins *and* every CSA MCP server, with no Homebrew/winget/npm/pip. The fast path |
| `clone-and-claude.sh` | `clone-and-claude.ps1` | Clone a CSA repo into `~/GitHub/Org/Repo` and print how to start Claude Code |

Plus `scripts/csa-claude-connectors.py` — disables chosen claude.ai connectors (Gmail, Google
Calendar, Google Drive by default) in Claude Code everywhere, so the CSA Google MCP servers are
used instead. Report-only unless `--apply`; backs up and writes atomically
([#129](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/129)).

**`*-plugins` is named badly on purpose.** It installs and upgrades every CSA MCP server, not
just plugins. The filename stays because it is in documented one-liners that fetch `HEAD`; the
strings were all corrected to say "CSA plugins **and MCP servers**"
([ADR-003](DECISIONS-ADR.md), from
[#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89)).

AI skills, MCP server catalogues and per-project tooling live in other repositories.

### Layout

```
scripts/
  csa-plugins.txt            # public plugin list, fetched from HEAD at runtime
  csa-plugins-internal.txt   # CSA-internal plugin list, same
tools/
  check-all.sh               # everything CI runs, locally, in one command
  check-*.py                 # eleven repo-specific checks; all eleven also run in CI
  sweep-csa-sources.sh       # weekly drift sweep (network + gh; NOT in check-all.sh)
tests/
  test_*.py                  # nine standalone executables — run one directly with python3
  NativeWrappers.Tests.ps1   # Pester; the only suite that needs real 5.1 to mean anything
docs/
  periodic-sweep.md          # the weekly sweep runbook
  mcp-servers.md             # historical third-party MCP config reference
archives/                    # previous script versions, for reference
```

Project documents — `BUSINESS-CASE.md`, `GOALS.md`, `RACI.md`, `DECISIONS-ADR.md`,
`FRICTION.md`, `WAITING-FOR.md`, `TODO.md`, `OPERATIONAL-RESOURCES.md`,
`BACKUP-RESOURCES.md` — are indexed in [`README.md`](README.md).

---

## Script versioning

Every script declares a version near the top: `SCRIPT_VERSION="YYYY.MMDDHHMM"` in bash,
`$ScriptVersion = "YYYY.MMDDHHMM"` in PowerShell. **Minutes, not seconds** — UTC.

```bash
python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y.%m%d%H%M'))"
```

`tools/check-script-versions.py` refuses a changed script that did not bump, comparing the merge
base against the **working tree** — so it catches the omission locally, before a commit, rather
than in CI. A version-only change is legitimate on its own.

---

## The target runtime is Windows PowerShell 5.1

Windows 11 ships 5.1. PowerShell 7 is an optional install and this installer does not perform
it ([ADR-002](DECISIONS-ADR.md)). Everything in `scripts/*.ps1` must parse and run under 5.1.

**7-only syntax fails at *parse* time**, so the whole file is dead rather than one branch of it:
the ternary `? :`, `??`, `??=`, `?.`, and the pipeline chain operators `&&` / `||`.
`tools/check-powershell-native.py` rejects all five.

Other 5.1 facts that have each cost a defect:

- **`Sort-Object` is not stable.** `-Stable` is 7-only. Three sign-in items once rendered in
  reverse order on the runtime that ships; stability is now built from an explicit
  read-position key.
- **`Set-Content -Encoding utf8` writes a BOM** (`ef bb bf`). Credential files are written with
  `[System.IO.File]::WriteAllText` and a `UTF8Encoding $false` instead. Note the asymmetry:
  `[System.IO.File]::ReadAllText` *strips* a BOM, so a round-trip hides the problem.
- **`$null` is dropped from a native command's argv**, so a `$null` argument shifts every
  argument after it.

### The `Invoke-Native*` wrappers, and why removing them is a mistake

In 5.1, a native command writing to **stderr** becomes a terminating `NativeCommandError` under
`$ErrorActionPreference = 'Stop'` *whatever its exit code*. npm writes deprecation warnings to
stderr routinely, so a script would die on a **successful** run.

Measured on 5.1.26100, in the shape these scripts actually run — `& ([ScriptBlock]::Create(…))`
invoked from a `'Stop'` session, which is how one script here runs another:

| form | result |
|---|---|
| bare call | kills the script **and its caller** |
| `\| Out-Null` | kills the script and its caller |
| `$x = cmd` (assignment) | kills the script and its caller |
| `cmd 2>$null` | kills the script and its caller |
| `cmd *> $null` | kills the script and its caller |
| `$x = cmd 2>&1 \| Out-String` | kills the script and its caller |
| any of the above, after `EAP = 'Continue'` | **all six survive** |

So **no form of redirection helps** — `2>$null` hides the text, not the termination. The trap
that makes this hard to believe: standalone, the same error is only *statement*-terminating, so
every form above looks survivable in isolation. Inside `& ([ScriptBlock]::Create(…))` the whole
invocation is **one statement in the caller**, so an error that merely ends a statement in the
callee ends the entire call. *Measure it the way it is deployed or not at all.* (This table
exists because the note it replaced had the conclusion backwards — twice, once in each
direction.)

`check-powershell-native.py` enforces that every native command (`winget`, `npm`, `gh`,
`claude`, `git`, `icacls`, …) goes through a wrapper or a `try/catch`. Its first run found 14
unguarded calls, 13 of them in `windows-work-tools.ps1`.

### What local `pwsh` proves, and what it does not

`brew install powershell` gives PowerShell **7**, which differs on precisely the behaviour the
wrappers exist for:

| | stderr on a **successful** command | non-zero exit |
|---|---|---|
| **Windows PowerShell 5.1** | **terminates** ← the bug | terminates |
| pwsh 7, `$PSNativeCommandUseErrorActionPreference=$false` *(default)* | survives | survives |
| pwsh 7, same flag `$true` | **survives** | terminates |

In pwsh 7 stderr output is not an error condition under **any** setting — the flag only makes a
non-zero *exit code* respect the preference.

**So local pwsh will tell you the wrappers are unnecessary, and it will be wrong.** Do not
remove them on the strength of a green run on macOS. Local pwsh is genuinely useful for parse
checking, PSScriptAnalyzer and Pester tests of pure logic. It is not a substitute for running
the installers on Windows.

### What has actually been run on Windows

On 2026-09-15, on Windows 11 26200 under real 5.1 (5.1.26100.9444), against the live machine:
`windows-update.ps1`'s `Test-Preconditions`, `Save-Snapshot`, `Show-Preflight` (including the
live network plugin comparison), `Show-Summary`, and the `pip list --outdated --format=json`
parse; plus `windows-work-tools.ps1`'s `Setup-GitIdentity`. The technique was to strip the
trailing `Main` invocation and dot-source the script, so the real shipping code ran without the
mutating half.

**Still never run: any installer end to end, and any actual upgrade** — `winget upgrade --all`,
`npm update -g`, `claude update`. The parts that decide *what* to do are tested on the target
runtime; the parts that *do* it are not.

### What a Windows authoring machine proves, and what it does not

The same lesson from the other direction. This repo was authored on a Mac; the suite first ran
on Windows on 2026-09-15 and ten of eleven checks failed — none because the scripts were wrong:

| | macOS / Linux | Windows |
|---|---|---|
| `Path.read_text()` default encoding | UTF-8 | **cp1252** — dies on bytes `0x81 0x8D 0x8F 0x90 0x9D` |
| `Path.chmod(0o755)` | mode `0o755` | mode **`0o666`** — Python cannot set the exec bit |
| `test -x stub` under Git Bash | true | **false** — yet the stub still runs |
| bare `"bash"` via `subprocess` | `/bin/bash` | **`System32\bash.exe`**, the WSL launcher |
| `shutil.which("bash")` | `/bin/bash` | `…\Git\usr\bin\bash.EXE` — *disagrees with the line above* |
| `pty.fork()` | works | **absent** |

Four consequences worth keeping:

- **Pin every `read_text`/`write_text` to `encoding="utf-8"`.** Not `errors="replace"`: that
  decodes cp1252 without raising and substitutes U+FFFD, so `check-duplication.py` would compare
  two functions *after* corrupting both identically — they differ in a non-ASCII character and
  still compare equal. A check that cannot fail, again. cp1252 chokes on only five byte values,
  so a file passes or fails on whether it happens to contain one; three checks here were passing
  by luck.
- **Resolve `bash` absolutely, never as a bare name.** `shutil.which` and `CreateProcess` resolve
  `"bash"` to *different binaries*, and the one `CreateProcess` picks is the WSL launcher, which
  exits 1 with a UTF-16LE "no installed distributions" message — which reads as the test failing.
  `tests/*.py` share a `_posix_bash()` helper that prefers Git Bash and refuses anything under
  `System32`; `CSA_TEST_BASH` overrides it.
- **The stub-executable technique still works.** Tests intercept `npm`/`gh`/`claude` with
  shebang'd stubs on a stub-only PATH. Windows cannot mark them executable and `test -x` agrees,
  but MSYS2 runs them anyway by sniffing the `#!`. Measure before assuming a POSIX technique is
  unavailable.
- **`tests/test_prompt_visibility.py` is the one genuine casualty** and exits **77**, not 0. It
  needs a real pty on both ends; three cheaper harnesses each produced a false negative.
- **Git Bash has no `pgrep` and no `ps -o ppid=`**, so the macOS running-client detection cannot
  be exercised from a Windows box at all ([FRICTION-003](FRICTION.md)).

**So a green run on Windows is worth slightly less than a green run on macOS** — one fewer check
— and `check-all.sh` says so explicitly rather than leaving you to remember.

---

## Conventions

### macOS (bash)

- Target macOS only (checks `uname -s`). **macOS ships bash 3.2**, so no `declare -A`.
- `set -euo pipefail`.
- Idempotent, and interactive by default: show the plan, ask, then act.
- `NONINTERACTIVE=1` for CI/automation — also auto-detected when `$CI` is set or stdin is not a
  TTY.
- Output helpers `info` / `warn` / `error` / `success` / `abort` (abort = error + exit 1).
  Colours are stripped when stdout is not a TTY.
- Never run as root (`$EUID`), except inside a container (`/.dockerenv`, `/run/.containerenv`)
  for CI.
- **An assignment from a pipeline needs a guard.** Under `pipefail` + `set -e`,
  `x="$(cmd | head -1)"` kills the script when `cmd` fails. Write `… )" || x=""`.
  `check-pipeline-assignments.py` enforces it, and the failure is silent — the script dies at
  that line with nothing printed.

### Windows (PowerShell)

- Target Windows 10/11, require winget. `$ErrorActionPreference = 'Stop'`.
- Same helper pattern: `Write-Info`, `Write-Success`, `Write-Warn`, `Write-Err`, `Abort`,
  `Has-Command`.
- Every native command through an `Invoke-Native*` wrapper (above).

### Install strategy

Homebrew/winget for system tools and desktop apps; the native installer for Claude Code (it
auto-updates); npm for the Codex and Gemini CLIs and for Wrangler; **uv for Python**.

- **Python comes from uv, Homebrew/winget as fallback**
  ([DEC-012](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/DECISIONS.md)).
  `install_uv` runs before `install_python`. **`--python` is not optional** on any `uv tool`
  call: without it uv picks its own managed default and ignores both PATH and anything the
  installer provisioned — which is how four CSA servers once landed on Python 3.10, the floor of
  `requires-python`, chosen by nobody.
- **`install_python` provisions nothing when the machine already has a floor-clearing Python**,
  deliberately, so an existing install is never churned. The honest claim is *clean machines
  converge on `CSA_PYTHON_PREFERRED`*, not *every machine runs the same version*.
- **uv creates no PATH shims** for interpreters it manages (measured, uv 0.12.10), so
  `find_usable_python` / `Find-UsablePython` probe PATH first and then ask `uv python find`
  directly. PATH probing alone would miss a good uv Python and install a second one.
- **Floors are derived from the consumer that asks for most, never picked.**
  `CSA_PYTHON_MIN=3.10` from CSA-Document-Pipeline's `requires-python`; the Node floor of **22**
  from Wrangler's `engines.node`. Both enforced on both platforms.
- **Node is pinned to the LTS line on both platforms**
  ([#56](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/56)):
  `brew install node@24`, `winget install OpenJS.NodeJS.LTS`.

  **`node@24` is keg-only, and three things about it were measured on a `macos-latest` runner
  rather than reasoned about.** `brew install node@24` **exits 1 even when it succeeds** — it
  installs, prints its Summary, then the keg-only caveat, and returns non-zero — so
  `install_node` checks whether the formula is installed rather than trusting the status; the
  first version of this aborted a perfectly good install. Keg-only is literal: immediately
  after a successful install there is **no `node` on PATH at all** until
  `brew link --overwrite --force node@24` runs, which is required, not defensive. And npm's
  global prefix is the Homebrew prefix in every state, so `wrangler`, `codex` and `gemini`
  installed with `npm -g` survive the switch. The unversioned formula is **removed**, not
  unlinked, because `brew upgrade` would otherwise relink it and flip the machine back to
  Current between runs.

### uv's exit codes are not states

Measured 2026-10-01, with an entry point held open by a running client:

| case | exit | what actually happened |
|---|---|---|
| dependency-only upgrade | 0 | upgraded |
| the tool's own version changes | **1** | **already upgraded** — uv's `.exe` is a version-free trampoline, so the copy it failed on was byte-identical |
| `--force` rebuild | **2** | **`site-packages` already deleted**, leaving a husk |

A husk is `pyvenv.cfg` + `Scripts/` with no importable package, which `uv tool list` reports as
*"Failed find package"* while exiting 0. Four working servers became four husks in one run that
way. So: **ask the environment, never the exit code**, and refuse a rebuild before calling uv if
any entry point is held. Generalised fleet-wide as
[`an-exit-code-is-not-a-state`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/an-exit-code-is-not-a-state.md).

---

## Duplicated state: the six-script lists

`CSA_MARKETPLACES`, the marketplace-name → repo mapping, `CSA_INTERNAL_SETUPS`, and the
constants `CSA_MCP_NAME` / `CSA_MCP_URL` / `CSA_MCP_GATE_REPO` are duplicated across **six**
scripts: `macos-ai-tools.sh`, `macos-update.sh`, `macos-plugins.sh`, `windows-ai-tools.ps1`,
`windows-update.ps1`, `windows-plugins.ps1`.

**Change all six, and bump each file's `SCRIPT_VERSION`.** The mapping is a
`plugin_marketplace_repo` function in the `.sh` files (a function because bash 3.2 has no
associative arrays) and a `$PluginMarketplaceRepos` hashtable in the `.ps1` files.

`tests/test_internal_setup_lists.py` asserts the six copies of `CSA_INTERNAL_SETUPS` agree, and
says in its own docstring what it cannot do: compare them against the private gate repo. The
installer closes that half at run time, reporting drift in both directions
([#95](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/95)).

**The plugin lists are single-source** and are the exception: `scripts/csa-plugins.txt` and
`scripts/csa-plugins-internal.txt` are fetched from `HEAD` at runtime, so a list-only change
needs one commit and **no** script edit or version bump.

All scripts also duplicate their output helpers, precondition checks and utilities. The two
macOS install scripts additionally share `install_xcode_cli_tools`, `install_homebrew`,
`install_node`, `setup_gh_auth`, `setup_git_identity`. **When changing shared logic, update
every file that uses it** — `check-duplication.py` enforces byte-identical behaviour.

---

## The guard layer

Eleven checkers in `tools/` and ten test files in `tests/`. **`./tools/check-all.sh` mirrors CI
exactly** — run it before pushing.

A guard here is added only for a mistake that actually shipped, names its issue in the file, and
carries a self-test that breaks its own rule on purpose ([ADR-005](DECISIONS-ADR.md)). Nine of
eleven comply; the two that do not are logged as G1 in [`TODO.md`](TODO.md).

Worth knowing individually:

- **`check-duplication.py`** — a function duplicated across scripts must be byte-identical in
  behaviour (comments and whitespace ignored). Deliberate differences live in its `PER_SCRIPT`
  map with a reason. Its first run found twelve already-drifted functions.
- **`check-parity.py`** — the complement: it catches what duplication structurally cannot, a
  function that is **absent**. Every macOS script needs a Windows counterpart, and the two
  `main()` step lists must match once mapped through its `EQUIV` table. Compared as *sets*,
  since the platforms order their base layers differently. A one-sided step goes in
  `PLATFORM_ONLY` or `PER_PAIR` with a reason, and **an allowlist entry matching nothing is
  itself reported** — an exception for a step that no longer exists has stopped checking without
  failing. Run against the scripts before #69 it reports exactly the three gaps that shipped.
- **`check-plan-covers-steps.py`** — every step `main()` runs must be named in the plan the user
  agreed to, across all six entry points. It imports `EQUIV` from `check-parity.py` so the two
  cannot disagree about what counts as a counterpart. `--rev <ref>` audits a historical commit;
  before #76 it reports nine findings, six of them the defect found by hand three weeks later.
  **It checks presence only** and says so — it cannot tell you a row's wording is still true.
- **`check-powershell-native.py`** — the wrapper rule above, plus the five 7-only syntax forms.
  It self-tests *before* it reports, because two separate bugs here each turned it into a check
  that printed *"all native calls are guarded"* no matter what.
- **`check-todo-citations.py`** — `TODO.md` cites findings by function name, never by line
  number, and every cited function must still exist. The original `file:line` citations had all
  rotted within seven months, one by 243 lines onto unrelated code about the same topic — worse
  than an obviously wrong citation.
- **`check-line-endings.py`** — nothing served to a shell may have a CR in the index. Reads the
  `i/` column of `git ls-files --eol`, where the path is whatever follows the **last tab**;
  nothing else on the line is reliably delimited.
- **`check-log-coverage.py`** — every screen-output helper routes through the logger, so the
  debug log contains what the user saw.
- **`check-script-versions.py`** — above.
- **`check-paste-safety.py`**, **`check-shell-tail-conditionals.py`**,
  **`check-pipeline-assignments.py`** — a README must not ask for a multi-line paste; no
  tail-position conditional under `set -e`; no unguarded pipeline assignment.

### What `check-all.sh` proves, and what it does not

It ends by asserting **the checks did not change the working tree** — `git status --porcelain
--untracked-files=all` before and after, so it passes mid-edit and fails only on what the run
itself did. Every other assertion once passed while `test_version_floors.py` installed a 167 MB
Python into the repo on each Windows run
([#67](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/67)); `git status` found it,
not the suite.

**Exit 77 means "could not run here"** and is counted — and **named** — separately from passes
([ADR-006](DECISIONS-ADR.md)). A check that could not run has not passed. Read the **tail** of
the output and the exit code; do not grep for `all checks passed`, which individual checkers
also print, and do not pipe through `head`. That is exactly how `main` stayed red for six
commits.

Every test extracts the code under test out of the shipping script rather than copying it, so a
test cannot drift from what runs. A copy *looks* equivalent and is the defect
`tests/test_summary_interpreter.py` was built to avoid after mutation testing showed its first
version passing while the guard it tested had been deleted.

The PowerShell half needs three things installed, or those steps print `skipped`:

```bash
brew install shellcheck powershell
pwsh -NoProfile -c 'Install-Module PSScriptAnalyzer -Scope CurrentUser'
pwsh -NoProfile -c 'Install-Module Pester -RequiredVersion 5.7.1 -Scope CurrentUser'
```

**Pester is pinned to 5.7.1, deliberately.** 6.1.0's manifest claims 5.1 support, but under real
5.1 it aborts the whole run with *"a 'break' or 'continue' statement … escaped from your code"* —
its own message cites pester/Pester#2669 — with no `break` anywhere in the suite. Both CI jobs
and `check-all.sh` pin the same version so the framework is not itself a source of divergence.
Being current matters less than matching CI.

Any single test runs on its own, which is the fast loop:

```bash
python3 tests/test_version_floors.py
```

On Windows the shell-driving tests find Git Bash themselves; `CSA_TEST_BASH` overrides. They
must never be handed a bare `bash`.

---

## Script execution flow, and the plan

All scripts follow `main` → preconditions → preflight (show the plan) → confirm → steps →
summary. `macos-ai-tools.sh` adds a migration layer: `detect_migrations()` during preflight,
then `migrate_*()` before each tool's install. The `*-update` scripts snapshot versions before
showing the plan.

**The plan must name what actually runs.** These scripts are "show the plan → confirm → act", so
a plan line describing something other than the step behind it is a correctness bug — the user
consented to the wrong thing. Three had drifted and were fixed together: Python said "install
via Homebrew" long after uv became the provider; the macOS Node line hid the only destructive
step in the script; and the Windows plan never mentioned `uv` or the document preflight deps at
all, though `Main` installed both.

`check-plan-covers-steps.py` now catches the *absent* case. It cannot catch stale **wording**,
so when you add a step to `main()`, add its plan line in the same change.

### The to-do ledger

The closing instructions used to be scattered across five styles and 200 lines, with the
terminal command printed as the primary route when it is the fallback
([#110](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/110)).

Now any script or nested setup script appends to `CSA_TODO_FILE`, tab-separated:

```
<order>\t<title>\t<in-claude>\t<terminal>
```

Orders: **10** restart, **20** sign in, **30** needs someone else, **40+** the installer's own.
Items are de-duplicated on the item, and the list renders **last** — nothing may print after it
or it stops being the final thing on screen, which was the original defect.

**`CSA_TODO_FILE` is set by the two `*-ai-tools` installers only.** The `*-plugins` and
`*-update` scripts run the same nested setup scripts with no ledger, so
`Add-CsaTodo` / `csa_todo_add` **return false there** and every caller must print the
instruction itself. That is not an edge case — `*-plugins` is the recommended fast path. A
Windows user once missed "restart Claude Desktop" entirely because three calls in one script
discarded that return.

`Sort-Object` is not stable on 5.1, so ordering is built from an explicit read-position key.

---

## Debug mode

`CSA_DEBUG=1` makes any script write a timestamped, mode-0600 log to `$HOME` —
`desktopsetup-YYYYMMDD-HHMMSS.log` — while still printing to screen. An environment variable
rather than a flag, because the documented invocation is `curl … | bash` / `irm … | iex`, which
passes no argument vector at all.

Two mechanisms, for a reason:

- **PowerShell:** the five `Invoke-Native*` wrappers log. Nothing at the call sites changed,
  because `check-powershell-native.py` already guarantees every native command goes through one
  — the wrappers were already the choke point.
- **bash:** `exec > >(csa_redact | tee -a "$CSA_LOG") 2>&1`, process-wide. There is no
  equivalent choke point, and retrofitting one onto ~1000 lines of direct calls would capture
  only the calls somebody remembered. Verified on bash 3.2.57: no output is lost on a clean
  exit, an `exit N`, or an uncaught failure under `set -e`.

`CSA_LOG` is **exported**, so a nested setup script appends to the *same* file. One file per run:
the person debugging is being asked to send a log, and "send both of them, and mind the
timestamps" is how half a report goes missing. The bash redactor is line-buffered (`sed -l`, or
`-u` on GNU) so the parent's output does not sit in the pipe while the child writes ahead of it.

**What the log contains, and the boundary.** Screen output is logged too, because a log of
commands without their output misdiagnoses
([#96](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/96)), and prompts are logged
*before* they block. A state snapshot records existence, sizes, timestamps, versions and
**key names** — never a file's contents and never an environment **value**, because
`claude_desktop_config.json` holds inlined secrets and the log is designed to be emailed.

Credential shapes are redacted **keeping the key**: `client_secret: <redacted>` still says which
line failed. ANSI colour is stripped from the file only. Base64 blobs are replaced by a line
count, a byte count and a SHA-256, because 82% of one log was base64
([#121](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/121)). The OAuth client
fetch is excluded from logging **by construction** rather than by pattern, because a base64 blob
has no shape to match.

---

## The CSA contracts

All four are **silent by default**: a user outside CSA should not see chatter about repos they
cannot see. Shared across the same six scripts.

### Plugin marketplace registration

1. If `claude` or `gh` is missing, or `gh` is unauthenticated, return silently.
2. For each `CSA_MARKETPLACES` entry: skip if already registered (parsed from `claude plugin
   marketplace list`); probe with `gh api repos/$repo` and silently skip on non-zero; otherwise
   `claude plugin marketplace add`.
3. Print only on an actual add, or on an `add` error — with the captured stderr indented
   underneath, so the schema/auth/network reason is visible.
4. The updaters additionally run `claude plugin marketplace update`, which always prints, since
   refreshing is their purpose.

### Plugin install

Driven by the two list files, fetched from `HEAD`. Entries are `<plugin>@<marketplace>`; blank
and `#` lines ignored. Pass 1 ensures each referenced marketplace is registered (public ones
unconditionally, CSA ones `gh`-probed). Pass 2 builds the install list without touching the
network. Pass 3 announces `Installing N plugin(s):` then prints `  + <plugin>` or `  ! <plugin>`
per item, so there is forward motion during a long install. Silent when nothing needs doing.

The preflight preview (`install_plugins_preview` / `Show-PluginsPreview`) compares the lists
against `claude plugin list` without `gh`-probing, so its count is an **upper bound**.

### The hosted CSA MCP server

`csa-mcp` → `https://cloudsecurityalliance.org/mcp`, HTTP transport, OAuth 2.1 + PKCE, Claude
Code only for now.

The server answers unauthenticated callers, so the gate is not about access — registration is
gated behind a `gh`-probe of `CloudSecurityAlliance-Internal/CSA-Plugins` as a CSA-membership
proxy, because a public bootstrap should only auto-wire CSA tooling into CSA-eligible accounts.
If already registered, return silently: re-running `claude mcp add` would either error or
invalidate the user's authenticated OAuth session.

**Two different gates, and the wording keeps them apart.** *Registration* is gated on GitHub
CSA-Internal access; *authenticating* to the running server needs a **free** CSA account from
`https://cloudsecurityalliance.org/` via the site's `Sign in or Sign Up` control. The account
unlocks member tiers rather than making the server work.

### Local CSA MCP servers — `setup_csa_internal_tools` / `Invoke-CSAInternalSetup`

A separate mechanism from the hosted server, and the **third** place a list drifts. Four servers
today: `csa-google-workspace`, `csa-google-gmail-calendar`, `csa-skilljar`, `csa-zendesk`.

The function `gh`-probes the gate repo, then fetches one setup script per server from
`CloudSecurityAlliance-Internal/CSA-Plugins/internal-setup/` and executes each with
`CSA_NESTED=1`. **The servers live in their own public repos; the setup scripts live in the
private gate repo because they carry CSA's OAuth client.** That repository must never be made
public.

Wire a server up by appending its `<name>-setup.{sh,ps1}` to `CSA_INTERNAL_SETUPS` — in all six
scripts, with a version bump each. The loop uses `continue`, not `return`, so an absent setup
script cannot disable the servers listed after it — which is also why a stale list produced **no
output at all** until the drift report was added.

---

## Periodic source sweep

Nothing in CSA notifies this repo when new tooling appears, so **run
`./tools/sweep-csa-sources.sh` weekly**, by hand, on a machine whose `gh` has CSA-Internal read
access. **Nothing runs it automatically.**

It reports four kinds of drift against four extension points: unregistered **marketplaces**
(`CSA_MARKETPLACES`, 6 scripts), published **plugins** nobody installs (the `.txt` files,
list-only), **MCP servers** ready to wire (`CSA_INTERNAL_SETUPS`, 6 scripts), and **version
floors** that no longer match upstream — the one thing here that can rot without anyone touching
this repo. Exit `0` no drift, `1` drift, `2` could not complete; `2` means *"I learned
nothing"*, never *"no drift"*.

Deliberately **not** in `check-all.sh`: it needs the network and a CSA-Internal token, and a
check that cannot pass in CI is a check that gets deleted.

**Do not make its probing parallel.** An early version used `xargs -P 12` and reported three
repos as lacking `marketplace.json` when all three have it — a probe that fails under load is
indistinguishable from a repo that genuinely lacks the file, so the sweep under-reports and the
failure looks exactly like success. Runbook: [`docs/periodic-sweep.md`](docs/periodic-sweep.md).

---

## Bootstrap commands

Every one carries `Cache-Control: no-cache`. Keep it.

```bash
# macOS — work tools / AI tools / update everything / CSA layer only
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-plugins.sh)"
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

```powershell
# Windows — work tools / AI tools / update everything / CSA layer only
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-update.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-plugins.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```

The macOS `bash -c "$(...)"` form — **not** a pipe — is required to preserve interactive stdin.

---

## Three habits that would have prevented most of this repo's defects

1. **Ask the environment, not the exit code.** Eight occurrences and counting.
2. **Know what your check ran on.** Its scope is never in its output. A true sentence about an
   empty set reads exactly like success.
3. **A verification step is itself a check**, and inherits every weakness of one — its own
   scope, its own runtime, its own ability to fail. A control that cannot fail proves nothing.

Both generalised at fleet level:
[`an-exit-code-is-not-a-state`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/an-exit-code-is-not-a-state.md),
[`a-green-check-is-only-evidence-about-what-it-ran-on`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/a-green-check-is-only-evidence-about-what-it-ran-on.md).
