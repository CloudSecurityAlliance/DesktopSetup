# Engineering notes

**The repository's facts, for whoever is editing it** — human, Claude Code, Codex, Gemini or
anything else. [`AGENTS.md`](AGENTS.md) holds the rules every AI agent follows and points here;
`CLAUDE.md` and `GEMINI.md` are one-line pointers to it. See [ADR-004](DECISIONS-ADR.md) for why
the facts live in one copy.

Read [`BUSINESS-CASE.md`](BUSINESS-CASE.md) first if you want to know *why* any of this exists.
This file is *how*.

---

## What is in here

| Section | Read it when |
|---|---|
| [`main` IS the release](#main-is-the-release) | before merging anything |
| [What the scripts are](#what-the-scripts-are) | orienting; ten scripts, five pairs |
| [Script versioning](#script-versioning) | you changed a script — the format is `YYYY-MM-DDTHH:MMZ` |
| [The target runtime is Windows PowerShell 5.1](#the-target-runtime-is-windows-powershell-51) | touching any `.ps1`. The `Invoke-Native*` tables are here |
| [Conventions](#conventions) | writing new code in either language |
| [Duplicated state: the six-script lists](#duplicated-state-the-six-script-lists) | adding a marketplace, plugin or MCP server |
| [The guard layer](#the-guard-layer) | adding a check, or wondering what `check-all.sh` proves |
| [Script execution flow, and the plan](#script-execution-flow-and-the-plan) | adding a step to `main()`. The to-do ledger is here |
| [Debug mode](#debug-mode) | diagnosing a user's run, or adding output |
| [The CSA contracts](#the-csa-contracts) | anything touching plugins or MCP servers, or what a rerun does to a registration |
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
| `macos-ai-tools.sh` | `windows-ai-tools.ps1` | The AI layer: Claude, ChatGPT, Gemini and Copilot desktop apps ([why each source](docs/desktop-ai-apps.md)); Claude Code, Codex and Gemini CLIs; uv, Python, Node; the doc toolchain; plugin marketplaces; the CSA MCP server; and every internal CSA MCP server |
| `macos-update.sh` | `windows-update.ps1` | Update everything — Homebrew/winget, npm globals, pip, `claude update` — then the plugin and MCP sync. Snapshots versions first, for rollback |
| `macos-plugins.sh` | `windows-plugins.ps1` | **The CSA layer only**: plugins *and* every CSA MCP server, with no Homebrew/winget/npm/pip. The fast path |
| `clone-and-claude.sh` | `clone-and-claude.ps1` | Clone a CSA repo into `~/GitHub/Org/Repo` and print how to start Claude Code |

Plus `scripts/csa-claude-connectors.py` — disables chosen claude.ai connectors (Gmail, Google
Calendar, Google Drive by default) in Claude Code everywhere, so the CSA Google MCP servers are
used instead. Report-only unless `--apply`; backs up and writes atomically
([#129](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/129)).

And `scripts/csa-mcp-registrations.py` — finds every registration of the four CSA MCP servers in
Claude Code, Claude Desktop, Codex and Gemini, re-points a dead one at the standard binary after
consent, and can check that a server answers. The three macOS entry points fetch it from `HEAD`
at run time; no Windows script runs it yet
([#184](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/184)). See
[Registration audit and repair](#registration-audit-and-repair).

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
  csa-mcp-registrations.py   # CSA MCP registration audit and repair, fetched from HEAD at runtime (macOS)
tools/
  check-all.sh               # everything CI runs, locally, in one command
  check-*.py                 # fourteen repo-specific checks; all fourteen also run in CI
  sweep-csa-sources.sh       # weekly drift sweep (network + gh; NOT in check-all.sh)
tests/
  test_*.py                  # seventeen standalone executables — run one directly with python3
  NativeWrappers.Tests.ps1   # Pester; the only suite that needs real 5.1 to mean anything
  DesktopApps.Tests.ps1      # Pester; windows-update.ps1's wait before replacing a running app
  NpmGlobals.Tests.ps1       # Pester; the npm installers run install -g <pkg>@latest (#153)
  ConfirmStep.Tests.ps1      # Pester; end of input at the consent prompt is a no
docs/
  desktop-ai-apps.md         # where each desktop AI app comes from, and how it stays current
  periodic-sweep.md          # the weekly sweep runbook
  mcp-servers.md             # historical third-party MCP config reference
archives/                    # previous script versions, for reference
```

Project documents — `BUSINESS-CASE.md`, `GOALS.md`, `RACI.md`, `DECISIONS-ADR.md`,
`FRICTION.md`, `WAITING-FOR.md`, `TODO.md`, `OPERATIONAL-RESOURCES.md`,
`BACKUP-RESOURCES.md` — are indexed in [`README.md`](README.md).

---

## Script versioning

Every script declares a version near the top: the UTC time of the change, ISO 8601 to the
minute. `SCRIPT_VERSION="2026-10-26T05:04Z"` in bash, `$ScriptVersion = "2026-10-26T05:04Z"`
in PowerShell. **Minutes, not seconds**, and always `Z`. It is printed as is, with no `v`
in front, in the banner and the debug log, so a log says when its code was written.
Until 2026-10-26 it was `YYYY.MMDDHHMM`; the checker still reads that form, so the
switch could be checked as moving forwards, but refuses it as a new value.

```bash
python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'))"
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
the npm global updates, `claude update`. The parts that decide *what* to do are tested on the target
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
- **Git Bash has no `lsof` and no `ps -o ppid=`**, which the macOS running-client detection
  (`running_ai_clients`) reads. `tests/test_running_clients.py` runs its logic against stubs, so
  that part runs on Windows too; its live check of the real `pgrep` and `lsof` needs a Mac
  ([FRICTION-003](FRICTION.md)).

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
  ([DEC-012](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/DECISIONS.md)).
  `install_uv` runs before `install_python`. **`--python` is not optional** on any `uv tool`
  call: without it uv picks its own managed default and ignores both PATH and anything the
  installer provisioned — which is how four CSA servers once landed on Python 3.10, the floor of
  `requires-python`, chosen by nobody.
- **macOS: the installer always ensures the uv-managed 3.14 standard build** (#179, decision
  D3). `install_python` runs `uv python install 3.14` on every run, a no-op when it is present,
  with `brew install python@3.14` as the fallback. It adds an interpreter (and uv's
  `~/.local/bin/python3.14` shim, below) and touches nothing else: PATH's `python3`, Homebrew's
  Pythons and every other uv interpreter are left as they were. `install_uv` keeps uv current:
  `brew upgrade` when Homebrew owns it, `uv self update` otherwise (it fails on a Homebrew
  install); a failed update only warns.
- **macOS: one resolver names the CSA Python, and verifies it by running it.**
  `python_is_csa_build` accepts an interpreter only when it runs, reports `CSA_PYTHON_PREFERRED`,
  and has `Py_GIL_DISABLED` falsy. `find_csa_python` tries
  `uv python find --system --managed-python 3.14`, then every `variant == "default"` entry of
  `uv python list --only-installed --managed-python 3.14 --output-format json`, then Homebrew's
  `opt/python@3.14`, and prints the first that verifies. **It never installs anything**,
  because the preflight calls it before consent; `ensure_csa_python` is the one that installs,
  and prints only the path on stdout. PATH is never consulted: Homebrew's 3.15 and an active
  venv's 3.13 are both on PATH on real machines. `tests/test_csa_python.py` pins all of it.
  - **`--system` is required.** Measured on uv 0.13.7: with `VIRTUAL_ENV` set,
    `uv python find` without it returns the active venv's interpreter.
  - **`UV_PYTHON_PREFERENCE` is dropped for those two calls**, in a subshell. Measured on uv
    0.13.7: exported at any value, it makes both `find` and `list` refuse `--managed-python`
    (exit 2), so the resolver found nothing with the standard 3.14 installed. `uv venv`,
    `uv pip` and a no-op `uv python install` are unaffected, and `UV_MANAGED_PYTHON` /
    `UV_NO_MANAGED_PYTHON` do not conflict. An empty listing (`[]`) is not handed to a parser,
    because `/usr/bin/python3` on a Mac without the Command Line Tools opens an install dialog,
    before consent. The stub `uv` in `tests/test_csa_python.py` refuses the same combination,
    and a `find` or `list` missing any of its flags; `real_uv_resolver` runs the resolver
    against real uv (required in CI's `venv-macos` job).
  - **The path is returned as uv prints it:** the minor-version directory
    (`cpython-3.14-<platform>`, a link uv points at the current patch release), never the
    resolved patch directory (`cpython-3.14.10-<platform>`), which a patch upgrade replaces.
  - **uv 0.13.7 creates a `~/.local/bin/python3.14` shim** (measured 2026-11-10; the earlier
    "uv creates no PATH shims" was measured on uv 0.12.10 and is out of date), and its JSON
    listing may report that shim as `path`, with the managed interpreter as `symlink`. The
    resolver tries `symlink` first and accepts either only if it verifies, so nothing depends
    on whether a shim exists.
- **Windows still resolves Python by floor** (`Find-UsablePython`: PATH first, then
  `uv python find`, provisioning nothing when a floor-clearing Python exists). Its resolver
  moves to the macOS shape in a Windows session
  ([#184](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/184)); until then the
  platforms differ, deliberately (decision D5 of #179).
- **Python is 3.14, and stays there until 3.15 is fully ready.** `CSA_PYTHON_MIN` and
  `CSA_PYTHON_PREFERRED` are both `3.14` on both platforms. That is a CSA policy, not a number
  derived from one consumer
  ([DEC-025](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/DECISIONS.md)).
  A move to 3.15 was reversed on 2026-11-10: `onnxruntime` has no cp315 wheel, and the fleet had
  split. When the CINO decides 3.15 is ready, every CSA repo moves together
  ([CINO-Engineering#312](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/issues/312)).
  The floor was 3.10, from CSA-Document-Pipeline's `requires-python`, until the MCP servers
  declared `>=3.14`.
- **The standard 3.14 build, never the free-threaded 3.14t.**
  - **The trap.** When free-threaded is the only uv-managed 3.14, `uv python find 3.14` returns
    `python3.14t`. One staff Mac had all four CSA servers on it
    ([#179](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/179)).
  - **The fix.** Once the standard 3.14 is also installed (`uv python install 3.14`), the same
    request returns the standard build.
  - **Not `3.14+gil`.** uv 0.13.7 never downloads for a `+gil` request, so it fails on a clean
    machine.
  - **Telling the builds apart.** `uv tool list --show-python` prints the same thing for both
    builds. Ask the interpreter for `sysconfig.get_config_var("Py_GIL_DISABLED")`.
  - **Enforced on macOS for the interpreter the installer names** (`find_csa_python`, above),
    and for `~/.default_venv`, which is rebuilt off 3.14t (below). The CSA tools already on
    3.14t are rebuilt by the private gate repo's setup scripts; `csa_tool_repairs` lists them,
    and why, in the plan's Internal MCP servers row - only the tools a `CSA_INTERNAL_SETUPS`
    entry owns, because a setup rebuilds nothing else. Windows is #184.
- **Node's floor is derived from the consumer that asks for most, never picked:** **22**, from
  Wrangler's `engines.node`. Enforced on both platforms.
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
- **npm updates only what npm installed; npm itself belongs to Node's installer**
  ([#153](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/153)). The force-link
  makes every file under `lib/node_modules/npm/` a symlink into the read-only keg, and npm's
  reify-finish rewrites `node_modules/npm/npmrc` through it. So `npm update -g <pkg>` failed
  with EACCES on every installer re-run (its `|| npm install -g` fallback did the work), and the
  updater's bare `npm update -g` installed a registry npm over Homebrew's link farm, a copy
  `bin/npm` never runs. Now:
  - the installers, on both platforms, run `npm install -g <pkg>@latest`, never `update -g`;
  - `macos-update.sh` lists `npm outdated -g` and `install -g`s each outdated package `@latest`
    in one call, **whoever owns npm updates it** (`npm_owner`, `npm_update_decision`):
    - **Homebrew's own copy** (the link farm into its Cellar) is skipped, because `brew upgrade`
      moves it and npm must not write into the keg;
    - **an nvm Node's npm and corepack, or any prefix you can write to**, are installed
      `@latest` like any other global, as `npm update -g` did. There is no keg there, so the
      EACCES cannot happen. That includes **the unversioned `node` formula's npm**: homebrew-core
      `node.rb` copies npm into `<prefix>/lib/node_modules/npm` as real files and points
      `bin/npm` at that copy, so it is the npm that runs;
    - **a copy in Homebrew's prefix that `<prefix>/bin/npm` does not run** (`npm_runs_copy`
      follows the links to see) is left alone. This is the registry npm an earlier `npm update -g`
      left over node@24's links (#153), and updating it would not change the npm that runs;
    - **a prefix you cannot write to** is left to its owner.

    The plan row (`npm_update_plan`) reads the same decision. It lists what will be installed,
    then one line per skipped package saying why, and calls a copy Homebrew's only when it is;
  - **a package `npm link` put there is skipped**, and named. `npm outdated -g` lists it, and
    `install -g <pkg>@latest` replaces the link with the registry copy where `update -g` left it
    (both measured on npm 11.20). The installers do not check: a linked Codex, Gemini or
    Wrangler is replaced there by the registry copy, judged too rare to guard;
  - **a failed `npm outdated` is never "all current".** It exits 1 both when something is
    outdated and when it failed (measured on npm 11.20: an unreachable registry exits 1 with
    empty stdout under `--parseable`), so the records decide, not the status.

  **`windows-update.ps1` still runs a bare `npm update -g`.** Its rewrite is a separate draft PR
  waiting for a Windows measurement (#184): there `npm.cmd` prefers
  `<global prefix>\node_modules\npm` when it exists, so on a PC where someone ran
  `npm install -g npm`, excluding npm would freeze the npm that runs.

  `tests/test_homebrew_owns_npm.py` (bash, with the pre-#153 code as controls; `--rev 7b6d743`
  reports the defect) and `tests/NpmGlobals.Tests.ps1` (Pester, the Windows installers) pin it.

### `~/.default_venv`: a link to a versioned venv (macOS)

document-pipeline's launchers are bash and probe `$HOME/.default_venv/bin/python3`, so this
venv is where the document deps go. On real Macs it had been built on whatever `python3` PATH
offered: Homebrew's 3.15, a 3.13, uv's 3.14t, or a Cellar path the next `brew upgrade` deletes.

- **One dependency list, and nothing in it may bring in onnxruntime.** `CSA_DOC_PY_DEPS` is
  `pyyaml "pymupdf>=1.24.3,<2" csa-google-workspace`, and it must install: a build without it is
  not a replacement.
  - **Why no onnxruntime** (#179's final review, 2026-11-10, decided on safety and privacy):
    onnxruntime's official macOS and Linux builds from 1.29 on ship Microsoft 1DS telemetry,
    **on by default**: a device id and an event cache under
    `~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime`, uploaded to
    `mobile.events.data.microsoft.com`, off only with `ORT_DISABLE_TELEMETRY=1` set before it
    loads.
  - **pymupdf is pinned below 2.** Unpinned, it resolves to 2.1, which requires onnxruntime,
    pymupdf-layout and pymupdf4llm unconditionally and has no macOS x86_64 wheel; 1.28.2 has no
    dependencies and has Intel wheels. The element is quoted, because `<2` is a redirection.
  - **markitdown (#157) is not installed** (the plan's D6, reversed): markitdown → magika →
    onnxruntime.
  - **What an earlier run left is reported, never removed silently.** A venv that had pymupdf
    2.x keeps onnxruntime, pymupdf-layout and pymupdf4llm after the pin puts 1.x back.
    `default_venv_leftovers`, after every deps install (`install_doc_python_deps`,
    `update_default_venv`), warns and adds the to-do `uv pip uninstall --python
    "<~/.default_venv/bin/python3>" onnxruntime pymupdf-layout pymupdf4llm` (order 44), or
    prints it without a ledger. It says nothing while pymupdf is still 2.x (the deps install
    failed), because removing what pymupdf 2 requires would break it.
  - **Guarded three ways.** `tests/test_python_pins.py` rejects onnxruntime, markitdown or
    magika in any array assignment or on any script line that runs an `install`, and a
    `CSA_DOC_PY_DEPS` without the pymupdf pin; run against 495ad6b's scripts it reports both
    defects. `tests/test_venv_replacement.py` (`doc_deps_pinned`) asserts every install passes the
    pin as one argument.
    `tools/check-doc-deps-resolve.py` resolves the array with real uv (universal, Apple silicon
    on macOS 15, Intel) and fails on onnxruntime; its `--self-test` resolves the list as it
    stood at 495ad6b and must report it. It needs PyPI, so `check-all.sh` skips it (named)
    without uv or network. In CI it has its own workflow, `.github/workflows/doc-deps.yml`, run
    on pull requests touching the two scripts, the tool or the workflow, and weekly (the answer
    can change upstream), and kept out of `lint.yml` so a PyPI outage cannot hide the other
    jobs. The self-test expires the day unpinned pymupdf stops requiring onnxruntime; that is
    the signal to revisit the pin, not a CI bug. Measured: without
    `MACOSX_DEPLOYMENT_TARGET=15.0`, uv's default Apple-silicon target predates onnxruntime's
    macOS 14 wheels, so uv quietly backtracks to pymupdf 1.x and the unpinned list looks clean.

- **The layout, decided by the CINO on 2026-11-10 (#179):** `~/.default_venv` is a **relative**
  symlink to `~/.default_venv-3.14` (`${CSA_VENV}-${CSA_PYTHON_PREFERRED}`), built on the CSA
  Python. Old versioned directories are kept for rollback and never deleted. `~/.zshrc` is
  never edited: a `[ -d ~/.default_venv ]` test follows the link.
- **`venv_rebuild_reason <dir>`** says why a venv must be rebuilt, or exits 1: its Python no
  longer exists (a dangling `bin/python3` is broken, never absent), does not run, is not 3.14, is
  free-threaded, or is **recorded** on a Homebrew Cellar path. Recorded means the first symlink
  hop out of the venv, or `pyvenv.cfg`'s `home`, never `realpath`: Homebrew's
  `opt/python@3.14` is stable across `brew upgrade` though its realpath is in the Cellar, so a
  Homebrew-fallback venv is not rebuilt on every run. A Cellar venv is rebuilt only onto a
  non-Cellar CSA Python; otherwise it is left working, with a warning.
- **`ensure_default_venv`** classifies what is there (`default_venv_state`, which the plan row
  uses too) and repairs it. The plan row (`default_venv_plan`) also asks `find_csa_python`, as
  the run does first, because the Python decides the outcome: `-update` with none installed, or a
  Cellar-pinned venv whose only Python is on a Cellar path too, changes nothing, and the row says
  so instead of naming a rebuild that will not run. That step installs no Python, but for a
  CSA-internal member the same `-update` run's Internal MCP servers step does (the gate repo's
  setup scripts install uv's standard 3.14), and the next `-update` repairs the venv (measured
  in the Task 6 acceptance run); the row says so, and every Internal MCP servers row, in all
  three macOS scripts, names that download. The cases: a real directory (pre-symlink machines)
  is renamed to `~/.default_venv-<X.Y>` (from `pyvenv.cfg`'s `version_info`, which uv writes, or
  `version`, which `python -m venv` writes; `-unknown` without one; a timestamp on a name
  collision); a link to an older version, or a dangling one, is flipped; a link the installer
  did not make is left alone when sound and flipped (naming it) when not; a broken `-3.14` is
  replaced. **Build first, swap last:** when the build fails, nothing has moved.
- **The flip is `ln -sfn` then `mv -h`.** Measured on macOS: a plain `mv newlink
  ~/.default_venv`, where that is a link to a directory, exits 0, changes nothing, and drops
  `newlink` *inside* the old target. `mv -h` replaces the link. (GNU `mv` has no `-h`; the test
  suite's Linux shim maps it to `-T`, the same operation.)
- **Replacing a broken `-3.14` uses `uv venv --seed --relocatable` at `.new-$$`, filled with `uv
  pip` only**, then renames the broken one to `.broken-<ts>` and the new one into place.
  Measured: a venv built at one path and renamed breaks `activate` and every console script,
  which hardcode the creation path; `--relocatable` survives the rename for seed scripts and for
  scripts `uv pip` installs, but not for one the venv's own `pip` installs (exit 127). So
  `csa_venv_pip_install`, whose fallback is that pip, is never used on `.new-$$`. Fresh builds
  go straight to the final path and are not relocatable. Without uv, the broken one is renamed
  away first and `python -m venv` builds at the final path; a failure puts it back.
- **Rebuilt even when it is the active venv** (decision D1). `$VIRTUAL_ENV` is compared with
  `-ef`, never as a string: `activate` records the creation path (`~/.default_venv-3.14`), while
  shells opened before the migration hold `~/.default_venv`. The active shell's directory never
  moves, so nothing dangles; the run adds the to-do *open a new terminal* (order 10).
- **What a rebuild did not bring back is reported:** the top-level packages the old venv had
  beyond `CSA_DOC_PY_DEPS`, read from its metadata (so it works when its interpreter is gone).
  Top-level means nothing in the *old* venv required it, not merely nothing that is gone: an old
  venv on pymupdf 2.1 rebuilt with 1.x otherwise reported `networkx onnxruntime psutil tabulate`
  as the person's own and asked them to reinstall onnxruntime. The report is a to-do with a
  ledger, printed without one. `macos-update.sh` has no `csa_todo_add` at all,
  and in `macos-ai-tools.sh` it returns false when `CSA_TODO_FILE` is unset, so every call is
  guarded: `if declare -F csa_todo_add >/dev/null && csa_todo_add …; then :; else <print>; fi`.
- **The Python comes from `find_csa_python` first,** and `ensure_csa_python` only when that finds
  nothing, so an ai-tools run (whose `install_python` has already ensured it) installs and
  announces once. With no CSA Python at all, the venv is left as it is, with a warning.
- **`-update` repairs, never creates** (decision D4): `update_default_venv` is its own `main()`
  step, before `update_pip`, and calls `ensure_default_venv --no-create` (`find_csa_python`
  only: no Python install, no Homebrew fallback), then refreshes `CSA_DOC_PY_DEPS`. Until now
  that refresh sat at the end of `update_pip`, after two early returns, so an up-to-date machine
  never reached it.
- **`update_pip` leaves the pinned deps to that step.** It upgrades whatever `python3 -m pip list
  --outdated` reports in the active environment, and in `~/.default_venv` that is pymupdf 1.28.2
  against 2.1 on every run; `pip install --upgrade pymupdf` brings 2.1 back, with onnxruntime
  (measured with real pip: 2.1 plus onnxruntime without a constraint, 1.28.2 with one). On a Mac
  whose `~/.zshrc` activates the venv, that would undo the pin every run. So when `python3`'s
  `sys.prefix` is `-ef` `~/.default_venv` or a `~/.default_venv-*`, `csa_venv_held_names` returns
  `CSA_DOC_PY_DEPS`' names: `pip_upgrades` (which the plan row prints and `update_pip` runs) drops
  them, and every other upgrade there runs with `PIP_CONSTRAINT` pointing at a `mktemp` file of
  the array's version pins, removed afterwards, so nothing else can pull pymupdf 2 back. Each
  of those pip calls gets `</dev/null`: the loop reads its list on stdin, and a pip that
  prompted would swallow the names still to come.
- **So `update_default_venv` keeps them current itself.** `csa_venv_pip_install` passes
  `--upgrade` on its uv path, as its pip fallback always did. Without it, measured on uv 0.13.7,
  `uv pip install` leaves an installed package that satisfies the request alone ("Would make no
  changes" for an outdated idna), and in an active `~/.default_venv` nothing upgraded pyyaml or
  csa-google-workspace any more. The pin travels in the same call: `--upgrade` with
  `pymupdf>=1.24.3,<2` moved 1.27.1 to 1.28.2, never to 2.x. The `.new-$$` build calls `uv pip`
  directly, without `--upgrade`, which makes no difference in an empty venv.
- Windows has no `~/.default_venv`; its document deps are #183.
- `tests/test_venv_replacement.py` runs all of it on stub uv, brew and interpreters, plus one
  case on real uv with wheels it builds itself (offline), and two controls that prove the cases
  can fail (a plain `mv`, a build without `--relocatable`). `plan_agrees_with_run` runs the plan
  row and then the step behind it, per state, and requires them to agree. CI runs the file twice:
  on ubuntu, where GNU `mv -T` stands in for `-h` and the real-uv case skips, and in the
  `venv-macos` job on `macos-latest` (BSD `mv`, uv from `astral-sh/setup-uv`, `uv python install
  3.14`), where `CSA_TEST_REQUIRE_REAL_UV=1` makes that skip a failure.

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
[`an-exit-code-is-not-a-state`](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/insights/an-exit-code-is-not-a-state.md).

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

**A seventh copy of the server list is `SERVERS` in `scripts/csa-mcp-registrations.py`:** each
server's name, entry point and module. `tests/test_mcp_registrations.py`'s
`servers_match_internal_setups` fails until it names the same servers, in the same order, as
the six `CSA_INTERNAL_SETUPS`.

**`CSA_PYTHON_PREFERRED` / `$CsaPythonPreferred` is declared in all six scripts** (`3.14`), not
only the two `*-ai-tools` ones: `-update` and `-plugins` hand it to the private gate repo's
setup scripts, and an undeclared value reached them empty, so the interpreter was guessed.
`CSA_PYTHON_MIN` / `$CsaPythonMin` (also `3.14`) lives in the `*-ai-tools` scripts.
`tests/test_python_pins.py` asserts the six preferred values and the two floors agree, that
every `CSA_DOC_PY_DEPS=(...)` copy in `scripts/*.sh` is identical (an array, so
`check-duplication.py` does not see it), and that no script installs onnxruntime, markitdown or
magika; `--self-test` breaks each rule on purpose.

**`macos-update.sh` carries its own copy of the `~/.default_venv` machinery:** `CSA_VENV`,
`CSA_DOC_PY_DEPS`, the three CSA-Python functions and every function from `venv_cfg_get` to
`default_venv_leftovers`, byte-identical to `macos-ai-tools.sh` (`check-duplication.py` holds the
functions, `test_python_pins.py` the array). Change both.

**The plugin lists are single-source** and are the exception: `scripts/csa-plugins.txt` and
`scripts/csa-plugins-internal.txt` are fetched from `HEAD` at runtime, so a list-only change
needs one commit and **no** script edit or version bump.

All scripts also duplicate their output helpers, precondition checks and utilities. The two
macOS install scripts additionally share `install_xcode_cli_tools`, `install_homebrew`,
`install_node`, `setup_gh_auth`, `setup_git_identity`. **When changing shared logic, update
every file that uses it** — `check-duplication.py` enforces byte-identical behaviour.

---

## The guard layer

Fourteen checkers in `tools/` and twenty-one test files in `tests/`. **`./tools/check-all.sh` mirrors CI
exactly** — run it before pushing.

A guard here is added only for a mistake that actually shipped, names its issue in the file, and
carries a self-test that breaks its own rule on purpose ([ADR-005](DECISIONS-ADR.md)). All of them
comply; the last two to lack one were closed as G1 in [`TODO.md`](TODO.md).

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
- **`check-app-lists.py`** — the third kind of duplication: repeated *data* within one
  script. Each work-tools script declares its app sets once: on macOS `CSA_CORE_APPS`
  (`label:cask:app-bundle`) and `CSA_DEV_TOOLS` (`label:kind:package:probe`, kind
  `cask|formula|npm`); on Windows `$CoreApps` and `$DevWingetApps`. Nothing changes a list
  after its declaration. Every rendering (menu, plan, install, summary, next steps) is checked
  one by one to be built from its list. The installers make no literal install calls, so a new
  app cannot bypass the list. No listed value appears on any other code line, except the
  `ALLOWED` lines, which each give a reason and are reported once stale. Matching is by whole
  token, so a trailing comment or "zoom in" is reported (its docstring says how to respond).
  Adding Office on Windows in #69 updated three of six copies. `--rev 1115b64` reports every
  copy, including the "install Office from your Microsoft 365 portal" line, and `--rev 36e76b4`
  reports the macOS copies #78 removed. **Windows' dev set is only partly a list.** Wrangler
  (npm) and `Show-Summary`'s version lines sit outside `$DevWingetApps` by #73's design. The two
  Windows `ALLOWED` lines are both `Show-Summary`'s: its VS Code winget Id and its AWS CLI line.
  Nothing records Wrangler. It passes only because `Install-NpmPackage` is not a listed install
  call, so deleting the Windows Wrangler install also passes.
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
- **`check-doc-deps-resolve.py`** — `CSA_DOC_PY_DEPS`, resolved with real uv against PyPI, must
  not bring in onnxruntime ([`~/.default_venv`](#default_venv-a-link-to-a-versioned-venv-macos),
  above). The one check that needs the network: exit 77 without it, a failure in its own CI
  workflow, `doc-deps.yml` (pull requests and weekly), where `CSA_TEST_REQUIRE_REAL_UV` is set.
- **`check-shellcheck.py`** — ShellCheck at **one pinned version** (0.11.0), which both CI and
  `check-all.sh` run, so the version, the flags and the file list exist once
  ([#186](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/186)). Before it,
  `check-all.sh` ran whatever shellcheck was installed and CI ran Ubuntu's 0.9.0, and on
  2026-11-10 a local 0.11.0 printed "clean" where CI failed on SC2120. It fetches the pinned
  release for the platform, refuses it unless its sha256 and its binary's match the pins, and
  caches the binary outside the repo. The cached copy is hashed again before every run, and
  anything else found there is deleted without being run, whatever version it claims.
  If it cannot get that binary (offline, or a platform with no pinned build), it runs the
  shellcheck on PATH and says which version that is. A different version that finds nothing exits
  **77**: *"clean under 0.10.0, but CI pins 0.11.0"*, never a bare "clean". CI sets
  `CSA_REQUIRE_PINNED_SHELLCHECK`, so CI itself never falls back.
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
brew install powershell
pwsh -NoProfile -c 'Install-Module PSScriptAnalyzer -Scope CurrentUser'
pwsh -NoProfile -c 'Install-Module Pester -RequiredVersion 5.7.1 -Scope CurrentUser'
```

ShellCheck needs no install. `tools/check-shellcheck.py` fetches the pinned release itself, and
uses a `brew install shellcheck` only when it cannot get that release.

**Pester is pinned to 5.7.1, deliberately.** 6.1.0's manifest claims 5.1 support, but under real
5.1 it aborts the whole run with *"a 'break' or 'continue' statement … escaped from your code"* —
its own message cites pester/Pester#2669 — with no `break` anywhere in the suite. Both CI jobs
and `check-all.sh` pin the same version so the framework is not itself a source of divergence.
Being current matters less than matching CI.

**ShellCheck is pinned to 0.11.0, the same way** (`VERSION` and `ASSETS` in
`tools/check-shellcheck.py`). Here the current release is also the right choice. It has an
Apple-silicon macOS build and GitHub-published sha256s, and 0.9.0, CI's version before #186, has
neither. It is also what Homebrew installs. To move the pin, change both values, run `check-all.sh`,
and fix or justify every new finding in the same PR. `ASSETS` also pins each binary's sha256,
which GitHub does not publish. The file's docstring gives the `gh api` command that lists a
release's digests and the commands that take each binary's from its verified archive.

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
scripts, with a version bump each — and adding it to `SERVERS` in
`scripts/csa-mcp-registrations.py`, bumping its own `SCRIPT_VERSION`. The loop uses `continue`,
not `return`, so an absent setup script cannot disable the servers listed after it — which is
also why a stale list produced **no output at all** until the drift report was added.

### Registration audit and repair

**Why it exists.** The gate setups leave a working registration alone, which protects policy,
and so they also left a dead one dead. In
[#179](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/179)'s incident a Claude Code
registration of csa-zendesk pointed into a source checkout whose venv had lost its Homebrew
Python, and a rerun changed nothing. `scripts/csa-mcp-registrations.py`
([Plan 2](plans/2026-11-12-registration-repair.md)) finds every registration of the four servers
in four clients and says what is wrong with each. After consent it re-points a dead one at the
standard binary, and it can check that a server answers. It lives in this public repo because it
carries no credential, and is Python because the same file is to serve Windows: stdlib only,
3.9 to 3.14 (Apple's `/usr/bin/python3` is 3.9), always run with `-I`. **This repo now re-points
existing CSA registrations; it still never creates one.**

**macOS only, for now.** Shipping macOS first was D3, the CINO's call, and he chose, verbatim,
*"Ship macOS first (Recommended)"* (2026-11-13). On Windows no `.ps1` runs the `.py`, and its four
readers each answer `not audited: Windows support is #184 (Task 1W)`, so a dead registration on
Windows stays dead and unreported, as before. `check-parity.py` cannot see this gap: the calls sit
inside `setup_csa_internal_tools`, not in `main()` (A6). What keeps it visible is
[#184](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/184),
[`TODO.md`](TODO.md) P1, and the SKIP `tests/test_mcp_registrations.py` prints for
`wiring_windows_twin_exists` on every run. The Windows tasks are in
[`plans/2026-11-12-registration-repair-windows.md`](plans/2026-11-12-registration-repair-windows.md).

The measurements behind the figures and rulings below (M0–M7) are in
[the measurement record](plans/reviews/2026-11-12-registration-repair-measurements.md).

#### What a macOS run does

`macos-ai-tools.sh`, `macos-update.sh` and `macos-plugins.sh` carry the same eight functions,
`csa_registrations_*` and `repair_csa_registrations`, byte-identical (`check-duplication.py`).

1. **In the plan, before you agree.** Inside the `Internal MCP servers` block, two header lines:

   ```
   then audit their registrations in Claude Code (user and local scopes), Claude Desktop, Codex and Gemini,
   and re-point a dead one at ~/.local/bin keeping every setting
   ```

   Then, only if `gh` is signed in and can see the gate repo, `csa_registrations_preview`:
   - makes the run's directory with `mktemp -d` (`CSA_REG_DIR`). `csa_on_exit` removes it on every
     exit path, a declined plan included;
   - finds a Python: the first that is a real file and answers as 3.9 or later within 10 s, of
     `python3` on `PATH`, `uv python find --system 3.14`, `/opt/homebrew/bin/python3`,
     `/usr/local/bin/python3`, and `/usr/bin/python3` only when the Command Line Tools are
     installed (without them it opens an install dialog);
   - fetches the `.py` from `HEAD` into that directory, with `Cache-Control: no-cache` and a 60 s
     limit. `CSA_REGISTRATIONS_PY=<path>` runs a local copy instead, for tests and branch runs;
   - asks the file whether it is the audit: `--version`, and each subcommand's `--help`, each
     bounded at 10 s. A network sign-in page or another file in its place is skipped;
   - runs `plan --out <dir>/plan.json` and prints its rows under the block.

   A step that fails prints one line, `registration audit skipped: <why>; nothing will be
   changed`, or `registration audit failed; nothing will be changed` when `plan` exits non-zero,
   and the run goes on. Without CSA-Internal access only the two header lines show.
2. **Consent** is the existing `confirm`. `NONINTERACTIVE=1` agrees, as it does for every step
   (it is also set when `CI` is set or stdin is not a terminal). End of input at the prompt is a
   no.
3. **After the four gate setups,** as the last step of `setup_csa_internal_tools`:
   `repair_csa_registrations` runs `apply --approved <dir>/plan.json`, then `verify` without
   `--run`. So it is behind the same `gh` gate, and every standard binary has been installed or
   rebuilt first. It finds the Python and checks the `.py` again, shows each `ok`, `info` and
   `warn` line as the `.py` prints it, and never fails the run. With no plan file (the audit was
   skipped or failed), `apply` is handed a plan with no findings, so it reports and changes
   nothing.
4. **To-dos** go to `CSA_TODO_FILE`, which only the `*-ai-tools` installers set; the other
   scripts print them as `info` lines. The orders:
   - **10:** `Restart <client>` after a repair, `Quit Claude Desktop and run again`, and
     `Claude Code's config is locked; …`;
   - **40:** a registration left for somebody to fix;
   - **45:** a server that did not answer.

**Run time.** These steps are bounded. The `plan` and `apply` processes themselves are not run
under a bound, nor are the `gh` gate calls, `uv python find` or `xcode-select -p`:
- **Before the plan:** each Python candidate gets 10 s, the fetch 60 s, and each of the four
  interface questions 10 s. Inside `plan`, `codex mcp list --json` gets 30 s, each distinct
  interpreter probe 10 s, and `ps` 30 s (asked only when a Desktop entry would be re-pointed).
- **After the setups:** the Python and interface checks again, then `apply` re-audits under the
  same bounds. It adds up to 10 s waiting on Claude Code's lock, and two `codex mcp get --json`
  calls of up to 30 s each per Codex entry it re-points.
- **`verify` without `--run`** reads nothing and launches nothing.

**How long this takes on a real machine is not measured yet;** Task 6's acceptance run records
it. What a server check adds, once one runs, is under [the server check](#the-server-check-verify).

#### What it reads

| Client | Where | What |
|---|---|---|
| Claude Code | `~/.claude.json`, or `$CLAUDE_CONFIG_DIR/.claude.json` | user `mcpServers`, and each project's local `mcpServers`. A project whose directory is gone is skipped, and logged |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json`, when `Claude.app` is in `/Applications` or `~/Applications` | `mcpServers` |
| Codex | `codex mcp list --json`, bounded at 30 s, because Apple's Python has no `tomllib` (A7). The file it edits is `$CODEX_HOME/config.toml`, else `~/.codex/config.toml` | the user's servers |
| Gemini | `~/.gemini/settings.json`, when `gemini` is on `PATH` | `mcpServers` |

- **Only the four names in `SERVERS`, and only stdio entries** (A9). Not read: `.mcp.json`, Codex's
  and Gemini's project configs (checked into repositories, and shared), plugin-bundled servers,
  Desktop extensions, and the hosted `csa-mcp`.
- **Its own client calls run from a fresh empty directory** (A11), so a project config where the
  installer stands cannot stand in for the user's.
- **A client is `not installed`, `no config yet (#156)` or `not audited: <why>`, never "fine".**
  A config that is unreadable, cut short, has comments (JSONC), a duplicate key, a byte-order
  mark or an unexpected shape is `not audited`, and nothing is written to it. So is a Codex
  whose CLI fails, times out or has no `--json`: a failing CLI is never read as "no
  registrations".

#### What it calls each registration

- **standard:** `~/.local/bin/<entry>`, or a path to the same file. Nothing to do. If that binary
  cannot start, its setup reinstalls it; it is never re-pointed at itself.
- **dead:** its command, or the Python behind it, is gone or does not run.
- **launcher:** it runs through `uv`, `uvx`, `npx` or another wrapper. Left, and never launched:
  launching one can rebuild a venv, download Python or write into a checkout (A12).
- **elsewhere:** it works, and is not the standard binary: usually a developer's checkout.

**A direct executable** is a regular file whose first line names an absolute Python, either
`#!<python>` or the `#!/bin/sh` + `'''exec' "<python>" "$0" "$@"` form installers write for long
paths. A Python whose args are exactly `-m <the server's module>` is one too. Anything else is a
launcher form, and so is a file whose name, or whose link target's name, is `uv`, `uvx`, `npx`,
`pipx`, `poetry`, `pdm`, `hatch`, `conda`, `mamba`, `pixi`, `node`, `bun`, `bunx`, `deno` or
`docker`.

**A Python is dead** when it does not exist, when its venv's `pyvenv.cfg` `home` is gone or the
venv has no `bin/python3`, or when `-I -B -c "import json, importlib.resources"` fails or takes
over 10 s. A bare command name resolves on the installer's `PATH` for Claude Code, Codex and
Gemini, which M3 measured passing their caller's `PATH` on. One that does not resolve there is
dead.

The reasons, verbatim; the plan prints each after `<name> in <client>:`. The Desktop row is
reworded from the plan's text, as is `verify`'s held line, and the `.py` says why beside each.
A dead registration's row then ends in one of two ways:
- `; it will be re-pointed at ~/.local/bin/<entry>, keeping its settings (<keys>)`;
- `; left as it is: <why>`, where the why is one of the rows below marked "dead, with", or D2's
  to-do.

| Reason | When |
|---|---|
| `its standard binary does not run yet; its setup reinstalls it` | standard, but that binary is missing, not executable, or its Python is dead |
| `its command does not exist`, `its command is not executable` | dead |
| `its Python no longer exists`, `its Python does not run` | dead |
| `it runs through <name>, which this does not inspect; left as it is` | a launcher form |
| `it points at <path>, not ~/.local/bin/<entry>; its Python runs, so it is left as it is` | elsewhere (D1) |
| `its args run a module this does not recognise` | a Python `-m` naming another module |
| `its args are not a form this re-points` | dead, with args other than the pinned `-m` form |
| `its <KEY> setting would point the release binary at another tree` (`settings`, for more than one) | dead, with an interpreter-shaping key in its env: `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONUSERBASE`, `PYTHONEXECUTABLE`, `VIRTUAL_ENV`, `CONDA_PREFIX` or any `UV_*` (A12) |
| `its config is a link to <path>; not changed — edit it there` | dead, and the config, or a directory between it and `HOME`, is a symlink (A10) |
| `not checked: Claude Desktop's PATH differs from machine to machine, so a bare command name can't be resolved here` | a bare-name Desktop entry (A8; reworded) |
| `not checked: its command is a relative path, which depends on where the client starts` | a relative command |
| `it is not a stdio registration, which is all this audits` | an HTTP or other transport |
| warning: `it runs from a venv built on a Homebrew Cellar Python, which the next brew upgrade deletes` | elsewhere, Cellar-pinned (#179 item 5) |
| warning: `<KEY> is set in this shell, and <client> passes it on to every server it starts, so the re-pointed binary would get it too` | a re-point in Claude Code or Gemini, which pass their own env on (M3) |

The plan ends `<n> CSA registrations in <m> clients; <k> need nothing`.

**The bare-name Desktop ruling** (the AI's, 2026-11-13, under P1). M3 recorded one Mac's Desktop
`PATH`, but it holds nvm and pyenv directories of that machine, and Desktop's own log said its
shell-environment extraction had timed out, so it may be a fallback. Applying it could call a
working entry dead and re-point it, which D1 forbids. So `DESKTOP_PATH` is `None`, and a bare
name in Desktop's config is left `not checked`, never re-pointed.

#### What `apply` changes, and only that

- **Only a re-point the plan showed, unchanged since** (A4; the CINO's rule of 2026-10-23, *"we
  want to check state, make sure we are up to date before we reply."*). For each finding, the plan
  file records the key `apply` matches on: its client, scope, project, name, config path, and a
  fingerprint, the sha256 of the command, the args and the sorted env **key names**, never a
  value. `apply` re-audits, and acts
  only on a finding that is still a re-point under the same key. Otherwise it says
  `found after you agreed to the plan; not changed — run again`,
  `the plan you agreed to left it as it was; not changed — run again`, or, when the plan file
  cannot be read, `not changed, because the plan you agreed to could not be read — run again`.
- **Only when the standard binary runs.** Otherwise
  `its standard binary is not installed yet; left as it is`, with a to-do to run again once its
  setup has installed it.
- **Only `command`,** set to the absolute `~/.local/bin/<entry>`, plus `args`, from
  `["-m", "<module>"]` to `[]`, in that one interpreter form. Every env var and every other field
  stays as parsed. That is checked in memory before the write
  (`the edit could not be confined to its command; not changed`), and again on read-back.
- **JSON** (Claude Code, Claude Desktop, Gemini) is parsed and written back keeping its key
  order, its indent (tabs too), its trailing newline or none, and CRLF. Only spelling can change:
  the whitespace between tokens, a `\u` escape of a printable character (written as the
  character), and a number's form (`1.5e3` becomes `1500.0`). A config holding NaN or an infinity
  is not rewritten. So the first repair of a file can change its bytes without changing a value:
  in M2, a whole-file re-serialisation with identical values went from 4636 to 4637 bytes.
- **Codex's `config.toml`** is edited line by line: only the `command` line, and for the
  interpreter form the one-line `args` line. A table laid out any other way (its header not
  exactly once, a multi-line string or array) is left with
  `its Codex entry is laid out in a way this cannot edit safely; left as it is`. The result is
  read back through `codex mcp get --json`.
- **No client CLI ever writes** (A3). `claude mcp add -e` and `codex mcp add --env` put values on
  a command line, which macOS shows to every account ([FRICTION-007](FRICTION.md)).
- **A repair reaches what starts after it.** A running Claude Code session, or Claude Desktop,
  keeps the command it started with (M1, M2). So the `ok` line for Claude Code ends
  `Claude Code sessions started after this use it`, and every client repaired gets a
  `Restart <client>` to-do.

#### The decisions, at their safe defaults

D1, D2, D4 and D5 are unanswered. Each is one constant at the top of the `.py`, pinned by one test;
an answer changes the constant and its test.

| Decision | Constant | In force | Pinned by |
|---|---|---|---|
| D1. A registration that works but is not the standard binary | `REPOINT_WORKING_ELSEWHERE = False` | left byte-identical and warned, with the to-do `… points at <path>, not ~/.local/bin/<entry>; if that is not deliberate, re-point it` | `working_elsewhere_left_and_warned` |
| D2. A dead Claude Code local-scope entry | `LOCAL_SCOPE_ACTION = "todo"` | left, with the to-do `rebuild that checkout's venv, or remove the local entry so your user entry applies there; removing it drops its settings (<keys>)` | `dead_local_scope_todo_names_rebuild_or_remove` |
| D4. Claude Desktop is running | `WRITE_DESKTOP_WHILE_RUNNING = False` | Desktop's config is not written while Desktop runs, or while that cannot be told (below) | `desktop_running_skipped_with_quit_todo` |
| D5. The server check on a rerun | `VERIFY_ON_RERUN = frozenset()` | a rerun launches no server, and the plan prints no check row | `verify_held_by_default` |

M5 has since measured each server's start: no token file changed and no connection was seen, for
all four. That makes each a candidate for D5's option (c), but the answer is still the CINO's.
M2 did not settle D4 (below).

#### What is never touched

- Token, OAuth-state and credential files: never opened, moved or deleted. No login, logout or
  re-consent is run.
- `.mcp.json`, and Codex's and Gemini's project configs.
- A launcher form, a registration whose env shapes the interpreter, and a working one elsewhere
  (D1).
- A dead local-scope entry (D2), a bare-name Desktop entry (A8), and Desktop's config while
  Desktop runs (D4).
- A config that is a symlink (A10), or that has a second name, a hard link:
  `its config has another name too (a hard link), which a replace would cut off; not changed — edit it by hand`.
- The registration list itself: nothing is created or removed. A missing registration is its
  setup's job.
- Any backup it did not make, including Claude Code's own in `~/.claude/backups/`.

#### Concurrency

- **Claude Code's lock (M1).** Claude Code takes `<config>.lock`, a directory, around each write
  of `.claude.json`, and waits for one somebody else holds. `apply` takes the same lock with
  `mkdir`, and holds it across the read, the checks, the backup and the replace. It waits up to
  10 s for a held lock, and **never breaks one**: the AI's ruling of 2026-11-12, under P1, because
  breaking a live session's lock lets two writers race.
  - Still locked after 10 s: `Claude Code's config stayed locked for 10s, so it was not changed;
    the lock was left as it is`. The to-do is `Claude Code's config is locked; close Claude Code
    and run again; if Claude Code is not running, remove <lock>`. A crashed session's lock blocks
    Claude Code's repair until it is removed, and every other client is still repaired.
  - A write that has held the lock for more than 5 s is abandoned (`… not written — run again`),
    well before the 10 s after which Claude Code's bundled `proper-lockfile` may call it stale.
  - A lock is removed only on proof that this run made it.
- **Claude Desktop (D4).** Whether it runs is read from `ps -axo comm=`, by executable path:
  `/Applications/Claude.app/Contents/MacOS/Claude`, or the same under `~/Applications`. Never by
  process name, since `claude` is also Claude Code, and Claude Code's updater renames its running
  image. It is asked when the plan is made, and again just before the write.
  - When Desktop is running, or `ps` cannot tell, the row says
    `Claude Desktop is running; <name> will not be re-pointed there this run — quit it and run again`
    (or `could not tell whether Claude Desktop is running; …`), and the to-do is
    `Quit Claude Desktop and run again`. It appears only when a Desktop entry would be re-pointed.
  - M2 showed an outside edit of an entry's command survived 14 minutes of Desktop running, and
    its quit. Whether a preference
    change makes a running Desktop write its old copy back was **not measured**, so D4 keeps its
    default.
- **Any other writer.** The file's identity (device, inode, mtime, size, mode, link count) is
  taken before the read, and checked before the backup and again before the replace. A change
  abandons the write, leaving no backup: `changed while this ran; not written — run again`.

#### Backups and temporary files

- **Before each replace, `<config>.bak-<YYYYmmddHHMMSS>`** (local time). It has the same name, the
  same match and the same three-generation prune as `csa-claude-connectors.py` (A13), so one cap
  bounds both tools' copies. **Each backup holds the same secrets as its config,** at its mode,
  and never looser: a looser one abandons the write.
  - The prune matches only `<config name>.bak-` plus fourteen digits, the name both tools write,
    so a backup named any other way is never touched. That also means Claude Code's own backups
    in `~/.claude/backups/` are not counted in the cap.
  - A backup is made only once the file is known unchanged since it was read, and is removed if
    the write is then abandoned. Only a replace that reads back as written prunes.
  - A read-back that differs restores the config from the backup:
    `its config did not read back as written, so it was restored from its backup; not changed`.
- **The write:** a temp file beside the config, at the config's mode from its creation
  (`.csa-registrations-<pid>-<8 characters>`), then fsync, then `os.replace`. That keeps the
  mode, but **drops the file's extended attributes and ACLs.**
- **Stopped:** SIGTERM, SIGHUP or Ctrl-C runs the clean-ups (the temp file, an unused backup, the
  lock). A run killed outright can leave a temp file holding the config's secrets; the next
  `apply` removes this tool's temp files that are older than itself and whose run is gone, and
  nothing else.

#### The credential rule

- Env **values** are held in memory only. They are never printed, logged, put on a command line,
  or written to the plan file or the to-do ledger. Key names and counts may be shown.
- A value is written only back into the config it came from and that config's backup, or into the
  env of a server `verify --run` launches.

#### Running it by hand

The entry scripts delete their fetched copy at exit, so the held check's line names no command
to run. From a checkout of this repo, current with `main` (`git pull`):

```bash
python3 -I scripts/csa-mcp-registrations.py plan             # read-only: what a run would show
python3 -I scripts/csa-mcp-registrations.py verify --run     # check every registered server now
```

- `plan` writes nothing; with `--out FILE` it writes only that new file, at `0600`.
- `verify --run` launches every registration it can check, one at a time and identical launches
  once, under your real `HOME` with its registered env, as the next section says. M5 measured
  that launch for all four servers on 2026-11-13: no token file changed and no connection was
  seen.
- `apply` without `--approved` re-plans, prints the plan, and applies it **without asking**:
  running it is the consent. Run `plan` first.

#### The server check: `verify`

`verify --run` launches each registered CSA server with its registered command and settings, and
sends it one MCP `initialize`
([#179](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/179), Plan 2 Task 3). It
shows the server answers when launched that way, **not** that it works in a client: tool
discovery and an authorised read in each client are
[#177](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/177)'s. A rerun runs
`verify` without `--run`, which checks only the servers `VERIFY_ON_RERUN` names. That is none
until the CINO answers D5, so a rerun prints one line and does nothing else, no audit and no
launch: `server check held: this run launched no CSA server; whether a rerun should is not
decided yet (#179, D5)`. To check by hand, see [Running it by hand](#running-it-by-hand).

- **What it launches:** a registration whose command is a direct executable that works (A12).
  It never launches these, and says why:
  - a launcher form (`uv run`, `uvx`, `npx`, …, or a link to one under another name):
    `not checked: launcher form`;
  - a dead registration, or a dead standard binary: `does not start: <reason>`;
  - a registration whose env holds an interpreter-shaping key, whose env or args use
    `$`-expansion, or that sets its own working directory: `not checked: …`.

  Identical launches are made once, and the line names every client that shares one.
- **How:** one launch at a time, each in a fresh empty directory, in a session and process group
  of its own. After the answer, or 20 s, its stdin is closed and it has 2 s to exit. Then its
  group gets SIGTERM and 2 s, then SIGKILL, and the server is reaped. A child it leaves in its
  group is stopped with it. A stop signal runs the same teardown. A process that leaves the group
  (`setsid`) is outside it; no CSA server does that.
- **Its launch env approximates each client's,** from M3 in
  [the measurement record](plans/reviews/2026-11-12-registration-repair-measurements.md). So the
  output says "launched with its registered command and settings", never "as <client> launches
  it". Every client also gets the registration's env, and none gets the installer's own keys
  (`CSA_TODO_FILE`, `CSA_LOG`, `CSA_DEBUG`, `CSA_NESTED`, `CSA_REGISTRATIONS_*`).
  - **Claude Code:** the installer's whole env. Claude Code also adds keys of its own (a session
    id, …); the check does not.
  - **Codex:** only `HOME LANG LOGNAME PATH SHELL TERM TMPDIR USER`, and the keys its
    registration names in `env_vars`. Those eight are a lower bound: only the keys in M3's input
    were tested. The two directories Codex prepends to `PATH` hold no CSA binary, and are not
    added.
  - **Gemini:** the installer's env minus what looks secret, by Gemini CLI 0.67's own rule, read
    from its installed bundle. Its settings' allow and block lists are not reproduced.
  - **Claude Desktop:** `HOME LOGNAME PATH SHELL USER`. M3 also recorded `LC_CTYPE` and
    `__CF_USER_TEXT_ENCODING`; Python and macOS add those to any process started without them
    (inferred), so they are left to them. `PATH` is the installer's: M3's one-Mac Desktop `PATH`
    is not applied (the A8 ruling of 2026-11-13). A Desktop entry the check launches has an
    absolute command, so `PATH` does not choose the binary.
- **What it prints: only fixed lines it composes itself.** None of a server's own text is
  printed: not its stdout or stderr, its name or version, or an error's message.
  - Only integers of the server's reach a line: an exit code or signal number, a JSON-RPC error
    code in the range the spec reserves (any other code is not printed), and a count of stdout
    lines that were not JSON, shown as "more than 1000" above that.
  - A to-do for a server that did not answer names its command, never its args or env, to run
    in a terminal to see its own messages. For the interpreter form it adds the pinned
    `-m <module>` from the script's own table, since a bare Python would open a prompt.
  - Masking the server's text was tried first. The review of `bbb6f82` got values past it four
    ways: an arg, a value split over two lines, an escaped value, and a value cut at the end of
    the stderr tail kept. A deny-list cannot be made complete, so nothing is shown.
- **Run time:** M4 measured 0.35–0.61 s to an answer warm, and up to about 3 s cold. M5, with
  real credentials, measured at most 1.84 s, and each server exited about 0.1 s after its stdin
  closed.
  - One launch is bounded at 24 s: 20 s, then 2 s and 2 s. A process that outlives SIGKILL adds
    2 s more.
  - The number of launches has no bound of its own. Per-client envs can defeat de-duplication,
    and each Claude Code local-scope entry can add one. So the launches together are held to
    `VERIFY_BUDGET`, 120 s. A launch that could run past it is not started, and is reported
    `not checked`.
  - While D5 holds, a rerun adds nothing.

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
[`an-exit-code-is-not-a-state`](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/insights/an-exit-code-is-not-a-state.md),
[`a-green-check-is-only-evidence-about-what-it-ran-on`](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/insights/a-green-check-is-only-evidence-about-what-it-ran-on.md).
