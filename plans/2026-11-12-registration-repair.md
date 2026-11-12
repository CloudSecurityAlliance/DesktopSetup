# CSA MCP registrations: a rerun audits every client, re-points a dead one in place, and checks each server answers: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (CINO rule B1: always
> subagent-driven) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every
> review runs on the strongest model, `fable` (B12). **Nothing here is built until the independent spec review
> (B11) has run and the CINO has decided D1 and D2, or accepted their safe defaults.**

**Goal:** a rerun of any macOS entry point (`-ai-tools`, `-update`, `-plugins`) finds every registration of the four
CSA MCP servers in Claude Code, Claude Desktop, Codex and Gemini. It shows in the plan which ones it will re-point and
why. After consent it re-points a dead registration at the standard `uv tool` binary, changing nothing but the
command. Then it checks that each registered server answers an MCP `initialize` handshake. A second rerun changes
nothing.

**Architecture:**
- **One auditor, in Python, in this public repo:** `scripts/csa-mcp-registrations.py`, with three subcommands:
  `plan` (read-only), `apply` and `verify`. Python because the same file must later serve Windows (R5: "Scripts that
  must run on Windows are Python"). It carries no credential, which is the only reason the gate repo is private.
- **The entry scripts fetch it from `HEAD`,** as they fetch the plugin lists. They run `plan` in the preflight, and
  `apply` then `verify` at the end of `setup_csa_internal_tools`, after the four gate setups have installed or
  rebuilt the binaries.
- **A repair is a minimal in-place edit of the client's own config file:** the `command` field, and nothing else.
  Every env var and every other field stays exactly as it was (#179 item 2).
- **The gate repo keeps its leave-alone rule,** which is right for policy. Two `.sh` defects found while planning are
  fixed there: G1 (a probe can read a shadowing local or project registration instead of the user's) and G2 (Desktop
  config writes can widen a file that holds secrets).
- **Windows halves are separate "W" tasks,** for the Windows session in #184.

**Tech stack:** Python 3.9 to 3.14 stdlib only (Apple's `/usr/bin/python3` is 3.9.6), bash 3.2, Windows PowerShell 5.1
(W tasks), the house test harnesses, Pester 5.7.1.

**Spec:**
- [#179](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/179) Part 2: items 1, 2, 5 (for venvs a
  registration points at), 6, 7 and 8, and its comments. The CINO's ask, verbatim: *"get python updated to 3.15, and
  on rerun fix everything, including already installed mcp servers."*
- Plan 1, `plans/2026-11-10-python-314-standard-build.md` (merged). Its tool rebuild and `csa_tool_repairs` plan rows
  are assumed.
- [csa-zendesk#70](https://github.com/CloudSecurityAlliance/csa-zendesk/issues/70): a working source-checkout
  registration that carries a write allowlist.
- #175, #176 and #177, for what this plan absorbs and what it leaves (section below).

**What is already true.** Measured on the CINO's Mac on 2026-11-12. Env key names were read; no value was read or
printed.
- **User scope (Claude Code):** all four CSA registrations point at `~/.local/bin/<entry>`. csa-skilljar's entry inlines
  `CSA_SKILLJAR_V1_API_KEY` and `CSA_SKILLJAR_V2_CLIENT_SECRET`. So does its Claude Desktop entry.
- **The incident's dead path is still there, in local scope.** One project's local registration of csa-zendesk points
  at that checkout's `.venv/bin/csa-zendesk-mcp`, and it carries `CSA_ZD_ALLOWLIST_WRITE`. The venv's `pyvenv.cfg`
  `home` is a Homebrew Cellar directory that no longer exists, and its shebang interpreter is a dangling link. Plan
  1's acceptance checked user scope only.
- **Claude Desktop's config:**
  - it is mode `0600`;
  - it holds Desktop's own `preferences` and `coworkUserFilesPath`, so Desktop writes this file too;
  - its four CSA entries point at `~/.local/bin`.
- **Codex 0.167:** `codex mcp list --json` returns a list of
  `{name, enabled, disabled_reason, startup_timeout_sec, tool_timeout_sec, auth_status, transport: {type, command,
  args, env, env_vars, cwd}}`.
- **Gemini 0.67:** it has no `mcp get`, and `~/.gemini/settings.json` is plain JSON here.
- **csa-google-gmail-calendar is in neither Codex nor Gemini.** That is the bash 3.2 crash fixed by CSA-Plugins#204;
  the next run adds it.
- **`/usr/bin/python3` is 3.9.6** and has no `tomllib`.
- **macOS shows every account's process arguments to a standard user.** `ps -axo user,args` printed root's and system
  daemons' argv. A value put on a command line is readable by every local account while that process runs. This
  rules out `claude mcp add -e` and `codex mcp add --env` for a repair (A3).

**Independent spec review (B11):** pending. Its findings are folded in before Task 1 starts, and decisions it
surfaces go to the CINO one at a time (K2).

## Decisions for the CINO

Each decision is one named constant in the `.py`, with one test that pins its value. Until he decides, the plan
ships the safe default.

### D1. A registration that works but does not point at the standard binary

- **Context.** #179 item 2 says to re-point a registration *"that points somewhere other than the standard `uv
  tool` binary"*. That wording is an agent's, from his one-line ask. csa-zendesk#70 raised the other side. A
  developer may deliberately run a working tree, and that registration carries a write allowlist. #70's option 3:
  warn when it points outside `~/.local/bin`, *"without touching it"*. Re-pointing would silently swap the code a
  developer is testing for the release, inside a plan they approve by skimming.
- **Options:**
  - **(a)** Leave it. Warn in the plan, add a to-do, and add the Cellar warning when it applies. If it dies, the next
    run re-points it, because it is then dead.
  - **(b)** Re-point it too, as the item reads literally.
  - **(c)** Re-point it only when it is fragile, that is, Cellar-pinned.
- **Recommendation: (a).** The leave-alone rule exists to protect choices. A working path somebody set is a choice;
  a dead one is not. (a) still fixes the incident, because the incident's registration was dead.
- **Why it is his:** it decides whether the installer may change which code runs on a developer's machine. That is
  policy he would notice, and (a) contradicts the issue text.
- **Safe default:** (a). `REPOINT_WORKING_ELSEWHERE = False`, pinned by `working_elsewhere_left_and_warned`.
- **What would let the AI decide next time:** a stated rule in ENGINEERING.md that a working registration is policy
  and only a dead one may be changed.

### D2. Scopes beyond Claude Code's user scope

- **Context.**
  - Claude Code merges three scopes, and the narrowest wins:
    - **local:** private, per project, inside `~/.claude.json`;
    - **project:** `.mcp.json`, checked into a repository;
    - **user.**
  - So a dead local entry breaks the server in that project even when the user entry is healthy. **This is the
    CINO's Mac today** (above).
  - Codex and Gemini also read project-level files that live inside repositories.
- **Options:**
  - **(a)** User scope only. Local findings are shown and get a to-do with the manual fix.
  - **(b)** Also re-point a *dead* local-scope registration, in place in `~/.claude.json`, with its env kept. A
    working one follows D1. Project files are never touched.
  - **(c)** Also project files inside repositories.
- **Recommendation: (b).**
  - A dead path is not a choice.
  - A local entry is the user's own private config, in a file the installer already edits for the user scope.
  - Without (b), the CINO's own machine keeps the incident's registration.
  - Not (c): those files are checked in and shared with a team, and a repair would leave a diff in somebody's
    repository. Finding them would also mean scanning disks for repositories.
- **Why it is his:** it reaches into per-project configuration on developers' machines.
- **Safe default:** (a). `REPAIR_LOCAL_SCOPE = False`, pinned by `local_scope_left_until_d2`. Project files are not
  read under any option.
- **What would let the AI decide next time:** a stated rule that the installer may edit a person's own per-user
  config, but never files inside repositories.

## The AI's decisions (P4: each names its rule)

- **A1. Audit, repair and verification live in DesktopSetup, in one Python file, not in the four gate scripts.**
  Decided under P1, correctness: one classifier serves both the plan and the run.
  - The spec puts *"the registration audit"* in this repo, and #177's verification belongs to it.
  - Rejected:
    - **Per-server repair in eight gate scripts:** eight classifiers, plus a ninth for the plan preview, which will
      drift.
    - **One private gate script:** public CI cannot test it, and the preview would execute private code before
      consent.
  - The AGENTS.md trap *"This repo's own code registers only …"* is updated: DesktopSetup now also *repairs* existing
    registrations, and still never creates one.
- **A2. The `.py` is fetched from `HEAD` at run time,** as `csa-plugins.txt` is. It goes into a `mktemp -d`
  directory (S1), and `CSA_REGISTRATIONS_PY=<path>` overrides it for tests and branch runs. Rejected: embedding it
  as a heredoc, which would mean three byte-identical copies of about 400 lines in the macOS scripts, and three more
  in the Windows ones.
- **A3. No client CLI write commands.** `claude mcp add`/`add-json` and `codex mcp add` take env values on the
  command line, and macOS shows argv to every account (measured above). Decided under P1 and S3.
  - So every repair is a minimal edit of the client's own file:
    - **JSON** for Claude Code, Claude Desktop and Gemini: parse, change one field, write back.
    - **A line-local TOML edit** for Codex, read back through `codex mcp get --json`.
  - This also keeps fields the CLIs cannot express, such as Codex's `startup_timeout_sec`. It also never leaves a
    server unregistered, as a remove-then-add that fails halfway would.
  - **Cost:** it can race a running client. The mitigation is a stat check just before the replace, a backup, a
    read-back, and the next run. Precedent: `csa-claude-connectors.py` edits `~/.claude.json` the same way.
  - **Rejected:** the CLIs for secret-free entries only. That is two mechanisms and twice the test surface.
- **A4. Only what the plan showed is changed.** `plan` writes its findings, with fingerprints and no values, to a
  file. `apply` acts only on a finding that is in that file *and* unchanged since. Anything new is reported as "found
  after you agreed to the plan; not changed — run again". This is the CINO's rule of 2026-10-23: *"we want to check
  state, make sure we are up to date before we reply."*
- **A5. The check is `initialize` only.**
  - One server process at a time, 20 s each, its process group killed and reaped (S2).
  - Identical launches are made once.
  - The env is built the way each client builds it (Review Focus 6).
  - `tools/list` and an authorised read are #177's in-client stages, so this check never says "works in <client>".
- **A6. No new `main()` step.** The repair runs inside `setup_csa_internal_tools`, behind its `gh` gate, so
  `check-parity.py` is untouched. The Windows gap is tracked by a per-case SKIP in `windows_twin_exists` and by #184,
  as Plan 1 did.
- **A7. Codex is read through `codex mcp list --json`,** because Apple's Python 3.9 has no `tomllib`. A Codex whose CLI
  lacks `--json` is reported "not audited", never "fine".
- **A8. A bare command name is resolved on the client's own PATH.** For Claude Desktop that is launchd's
  `/usr/bin:/bin:/usr/sbin:/sbin`, as the gate README states.
- **A9. Only the four canonical names are audited:** `csa-google-workspace`, `csa-google-gmail-calendar`,
  `csa-skilljar` and `csa-zendesk`, and only stdio transports. The hosted `csa-mcp` (HTTP) is out of scope, as are
  plugin-bundled and Desktop-extension servers.

## Repos, branches and merge order

| Repo | Branch | Tasks |
|---|---|---|
| CSA-Plugins | `fix/registration-probes-and-modes` | G1, G2 (`.sh`) |
| DesktopSetup | `feat/registration-repair` | 1, 2, 3, 4, 5, 6 |
| CSA-Plugins | `fix/registration-probes-and-modes-windows` | G1W, G2W (held for #184) |
| DesktopSetup | `feat/registration-repair-windows` | 1W, 4W, 6W (held for #184) |

1. **CSA-Plugins G1 and G2 merge first.** From then on, a gate run cannot replace a policy-bearing user registration
   because of the directory DesktopSetup was started from, and never widens the Desktop config's mode.
   - DesktopSetup does not depend on them, and its plan rows claim nothing about them.
   - Work in a fresh clone under the session scratchpad, never in
     `/Users/kurt/GitHub/CloudSecurityAlliance-Internal/CSA-Plugins`.
   - CSA-Plugins#206 is open in another session. Rebase onto main after it merges, and don't touch it.
2. **DesktopSetup Tasks 1–6 merge after,** Task 6 carrying the isolated run and measurements M1, M3 and M4. The
   first run that repairs then also runs the fixed probes.
3. **Task 6 Step 3, the real run on the CINO's Mac, comes after both,** with his go-ahead. So does M2, which touches
   the real Desktop config. Until M2 is measured, Review Focus 5's default stands; its worst case is today's state.
4. **The Windows halves stay drafts** until a Windows session has measured and run them end to end (Plan 1's D5,
   carried over). Task 5 adds them to #184.

## What this plan absorbs from #175, #176 and #177, and what stays there

| Item | Here | Stays |
|---|---|---|
| #176 "detect stale managed launchers and explain the repair; do not interpret every custom path as permission to replace it" | Tasks 1–2, D1 | — |
| #176 "preserve … credentials and intentional operator settings" on reruns | Task 2 (every field kept), G1 (no policy loss to a shadowing cwd) | first-use registration: the gate scripts and #156 |
| #176 "resolved executable paths for GUI launches" | a Desktop entry that names a bare command is re-pointed at the absolute binary (A8) | — |
| #176 "an absent client should produce an accurate skip/pending result" | audit and check output (Tasks 1, 3) | the gate scripts' own registration messages |
| #175 "stale repo-venv registrations" | Tasks 1–2, D1, D2 | — |
| #177 truthful outcomes in the closing list | a failed handshake, and a registration left for a decision, become to-dos | #154 (a setup that dies partway) |
| #177 "a CLI check does not prove the desktop client loads the server" | the handshake is worded as the installer-side stage only | tool discovery and an authorised read in each client; the published matrix |
| csa-zendesk#70 | D1's default is its option 3; a dead path is repaired | whether the server reports an editable install (#70 option 1) |
| csa-google-gmail-calendar#45 "register … and verify it" | Task 3 supplies the verification | registering when absent: that server's setup script |

**Stays out of this plan entirely:**
- ChatGPT Desktop, Gemini Desktop and `agy` (#175, #167, #172). Nothing registers servers with them today. Task 1's
  client table is the one place they would be added.
- Workspace Audit, which is not implemented.
- Authentication flows.
- The 5×6 status matrix.
- Gemini folder trust (#155).

## Global Constraints

- **Credentials (#179 item 8, S3):**
  - No token file, OAuth state or credential file is opened, moved or deleted.
  - No login, logout or re-consent is run.
  - Env **values** are held in memory only. They are never printed, logged, put on a command line, or written to the
    plan file, the to-do ledger or evidence.
  - Key names and counts may be shown.
  - A value is written only back into the config file it came from, and into that file's backup at the same mode.
- **The repair (#179 item 2):**
  - It changes `command`.
  - It replaces `args` only in the interpreter form `["-m", "<module>"]`, with `[]`.
  - Every env var and every other field stays as parsed. This is asserted in memory before the write and on
    read-back after it.
- **Fail safe (B9):**
  - A config that is unreadable, truncated, has a duplicate key (`object_pairs_hook`) or has an unexpected shape is
    "not audited", nothing is written to it, and the screen says so.
  - A failing client CLI is never read as "absent".
  - Ask *what if the write was torn?* of every write: mkstemp in the same directory, the mode set before any byte is
    written, fsync, then `os.replace`.
- **Consent (#179 item 6):** the plan lists every change, and only those are made (A4). The existing `confirm`
  gate is the ask; `NONINTERACTIVE=1` auto-confirms, as it does for every step.
- **Bounded (S2):** at most one server process at a time, with a 20 s timeout, its process group killed and the
  process reaped. Tests assert that no process survives.
- **Temp paths (S1):**
  - **Shell:** `mktemp -d`.
  - **Python:** `tempfile`.
  - **Tests:** a fixture `HOME`, never the real `~`.
- **Python:** stdlib only, runs on 3.9 through 3.14, invoked with `-I`. A test parses it with
  `ast.parse(..., feature_version=(3, 9))`.
- **bash 3.2:**
  - no `declare -A`;
  - `set -euo pipefail`;
  - `|| x=""` on pipeline assignments;
  - no tail-position conditionals;
  - `${a[@]+"${a[@]}"}` for any array that may be empty.
- **PowerShell 5.1 (W tasks):**
  - no `?:`, `??`, `?.`, `&&` or `||`;
  - every native command through `Invoke-Native*`;
  - Python is run from a file, never from `-c` code containing `"`.
- **Shared shell functions are byte-identical** in the three macOS scripts (`check-duplication.py`), and later in the
  three Windows ones. No `main()` changes (A6).
- **Plan lines name what runs, truthfully.** A row describes only what the `.py` will do, never what a gate script
  does. They keep the `Internal MCP servers` label for `check-plan-covers-steps.py`.
- **Gate helpers marked KEEP IN SYNC are byte-identical in all four `.sh`,** enforced by a test, not by the comment
  (CSA-Plugins#199).
- **Bump `SCRIPT_VERSION` in every changed `.sh`/`.ps1`.** The `.py` declares its own and is bumped by hand, like
  `csa-claude-connectors.py`. `check-script-versions.py` reads only `.sh`/`.ps1`, and no defect has shipped that a
  new guard would encode (ADR-005).
- **New test files go into `tools/check-all.sh` and `lint.yml`:** the ubuntu job, plus the `macos-latest` job under
  both `python3` and `/usr/bin/python3`. `check-all.sh` must be fully green on macOS; #169 closed on 2026-11-11.
  Read the tail and the exit code.
- **Commit subjects state the claim.** Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus (each pinned by a named test)

1. **A developer's deliberate source-checkout registration.**
   - When it is working, with a write allowlist in env, it is left **byte-identical** and warned about (D1).
   - When it is Cellar-pinned, the plan says the next `brew upgrade` deletes its interpreter.
   - When it is dead, it is re-pointed with its env kept (user scope), or reported (local scope, D2).
   - Tests: `working_elsewhere_left_and_warned`, `cellar_venv_warned`, `homebrew_opt_is_not_cellar`,
     `dead_user_scope_repointed_env_kept`, `local_scope_left_until_d2`.
2. **A registration with secrets in env.**
   - No value reaches stdout, stderr, any argv, the plan file, the ledger, or a handshake diagnostic. It is masked
     there as `<KEY>`.
   - The value *is* carried into the repaired entry.
   - The file's mode and its backup's mode are never wider.
   - Tests: `secret_values_never_emitted`, `no_client_cli_writes`, `desktop_mode_0600_kept`,
     `backup_same_mode_and_pruned_to_3`, `exits_before_answering_masked`.
3. **Clients not installed.** The output says "not installed" or "no config yet (#156)", never "fine", and nothing
   is written. Tests: `client_absent_not_installed` (for Codex, Gemini and Desktop) and `desktop_config_dir_absent`.
4. **Configs that are unreadable or malformed (B9):**
   - truncated JSON;
   - JSONC comments in Gemini settings;
   - a duplicate key;
   - an `mcpServers` that is not a dict;
   - a Codex without `--json`, or with a failing CLI;
   - an unreadable plan file.

   Each is "not audited", nothing is written, and the screen says so. Tests: `torn_claude_json_untouched`,
   `jsonc_gemini_not_audited`, `duplicate_key_is_unreadable`, `codex_json_unsupported_not_audited`,
   `codex_list_failure_is_not_absence`, `unreadable_plan_file_applies_nothing`.
5. **A client running and holding the config.**
   - The file changes between our read and our replace: the write is abandoned with "changed while this ran; run
     again".
   - A read-back mismatch restores the backup.
   - Claude Desktop running: the edit still goes ahead, with the restart to-do. The worst case is that Desktop writes
     its old copy back, which is today's state, and the next run repairs again. Task 6 measures whether Desktop and
     a Claude Code session do this.
   - Tests: `concurrent_change_aborts_write`, `readback_mismatch_restores`, `desktop_running_writes_with_restart_todo`.
6. **Codex and Gemini CLI versions whose `mcp` subcommands differ.**
   - Codex's JSON comes as a list or a dict, with `transport` nested or flat.
   - The TOML table header may be quoted.
   - A multi-line `args` array is refused rather than guessed.
   - Gemini has no `get`, and its extra fields (`trust`, `includeTools`, `timeout`) survive.
   - Each client's handshake env is an approximation that Task 6 measures.
   - Tests: `codex_json_shapes`, `codex_quoted_table_header`, `codex_multiline_args_refused`,
     `codex_readback_mismatch_restores`, `gemini_extra_fields_kept`, `desktop_env_is_minimal`.
7. **Plan and run drift.** A finding that appears, or changes, after consent is not acted on. Tests:
   `unapproved_finding_not_repaired`, `changed_since_plan_not_written`.
8. **Idempotence.** A second run writes nothing: every config's inode, mtime and bytes are unchanged, and no backup
   is made. Tests: `second_run_noop`, plus the Task 6 acceptance run.

---

### Task 1: `csa-mcp-registrations.py plan` — find every CSA registration in four clients, and say what is wrong with each, without writing anything

**Files:**
- Create: `scripts/csa-mcp-registrations.py` (`SCRIPT_VERSION`, a module docstring in the `csa-claude-connectors.py`
  style, `plan` only in this task).
- Create: `tests/test_mcp_registrations.py`. It imports the shipping file with `importlib` for unit cases, and runs
  it as a CLI with a fixture `HOME` and stub `codex`/`gemini`/`claude` on `PATH` for end-to-end cases. Wire it into
  `check-all.sh` and `lint.yml`.

**Interfaces:**
- **`SERVERS`** maps each canonical name to its entry point:
  - `csa-google-workspace` → `csa-google-workspace-mcp`;
  - `csa-google-gmail-calendar` → `csa-google-gmail-calendar`;
  - `csa-skilljar` → `csa-skilljar-mcp`;
  - `csa-zendesk` → `csa-zendesk-mcp`.

  The standard binary is `$HOME/.local/bin/<entry>`.
- **Readers.** Each returns `(status, [Registration])`, and `status` is one of `ok`, `not installed`,
  `no config yet`, or `not audited: <why>`.
  - **Claude Code:** `$CLAUDE_CONFIG_DIR/.claude.json`, or `~/.claude.json` when that is unset. User scope is
    top-level `mcpServers`; local scope is `projects[<dir>].mcpServers`.
  - **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json`. "Not installed" when
    neither `/Applications/Claude.app` nor `~/Applications/Claude.app` exists.
  - **Codex:** `codex mcp list --json`, run with `CODEX_HOME` honoured, a 30 s timeout and stdin closed.
  - **Gemini:** `~/.gemini/settings.json`, user scope. "Not installed" without a `gemini` on `PATH`.
  - On `win32`, every reader returns `not audited: Windows support is #184 (Task 1W)`.
- **`Registration`:** client, scope, project, name, command, args, env (in memory only), the other fields untouched,
  and a fingerprint. The fingerprint is the sha256 of the command, the args and the **sorted env key names**, never
  the values.
- **Classification.** Each finding has a state, a reason, warnings and an action. The reasons, verbatim:
  - **`standard`:** the realpath equals the standard binary's realpath, which also covers uv's own tool path. When
    the standard link is itself dead, the action is none: "its setup reinstalls it", as Plan 1 rebuilds it.
  - **`dead`:**
    - `its command does not exist`;
    - `its command is not executable`;
    - `its Python no longer exists`: the shebang interpreter, or the venv's `bin/python3`, is dangling or missing, or
      `pyvenv.cfg` `home` is gone;
    - `its Python does not run`: `<interp> -I -c "import sys"` fails or takes more than 10 s. This is the
      incident's first stage.
  - **`elsewhere`:** it works but is not the standard binary: `it points at <~-path>, not ~/.local/bin/<entry>`.
  - **Warning:** `it runs from a venv built on a Homebrew Cellar Python, which the next brew upgrade deletes`. Use
    Plan 1's recorded-path rule: the first hop out of the venv, or `home`, literally contains `/Cellar/`. An `opt/`
    path is fine.
  - A bare command resolves on the client's PATH (A8).
- **Actions:**
  - **`re-point`** applies when all of these hold:
    - the state is `dead`;
    - the scope may be repaired (user always; local only when `REPAIR_LOCAL_SCOPE`);
    - `args` is empty or the interpreter `-m` form.
  - With `REPOINT_WORKING_ELSEWHERE`, `elsewhere` also re-points.
  - Otherwise **`leave`**, with the reason, plus a to-do where somebody has to act.
- **Output:** `plan --out FILE` prints one line per row on stdout as `row<TAB>text`. The rows are:
  - each `re-point` and `leave`;
  - each warning;
  - each client that is not audited, and why;
  - a count line: `<n> CSA registrations in <m> clients; <k> need nothing`.

  It writes the findings, as JSON with no values and mode `0600`, to `FILE`. It exits 0, or 2 on an internal error,
  in which case `FILE` is not written.

- [ ] **Step 1: Failing tests.**
  - **Fixtures:**
    - real-shaped symlink chains: uv's `cpython-3.14-…` link, Homebrew `opt/python@3.14 → ../Cellar/…`, and a deleted
      Cellar directory;
    - a source-checkout `.venv` whose `bin/csa-zendesk-mcp` has an absolute shebang into its own `bin/python`;
    - stub `codex`, printing JSON from a scenario file;
    - fake secret values, unique strings that a test can grep for.
  - **Cases:**
    - `standard_registration_is_fine` (including `~/.local/share/uv/tools/<pkg>/bin/<entry>`);
    - `dead_command_missing`, `dead_command_not_executable`;
    - `dead_shebang_interpreter` (the incident's second stage);
    - `dead_venv_home_missing` (the CINO's local-scope shape);
    - `python_does_not_run` (the first stage);
    - `working_elsewhere_left_and_warned`, `cellar_venv_warned`, `homebrew_opt_is_not_cellar`;
    - `bare_name_desktop_uses_launchd_path`;
    - `local_scope_found_and_reported`, `local_scope_missing_project_skipped` (only logged);
    - `interpreter_module_form_repairable`, `other_args_not_repairable`;
    - `http_registration_not_audited`;
    - `client_absent_not_installed` (×3), `desktop_config_dir_absent`;
    - `torn_claude_json_untouched`, `duplicate_key_is_unreadable`, `jsonc_gemini_not_audited`;
    - `codex_json_unsupported_not_audited`, `codex_list_failure_is_not_absence`, `codex_json_shapes`;
    - `claude_config_dir_respected`;
    - `plan_file_has_no_values`;
    - `plan_writes_nothing`: every fixture file byte-identical, and no new file but `--out`;
    - `token_dirs_unreadable_still_plans`: the servers' config directories at mode `000`, which proves it never
      reads them;
    - `py39_syntax`;
    - `servers_match_internal_setups`: the `SERVERS` names equal `CSA_INTERNAL_SETUPS` in all six scripts.
- [ ] **Step 2:** run `python3 tests/test_mcp_registrations.py`. Expected: FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4: Prove the tests can fail.** Each mutation must be caught by the named test:
  - classify by `realpath`, not the recorded path, for Cellar: `homebrew_opt_is_not_cellar`;
  - swallow `codex` failure as "no registrations": `codex_list_failure_is_not_absence`;
  - hash the env values into the fingerprint: `plan_file_has_no_values`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: csa-mcp-registrations.py plan finds every CSA MCP registration in four clients and says which are dead, without reading a credential or writing a file`.

### Task 2: `apply` — re-point an approved dead registration in place, changing only its command

**Files:**
- Modify: `scripts/csa-mcp-registrations.py`, adding `apply [--approved FILE]`. Without `--approved`, a person
  running it by hand re-plans and applies, as `csa-claude-connectors.py --apply` does. Bump its version.
- Modify: `tests/test_mcp_registrations.py`.

**Interfaces:**
- **Re-audit, then act on each `re-point` finding** only when it is in the approved file with the same
  `(client, scope, project, name, fingerprint)`. Otherwise:
  - `found after you agreed to the plan; not changed — run again`;
  - nothing at all, when the re-audit finds it is now fine. A gate setup may have fixed it.
- **Precondition:** the standard binary exists and runs. Otherwise `leave`, with
  `its standard binary is not installed yet`.
- **`edit_json(path, locate, new_command, new_args)`** is used for Claude Code, Desktop and Gemini:
  1. stat and read the file, parse it with duplicate-key detection, and check the fingerprint;
  2. build the new entry, and assert that only `command` and `args` differ;
  3. back up to `<path>.bak-<YYYYmmddHHMMSS>` with `copy2`. Check the backup's mode, and prune to 3 generations,
     with the same regex and count as `csa-claude-connectors.py`, deliberately;
  4. `mkstemp` in the same directory, `fchmod` to the original's mode before writing, write `indent=2,
     ensure_ascii=False`, then fsync;
  5. stat again. If the inode, mtime or size moved, unlink the temp file and report
     `changed while this ran; not written — run again`;
  6. `os.replace`;
  7. read back and parse. If the entry is not exactly the intended one, restore the backup and warn.
- **`edit_codex(name, old_command, new_command, args_rule)`:**
  - Find the table `[mcp_servers.<name>]`, or `[mcp_servers."<name>"]`, exactly once.
  - Inside it, until the next header, find exactly one `command = "<old, TOML-escaped>"` line, and, for the
    interpreter form, exactly one single-line `args = ["-m", "<module>"]`.
  - Otherwise refuse with `its Codex entry is laid out in a way this cannot edit safely; left as it is`.
  - Write with steps 3–6 of `edit_json`. Read back with `codex mcp get <name> --json`: the command is new, and every
    other field equals the original. On a mismatch, restore.
- **To-dos:** `Restart Claude Code`, `Restart Claude Desktop` (the gate's title, so they de-duplicate),
  `Restart Codex` or `Restart Gemini`, at order 10. Left registrations get order 40. All go to `CSA_TODO_FILE` when it
  is set; otherwise `info<TAB>` lines say the same thing.
- **Output lines:**
  - `ok<TAB><name> re-pointed in <client> (<scope>) at ~/.local/bin/<entry>; its <n> settings kept`;
  - `warn<TAB>…` for each refusal.

- [ ] **Step 1: Failing tests:**
  - `dead_user_scope_repointed_env_kept`: the env dict and every other key are equal, and only `command` differs;
  - `local_scope_left_until_d2`, and `local_scope_repaired_when_enabled` (the constant flipped through the module);
  - `working_elsewhere_byte_identical`;
  - `desktop_mode_0600_kept`, `backup_same_mode_and_pruned_to_3`;
  - `codex_line_edit_keeps_other_fields` (`startup_timeout_sec`, `env_vars`, `enabled`), `codex_quoted_table_header`,
    `codex_multiline_args_refused`, `codex_readback_mismatch_restores`;
  - `gemini_extra_fields_kept`;
  - `unapproved_finding_not_repaired`, `changed_since_plan_not_written`, `unreadable_plan_file_applies_nothing`;
  - `concurrent_change_aborts_write`, through a test hook between the read and the replace;
    `readback_mismatch_restores`;
  - `standard_binary_missing_no_repoint`;
  - `desktop_running_writes_with_restart_todo`;
  - `secret_values_never_emitted`: the fake secrets are absent from stdout, stderr, the plan file and the ledger, and
    present in the repaired config;
  - `no_client_cli_writes`: the stub clients log their argv; only `codex mcp list|get --json` may appear, and no
    value is in any argv;
  - `todo_per_client_restart`, `todo_printed_without_ledger`;
  - `second_run_noop`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4: Prove the tests can fail.** Each mutation must be caught:
  - drop the fingerprint comparison: `changed_since_plan_not_written`;
  - write with plain `open()`, so the file is 0644: `desktop_mode_0600_kept`;
  - copy `env` through `str()`: `dead_user_scope_repointed_env_kept`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: a dead CSA MCP registration is re-pointed at its standard binary in place, changing only its command, and only when the plan showed it`.

### Task 3: `verify` — each registered server answers an MCP `initialize` handshake, launched as its client launches it

**Files:**
- Modify: `scripts/csa-mcp-registrations.py`, adding `verify`. Bump its version.
- Modify: `tests/test_mcp_registrations.py`, with stub MCP servers written as small Python scripts by the test.

**Interfaces:**
- **What is launched.** Re-audit, and launch each `standard` or `elsewhere` registration. A `dead` one is reported
  `does not start: <reason>` and never launched.
  - Launches are de-duplicated on `(command, args, launch env)`. The output names every client that shares a launch.
- **The launch env, approximating each client** (Task 6 measures it):
  - **Claude Code, Codex and Gemini:** the installer's environment, minus `CSA_TODO_FILE`, `CSA_LOG`, `CSA_DEBUG`,
    `CSA_NESTED` and `CSA_REGISTRATIONS_*`, plus the registration's env.
  - **Claude Desktop:** `HOME`, `USER`, `LOGNAME`, `TMPDIR`, and `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, plus the
    registration's env.
  - **An env value containing `$`:** the launch is not made, and the output says `not checked: its environment uses
    $-expansion, which this check does not reproduce`.
- **The exchange:**
  - Send `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},
    "clientInfo":{"name":"csa-desktopsetup-check","version":SCRIPT_VERSION}}}` and a newline.
  - Read stdout until a JSON object with `id == 1` arrives, or 20 s pass. Non-JSON lines are skipped and counted.
  - **Pass:** `result.serverInfo.name` is present. Report the name and the version.
  - **Failure messages:**
    - `answered with error <code>`;
    - `exited <code> before answering: <last stderr line>`, masked and cut to 200 characters;
    - `did not answer within 20s`.
- **Lifecycle:**
  - `start_new_session=True`, stdin a pipe.
  - Close stdin, wait 2 s, then send SIGTERM to the process group, wait 2 s, then SIGKILL it, and reap.
  - Never two children at once.
- **Masking:**
  - every registration env value of 4 characters or more becomes `<KEY>`;
  - then the gate's `csa_log` token patterns are applied: `access_token`, `refresh_token`, `client_secret`, `ghp_…`,
    `Bearer …`.
- **Output lines:**
  - `ok<TAB><name> answers an MCP initialize handshake, launched as <clients> launch it (<server> <version>)`.
  - `warn<TAB>…`, with an order-45 to-do: `<name> did not start when launched as <client> launches it`.
  - The wording never claims the server works *in* the client (#177).

- [ ] **Step 1: Failing tests:**
  - `answers`, `junk_before_response_tolerated`, `error_response_reported`;
  - `silent_server_times_out_and_is_killed`: after the run, no process of the stub's process group exists;
  - `exits_before_answering_masked`: the stub echoes its env to stderr, and no value reaches the output;
  - `one_process_at_a_time`: the stub holds an exclusive lock file and fails on contention;
  - `deduped_launches`;
  - `desktop_env_is_minimal`: the stub writes its env **key names** to a file;
  - `dollar_env_not_checked`, `dead_registration_not_launched`;
  - `token_files_untouched`: a token file at mode `000`, unchanged by stat before and after;
  - `failure_todo_and_ledger_absent_print`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4: Prove the tests can fail.** Each mutation must be caught:
  - remove the process-group kill: `silent_server_times_out_and_is_killed`;
  - skip masking: `exits_before_answering_masked`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: every registered CSA MCP server is checked with an initialize handshake, one at a time, bounded, with no secret in what it prints`.

### Task 4 (macOS): the three entry scripts show the repairs in the plan, then apply and check them after the setups

**Files:**
- Modify: `scripts/macos-ai-tools.sh`, `scripts/macos-update.sh` and `scripts/macos-plugins.sh`.
  - **Add, byte-identical in all three:**
    - `csa_registrations_py`;
    - `csa_registrations_python`;
    - `csa_registrations_preview`;
    - `repair_csa_registrations`.
  - **Call `csa_registrations_preview`** from each `preflight`, inside the `Internal MCP servers` block, before
    `each prints what it may do before it is used`. In `-ai-tools` that is after the `csa_tool_repairs` rows.
  - **Call `repair_csa_registrations`** as the last line of `setup_csa_internal_tools`, after its loop, so it is
    behind the same `gh` gate.
  - Bump all three versions.
- Modify: `tests/test_mcp_registrations.py`, adding `wiring_` cases that extract the four functions and
  `setup_csa_internal_tools` from each script.

**Interfaces:**
- **`csa_registrations_py`** prints a readable `.py` path, or nothing.
  - If `$CSA_REGISTRATIONS_PY` is set and readable, it prints that.
  - Otherwise, once per run, it creates `CSA_REG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csa-registrations.XXXXXX")"` and
    runs `curl -fsSL -H 'Cache-Control: no-cache' <raw HEAD>/scripts/csa-mcp-registrations.py`.
- **`csa_registrations_python`** prints `python3` from `PATH` if it runs and is at least 3.9. It never prints
  `/usr/bin/python3` when `xcode-select -p` fails, because that stub opens an install dialog.
- **`csa_registrations_preview`:**
  - **When it skips, and what it prints:**
    - `gh` is missing or unauthenticated, or the gate probe fails: it prints only the header, worded "if your GitHub
      account has CSA-Internal access", as the existing rows are.
    - There is no Python or no `.py`: it prints `registration audit skipped: <why>; nothing will be changed`.
  - **Otherwise** it runs `plan --out "$CSA_REG_DIR/plan.json" </dev/null`, with
    `out="$(…)" || rc=$?`. It prints each `row` line under the 23-column indent, through the same helper as the rows
    around it, so `check-log-coverage.py` holds.
  - **A non-zero exit** prints `registration audit failed; nothing will be changed` and removes the plan file.
- **`repair_csa_registrations`:**
  - **Apply:** run `apply --approved "$CSA_REG_DIR/plan.json"`. When there is no plan file, pass an empty approved
    file, so every finding is reported, not acted on.
  - **Verify:** then run `verify`.
  - **Printing:** map `ok`, `info` and `warn` lines onto `success`, `info` and `warn`.
  - **Clean-up:** remove `$CSA_REG_DIR`. Never fail the run.
- **The plan's header row** in all three scripts, verbatim:

  ```
  then audit their registrations in Claude Code (user and local scopes), Claude Desktop, Codex and Gemini,
  re-point a dead one at ~/.local/bin keeping every setting, and check each answers an MCP initialize handshake
  ```

  The per-finding rows follow it.

- [ ] **Step 1: Failing tests:**
  - `preview_rows_under_internal_mcp_servers`, for each of the three scripts;
  - `repair_uses_the_previewed_plan`: the same path reaches `--approved`;
  - `fetch_failure_says_skipped`: a stub `curl` fails;
  - `py_failure_survives_set_e`: the stub `.py` exits 2;
  - `no_fixed_temp_path`: the directory comes from `mktemp` and is gone afterwards;
  - `non_member_silent`: the `gh` probe fails, so there are no rows and no apply;
  - `override_env_used`;
  - `apple_python_stub_not_invoked_without_clt`;
  - `windows_twin_exists`: `windows-*.ps1` on the Windows branch define `Show-CsaRegistrationsPreview` and
    `Repair-CsaRegistrations`. While that branch is unmerged, print a per-case
    `SKIP (Windows twin pending #184, Task 4W)` and still exit 0.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3:** implement. Bump the three versions.
- [ ] **Step 4:** run the test, `check-duplication.py`, `check-plan-covers-steps.py`, `check-log-coverage.py`,
  `test_headless.py`, `test_prompt_visibility.py`, `test_internal_setup_lists.py` and `./tools/check-all.sh`. All
  pass.
- [ ] **Step 5: File an issue for a Plan 1 gap noticed while planning.** `-update`'s and `-plugins`'s plans do not list
  the tool rebuilds (`csa_tool_repairs`) that their gate setups perform. It is not fixed here.
- [ ] **Step 6: Commit:**
  `feat: every macOS entry point lists the CSA registrations it will re-point before asking, then repairs and checks them after the server setups`.

### Task 5: The docs say what the installer now does to registrations, and the Windows halves are handed to #184

**Files:**
- Modify: `ENGINEERING.md`.
  - **"What the scripts are":** add the `.py` beside `csa-claude-connectors.py`.
  - **Layout.**
  - **The guard layer:** the test count.
  - **A new § "Registration audit and repair"** under "The CSA contracts". It covers:
    - the readers;
    - the reasons, verbatim;
    - the command-only rule;
    - D1 and D2, with their constants;
    - the approved set;
    - the handshake, and what it does *not* prove (#177);
    - the credential rule;
    - concurrency and backups.
- Modify: `AGENTS.md`. Update the trap *"Which clients get CSA tooling depends on who registers it"* to say that this
  repo also re-points existing CSA registrations in place, and never creates one. Do not edit `CLAUDE.md` or
  `GEMINI.md`.
- Modify: `FRICTION.md`, with two measured entries:
  - macOS shows every account's argv, so a secret never goes on a command line;
  - Claude Code's narrowest scope wins, and the incident's dead path survived in local scope after user scope was
    repaired.
- Modify: `TODO.md`. The #184 row gains `1W`, `4W`, `G1W`, `G2W` and `6W`.
- **On GitHub:**
  - comment on #184 with the W tasks;
  - comment on #179 with D1 and D2 as they stand;
  - link csa-zendesk#70 and csa-google-gmail-calendar#45.

- [ ] **Step 1:** write. Then run `check-todo-citations.py`, `check-paste-safety.py` and `./tools/check-all.sh`.
- [ ] **Step 2: Commit:**
  `docs: ENGINEERING says the installer re-points a dead CSA registration in place and checks each server answers, and the Windows halves are on #184`.

### Task G1 (CSA-Plugins, `.sh`): every client command runs from a fresh empty directory, so a local or project registration in the caller's directory can't stand in for the user's

**Why:** the four scripts run `claude mcp get`, `codex mcp get` and `gemini mcp list` from DesktopSetup's working
directory.
- **Claude Code reports the narrowest scope that wins there.** If the caller stands in a project whose local entry has
  no CSA env, zendesk, skilljar and gw take their "unconfigured" branch. They then `remove --scope user` and re-add
  with defaults, which drops a write allowlist or a narrowed profile. That is the policy item 2 protects.
- **A shadowing entry can also hide a missing user entry:** ggc registers with Claude Code only when `get` finds
  nothing, and Codex and Gemini are probed the same way.

**Files** (in the scratch clone):
- Modify: the four `internal-setup/csa-*-setup.sh`.
  - **Create the directory once,** near the top:
    `CSA_CLIENT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csa-client.XXXXXX")"`, removed by an EXIT trap. Verify that no
    script already sets one.
  - **Add the helper `csa_client() { ( cd "$CSA_CLIENT_DIR" && "$@" ); }`.**
  - **Route every `claude mcp`, `codex mcp` and `gemini mcp` call through it,** including `csa_gw_registered_env` and
    `register_other_clients`.
  - Both helpers are marked KEEP IN SYNC.
- Modify: `internal-setup/check-setup-scripts.py`. Add **defect 30**: every uncommented `claude mcp`, `codex mcp` or
  `gemini mcp` call in a `.sh` goes through `csa_client`. Its self-test mutation unwraps one call.
- Create: `internal-setup/test-client-registration.py`, wired into `checks.yml`, where the cross-repo job can see
  `.desktopsetup/`.

- [ ] **Step 1: Measure before changing anything (D5, predict then test).**
  - **Where:** in an isolated `HOME` (and `CODEX_HOME`), with the real CLIs and a dummy server named `csa-plan2-probe`,
    never a CSA one.
  - **What:** does `claude mcp get` from a project with a local entry report the local one? Does `gemini mcp list`
    from a directory with `.gemini/settings.json` list the project entry? Does Codex read a project-level config?
  - **Record** the result in the PR body.
  - **If a client shows no shadowing,** leave it out of the wrapper and the rule, and record why. If none does, G1
    shrinks to the record.
- [ ] **Step 2: Failing tests:**
  - `probe_runs_in_fresh_dir` (×4): the stubs log `$PWD`;
  - `shadowing_cwd_does_not_replace_user_policy` (×4): run from a directory holding a marker. The marker makes the
    stub `claude` answer with an entry that has no env. Assert there is no `remove`.
  - `client_helper_identical_in_four_scripts` and `register_other_clients_identical` (part of CSA-Plugins#199);
  - `desktopsetup_server_table_matches`: each script's `MCP_NAME` and entry-point name equal `SERVERS` in
    `.desktopsetup/scripts/csa-mcp-registrations.py`. Until that file exists on DesktopSetup's main, print a per-case
    SKIP.
- [ ] **Step 3:** implement. Then run `check-setup-scripts.py --self-test`, validated against current `main`, where
  defect 30 must report the unwrapped calls.
- [ ] **Step 4:** run the tests, `test-tool-interpreter.py`, and DesktopSetup's `check-shell-tail-conditionals`,
  `check-pipeline-assignments` and `check-line-endings` against `internal-setup/`.
- [ ] **Step 5: Commit:**
  `fix: internal-setup asks every client about its user registration from an empty directory, so a project's own entry can no longer get a user's policy replaced with defaults`.

### Task G2 (CSA-Plugins, `.sh`): writing Claude Desktop's config never widens its mode

**Why:**
- **csa-skilljar inlines secrets into `claude_desktop_config.json` and chmods it `0600`.**
- **The other three writers don't keep that mode.**
  - **What they do:** gw, ggc and zendesk write a fresh `<cfg>.tmp` or `<cfg>.csa-tmp` with plain `open()`, which
    gives 0644 under umask 022, then `os.replace` it.
  - **When it happens:** on a rerun where one of them registers an absent entry.
  - **What it does:** it leaves the secrets world-readable. skilljar re-narrows the file only when it writes itself.
- **The temp name is also fixed (S1).**

**Files:** the four `.sh` Desktop heredocs:
- `tempfile.mkstemp(dir=<cfg dir>, prefix=".csa-")`, which is created 0600;
- `shutil.copymode(cfg, tmp)` when `cfg` exists;
- fsync, then `os.replace`;
- the temp file is removed on any failure.

**Plus** a defect 31 rule with its self-test, and cases in `test-client-registration.py`:
- `desktop_config_mode_kept`: a fixture at 0600 stays 0600 after each script adds its entry;
- `no_temp_file_left_beside_config`.

- [ ] **Steps:** fail, implement, run (as G1, Step 4). **Commit:**
  `fix: internal-setup's Claude Desktop writes keep the config's mode, so a file holding skilljar's secrets never becomes world-readable`.

### Task 6: Acceptance on macOS: from a seeded broken state, one run repairs exactly what the plan showed, and a second changes nothing

**Files:**
- Create: `plans/reviews/2026-11-12-registration-repair-acceptance.md`, scrubbed of secrets, personal data and
  names.

- [ ] **Step 1: An isolated run.**
  - **Environment:** a scratch `HOME`, `CODEX_HOME` and `TMPDIR`, with the real `codex` and `gemini` CLIs and the
    branch's `.py` (`CSA_REGISTRATIONS_PY`).
  - **Standard binaries:** `$HOME/.local/bin/<entry>` symlinks to the real installed entry points. Launched with
    the scratch `HOME`, they find no token.
  - **Seed:**
    1. user-scope csa-zendesk, dead: a `.venv` whose `home` is a deleted Cellar directory. Its env includes a fake
       `CSA_ZD_ALLOWLIST_WRITE`.
    2. The same shape in local scope, for a scratch project.
    3. A working source-checkout csa-skilljar with fake secret env, built on a uv Python.
    4. A Desktop config at `0600`:
       - a skilljar entry with fake secrets;
       - a gw entry with a bare command name;
       - a `preferences` key.
    5. A Codex entry that is dead and has `startup_timeout_sec = 30`.
    6. A Gemini entry that is dead, with `trust` and `includeTools`.
  - **Run** `plan`, `apply --approved` and `verify`.
  - **Assert that run 1 changed exactly** items 1, 4 (gw), 5 and 6, and left 2 (D2 default) and 3 (D1 default)
    alone.
  - **Compare in process,** printing only `identical: yes|no`:
    - the env and the other fields;
    - the modes and the backups.
  - **No fake secret appears in any captured output.**
  - **The servers' config directories:** their stat is unchanged.
  - **Run again,** and assert no write and no backup.
- [ ] **Step 2: Measurements, recorded:**
  - **M1.** With a Claude Code session running in a scratch project, edit a dummy `csa-plan2-probe` user entry's
    command directly, then end the session. Does the edit survive?
  - **M2.** The same for a running Claude Desktop, with its own dummy entry, across a preference change and a quit.
    This touches the real Desktop config, so it needs the CINO's go-ahead. The config is backed up first, and only
    the dummy entry is added and removed.
  - **M3.** Which env key names each client passes to a stdio server. A dummy server writes **key names only**.
  - **M4.** Each handshake's duration, against the 20 s timeout.
  - **If M1 or M2 shows the edit lost, change Review Focus 5's behaviour,** under P1, and record why. For Desktop,
    that means skipping while it runs and adding a to-do to quit it.
- [ ] **Step 3: The real run on this Mac is queued for the CINO's go-ahead,** after the merges.
  - **Under the defaults,** it repairs nothing: every user entry is standard. It reports the dead local-scope
    csa-zendesk (D2) with a to-do, and checks every registration.
  - **Under D2 (b),** it re-points that entry, keeping `CSA_ZD_ALLOWLIST_WRITE`.
  - **A second run must print no repair.**
- [ ] **Step 4: Commit:**
  `docs: acceptance evidence — one run re-points exactly the planned dead registrations with every setting kept, a second changes nothing`.

---

### Windows halves (held for the Windows session, #184)

These keep the platforms from drifting. They are specified now, and run only after #184's measurements.

### Task 1W: the `.py` audits, repairs and checks on Windows

**Measure first, on a real Windows machine:**
- **Claude Desktop's config path.** Is it `%APPDATA%\Claude\` or the MSIX-virtualised
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`? Which one does Desktop actually read (#156, #168)?
- **Interpreters behind entry points.** How do you find the interpreter behind a uv trampoline
  `~\.local\bin\<entry>.exe`, and behind a pip console-script `.exe` in a venv's `Scripts\`? What does
  `pyvenv.cfg` `home` look like for each?
- **Bare names.** How does each client resolve a bare name: `PATHEXT`, and Desktop's environment?
- **The env Desktop passes** to a stdio server.
- **Locking.** Does `os.replace` fail while Desktop or a Claude Code session holds the file?

**Then:**
- Replace the `win32` "not audited" stubs with real readers and classifiers. The reasons stay verbatim, except that
  `Scripts\python.exe` takes the place of `bin/python3`.
- **The handshake:** `CREATE_NEW_PROCESS_GROUP`, then `taskkill /T /F /PID` on timeout.
- **Running-client detection** is by path, never by process name. Claude Code's updater renames its running image
  (AGENTS.md trap).
- **A locked file** gives `in use by <client>; not written — close it and run again`.

**Tests:** the same test file's Windows cases, run on `windows-latest` CI and on the machine. A green CI run is not a
Windows run (R5).

**PR:** a draft, listing the measurements.

### Task 4W: the three `.ps1` entry scripts wire it as Task 4 does

**Files:** `windows-ai-tools.ps1`, `windows-update.ps1` and `windows-plugins.ps1`.
- **Add, byte-identical in all three:**
  - `Get-CsaRegistrationsPy`;
  - `Show-CsaRegistrationsPreview`, called from each `Show-Preflight`;
  - `Repair-CsaRegistrations`, the last call in `Invoke-CSAInternalSetup`.
- **Python** is the CSA Python from Plan 1's Task 4W, `Find-CsaPython`, which must land first.
- **The `.py` runs through a bounded `ProcessStartInfo` helper** that captures stdout. Its arguments are paths and
  flags only, quoted for paths with spaces.
- **Temp directories:** `[IO.Path]::GetTempPath()` plus a GUID directory.

**Tests:** Pester cases that mirror the `wiring_` cases. Once these land, `windows_twin_exists` passes instead of
skipping. Then run PSScriptAnalyzer, `check-powershell-native.py` and `check-duplication.py`.

**PR:** a draft.

### Task G1W and G2W (CSA-Plugins, `.ps1`)

- **G1W:** every `claude`, `codex` and `gemini` `mcp` call in the four `.ps1` runs with its working directory set to
  a fresh empty temp directory. Use `Push-Location`/`Pop-Location` in `try`/`finally`, inside `Invoke-CsaNative`'s
  scriptblock. Apply Step 1's measurement on Windows.
- **G2W:** measure whether a new file in Desktop's config directory inherits a user-only ACL. Change code only if it
  is wider than the file it replaces. Fold in CSA-Plugins#198, which is the same files.

**PRs:** drafts.

### Task 6W: acceptance on Windows

Task 6's seed and assertions, on the Windows machine, from the branches. Record the evidence on #184.

---

**After Task 6:**
- A whole-branch review per repo, on `fable`.
- A review brief (A1), `plans/2026-11-12-registration-repair-review-brief.md`, with claims to verify.
- The PRs, in the merge order above.
- A resumption summary.
