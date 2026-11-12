# CSA MCP registrations: a rerun audits every client, re-points a dead one in place, and checks each server answers: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (CINO rule B1: always
> subagent-driven) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every
> review runs on the strongest model, `fable` (B12). **Task 0's measurements run before any build task, and a build
> task starts only when the measurements it depends on are recorded** in
> `plans/reviews/2026-11-12-registration-repair-measurements.md`. The build never waits on the CINO: where a decision
> or a go-ahead is pending, it builds the safe default, and his answer later changes one constant and its pinning
> test.
>
> **Companions:** the Windows halves are in [`2026-11-12-registration-repair-windows.md`](2026-11-12-registration-repair-windows.md).
> The two spec reviews' dispositions are in
> [`reviews/2026-11-12-registration-repair-spec-reviews.md`](reviews/2026-11-12-registration-repair-spec-reviews.md).

**Goal:** a rerun of any macOS entry point (`-ai-tools`, `-update`, `-plugins`) finds every registration of the four
CSA MCP servers in Claude Code, Claude Desktop, Codex and Gemini. It shows in the plan which ones it will re-point and
why. After consent it re-points a dead registration at the standard `uv tool` binary, changing nothing but the
command. Once the startup measurement allows it (M5, D5), it also checks that each registered server answers an MCP
`initialize` handshake. A second rerun changes nothing.

**Architecture:**
- **One auditor, in Python, in this public repo:** `scripts/csa-mcp-registrations.py`, with three subcommands:
  `plan` (read-only), `apply` and `verify`. Python because the same file must later serve Windows (R5: "Scripts that
  must run on Windows are Python"). It carries no credential, which is the only reason the gate repo is private.
- **The entry scripts fetch it from `HEAD`,** as they fetch the plugin lists. They run `plan` in the preflight, and
  `apply` then `verify` at the end of `setup_csa_internal_tools`, after the four gate setups have installed or
  rebuilt the binaries. `verify` launches nothing until D5 allows it.
- **A repair is a minimal in-place edit of the client's own config file:** the `command` field, plus `args` in one
  pinned interpreter form, and nothing else. Every env var and every other field stays exactly as it was (#179
  item 2). A registration that runs through a launcher (`uv run`, `uvx`, `npx`), or whose env shapes the
  interpreter, is left alone and reported (A12).
- **The gate repo keeps its leave-alone rule,** which is right for policy. Three `.sh` defects found while planning
  and reviewing are fixed there:
  - **G2** (Desktop config writers create their temp file at the default mode, under a fixed name) and **G3**
    (`csa-skilljar-setup.sh` puts secret-bearing `claude mcp get` output on `python3`'s argv) ship first, in their
    own gate PR, CloudSecurityAlliance-Internal/CSA-Plugins#213, which fixes the `.ps1` too (D6).
  - **G1** (a probe can read a shadowing local or project registration instead of the user's) follows its
    measurement (M7), under D3.
- **The Windows halves** are the companion file's W tasks, for the Windows session in #184. Whether macOS ships first
  is D3.

**Tech stack:** Python 3.9 to 3.14 stdlib only (Apple's `/usr/bin/python3` is 3.9.6), bash 3.2, the house test
harnesses. Windows PowerShell 5.1 and Pester 5.7.1 in the companion.

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
  - it is mode `0600`, inside `~/Library`, which is `0700`;
  - it holds Desktop's own `preferences` and `coworkUserFilesPath`, so Desktop writes this file too;
  - its four CSA entries point at `~/.local/bin`;
  - Claude Desktop was running; `ps -axo comm=` shows its executable as
    `/Applications/Claude.app/Contents/MacOS/Claude`.
- **File modes:** `~/.claude.json` and the Codex config are `0600`; Gemini's `settings.json` is `0644`.
- **`~/.claude.json` backups:** nine, by name only (contents not read). Two match `.bak-<14 digits>`, the name
  `csa-claude-connectors.py` writes and prunes; seven were made by hand or by other tools, and no prune touches them.
- **Codex 0.167:** `codex mcp list --json` returns a list of
  `{name, enabled, disabled_reason, startup_timeout_sec, tool_timeout_sec, auth_status, transport: {type, command,
  args, env, env_vars, cwd}}`. Measured by the planning session; the spec reviewer had no `codex` on PATH and could
  not re-check it.
- **Gemini 0.67:** it has no `mcp get`, and `~/.gemini/settings.json` is plain JSON here.
- **csa-google-gmail-calendar is in neither Codex nor Gemini.** That is the bash 3.2 crash fixed by CSA-Plugins#204;
  the next run adds it.
- **`/usr/bin/python3` is 3.9.6** and has no `tomllib`.
- **Claude Code 2.1.323:** `claude mcp get` from an empty directory, with an isolated `CLAUDE_CONFIG_DIR`, added no
  `projects` entry (spec review).
- **macOS shows every account's process arguments to a standard user.** `ps -axo user,args` printed root's and system
  daemons' argv. A value put on a command line is readable by every local account while that process runs. This
  rules out `claude mcp add -e` and `codex mcp add --env` for a repair (A3).

**What is not measured yet** is Task 0's table. Until a measurement is recorded, the plan calls what it decides
inferred.

**Independent spec reviews (B11):** three, on `fable`, on 2026-11-12. The first, at `a9ab5e4`, found 3 blockers,
10 majors and 7 minors, plus four additions to Task 1W, and surfaced D3 to D6. The second, at `762347a`, found
5 majors and 7 minors; the third, at `1d18298`, found 1 major and 4 minors. All are folded in; the dispositions file
says where each went. Decisions go to the CINO one at a time (K2).

## Decisions

D1, D2, D4 and D5 are each one named constant in the `.py`, pinned by one test. D3 is a merge decision. D6 is decided.
Until the CINO decides, the build ships the safe default.

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
- **Under every option,** a registration that runs through a launcher (`uv run --directory …`, `uvx`, `npx`) is not
  "working elsewhere": it is left, and never launched (A12).
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
  - A local entry usually belongs to a developer's checkout and carries that checkout's policy. The CINO's carries
    `CSA_ZD_ALLOWLIST_WRITE`. Re-pointing it moves a write allowlist meant for development code onto the release
    binary (spec review).
  - Codex and Gemini also read project-level files that live inside repositories.
- **Options:**
  - **(a)** Report a dead local entry, with a to-do naming the manual re-point.
  - **(b)** Re-point a dead local entry in place in `~/.claude.json`, with its env kept. A working one follows D1.
  - **(d)** Leave a dead local entry, with a to-do naming the two fixes that keep a checkout's policy with that
    checkout's code: rebuild the checkout's venv, or remove the local entry so the user entry applies. The to-do says
    that removing it drops its settings, and names them by key.
  - **Not offered:** project files (`.mcp.json`, and Codex's and Gemini's project configs). They are checked in and
    shared with a team. They are never read or written under any option.
- **Recommendation: (d).** A dead path is not a choice, but the policy on it is. (d) gets the incident's registration
  fixed without changing which code a write allowlist governs. (b) only if he wants the installer to make that move.
- **Why it is his:** it reaches into per-project configuration on developers' machines, and decides which code a
  write allowlist governs.
- **Safe default:** (d). `LOCAL_SCOPE_ACTION = "todo"`; the other values are `"report"` (a) and `"repoint"` (b).
  Pinned by `dead_local_scope_todo_names_rebuild_or_remove`.
- **What would let the AI decide next time:** a stated rule that the installer may edit a person's own per-user
  config only where the edit does not change which code a policy setting governs, and never files inside
  repositories.

### D3. Ship macOS first, or hold it until the Windows halves have run

- **Context.**
  - AGENTS.md: *"Both platforms, or neither."*
  - **D3 covers every macOS-only behaviour change in this plan, in either repo:** DesktopSetup Tasks 1–4 and
    CSA-Plugins G1. G1 is live for every user once it merges, because the entry scripts run the gate's `HEAD`.
  - The Windows halves (the companion's 1W, 4W, 6W, G1W, G2W) need a session on a real Windows machine (#184), which
    is not scheduled.
  - The repair runs inside `setup_csa_internal_tools`, so `check-parity.py` does not see it (A6). Only this decision,
    #184 and `windows_twin_exists`'s per-case SKIP keep the gap visible.
  - Plan 1's D5 (*"Hold as drafts for a Windows session"*, 2026-11-10) was his decision for Plan 1. It does not
    decide this plan.
  - D6's gate PR is outside D3: it changes the `.sh` and the `.ps1` together.
- **Options:**
  - **(a)** Ship macOS when it passes. The Windows halves are drafts handed to #184, and the gap is recorded there and
    in TODO.md.
  - **(b)** Hold the macOS PRs until a Windows session has run the W tasks end to end.
- **Recommendation: (a).** The incident's machine is a Mac, and the macOS half is measured. Holding it leaves dead
  registrations unreported on Macs and gains Windows nothing, since Windows behaves as today either way. The gap
  stays visible on #184, in TODO.md and in a per-case SKIP.
- **Why it is his:** it is an exception to a repo rule, and Windows users keep today's behaviour for as long as it
  lasts.
- **Safe default:** the repo rule. Building, review and the isolated acceptance run go ahead; neither G1 nor the
  DesktopSetup PR merges until he answers.
- **What would let the AI decide next time:** a standing rule in AGENTS.md saying when one platform may ship first,
  for example *"the other half is specified, on an open issue, and pinned by a per-case SKIP"*.

### D4. Claude Desktop is running when a Desktop entry needs re-pointing

- **Context.** Desktop writes its own config. If a running Desktop writes its in-memory copy back after our edit, the
  run has already printed `ok … re-pointed` and passed its read-back: a false success (spec review). Whether it does
  is M2, which touches the real Desktop config.
- **Options:**
  - **(a)** Write anyway, with a restart to-do.
  - **(b)** Don't write Desktop's config while it runs. The plan row says so before consent, and the finding gets a
    to-do, `Quit Claude Desktop and run again`.
- **Recommendation: (b)** until M2 is measured, then (a) if M2 shows Desktop never writes an old copy back.
- **Why it is his:** it decides whether a rerun asks someone to quit an app they are using, and M2 needs his
  go-ahead.
- **Safe default:** (b). `WRITE_DESKTOP_WHILE_RUNNING = False`, pinned by `desktop_running_skipped_with_quit_todo`.
  - **Detection is by executable path, never process name:** a `ps -axo comm=` line equal to
    `/Applications/Claude.app/Contents/MacOS/Claude`, or the same under `~/Applications`. `claude` is also Claude
    Code, and Claude Code's updater renames its running image (AGENTS.md trap). `ps` is run from `PATH`, so tests can
    stub it.
  - The to-do appears only when a Desktop finding would be re-pointed.
- **What would let the AI decide next time:** M2's result. If Desktop never writes over an external edit, the AI lifts
  the skip under P1 (correctness) and cites the measurement.

### D5. Run the handshake check on every rerun, or hold it until measured

- **Context.**
  - `verify` launches each registered server with its registered env, outside any client. Under the real `HOME`, a
    server holds a token.
  - Whether a server refreshes it, writes its token file or calls the network before answering `initialize` is not
    measured (B2). The tests use stub servers, and Task 6's isolated run has no token under its `HOME`. If a server
    does, the Global Constraint "no token file is opened" fails through the child.
  - M5 measures it. It touches his real `HOME`, so it runs with his go-ahead.
  - M6 measures whether the gate's `claude mcp get` probe already starts each server on every run. If it does, a
    `verify` launch is one more of a kind every run already makes, and the question to him says so.
- **Options:**
  - **(a)** On in every rerun.
  - **(b)** Built and tested, but a rerun launches nothing. `verify` prints one `info` line saying the check is held,
    and `verify --run` runs it by hand.
  - **(c)** On per server, for each server M5 shows changes no token file and opens no connection at startup.
- **Recommendation: (b)** now, then (c) from M5's result.
- **Why it is his:** if a server refreshes a token at startup, turning the check on means every rerun acts on the
  person's accounts. Trading a truthful "it answers" against that is policy.
- **Safe default:** (b). `VERIFY_ON_RERUN = frozenset()`, the set of servers a rerun checks, pinned by
  `verify_held_by_default`. (a) is all four names; (c) is the ones M5 cleared. While a server is held, the plan
  prints no check row for it, so the plan claims nothing the run won't do.
- **What would let the AI decide next time:** M5 showing, for a server, no token-file change and no network
  connection between spawn and kill. The AI then adds that server under P1 and records the measurement.

### D6. Decided by the AI (2026-11-12, under P1: safety and privacy first): G2 and G3 ship first, alone

- **G2.** The gw, ggc and zendesk Desktop writers create `<cfg>.tmp` or `<cfg>.csa-tmp` with plain `open()`. Under
  umask 022 the temp file, and then the config it replaces, are `0644`, and the temp name is fixed (S1). skilljar
  chmods only after the replace, which leaves a `0644` window. `~/Library` is `0700` on this Mac, so other accounts
  cannot reach the file. This is a group/other-readable mode on a file that holds secrets, fixed as defence in depth.
  The fix: each writer creates its temp file `0600` (`mkstemp` in the config's directory) before writing.
- **G3** (spec review M8). `csa-skilljar-setup.sh` passes `"${existing:-}"`, the `claude mcp get` output it parses
  secret values from, as an argument to `python3` in its Desktop block. macOS shows argv to every account (measured
  above), so those values are readable by other local accounts while that `python3` runs. The fix: pass it on stdin
  or through the environment.
- **Why first and alone:** both are small and change nothing a user sees, and G3 is a live exposure. Neither needs a
  measurement; G1 does (M7).
- **Where:** CloudSecurityAlliance-Internal/CSA-Plugins#213 (open), built by another session. It fixes both in the
  four `.sh` and the four `.ps1`. Its one Desktop writer skips `fchmod` on Windows, which has no mode bits, so G2W's
  ACL measurement still applies. This plan calls it "the G2/G3 PR" and carries no G2 or G3 task. **Only Task 6 Step 2
  depends on it.**

## The AI's decisions (P4: each names its rule)

- **A1. Audit, repair and verification live in DesktopSetup, in one Python file, not in the four gate scripts.**
  Decided under P1, correctness: one classifier serves both the plan and the run.
  - The spec puts *"the registration audit"* in this repo, and #177's verification belongs to it.
  - Rejected:
    - **Per-server repair in eight gate scripts:** eight classifiers, plus a ninth for the plan preview, which will
      drift.
    - **One private gate script:** public CI cannot test it, and the preview would execute private code before
      consent.
  - The AGENTS.md trap *"Which clients get CSA tooling depends on who registers it"* is updated: DesktopSetup now also
    *repairs* existing registrations, and still never creates one.
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
  - **Cost:** it can race a running client. The mitigations: Claude Code's lock, if M1 finds one; a stat check just
    before the replace; a backup; a read-back; no Desktop write while Desktop runs (D4); and the next run. Precedent:
    `csa-claude-connectors.py` edits `~/.claude.json` the same way.
  - **Rejected:** the CLIs for secret-free entries only. That is two mechanisms and twice the test surface.
- **A4. Only what the plan showed is changed.** `plan` writes its findings, with fingerprints and no values, to a
  file. `apply` acts only on a finding that is in that file *and* unchanged since. Anything new is reported as "found
  after you agreed to the plan; not changed — run again". This is the CINO's rule of 2026-10-23: *"we want to check
  state, make sure we are up to date before we reply."*
- **A5. The check is `initialize` only.**
  - One server process at a time, 20 s each (M4 checks the figure), its process group killed and reaped (S2).
  - Identical launches are made once.
  - Only a direct executable is launched (A12). A launcher form is `not checked: launcher form`.
  - The env approximates each client's, as M3 measured it. The output says "launched with its registered command and
    settings", never "as <client> launches it".
  - `tools/list` and an authorised read are #177's in-client stages, so this check never says "works in <client>".
  - It is held by D5 until M5.
- **A6. No new `main()` step.** The repair runs inside `setup_csa_internal_tools`, behind its `gh` gate. That
  placement is for the gate. It also means `check-parity.py` does not see the change, which is not a parity pass:
  shipping it one-sided is D3's call. The gap is tracked by a per-case SKIP in `windows_twin_exists` and by #184.
- **A7. Codex is read through `codex mcp list --json`,** because Apple's Python 3.9 has no `tomllib`. A Codex whose CLI
  lacks `--json` is reported "not audited", never "fine".
- **A8. A bare command name is resolved on the client's own `PATH`, as M3 measured it.** Until Claude Desktop's is
  measured, a bare-name Desktop entry is left: `not checked: Claude Desktop's PATH is not measured yet`. It is never
  re-pointed then, because only a provably dead path is changed. Decided under P1 (correctness): if Desktop adds
  directories to `PATH`, a guessed `PATH` would call a working entry dead and re-point it, which breaks D1.
- **A9. Only the four canonical names are audited:** `csa-google-workspace`, `csa-google-gmail-calendar`,
  `csa-skilljar` and `csa-zendesk`, and only stdio transports. The hosted `csa-mcp` (HTTP) is out of scope, as are
  plugin-bundled and Desktop-extension servers.
- **A10. A config file that is a symlink is read, never written** (spec review M5). Decided under P1 (safety).
  `os.replace` on a link replaces the link with a regular file, and writing through it edits a dotfile repository,
  which D2 rules out. The finding is left: `its config is a link to <~-path>; not changed — edit it there`.
- **A11. The `.py`'s own client CLI calls run from a fresh empty directory** (`tempfile`), as G1 makes the gate's do
  (spec review M6). Decided under P1 (correctness): a project config in the installer's working directory must not
  stand in for the user's.
- **A12. A launcher form, or an env that shapes the interpreter, is left alone** (spec review B1, B3). Decided under P1
  (safety).
  - **A direct executable** is a regular file that is either:
    - a script whose interpreter chain is parsed: `#!<absolute interpreter>`, or the `#!/bin/sh` +
      `'''exec' "<interpreter>" "$0" "$@"` form installers emit for long or spaced paths;
    - or a Python interpreter whose args are exactly `["-m", SERVERS[name].module]`.
  - **Anything else is a launcher form** (`uv run --directory <checkout> …`, `uvx`, `npx`, a wrapper script). It is
    left with `it runs through <basename>, which this does not inspect; left as it is`, and never launched: launching
    it can rebuild a venv, download Python or write into a checkout.
  - **Interpreter-shaping keys,** by name: `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONUSERBASE`,
    `PYTHONEXECUTABLE`, `VIRTUAL_ENV`, `CONDA_PREFIX`, and any `UV_*`. A dead registration carrying one is left, with
    a to-do: `<name> in <client> is dead, and its <KEY> setting would point the release binary at another tree; fix
    it by hand`. Re-pointed, the release binary would import the checkout's tree, or break.
  - An `-m` form naming any module but the server's pinned one is left: `its args run a module this does not
    recognise`.
- **A13. Backups share `csa-claude-connectors.py`'s name and prune,** `<path>.bak-<YYYYmmddHHMMSS>`, 3 generations.
  Decided under P1 (safety): each backup holds the same secrets as the file, at the same mode, so one shared cap
  means fewer copies. The prune matches only that exact name, so the seven other backups on this Mac are never
  touched. ENGINEERING.md says all of this.

## Repos, branches and merge order

| Repo | Branch | Tasks |
|---|---|---|
| DesktopSetup | `feat/registration-repair` | 0 (measurements), 1, 2, 3, 4, 5, 6 |
| CSA-Plugins | `fix/desktop-config-0600-no-secret-argv` (#213, D6) | G2 and G3, `.sh` and `.ps1` (another session) |
| CSA-Plugins | `fix/registration-probes` | G1 (`.sh`), after M7, under D3 |

The Windows branches are in the companion.

1. **Task 0 starts at once.** It depends on nothing. Its measurements that need nothing from the CINO run first;
   those that touch his real `HOME` run when he gives the go-ahead, and until then their safe defaults stand. The
   evidence is the first commit on `feat/registration-repair`.
2. **The G2/G3 PR merges whenever it is ready.** Nothing here waits for it except Task 6 Step 2.
3. **G1 merges after M7 is recorded, and before DesktopSetup's Tasks 1–6;** both merge only when D3 allows. The first
   run that repairs then also runs the fixed probes.
   - Work in a fresh clone under the session scratchpad, never in
     `~/GitHub/CloudSecurityAlliance-Internal/CSA-Plugins`.
   - CSA-Plugins#206 is open in another session. Rebase onto main after it merges, and don't touch it. Rebase onto
     the G2/G3 PR too if it has merged, since both edit the four `.sh`.
4. **Task 6 Step 2, the real run on the CINO's Mac,** comes after the G2/G3 PR, G1 and Tasks 1–6 have merged, with
   his go-ahead.
5. **The Windows halves stay drafts** until a Windows session has measured and run them end to end. Task 5 hands the
   companion to #184.

## What this plan absorbs from #175, #176 and #177, and what stays there

| Item | Here | Stays |
|---|---|---|
| #176 "detect stale managed launchers and explain the repair; do not interpret every custom path as permission to replace it" | Tasks 1–2, D1, A12 | — |
| #176 "preserve … credentials and intentional operator settings" on reruns | Task 2 (every field kept), A12, G1 (no policy loss to a shadowing cwd) | first-use registration: the gate scripts and #156 |
| #176 "resolved executable paths for GUI launches" | a bare-name Desktop entry that does not resolve on Desktop's measured `PATH` is dead and re-pointed at the absolute binary; until M3, it is left and reported (A8) | — |
| #176 "an absent client should produce an accurate skip/pending result" | audit and check output (Tasks 1, 3) | the gate scripts' own registration messages |
| #175 "stale repo-venv registrations" | Tasks 1–2, D1, D2 | — |
| #177 truthful outcomes in the closing list | a failed handshake, and a registration left for a decision, become to-dos | #154 (a setup that dies partway) |
| #177 "a CLI check does not prove the desktop client loads the server" | the handshake is worded as the installer-side stage only, and held until M5 (D5) | tool discovery and an authorised read in each client; the published matrix |
| csa-zendesk#70 | D1's default is its option 3; a dead user-scope path is repaired; a dead local one gets D2's to-do | whether the server reports an editable install (#70 option 1) |
| csa-google-gmail-calendar#45 "register … and verify it" | Task 3 supplies the verification, under D5 | registering when absent: that server's setup script |

**Stays out of this plan entirely:**
- ChatGPT Desktop, Gemini Desktop and `agy` (#175, #167, #172). Nothing registers servers with them today. Task 1's
  client table is the one place they would be added.
- Workspace Audit, which is not implemented.
- Authentication flows.
- The 5×6 status matrix.
- Gemini folder trust (#155), beyond M7's check that G1's empty directory does not change what `gemini mcp` does.

## Global Constraints

- **Credentials (#179 item 8, S3):**
  - The `.py` never opens, moves or deletes a token file, OAuth state or credential file. A server that `verify`
    launches might: that is B2, measured by M5, and the reason D5 holds the check.
  - No login, logout or re-consent is run.
  - Env **values** are held in memory only. They are never printed, logged, put on a command line, or written to the
    plan file, the to-do ledger or evidence.
  - Key names and counts may be shown.
  - A value is written only back into the config file it came from, and into that file's backup at the same mode.
- **The repair (#179 item 2):**
  - It changes `command`.
  - It replaces `args` only in the pinned interpreter form `["-m", SERVERS[name].module]`, with `[]`.
  - Every env var and every other field stays as parsed. This is asserted in memory before the write and on
    read-back after it.
  - A launcher form, an interpreter-shaping env key or another module is never repaired (A12).
- **Writing JSON:**
  - The indent is detected from the file's first indented line (default 2), a trailing newline is kept only if the
    original had one, key order is kept, and `ensure_ascii=False`.
  - `mkstemp` plus `os.replace` keeps the mode but drops the original's extended attributes and ACLs. ENGINEERING.md
    says so.
  - A symlinked config is never written (A10).
- **Fail safe (B9):**
  - A config that is unreadable, truncated, has a duplicate key (`object_pairs_hook`) or has an unexpected shape is
    "not audited", nothing is written to it, and the screen says so.
  - A failing client CLI is never read as "absent".
  - Ask *what if the write was torn?* of every write: mkstemp in the same directory, the mode set before any byte is
    written, fsync, then `os.replace`.
- **Consent (#179 item 6):** the plan lists every change, and only those are made (A4). The existing `confirm`
  gate is the ask; `NONINTERACTIVE=1` auto-confirms, as it does for every step.
- **Bounded (S2):** at most one server process at a time, with a 20 s timeout, its process group killed and the
  process reaped. Tests assert that no process survives. Each distinct launch can add up to 24 s (20 s, then 2 s and
  2 s of teardown), so up to about 96 s for four. M4 records the typical figure. While D5 holds, it adds nothing.
- **Measurements:** Task 0's rules bind every measurement, and any later one.
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
  - `${a[@]+"${a[@]}"}` for any array that may be empty;
  - a function that sets a variable for its caller is called directly, never inside `$(…)`.
- **Shared shell functions are byte-identical** in the three macOS scripts (`check-duplication.py`). No `main()`
  changes (A6).
- **Plan lines name what runs, truthfully.** A row describes only what the `.py` will do, never what a gate script
  does. They keep the `Internal MCP servers` label for `check-plan-covers-steps.py`.
- **Gate helpers marked KEEP IN SYNC are byte-identical in all four `.sh`,** enforced by a test, not by the comment
  (CSA-Plugins#199).
- **Bump `SCRIPT_VERSION` in every changed `.sh`.** The `.py` declares its own and is bumped by hand, like
  `csa-claude-connectors.py`. `check-script-versions.py` reads only `.sh`/`.ps1`, and no defect has shipped that a
  new guard would encode (ADR-005).
- **New test files go into `tools/check-all.sh` and `lint.yml`:** the ubuntu job, plus the `macos-latest` job under
  both `python3` and `/usr/bin/python3`. `check-all.sh` must be fully green on macOS; #169 closed on 2026-11-11.
  Read the tail and the exit code.
- **Commit subjects state the claim.** Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

Each point is pinned by tests named in Tasks 1–4.

1. **A developer's deliberate source-checkout registration.** Working, with a write allowlist in env: left
   byte-identical and warned about (D1). Through a launcher: left, never launched (A12). Cellar-pinned: the plan says
   the next `brew upgrade` deletes its interpreter. Dead: re-pointed with its env kept in user scope, unless an env
   key shapes the interpreter (A12); in local scope, D2's to-do.
2. **A registration with secrets in env.** No value reaches stdout, stderr, any argv, the plan file, the ledger or a
   handshake diagnostic; it is masked there as `<KEY>`. The value *is* carried into the repaired entry. The file's
   mode and its backup's mode are never wider.
3. **Clients not installed.** The output says "not installed" or "no config yet (#156)", never "fine", and nothing is
   written.
4. **Configs that are unreadable, malformed or linked (B9, A10):** truncated JSON, JSONC comments in Gemini settings,
   a duplicate key, an `mcpServers` that is not a dict, a Codex without `--json` or with a failing CLI, an unreadable
   plan file, a config that is a symlink. Each is "not audited" or left with its reason, nothing is written, and the
   screen says so.
5. **A client running and holding the config.**
   - The file changes between our read and our replace: the write is abandoned with "changed while this ran; run
     again", and no backup is left.
   - A read-back mismatch restores the backup.
   - **Claude Desktop running:** its config is not written (D4). Writing anyway could print `ok` and pass read-back,
     then lose the edit when Desktop writes its old copy: a false success. M2 measures whether that happens.
   - **A Claude Code session running:** M1 decides, before Task 2 is built, whether Claude Code has a lock to honour
     and whether a session writes an old copy back. The `ok` line claims no more than M1 supports.
6. **Codex and Gemini CLI versions whose `mcp` subcommands differ.** Codex's JSON as a list or a dict, `transport`
   nested or flat; a quoted TOML table header; a multi-line `args` array refused rather than guessed; Gemini's extra
   fields (`trust`, `includeTools`, `timeout`) kept; CLI calls from an empty directory (A11); each client's
   handshake env as M3 measured it, or labelled an approximation.
7. **Plan and run drift.** A finding that appears, or changes, after consent is not acted on.
8. **Idempotence.** A second run writes nothing: every config's inode, mtime and bytes are unchanged, and no backup
   is made.
9. **The check acts on nothing it has not measured.** While D5 holds, a rerun launches no server, and the plan prints
   no check row.

---

### Task 0: Measurements that decide the design, before any build task

**Rules for every measurement:**
- **Never read, move or delete a credential, a token file or OAuth state.** A token file is only `stat`ed: metadata,
  never opened.
- **Never print a secret value.** The dummy server records env **key names**, and `PATH`'s value with `$HOME` shown
  as `~`.
- **Never register through a client CLI write command** (`claude mcp add`, `codex mcp add`): argv is visible to
  every account. A dummy entry is written into the config file directly.
- **Only a dummy server, `csa-plan2-probe`, is ever added.** A CSA registration is never edited.
- **Every dummy entry's `command` is an absolute path** to a Python verified to run (never `/usr/bin/python3` without
  the Command Line Tools), with the probe script's absolute path as its argument. A bare name would depend on the
  `PATH` being measured.
- **Isolated runs use `mktemp -d`** for `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and `TMPDIR`. At most 4 processes,
  each with a timeout, and cleanup.
- **A measurement that touches the real `HOME`** backs up any file it edits first (`.bak-<14 digits>`, same mode),
  adds and removes only the dummy entry, deletes the backup when it is done (it holds the file's secrets), and runs
  only with the CINO's go-ahead.

**The dummy server,** `probe_server.py` in the scratch directory, stdlib only. On start it appends to a log in its own
scratch directory: a start marker, its env key names, `PATH` (home as `~`), its working directory, then the method
name of each JSON-RPC message it receives. It answers `initialize`, and exits when stdin closes.

| ID | Question | Where | Needs from the CINO | Touches his real `HOME` |
|---|---|---|---|---|
| M0 | Where does each server keep its token and credentials: under `HOME`, or outside it (the login keychain, an absolute path)? | each server's public source | nothing | no |
| M1 | Does a running Claude Code session write an old `.claude.json` over an external edit of a user entry's `command`? Does Claude Code take a lock file when it writes the file? | isolated `CLAUDE_CONFIG_DIR`, scratch project | nothing, unless a session there cannot reach a config write without a login; then the real config, with his go-ahead | no (fallback: yes) |
| M2 | The same for a running Claude Desktop, across a preference change and a quit | the real Desktop config | go-ahead, and four actions in Desktop | yes |
| M3 | Which env key names, and which `PATH` value, each client passes to a stdio server | Claude Code and Gemini: isolated. Codex: isolated, if a launch needs no login. Desktop: the real config, in M2's session | Desktop, and Codex if it needs a login: go-ahead | Desktop: yes |
| M4 | How long each standard binary takes to answer `initialize` | scratch `HOME`, the real `~/.local/bin` binaries; after M0 | nothing for a server whose token M0 places under `HOME`; go-ahead for any other | no; a launch may write bytecode caches into the tool's own venv, as any launch does |
| M5 | Under the real `HOME`, does each server change a token file, or open a network connection, between spawn and 2 s after its `initialize` answer? | the real `HOME` | go-ahead | yes |
| M6 | Does `claude mcp get <name>`, the gate's probe, start the server? Which methods does it send? | isolated | nothing | no |
| M7 | G1's question: from a directory with a project or local entry, does each CLI report that entry instead of the user's? Does Gemini behave differently in an untrusted empty directory (folder trust, #155)? | isolated | nothing | no |

**How each is measured, and the result that changes the design:**
- **M0.** From each server's public source: its token path constant, or its keychain service name, cited by repo,
  file and commit. Source code only; no file on this Mac is read.
  - **Changes the design if** any token is outside `HOME`. A scratch `HOME` then does not isolate that server, so its
    real launch in M4 and in Task 6 Step 1 waits for the go-ahead (asked with M5), and uses the stub server meanwhile.
- **M1.** Seed the isolated `.claude.json` with a user entry `csa-plan2-probe`. Start an interactive `claude` session
  in a scratch project under `script -q`, bounded.
  - While it runs, edit the entry's `command` directly (atomic replace). Then make the session write its config: change
    a setting, then exit. Read the entry back.
  - **Lock:** poll the config directory's listing every 10 ms while the session writes, and record any new name.
    `strings` matches for `.lock` beside `claude.json` in the binary are supporting evidence only, labelled inferred.
  - If the session cannot reach a config write without a login, record that and ask for the real-config fallback.
  - **Changes the design if** a lock is found: Task 2 takes it with the same protocol. **Or if** the edit is lost with
    no lock: the `ok` line says a running session can write its old copy back, the to-do says to restart Claude Code
    sessions, and the next run's audit is the check. Otherwise Task 2 stands as written.
- **M2.** With the go-ahead. Who does what: **the AI** edits and reads the file; **the CINO** does four actions in
  Desktop (quit, start, change a preference, quit), because they are in Desktop's own window. Desktop must *start*
  with the dummy entry in place, or it never launches the dummy and M3's Desktop part records nothing.
  1. The CINO quits Desktop, if it is running.
  2. The AI backs up the Desktop config and adds `csa-plan2-probe`.
  3. The CINO starts Desktop. Its start launches the dummy, whose log is M3's Desktop record.
  4. With Desktop running, the AI edits the entry's `command` directly, to a second absolute path that runs the same
     probe with a marker, so a later launch shows which command ran.
  5. The CINO changes one preference the AI names, then quits Desktop.
  6. The AI reads the entry: did the edit survive?
  7. With Desktop quit, the AI removes the dummy entry and compares the file with the backup in process, excluding
     `preferences`. It prints `identical: yes|no`, and names the changed preference key only. The CINO sets that
     preference back the next time he uses Desktop.
  8. The AI deletes the backup, which holds the same secrets as the config, once the comparison says `identical:
     yes`. If it says `no`, the AI changes nothing on its own, tells the CINO which keys differ, and deletes the
     backup once he has decided.
  - **Changes the design if** the edit survives: D4's recommendation becomes (a), for him to confirm. If it is lost,
    D4's safe default is confirmed.
- **M3.** From the dummy server's log.
  - **Claude Code:** after M6's `claude mcp get`, and after a session start if one is possible.
  - **Gemini:** `gemini mcp list`, if it connects to servers, or a session start.
  - **Codex:** a session start in an isolated `CODEX_HOME` if it needs no login. Otherwise record "not measured", and
    keep the approximation labelled as one.
  - **Desktop:** Desktop's start at M2's step 3 launches the dummy.
  - A health-check launch's env may differ from a session's. Each is recorded by the path that made it.
  - **Changes the design:** A8 resolves bare names on each recorded `PATH`, and Task 3 builds each client's launch env
    from the recorded key names. A client M3 could not measure keeps the approximation, labelled one.
- **M4.** After M0. Three timed `initialize` exchanges per standard binary, with a scratch `HOME` and no registration
  env. Record the minimum and maximum.
  - **Changes the design if** any maximum exceeds 10 s, half the timeout: the timeout becomes twice the largest
    maximum, rounded up to 5 s. Otherwise 20 s stands. Either way the figures go into ENGINEERING.md's run time.
- **M5.** With the go-ahead. For each server:
  1. Take its token paths, or keychain service, from M0. Never open them. For a keychain item, record its
     modification date only (`security find-generic-password -s <service>`, never `-g` or `-w`, filtered to the
     `mdat` line), or "not observed" if that would prompt.
  2. `stat -f '%i %m %z %Sp'` each path and its directory.
  3. Launch it exactly as Task 3 will. A scratch harness reads the user-scope entry in memory, the same read the
     `.py` makes, and passes its env through `subprocess`'s `env`, never argv. It prints nothing from it. Send one
     `initialize`, close stdin, and kill the process group 2 s after the answer.
  4. From spawn to kill, sample `lsof -nP -a -g <pgid> -i` every 100 ms, and record remote `host:port` only. A
     connection shorter than the interval can be missed; the evidence says so.
  5. `stat` again, and record `unchanged` or the field that changed. A server already running in an open client could
     also change a token file. If one changes, repeat once and record both.
  - **Changes the design:** a server with no token change and no connection becomes a candidate for D5 (c), and the
    question to the CINO lists what each server touched. With no result, D5's safe default stands.
- **M6.** Seed the isolated config with `csa-plan2-probe`, run `claude mcp get csa-plan2-probe` from an empty
  directory, and read the dummy server's log.
  - **Changes the design if** it starts the server and sends `initialize`: every gate run already launches each
    Claude Code user-registered server once, and D5's question says a `verify` launch is one more of that kind. No
    constant changes on M6 alone. If it does not start the server, D5 stands as written.
- **M7.** In an isolated `HOME` and `CODEX_HOME`, with the real CLIs and the dummy server:
  - Does `claude mcp get` from a project with a local entry report the local one?
  - Does `gemini mcp list` from a directory with `.gemini/settings.json` list the project entry?
  - Does Codex read a project-level config?
  - Do `gemini mcp list` and `gemini mcp add` behave differently in an untrusted empty directory than in a trusted
    one?
  - **Changes the design:** G1 Step 1's rules.

- [ ] **Step 1: The measurements that need nothing from the CINO,** in this order: M0; then M1 (isolated), M3 (its
  isolated parts), M4 (for each server M0 places under `HOME`), M6 and M7.
- [ ] **Step 2: Ask for the go-aheads,** one at a time (K2), each saying what it touches:
  - M2 with M3's Desktop part, in one session, including the four actions in Desktop it needs from him;
  - M5, saying that the launch itself may refresh or rotate a token, as a client's start would, and adding M4's and
    Task 6 Step 1's real launches of any server M0 placed outside `HOME`;
  - M1's fallback, if Step 1 needed it.

  Run each when given. Until then, the safe defaults stand and the build does not wait.
- [ ] **Step 3: Record.** Results go into `plans/reviews/2026-11-12-registration-repair-measurements.md` only,
  scrubbed of secrets, personal data and names of people. This plan is not rewritten mid-run: each dependent task
  applies the measurement's "Changes the design" rule, and that task's review checks the change against the file.
  **Commit:**
  `docs: Plan 2's measurements record what each client passes a server, whether a running client overwrites an edit, and what a server touches at startup`.

### Task 1: `csa-mcp-registrations.py plan` — find every CSA registration in four clients, and say what is wrong with each, without writing anything

**Depends on:** M3's Desktop `PATH` in `plans/reviews/2026-11-12-registration-repair-measurements.md`, or A8's leave
rule while it is not there.

**Files:**
- Create: `scripts/csa-mcp-registrations.py` (`SCRIPT_VERSION`, a module docstring in the `csa-claude-connectors.py`
  style, `plan` only in this task).
- Create: `tests/test_mcp_registrations.py`. It imports the shipping file with `importlib` for unit cases, and runs
  it as a CLI with a fixture `HOME` and stub `codex`/`gemini`/`claude`/`ps` on `PATH` for end-to-end cases. Wire it
  into `check-all.sh` and `lint.yml`.

**Interfaces:**
- **`SERVERS`** maps each canonical name to its entry point and its module:
  - `csa-google-workspace` → `csa-google-workspace-mcp`;
  - `csa-google-gmail-calendar` → `csa-google-gmail-calendar`;
  - `csa-skilljar` → `csa-skilljar-mcp`;
  - `csa-zendesk` → `csa-zendesk-mcp`.

  Each module is the package of the console-script target in that server's `pyproject.toml` `[project.scripts]`,
  read at build time; a comment cites the repo and commit. The standard binary is `$HOME/.local/bin/<entry>`.
- **Readers.** Each returns `(status, [Registration])`, and `status` is one of `ok`, `not installed`,
  `no config yet`, or `not audited: <why>`.
  - **Claude Code:** `$CLAUDE_CONFIG_DIR/.claude.json`, or `~/.claude.json` when that is unset. User scope is
    top-level `mcpServers`; local scope is `projects[<dir>].mcpServers`.
  - **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json`. "Not installed" when
    neither `/Applications/Claude.app` nor `~/Applications/Claude.app` exists. Whether it runs is read from
    `ps -axo comm=`, `ps` from `PATH`, by exact executable path (D4).
  - **Codex:** `codex mcp list --json`, run with `CODEX_HOME` honoured, a 30 s timeout, stdin closed, and `cwd` a fresh
    empty directory (A11).
  - **Gemini:** `~/.gemini/settings.json`, user scope. "Not installed" without a `gemini` on `PATH`.
  - On `win32`, every reader returns `not audited: Windows support is #184 (Task 1W)`.
- **`Registration`:** client, scope, project, name, command, args, env (in memory only), the other fields untouched,
  whether its config file is a symlink, and a fingerprint. The fingerprint is the sha256 of the command, the args and
  the **sorted env key names**, never the values.
- **Classification.** Each finding has a state, a reason, warnings and an action. The checks run in this order, and
  the reasons are verbatim:
  1. **`standard`,** tested first, before any liveness check: the command, `~` expanded, is the standard path
     `$HOME/.local/bin/<entry>`, or its realpath equals the standard binary's realpath, which also covers uv's own
     tool path. Its action is none. Its liveness is then classified too, and recorded on the finding. When the
     standard binary is itself dead (the incident state before the rebuild), the row says `its standard binary does
     not run yet; its setup reinstalls it`, as Plan 1 rebuilds it. It is never a re-point aimed at itself, and
     `verify` never launches it.
  2. **`dead`,** when the command itself fails:
     - `its command does not exist`;
     - `its command is not executable`.
  3. **`launcher`,** when it is not a direct executable (A12): `it runs through <basename>, which this does not
     inspect; left as it is`.
  4. **`dead`,** when its interpreter fails:
     - `its Python no longer exists`: the parsed interpreter, or the venv's `bin/python3`, is dangling or missing, or
       `pyvenv.cfg` `home` is gone;
     - `its Python does not run`: `<interp> -I -c "import json, importlib.resources"` fails or takes more than 10 s.
       Both are stdlib packages on every supported version. `import sys` alone is built in and proves nothing.
  5. **`elsewhere`:** it works but is not the standard binary: `it points at <~-path>, not ~/.local/bin/<entry>`.
  - **Warning:** `it runs from a venv built on a Homebrew Cellar Python, which the next brew upgrade deletes`. Use
    Plan 1's recorded-path rule: the first hop out of the venv, or `home`, literally contains `/Cellar/`. An `opt/`
    path is fine.
  - A bare command resolves on the client's `PATH`, as M3 measured it. A bare-name Desktop entry before M3 is left,
    `not checked: Claude Desktop's PATH is not measured yet` (A8).
- **Actions:**
  - **`re-point`** applies when all of these hold:
    - the state is `dead`;
    - the scope may be repaired: user always; local only when `LOCAL_SCOPE_ACTION == "repoint"` (D2);
    - `args` is empty or exactly `["-m", SERVERS[name].module]`;
    - no env key shapes the interpreter (A12);
    - the config file is not a symlink (A10);
    - for Claude Desktop, Desktop is not running, or `WRITE_DESKTOP_WHILE_RUNNING` (D4).
  - With `REPOINT_WORKING_ELSEWHERE`, `elsewhere` also re-points.
  - Otherwise **`leave`**, with the reason, plus a to-do where somebody has to act. A dead local entry's to-do is set
    by `LOCAL_SCOPE_ACTION`: the manual re-point for `"report"`, rebuild-or-remove for `"todo"`.
- **Output:** `plan --out FILE` prints one line per row on stdout as `row<TAB>text`. The rows are:
  - each `re-point` and `leave`;
  - each warning;
  - each client that is not audited, and why;
  - `Claude Desktop is running; <name> will not be re-pointed there this run — quit it and run again`, only when a
    Desktop finding would otherwise re-point;
  - one check row per server in `VERIFY_ON_RERUN`, and none while it is empty (D5);
  - a count line: `<n> CSA registrations in <m> clients; <k> need nothing`.

  It writes the findings, as JSON with no values and mode `0600`, to `FILE`. It exits 0, or 2 on an internal error,
  in which case `FILE` is not written.

- [ ] **Step 1: Failing tests.**
  - **Fixtures:**
    - real-shaped symlink chains: uv's `cpython-3.14-…` link, Homebrew `opt/python@3.14 → ../Cellar/…`, and a deleted
      Cellar directory;
    - a source-checkout `.venv` whose `bin/csa-zendesk-mcp` has an absolute shebang into its own `bin/python`;
    - an entry point in the `#!/bin/sh` + `'''exec'` form;
    - a stub interpreter that succeeds on `import sys` and fails on `import json, importlib.resources`;
    - stub `codex`, printing JSON from a scenario file and logging `$PWD`; stub `ps`;
    - fake secret values, unique strings that a test can grep for.
  - **Cases:**
    - `standard_registration_is_fine` (including `~/.local/share/uv/tools/<pkg>/bin/<entry>`);
    - `dead_standard_binary_no_self_repoint`;
    - `dead_command_missing`, `dead_command_not_executable`;
    - `dead_shebang_interpreter` (the incident's second stage), `sh_exec_launcher_shebang_parsed`;
    - `dead_venv_home_missing` (the CINO's local-scope shape);
    - `python_stdlib_partly_missing` (the first stage);
    - `working_elsewhere_left_and_warned`, `cellar_venv_warned`, `homebrew_opt_is_not_cellar`;
    - `launcher_form_left` (`uv run --directory`, `uvx`, `npx`);
    - `interpreter_env_keys_left` (each named key, and a `UV_` key), `unknown_module_left`;
    - `desktop_bare_name_unmeasured_left`, and `bare_name_desktop_uses_measured_path` once M3 is recorded;
    - `desktop_running_skipped_with_quit_todo`, `desktop_detected_by_path_not_name` (a process named `Claude`
      elsewhere, and Claude Code's renamed image, do not count);
    - `local_scope_found_and_reported`, `dead_local_scope_todo_names_rebuild_or_remove`,
      `local_scope_action_values` (each of the three values), `local_scope_missing_project_skipped` (only logged);
    - `interpreter_module_form_repairable`, `other_args_not_repairable`;
    - `symlinked_config_refused`;
    - `http_registration_not_audited`;
    - `client_absent_not_installed` (×3), `desktop_config_dir_absent`;
    - `torn_claude_json_untouched`, `duplicate_key_is_unreadable`, `jsonc_gemini_not_audited`;
    - `codex_json_unsupported_not_audited`, `codex_list_failure_is_not_absence`, `codex_json_shapes`,
      `client_reads_run_in_empty_dir`;
    - `claude_config_dir_respected`;
    - `plan_file_has_no_values`;
    - `no_check_rows_while_held`;
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
  - hash the env values into the fingerprint: `plan_file_has_no_values`;
  - test liveness before the standard path: `dead_standard_binary_no_self_repoint`;
  - treat `uv` as a direct executable: `launcher_form_left`;
  - drop the `UV_` prefix rule: `interpreter_env_keys_left`;
  - detect Desktop by process name: `desktop_detected_by_path_not_name`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: csa-mcp-registrations.py plan finds every CSA MCP registration in four clients and says which are dead, without reading a credential or writing a file`.

### Task 2: `apply` — re-point an approved dead registration in place, changing only its command

**Depends on:** M1 in `plans/reviews/2026-11-12-registration-repair-measurements.md`. M2 there only to lift D4's
safe default.

**Files:**
- Modify: `scripts/csa-mcp-registrations.py`, adding `apply [--approved FILE]`. Without `--approved`, a person
  running it by hand re-plans and applies, as `csa-claude-connectors.py --apply` does. Bump its version.
- Modify: `tests/test_mcp_registrations.py`.

**Interfaces:**
- **Re-audit, then act on each `re-point` finding** only when it is in the approved file with the same
  `(client, scope, project, name, fingerprint)`. Otherwise:
  - `found after you agreed to the plan; not changed — run again`;
  - nothing at all, when the re-audit finds it is now fine. A gate setup may have fixed it.
- **Re-check what can change between plan and apply:** Desktop may have started (D4), and a config may have become a
  link (A10). Either turns the finding into `leave`.
- **Precondition:** the standard binary classifies as not dead, by the same classifier. It is never launched as a
  check. Otherwise `leave`, with `its standard binary is not installed yet`.
- **`edit_json(path, locate, new_command, new_args)`** is used for Claude Code, Desktop and Gemini:
  1. refuse a symlink (A10). For Claude Code, take its lock if M1 found one;
  2. stat and read the file, parse it with duplicate-key detection, and check the fingerprint;
  3. build the new entry, and assert that only `command` and `args` differ;
  4. `mkstemp` in the same directory, `fchmod` to the original's mode before writing, write with the detected indent,
     `ensure_ascii=False` and the original's trailing newline, then fsync;
  5. stat again. If the inode, mtime or size moved, unlink the temp file and report
     `changed while this ran; not written — run again`. No backup has been made, and none is pruned;
  6. back up to `<path>.bak-<YYYYmmddHHMMSS>` with `copy2`, and check the backup's mode;
  7. stat once more. If anything moved, unlink the temp file and the backup just made, and report as in step 5;
  8. `os.replace`;
  9. read back and parse. If the entry is not exactly the intended one, restore the backup and warn;
  10. only after a successful replace and read-back, prune to 3 generations, with the same regex and count as
      `csa-claude-connectors.py`, deliberately (A13).
- **`edit_codex(name, old_command, new_command, args_rule)`:**
  - Find the table `[mcp_servers.<name>]`, or `[mcp_servers."<name>"]`, exactly once.
  - Inside it, until the next header, find exactly one `command = "<old, TOML-escaped>"` line, and, for the
    interpreter form, exactly one single-line `args = ["-m", "<module>"]`.
  - Otherwise refuse with `its Codex entry is laid out in a way this cannot edit safely; left as it is`.
  - Write with steps 4–10 of `edit_json`. Read back with `codex mcp get <name> --json`, from an empty directory
    (A11): the command is new, and every other field equals the original. On a mismatch, restore.
- **To-dos:** `Restart Claude Code`, `Restart Claude Desktop` (the gate's title, so they de-duplicate),
  `Restart Codex` or `Restart Gemini`, at order 10. `Quit Claude Desktop and run again` at order 10 when D4 skipped a
  write. Left registrations get order 40. All go to `CSA_TODO_FILE` when it is set; otherwise `info<TAB>` lines say
  the same thing.
- **Output lines:**
  - `ok<TAB><name> re-pointed in <client> (<scope>) at ~/.local/bin/<entry>; its <n> settings kept`, worded as M1
    allows for Claude Code;
  - `warn<TAB>…` for each refusal.

- [ ] **Step 1: Failing tests:**
  - `dead_user_scope_repointed_env_kept`: the env dict and every other key are equal, and only `command` differs;
  - `dead_local_scope_todo_names_rebuild_or_remove`, and `local_scope_repaired_when_repoint` (the constant set
    through the module);
  - `working_elsewhere_byte_identical`;
  - `desktop_mode_0600_kept`, `backup_same_mode_and_pruned_to_3`, `prune_spares_other_backup_names`;
  - `json_format_preserved`: a 4-space file with no trailing newline keeps both;
  - `symlinked_config_refused`: the link and its target are unchanged;
  - `codex_line_edit_keeps_other_fields` (`startup_timeout_sec`, `env_vars`, `enabled`), `codex_quoted_table_header`,
    `codex_multiline_args_refused`, `codex_readback_mismatch_restores`;
  - `gemini_extra_fields_kept`;
  - `unapproved_finding_not_repaired`, `changed_since_plan_not_written`, `unreadable_plan_file_applies_nothing`;
  - `concurrent_change_aborts_write`, through a test hook between the read and the replace;
    `abandoned_write_leaves_no_backup`: after an abort at step 5 or 7, the directory holds the same backups as before;
    `readback_mismatch_restores`;
  - `claude_lock_honoured`, only if M1 found a lock;
  - `standard_binary_missing_no_repoint`;
  - `desktop_running_skipped_with_quit_todo`, `desktop_started_after_plan_skipped`;
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
  - copy `env` through `str()`: `dead_user_scope_repointed_env_kept`;
  - write through the link: `symlinked_config_refused`;
  - back up before the stat check: `abandoned_write_leaves_no_backup`;
  - drop the apply-time Desktop re-check: `desktop_started_after_plan_skipped`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: a dead CSA MCP registration is re-pointed at its standard binary in place, changing only its command, and only when the plan showed it`.

### Task 3: `verify` — each registered server answers an MCP `initialize` handshake, launched with its registered command and settings

**Depends on:** M3, M4 and M6 in `plans/reviews/2026-11-12-registration-repair-measurements.md`. M5 there only to
lift D5's safe default.

**Files:**
- Modify: `scripts/csa-mcp-registrations.py`, adding `verify [--run]`. Bump its version.
- Modify: `tests/test_mcp_registrations.py`, with stub MCP servers written as small Python scripts by the test.

**Interfaces:**
- **Held (D5).** Without `--run`, `verify` checks only the servers in `VERIFY_ON_RERUN`. While it is empty, it
  launches nothing and prints `info<TAB>server check held until its effect on tokens is measured (#179, D5); run
  "verify --run" to check by hand`.
- **What is launched.** Re-audit, and launch each `standard` or `elsewhere` registration that is a direct executable
  and whose binary is not dead.
  - A `launcher` one is reported `not checked: launcher form`, and never launched (A12).
  - A `dead` one is reported `does not start: <reason>`, and never launched.
  - A `standard` one whose standard binary is dead is reported `does not start: its standard binary does not run yet;
    its setup reinstalls it`, and never launched.
  - Launches are de-duplicated on `(command, args, launch env)`. The output names every client that shares a launch.
- **The launch env,** per client as M3 recorded it. Where M3 could not measure a client, the approximation is labelled
  one in ENGINEERING.md:
  - **Claude Code, Codex and Gemini:** the installer's environment, minus `CSA_TODO_FILE`, `CSA_LOG`, `CSA_DEBUG`,
    `CSA_NESTED` and `CSA_REGISTRATIONS_*`, plus the registration's env.
  - **Claude Desktop:** the key names and `PATH` M3 recorded, plus the registration's env.
  - **An env value containing `$`:** the launch is not made, and the output says `not checked: its environment uses
    $-expansion, which this check does not reproduce`.
- **The exchange:**
  - Send `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},
    "clientInfo":{"name":"csa-desktopsetup-check","version":SCRIPT_VERSION}}}` and a newline.
  - Read stdout until a JSON object with `id == 1` arrives, or the timeout passes (20 s unless M4 changed it).
    Non-JSON lines are skipped and counted.
  - **Pass:** `result.serverInfo.name` is present. Report the name and the version.
  - **Failure messages:**
    - `answered with error <code>`;
    - `exited <code> before answering: <last stderr line>`, masked and cut to 200 characters;
    - `did not answer within <n>s`.
- **Lifecycle:**
  - `start_new_session=True`, stdin a pipe.
  - Close stdin, wait 2 s, then send SIGTERM to the process group, wait 2 s, then SIGKILL it, and reap.
  - Never two children at once.
  - Run time: up to 24 s per distinct launch (Global Constraints).
- **Masking:**
  - every registration env value of 4 characters or more becomes `<KEY>`;
  - then the gate's `csa_log` token patterns are applied: `access_token`, `refresh_token`, `client_secret`, `ghp_…`,
    `Bearer …`.
- **Output lines:**
  - `ok<TAB><name> answers an MCP initialize handshake, launched with its registered command and settings (<clients>;
    <server> <version>)`.
  - `warn<TAB>…`, with an order-45 to-do: `<name> did not answer when launched with its <client> registration's
    command and settings`.
  - The wording never claims the server works *in* the client (#177), nor that it was launched as the client
    launches it.

- [ ] **Step 1: Failing tests:**
  - `answers`, `junk_before_response_tolerated`, `error_response_reported`;
  - `silent_server_times_out_and_is_killed`: after the run, no process of the stub's process group exists;
  - `exits_before_answering_masked`: the stub echoes its env to stderr, and no value reaches the output;
  - `one_process_at_a_time`: the stub holds an exclusive lock file and fails on contention;
  - `deduped_launches`;
  - `desktop_env_is_minimal`: the stub writes its env **key names** to a file;
  - `dollar_env_not_checked`, `dead_registration_not_launched`, `dead_standard_binary_not_launched`;
  - `launcher_form_not_launched`: a stub `uv` logs any call, and none appears;
  - `verify_held_by_default`: `VERIFY_ON_RERUN` is empty, and nothing is launched without `--run`;
  - `verify_run_flag_runs`;
  - `token_files_untouched`: a token file at mode `000`, unchanged by stat before and after. Stubs only; the real
    servers are M5's;
  - `failure_todo_and_ledger_absent_print`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4: Prove the tests can fail.** Each mutation must be caught:
  - remove the process-group kill: `silent_server_times_out_and_is_killed`;
  - skip masking: `exits_before_answering_masked`;
  - launch launcher forms: `launcher_form_not_launched`;
  - default `VERIFY_ON_RERUN` to all four: `verify_held_by_default`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: a registered CSA MCP server can be checked with an initialize handshake, one at a time, bounded, with no secret in what it prints, and a rerun holds the check until it is measured`.

### Task 4 (macOS): the three entry scripts show the repairs in the plan, then apply them after the setups

**Depends on:** Tasks 1–3. No measurement of its own.

**Files:**
- Modify: `scripts/macos-ai-tools.sh`, `scripts/macos-update.sh` and `scripts/macos-plugins.sh`.
  - **Add, byte-identical in all three:**
    - `csa_registrations_dir`;
    - `csa_registrations_py`;
    - `csa_registrations_python`;
    - `csa_registrations_preview`;
    - `repair_csa_registrations`.
  - **Call `csa_registrations_preview`** from each `preflight`, inside the `Internal MCP servers` block, before
    `each prints what it may do before it is used`. In `-ai-tools` that is after the `csa_tool_repairs` rows.
  - **Call `repair_csa_registrations`** as the last line of `setup_csa_internal_tools`, after its loop, so it is
    behind the same `gh` gate.
  - **Add to each script's `csa_on_exit`,** before `csa_debug_hint`:
    `if [[ -n "${CSA_REG_DIR:-}" && -d "$CSA_REG_DIR" ]]; then rm -rf "$CSA_REG_DIR"; fi`. The directory is then
    removed on every exit path, including when the user declines the plan or the run stops early.
  - Bump all three versions.
- Modify: `tests/test_mcp_registrations.py`, adding `wiring_` cases that extract the five functions and
  `setup_csa_internal_tools` from each script.

**Interfaces:**
- **`csa_registrations_dir`** creates the run's working directory in the caller's shell. It is called directly, never
  inside `$(…)`, by both `csa_registrations_preview` and `repair_csa_registrations`.
  - When `CSA_REG_DIR` is unset or not a directory, it sets
    `CSA_REG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csa-registrations.XXXXXX")"`.
  - It runs under the `CSA_REGISTRATIONS_PY` override too, because the plan file lives there.
- **`csa_registrations_py`** prints a readable `.py` path, or nothing. It reads `CSA_REG_DIR` and sets nothing, so it
  is safe inside `$(…)`.
  - If `$CSA_REGISTRATIONS_PY` is set and readable, it prints that.
  - Otherwise it prints `$CSA_REG_DIR/csa-mcp-registrations.py`, fetching it first if it is not there:
    `curl -fsSL -H 'Cache-Control: no-cache' <raw HEAD>/scripts/csa-mcp-registrations.py`.
- **`csa_registrations_python`** prints the first candidate that passes, or nothing (spec review M1). It is
  self-contained, because `-plugins` has no `find_csa_python`.
  - **Candidates, in order:**
    1. `python3` from `PATH`;
    2. `uv python find 3.14`, when `uv` is on `PATH`. Any build will do: the `.py` is stdlib-only;
    3. `/opt/homebrew/bin/python3`;
    4. `/usr/local/bin/python3`;
    5. `/usr/bin/python3`, only when `xcode-select -p` succeeds, because without the Command Line Tools that stub
       opens an install dialog.
  - **Each must pass `[[ -x ]]` first,** which follows links, so a dangling one is never executed. It must then run
    `-I -c 'import sys, json; sys.exit(sys.version_info < (3, 9))'` within a 10 s watchdog (stock macOS has no
    `timeout`).
  - So a dead `~/.default_venv` activated by `~/.zshrc`, or a dead Homebrew Python, no longer skips the preview: the
    next candidate is tried.
- **`csa_registrations_preview`:**
  - **When it skips, and what it prints:**
    - `gh` is missing or unauthenticated, or the gate probe fails: it prints only the header, worded "if your GitHub
      account has CSA-Internal access", as the existing rows are.
    - There is no Python or no `.py`: it prints `registration audit skipped: <why>; nothing will be changed`.
  - **Its first action after the `gh` check** is `csa_registrations_dir`, before the Python and `.py` checks, because
    `csa_registrations_py` reads `CSA_REG_DIR`, which `set -u` would otherwise abort on.
  - **Otherwise** it runs `plan --out "$CSA_REG_DIR/plan.json" </dev/null`, with `out="$(…)" || rc=$?`. It prints
    each `row` line under the 23-column indent, through the same helper as the rows around it, so
    `check-log-coverage.py` holds.
  - **A non-zero exit** prints `registration audit failed; nothing will be changed` and removes the plan file.
- **`repair_csa_registrations`:**
  - **Apply:** call `csa_registrations_dir`, then run `apply --approved "$CSA_REG_DIR/plan.json"`. When there is no
    plan file, pass an empty approved file, so every finding is reported, not acted on.
  - **Verify:** then run `verify`, without `--run`. The `.py` decides, by D5, whether anything is launched.
  - **Printing:** map `ok`, `info` and `warn` lines onto `success`, `info` and `warn`.
  - **Clean-up:** remove `$CSA_REG_DIR` and unset it; `csa_on_exit` covers every other exit path. Never fail the
    run.
- **The plan's header row** in all three scripts, verbatim:

  ```
  then audit their registrations in Claude Code (user and local scopes), Claude Desktop, Codex and Gemini,
  and re-point a dead one at ~/.local/bin keeping every setting
  ```

  The per-finding rows follow it, and the `.py`'s check rows only for servers D5 allows.

- [ ] **Step 1: Failing tests:**
  - `preview_rows_under_internal_mcp_servers`, for each of the three scripts;
  - `repair_uses_the_previewed_plan`: the same plan file reaches `--approved`, through each script's real call path
    from `preflight` to `setup_csa_internal_tools`;
  - `reg_dir_set_in_caller_shell`: after `csa_registrations_preview`, `CSA_REG_DIR` is set in the calling shell;
  - `reg_dir_created_under_override`: with `CSA_REGISTRATIONS_PY` set, the directory and plan file still exist;
  - `preview_no_py_under_set_u`: with no Python, under `set -u`, the preview prints the skip row and does not abort;
  - `reg_dir_removed_when_declined`: the user declines at `confirm`, and the directory is gone after exit;
  - `fetch_failure_says_skipped`: a stub `curl` fails;
  - `py_failure_survives_set_e`: the stub `.py` exits 2;
  - `no_fixed_temp_path`: the directory comes from `mktemp` and is gone afterwards;
  - `non_member_silent`: the `gh` probe fails, so there are no rows and no apply;
  - `override_env_used`;
  - `python_candidates_in_order`, `dead_path_python_skipped` (a dangling `python3` first on `PATH`, never executed),
    `apple_python_stub_not_invoked_without_clt`;
  - `verify_called_without_run`;
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
  `feat: every macOS entry point lists the CSA registrations it will re-point before asking, then repairs them after the server setups`.

### Task 5: The docs say what the installer now does to registrations, and the Windows halves are handed to #184

**Depends on:** Tasks 1–4, and the measurements file for the figures it cites.

**Files:**
- Modify: `ENGINEERING.md`.
  - **"What the scripts are":** add the `.py` beside `csa-claude-connectors.py`.
  - **Layout.**
  - **The guard layer:** the test count.
  - **A new § "Registration audit and repair"** under "The CSA contracts". It covers:
    - the readers, and that their CLI calls run from an empty directory;
    - the reasons, verbatim, including the launcher form and the interpreter-shaping keys;
    - the command-only rule;
    - D1, D2, D4 and D5, with their constants;
    - the approved set;
    - the handshake, what it does *not* prove (#177), and that it is held until measured;
    - the credential rule;
    - concurrency, the symlink rule, and backups: the shared name and prune, that each holds secrets at the file's
      mode, and that `mkstemp` plus `os.replace` drops extended attributes and ACLs;
    - the run time a check adds;
    - a link to the measurements file.
- Modify: `AGENTS.md`. Update the trap *"Which clients get CSA tooling depends on who registers it"* to say that this
  repo also re-points existing CSA registrations in place, and never creates one. Do not edit `CLAUDE.md` or
  `GEMINI.md`.
- Modify: `FRICTION.md`, with three measured entries:
  - macOS shows every account's argv, so a secret never goes on a command line;
  - Claude Code's narrowest scope wins, and the incident's dead path survived in local scope after user scope was
    repaired;
  - a check that launches a server can act on its account, so a launch check is measured under the real `HOME`
    before it runs by default (M5's result).
- Modify: `TODO.md`. The #184 row gains `1W`, `4W`, `G1W`, `G2W` and `6W`, a link to the Windows companion, and D3's
  answer.
- **On GitHub:**
  - comment on #184 with a link to `plans/2026-11-12-registration-repair-windows.md`;
  - comment on #179 with D1 to D5 as they stand, and the measurements;
  - link csa-zendesk#70 and csa-google-gmail-calendar#45.

- [ ] **Step 1:** write. Then run `check-todo-citations.py`, `check-paste-safety.py` and `./tools/check-all.sh`.
- [ ] **Step 2: Commit:**
  `docs: ENGINEERING says the installer re-points a dead CSA registration in place and holds its server check until measured, and the Windows halves are on #184`.

### Task G1 (CSA-Plugins, `.sh`): every client command runs from a fresh empty directory, so a local or project registration in the caller's directory can't stand in for the user's

**Depends on:** M7 in `plans/reviews/2026-11-12-registration-repair-measurements.md`. Merges only when D3 allows.

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

- [ ] **Step 1: Apply M7's results.**
  - **If a client shows no shadowing,** leave it out of the wrapper and the rule, and record why. If none does, G1
    shrinks to the record.
  - **If an untrusted empty directory changes what `gemini mcp list` or `gemini mcp add` does,** Gemini's calls do not
    move to the empty directory; record why, and add the finding to #155.
  - Record the results in the PR body.
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

### Task 6: Acceptance on macOS: from a seeded broken state, one run repairs exactly what the plan showed, and a second changes nothing

**Depends on:** Tasks 1–4, and M0 in `plans/reviews/2026-11-12-registration-repair-measurements.md` for Step 1's
real launches. Step 2 also depends on the G2/G3 PR having merged.

**Files:**
- Create: `plans/reviews/2026-11-12-registration-repair-acceptance.md`, scrubbed of secrets, personal data and
  names.

- [ ] **Step 1: An isolated run.**
  - **Environment:** a scratch `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and `TMPDIR`, each set explicitly, so an
    exported `CLAUDE_CONFIG_DIR` cannot point the run at the real config. The real `codex` and `gemini` CLIs, the
    branch's `.py` (`CSA_REGISTRATIONS_PY`), and a stub `ps` first on `PATH`. The Claude Code seeds go into
    `$CLAUDE_CONFIG_DIR/.claude.json`.
  - **Standard binaries:** `$HOME/.local/bin/<entry>` symlinks to the real installed entry points. A server M0 placed
    under `HOME` finds no token under the scratch `HOME`. A server M0 placed outside it is launched for real only
    after the go-ahead, and through the stub server until then. A server launched with the seeded fake credentials may
    call its service with them; that sends no real credential.
  - **Seed, and the result expected under the safe defaults:**

    | # | Seed | Expected |
    |---|---|---|
    | 1 | Claude Code user scope: csa-zendesk, dead (a `.venv` whose `home` is a deleted Cellar directory), with a fake `CSA_ZD_ALLOWLIST_WRITE` | re-pointed; env and other fields identical |
    | 2 | The same shape in local scope, for a scratch project | left, with D2's rebuild-or-remove to-do |
    | 3 | Claude Code user scope: a working source-checkout csa-skilljar with fake secret env, built on a uv Python | left byte-identical, warned (D1) |
    | 4 | A Desktop config at `0600`: a skilljar entry with fake secrets, a gw entry with a bare command name, a `preferences` key | **4a**, stub `ps` reports Desktop running: not written, with the quit to-do (D4). **4b**, stub `ps` reports it not running: gw is re-pointed only if M3 recorded Desktop's `PATH` and the name does not resolve on it; otherwise it is left `not checked` (A8). The mode stays `0600` in both. |
    | 5 | A Codex entry that is dead and has `startup_timeout_sec = 30` | re-pointed; other fields identical |
    | 6 | A Gemini entry that is dead, with `trust` and `includeTools` | re-pointed; extras kept |
    | 7 | Claude Code user scope: csa-google-gmail-calendar as `uv run --directory <scratch checkout> …` | left; never launched: the checkout's listing and mtimes are unchanged |
    | 8 | Claude Code user scope: csa-google-workspace, dead, with a `PYTHONPATH` key | left, with A12's to-do |

  - **Run** `plan`, `apply --approved`, then `verify` (held: one `info` line, nothing launched), then `verify --run`.
    Row 4 is run twice, from the same seed, once per stub `ps` answer.
  - **Compare in process,** printing only `identical: yes|no`:
    - the env and the other fields;
    - the modes and the backups.
  - **No fake secret appears in any captured output.**
  - **The servers' config directories:** their stat is unchanged.
  - **Run again,** and assert no write and no backup.
- [ ] **Step 2: The real run on this Mac is queued for the CINO's go-ahead,** after the G2/G3 PR, G1 and Tasks 1–6
  have merged.
  - **Under the safe defaults,** it repairs nothing: every user entry is standard. It reports the dead local-scope
    csa-zendesk with D2's rebuild-or-remove to-do, and launches no server (D5).
  - **Under D2 `"repoint"`,** it re-points that entry, keeping `CSA_ZD_ALLOWLIST_WRITE`.
  - **Under D5 (a) or (c),** it checks the servers allowed.
  - **The Desktop config is still `0600`** after the gate setups and the repair: the G2/G3 PR's claim, checked end to
    end.
  - **A second run must print no repair.**
- [ ] **Step 3: Commit:**
  `docs: acceptance evidence — one run re-points exactly the planned dead registrations with every setting kept, a second changes nothing`.

---

**Windows halves:** Tasks 1W, 4W, G1W, G2W and 6W are in
[`2026-11-12-registration-repair-windows.md`](2026-11-12-registration-repair-windows.md), held for #184 (D3).

**After Task 6:**
- A whole-branch review per repo, on `fable`.
- A review brief (A1), `plans/2026-11-12-registration-repair-review-brief.md`, with claims to verify.
- The PRs, in the merge order above.
- A resumption summary.
