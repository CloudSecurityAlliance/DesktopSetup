# CSA MCP registrations: a rerun audits every client, re-points a dead one in place, and checks each server answers: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (CINO rule B1: always
> subagent-driven) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every
> review runs on the strongest model, `fable` (B12). **Task 0's measurements run before any build task, and a build
> task starts only when the measurements it depends on are recorded** (Task 0's table). The build never waits on the
> CINO: where a decision or a go-ahead is pending, it builds the safe default, and his answer later changes one
> constant and its pinning test.

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
  item 2). A registration that runs through a launcher (`uv run`, `uvx`, `npx`) or whose env shapes the interpreter
  is left alone and reported (A12).
- **The gate repo keeps its leave-alone rule,** which is right for policy. Three `.sh` defects found while planning
  and reviewing are fixed there:
  - **G2** (Desktop config writers create their temp file at the default mode, under a fixed name) and **G3**
    (`csa-skilljar-setup.sh` puts secret-bearing `claude mcp get` output on `python3`'s argv) ship first, in their
    own CSA-Plugins PR (D6).
  - **G1** (a probe can read a shadowing local or project registration instead of the user's) follows, after its
    measurement (M7).
- **Windows halves are separate "W" tasks,** for the Windows session in #184. Whether macOS ships first is D3.

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

**Not measured yet; Task 0 measures each before the task that depends on it.** Until then the plan calls it inferred.
- **Claude Desktop's `PATH` and env for a stdio server.** The earlier draft took launchd's
  `/usr/bin:/bin:/usr/sbin:/sbin` from the gate README. That is documentation, not a measurement.
- **Whether a running Claude Code session or Claude Desktop writes its old copy over an external edit,** and whether
  Claude Code takes a lock file when it writes `~/.claude.json`.
- **Whether a real server, started under the real `HOME` with its token, changes a token file or opens a network
  connection before it answers `initialize`.**
- **Whether the gate's `claude mcp get` probe starts the server.** If it does, every run already launches each server
  once.
- **Each handshake's duration,** and G1's shadowing, including Gemini folder trust in an empty directory.

**Independent spec review (B11), 2026-11-12, on `fable`, at `a9ab5e4`:** 3 blockers, 10 majors and 7 minors, plus
four additions to Task 1W. All are folded in below, and the disposition table at the end says where each went. It
surfaced D3 to D6. Decisions go to the CINO one at a time (K2).

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
  - **(a)** User scope only. A local finding is shown, with a to-do naming the manual re-point.
  - **(b)** Also re-point a *dead* local-scope registration, in place in `~/.claude.json`, with its env kept. A
    working one follows D1.
  - **(d)** Leave a dead local entry, with a to-do naming the two fixes that keep a checkout's policy with that
    checkout's code: rebuild the checkout's venv, or remove the local entry so the user entry applies. The to-do says
    that removing it drops its settings, and names them by key.
  - **Not offered:** project files (`.mcp.json`, and Codex's and Gemini's project configs). They are checked in and
    shared with a team. They are never read or written under any option.
- **Recommendation: (d).** A dead path is not a choice, but the policy on it is. (d) gets the incident's registration
  fixed without changing which code a write allowlist governs. (b) only if he wants the installer to make that move.
- **Why it is his:** it reaches into per-project configuration on developers' machines, and decides which code a
  write allowlist governs.
- **Safe default:** (d). `REPAIR_LOCAL_SCOPE = False`, pinned by `dead_local_scope_todo_names_rebuild_or_remove`.
- **What would let the AI decide next time:** a stated rule that the installer may edit a person's own per-user
  config only where the edit does not change which code a policy setting governs, and never files inside
  repositories.

### D3. Ship macOS first, or hold it until the Windows halves have run

- **Context.**
  - AGENTS.md: *"Both platforms, or neither."*
  - This plan's Windows halves (1W, 4W, 6W, G1W, G2W) need a session on a real Windows machine (#184), which is not
    scheduled.
  - The repair runs inside `setup_csa_internal_tools`, so `check-parity.py` does not see it (A6). Only this decision,
    #184 and `windows_twin_exists`'s per-case SKIP keep the gap visible.
  - Plan 1's D5 (*"Hold as drafts for a Windows session"*, 2026-11-10) was his decision for Plan 1. It does not
    decide this plan.
- **Options:**
  - **(a)** Ship macOS when it passes. The Windows halves are drafts handed to #184, and the gap is recorded there and
    in TODO.md.
  - **(b)** Hold the macOS PRs until a Windows session has run the W tasks end to end.
- **Recommendation: (a).** The incident's machine is a Mac, and the macOS half is measured. Holding it leaves dead
  registrations unreported on Macs and gains Windows nothing, since Windows behaves as today either way. The gap
  stays visible on #184, in TODO.md and in a per-case SKIP.
- **Why it is his:** it is an exception to a repo rule, and Windows users keep today's behaviour for as long as it
  lasts.
- **Safe default:** the repo rule. Building, review and the isolated acceptance run go ahead; the macOS PRs do not
  merge until he answers.
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
    Code, and Claude Code's updater renames its running image (AGENTS.md trap).
  - The to-do appears only when a Desktop finding would be re-pointed.
- **What would let the AI decide next time:** M2's result. If Desktop never writes over an external edit, the AI lifts
  the skip under P1 (correctness) and cites the measurement.

### D5. Run the handshake check on every rerun, or hold it until measured

- **Context.**
  - `verify` launches each registered server with its registered env, outside any client. Under the real `HOME`, a
    server holds a token.
  - Whether a server refreshes it, writes its token file or calls the network before answering `initialize` is not
    measured (B2). The tests use stub servers, and Task 6's isolated run has no token. If a server does, the Global
    Constraint "no token file is opened" fails through the child.
  - M5 measures it. It touches his real `HOME`, so it runs with his go-ahead.
  - M6 measures whether the gate's `claude mcp get` probe already starts each server on every run. If it does, one
    more launch adds no new kind of effect.
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
- **Done in CSA-Plugins PR <number TBD>; Plan 2 depends on it** (merge order, step 1). This plan carries no G2 or G3
  task.

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
| CSA-Plugins | named in that PR | G2, G3 (PR <number TBD>, ships first, D6) |
| DesktopSetup | `feat/registration-repair` | 0 (measurements), 1, 2, 3, 4, 5, 6 |
| CSA-Plugins | `fix/registration-probes` | G1 (`.sh`), after M7 |
| CSA-Plugins | `fix/registration-probes-windows` | G1W, G2W (held, D3) |
| DesktopSetup | `feat/registration-repair-windows` | 1W, 4W, 6W (held, D3) |

1. **CSA-Plugins PR <number TBD> (G2, G3) merges first.** Plan 2 depends on it:
   - Task 6's real run asserts that the Desktop config is still `0600` after the gate setups and the repair. That
     holds only once every gate writer creates its temp file `0600`.
   - The real run runs `csa-skilljar-setup.sh`, whose argv exposure G3 removes.
2. **Task 0's measurements run next.** Those that need nothing from the CINO run at once. Those that touch his real
   `HOME` run when he gives the go-ahead; until then, their safe defaults stand. The evidence is the first commit on
   `feat/registration-repair`.
3. **CSA-Plugins G1 merges after M7 is recorded,** and before DesktopSetup's Tasks 1–6. The gate's `HEAD` is live for
   every user on merge, so its measurement comes first.
   - Work in a fresh clone under the session scratchpad, never in
     `/Users/kurt/GitHub/CloudSecurityAlliance-Internal/CSA-Plugins`.
   - CSA-Plugins#206 is open in another session. Rebase onto main after it merges, and don't touch it.
4. **DesktopSetup Tasks 1–6 merge after,** when D3 allows. The first run that repairs then also runs the fixed probes.
5. **Task 6 Step 2, the real run on the CINO's Mac, comes after all of them,** with his go-ahead.
6. **The Windows halves stay drafts** until a Windows session has measured and run them end to end. Task 5 hands them
   to #184. Whether macOS waits for them is D3.

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
- **Measurements (Task 0):** its rules bind every measurement, and any later one.
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
   - When it runs through a launcher, it is left and never launched (A12).
   - When it is Cellar-pinned, the plan says the next `brew upgrade` deletes its interpreter.
   - When it is dead, it is re-pointed with its env kept (user scope), unless an env key shapes the interpreter
     (A12). In local scope it gets D2's to-do.
   - Tests: `working_elsewhere_left_and_warned`, `launcher_form_left`, `launcher_form_not_launched`,
     `interpreter_env_keys_left`, `cellar_venv_warned`, `homebrew_opt_is_not_cellar`,
     `dead_user_scope_repointed_env_kept`, `dead_local_scope_todo_names_rebuild_or_remove`.
2. **A registration with secrets in env.**
   - No value reaches stdout, stderr, any argv, the plan file, the ledger, or a handshake diagnostic. It is masked
     there as `<KEY>`.
   - The value *is* carried into the repaired entry.
   - The file's mode and its backup's mode are never wider.
   - Tests: `secret_values_never_emitted`, `no_client_cli_writes`, `desktop_mode_0600_kept`,
     `backup_same_mode_and_pruned_to_3`, `exits_before_answering_masked`.
3. **Clients not installed.** The output says "not installed" or "no config yet (#156)", never "fine", and nothing
   is written. Tests: `client_absent_not_installed` (for Codex, Gemini and Desktop) and `desktop_config_dir_absent`.
4. **Configs that are unreadable, malformed or linked (B9, A10):**
   - truncated JSON;
   - JSONC comments in Gemini settings;
   - a duplicate key;
   - an `mcpServers` that is not a dict;
   - a Codex without `--json`, or with a failing CLI;
   - an unreadable plan file;
   - a config that is a symlink.

   Each is "not audited", or left with its reason, nothing is written, and the screen says so. Tests:
   `torn_claude_json_untouched`, `jsonc_gemini_not_audited`, `duplicate_key_is_unreadable`,
   `codex_json_unsupported_not_audited`, `codex_list_failure_is_not_absence`, `unreadable_plan_file_applies_nothing`,
   `symlinked_config_refused`.
5. **A client running and holding the config.**
   - The file changes between our read and our replace: the write is abandoned with "changed while this ran; run
     again".
   - A read-back mismatch restores the backup.
   - **Claude Desktop running:** its config is not written (D4). The plan row says so before consent, and the to-do
     says to quit it and run again. Writing anyway could print `ok` and pass read-back, then lose the edit when
     Desktop writes its old copy: a false success. M2 measures whether that happens.
   - **A Claude Code session running:** M1 decides, before Task 2 is built, whether Claude Code has a lock to honour
     and whether a session writes an old copy back. The `ok` line claims no more than M1 supports.
   - Tests: `concurrent_change_aborts_write`, `readback_mismatch_restores`, `desktop_running_skipped_with_quit_todo`,
     `desktop_detected_by_path_not_name`, plus `claude_lock_honoured` if M1 finds a lock.
6. **Codex and Gemini CLI versions whose `mcp` subcommands differ.**
   - Codex's JSON comes as a list or a dict, with `transport` nested or flat.
   - The TOML table header may be quoted.
   - A multi-line `args` array is refused rather than guessed.
   - Gemini has no `get`, and its extra fields (`trust`, `includeTools`, `timeout`) survive.
   - The CLI calls run from an empty directory (A11).
   - Each client's handshake env follows M3; where M3 could not measure a client, the approximation is labelled one.
   - Tests: `codex_json_shapes`, `codex_quoted_table_header`, `codex_multiline_args_refused`,
     `codex_readback_mismatch_restores`, `gemini_extra_fields_kept`, `client_reads_run_in_empty_dir`,
     `desktop_env_is_minimal`.
7. **Plan and run drift.** A finding that appears, or changes, after consent is not acted on. Tests:
   `unapproved_finding_not_repaired`, `changed_since_plan_not_written`.
8. **Idempotence.** A second run writes nothing: every config's inode, mtime and bytes are unchanged, and no backup
   is made. Tests: `second_run_noop`, plus the Task 6 acceptance run.
9. **The check acts on nothing it has not measured.** While D5 holds, a rerun launches no server, and the plan prints
   no check row. Tests: `verify_held_by_default`, `verify_run_flag_runs`.

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
- **Isolated runs use `mktemp -d`** for `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and `TMPDIR`. At most 4 processes,
  each with a timeout, and cleanup.
- **A measurement that touches the real `HOME`** backs up any file it edits first (`.bak-<14 digits>`, same mode),
  adds and removes only the dummy entry, and runs only with the CINO's go-ahead.

**The dummy server,** `probe_server.py` in the scratch directory, stdlib only. On start it appends to a log in its own
scratch directory: a start marker, its env key names, `PATH` (home as `~`), its working directory, then the method
name of each JSON-RPC message it receives. It answers `initialize`, and exits when stdin closes.

| ID | Question | Decides | Where | Needs from the CINO | Touches his real `HOME` |
|---|---|---|---|---|---|
| M1 | Does a running Claude Code session write an old `.claude.json` over an external edit of a user entry's `command`? Does Claude Code take a lock file when it writes the file? | Task 2's write protocol for Claude Code; Review Focus 5 | isolated `CLAUDE_CONFIG_DIR`, scratch project | nothing, unless a session there cannot reach a config write without a login; then the real config, with his go-ahead | no (fallback: yes) |
| M2 | The same for a running Claude Desktop, across a preference change and a quit | D4 | the real Desktop config | go-ahead | yes |
| M3 | Which env key names, and which `PATH` value, each client passes to a stdio server | A8; Task 3's launch env | Claude Code and Gemini: isolated. Codex: isolated, if a launch needs no login. Desktop: the real config, in M2's session | Desktop, and Codex if it needs a login: go-ahead | Desktop: yes |
| M4 | How long each standard binary takes to answer `initialize`, with no token | Task 3's 20 s timeout and the run time | scratch `HOME`, the real `~/.local/bin` binaries | nothing | no; a launch may write bytecode caches into the tool's own venv, as any launch does |
| M5 | Under the real `HOME`, does each server change a token file, or open a network connection, between spawn and 2 s after its `initialize` answer? | D5 (B2) | the real `HOME` | go-ahead | yes |
| M6 | Does `claude mcp get <name>`, the gate's probe, start the server? Which methods does it send? | how D5 is framed | isolated | nothing | no |
| M7 | G1's question: from a directory with a project or local entry, does each CLI report that entry instead of the user's? Does Gemini behave differently in an untrusted empty directory (folder trust, #155)? | G1's scope | isolated | nothing | no |

**How each is measured:**
- **M1.** Seed the isolated `.claude.json` with a user entry `csa-plan2-probe` that runs the dummy server. Start an
  interactive `claude` session in a scratch project under `script -q`, bounded.
  - While it runs, edit the entry's `command` directly (atomic replace). Then make the session write its config: change
    a setting, then exit. Read the entry back.
  - **Lock:** poll the config directory's listing every 10 ms while the session writes, and record any new name.
    `strings` matches for `.lock` beside `claude.json` in the binary are supporting evidence only, labelled inferred.
  - If the session cannot reach a config write without a login, record that and ask for the real-config fallback.
  - **What changes Task 2:** a lock found means Task 2 takes it with the same protocol. An edit lost with no lock
    means the `ok` line says a running session can write its old copy back, the to-do says to restart Claude Code
    sessions, and the next run's audit is the check. The AI records the choice under P1 (honesty) before Task 2.
- **M2.** With the go-ahead: back up the Desktop config and add `csa-plan2-probe`. With Desktop running, edit its
  `command` directly, change a Desktop preference, quit Desktop, and read the entry. Then remove the dummy entry, with
  Desktop quit, and compare the rest with the backup in process, printing only `identical: yes|no`.
- **M3.** From the dummy server's log.
  - **Claude Code:** after M6's `claude mcp get`, and after a session start if one is possible.
  - **Gemini:** `gemini mcp list`, if it connects to servers, or a session start.
  - **Codex:** a session start in an isolated `CODEX_HOME` if it needs no login. Otherwise record "not measured", and
    keep the approximation labelled as one.
  - **Desktop:** Desktop's start in M2's session launches the dummy.
  - A health-check launch's env may differ from a session's. Each is recorded by the path that made it.
- **M4.** Three timed `initialize` exchanges per standard binary, with a scratch `HOME`. Record the minimum and
  maximum.
- **M5.** With the go-ahead. For each server:
  1. Take its token and credential paths from its public source: the path constant, cited by repo, file and commit.
     Never open them. For a token kept in the login keychain, record the item's modification date only
     (`security find-generic-password -s <service>`, never `-g` or `-w`, filtered to the `mdat` line), or "not
     observed" if that would prompt.
  2. `stat -f '%i %m %z %Sp'` each path and its directory.
  3. Launch it exactly as Task 3 will. A scratch harness reads the user-scope entry in memory, the same read the
     `.py` makes, and passes its env through `subprocess`'s `env`, never argv. It prints nothing from it. Send one
     `initialize`, close stdin, and kill the process group 2 s after the answer.
  4. From spawn to kill, sample `lsof -nP -a -g <pgid> -i` every 100 ms, and record remote `host:port` only. A
     connection shorter than the interval can be missed; the evidence says so.
  5. `stat` again, and record `unchanged` or the field that changed. A server already running in an open client could
     also change a token file. If one changes, repeat once and record both.
- **M6.** Seed the isolated config with `csa-plan2-probe`, run `claude mcp get csa-plan2-probe` from an empty
  directory, and read the dummy server's log.
- **M7.** In an isolated `HOME` and `CODEX_HOME`, with the real CLIs and the dummy server:
  - Does `claude mcp get` from a project with a local entry report the local one?
  - Does `gemini mcp list` from a directory with `.gemini/settings.json` list the project entry?
  - Does Codex read a project-level config?
  - Do `gemini mcp list` and `gemini mcp add` behave differently in an untrusted empty directory than in a trusted
    one?

**What waits for what:**
- **Task 1:** M3's Desktop `PATH`. Without it, A8's leave rule.
- **Task 2:** M1. M2 only to lift D4's safe default.
- **Task 3:** M3, M4 and M6. M5 only to lift D5's safe default.
- **G1:** M7.

- [ ] **Step 1: The measurements that need nothing from the CINO:** M1 (isolated), M3 (its isolated parts), M4, M6
  and M7.
- [ ] **Step 2: Ask for the go-aheads,** one at a time (K2), each saying what it touches: M2 with M3's Desktop part
  (one session), M5, and M1's fallback if Step 1 needed it. Run each when given. Until then, the safe defaults stand
  and the build does not wait.
- [ ] **Step 3: Record and apply.** Write `plans/reviews/2026-11-12-registration-repair-measurements.md`, scrubbed of
  secrets, personal data and names of people. Update the dependent parts of this plan (A8, Task 2's write protocol,
  Task 3's env and timeout), each change naming its measurement and its rule. **Commit:**
  `docs: Plan 2's measurements say what each client passes a server, whether a running client overwrites an edit, and what a server touches at startup`.

### Task 1: `csa-mcp-registrations.py plan` — find every CSA registration in four clients, and say what is wrong with each, without writing anything

**Depends on:** M3's Desktop `PATH`, or A8's leave rule.

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
    `ps -axo comm=` by exact executable path (D4).
  - **Codex:** `codex mcp list --json`, run with `CODEX_HOME` honoured, a 30 s timeout, stdin closed, and `cwd` a fresh
    empty directory (A11).
  - **Gemini:** `~/.gemini/settings.json`, user scope. "Not installed" without a `gemini` on `PATH`.
  - On `win32`, every reader returns `not audited: Windows support is #184 (Task 1W)`.
- **`Registration`:** client, scope, project, name, command, args, env (in memory only), the other fields untouched,
  whether its config file is a symlink, and a fingerprint. The fingerprint is the sha256 of the command, the args and
  the **sorted env key names**, never the values.
- **Classification.** Each finding has a state, a reason, warnings and an action. The checks run in this order, and
  the reasons are verbatim:
  - **`dead`,** when the command itself fails:
    - `its command does not exist`;
    - `its command is not executable`.
  - **`launcher`,** when it is not a direct executable (A12): `it runs through <basename>, which this does not
    inspect; left as it is`.
  - **`dead`,** when its interpreter fails:
    - `its Python no longer exists`: the parsed interpreter, or the venv's `bin/python3`, is dangling or missing, or
      `pyvenv.cfg` `home` is gone;
    - `its Python does not run`: `<interp> -I -c "import json, importlib.resources"` fails or takes more than 10 s.
      Both are stdlib packages on every supported version. `import sys` alone is built in and proves nothing.
  - **`standard`:** the realpath equals the standard binary's realpath, which also covers uv's own tool path. When
    the standard link is itself dead, the action is none: "its setup reinstalls it", as Plan 1 rebuilds it.
  - **`elsewhere`:** it works but is not the standard binary: `it points at <~-path>, not ~/.local/bin/<entry>`.
  - **Warning:** `it runs from a venv built on a Homebrew Cellar Python, which the next brew upgrade deletes`. Use
    Plan 1's recorded-path rule: the first hop out of the venv, or `home`, literally contains `/Cellar/`. An `opt/`
    path is fine.
  - A bare command resolves on the client's `PATH`, as M3 measured it. A bare-name Desktop entry before M3 is left,
    `not checked: Claude Desktop's PATH is not measured yet` (A8).
- **Actions:**
  - **`re-point`** applies when all of these hold:
    - the state is `dead`;
    - the scope may be repaired (user always; local only when `REPAIR_LOCAL_SCOPE`);
    - `args` is empty or exactly `["-m", SERVERS[name].module]`;
    - no env key shapes the interpreter (A12);
    - the config file is not a symlink (A10);
    - for Claude Desktop, Desktop is not running, or `WRITE_DESKTOP_WHILE_RUNNING` (D4).
  - With `REPOINT_WORKING_ELSEWHERE`, `elsewhere` also re-points.
  - Otherwise **`leave`**, with the reason, plus a to-do where somebody has to act. A dead local entry's to-do is
    D2 (d)'s.
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
      `local_scope_missing_project_skipped` (only logged);
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
  - treat `uv` as a direct executable: `launcher_form_left`;
  - drop the `UV_` prefix rule: `interpreter_env_keys_left`;
  - detect Desktop by process name: `desktop_detected_by_path_not_name`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: csa-mcp-registrations.py plan finds every CSA MCP registration in four clients and says which are dead, without reading a credential or writing a file`.

### Task 2: `apply` — re-point an approved dead registration in place, changing only its command

**Depends on:** M1.

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
  4. back up to `<path>.bak-<YYYYmmddHHMMSS>` with `copy2`. Check the backup's mode, and prune to 3 generations,
     with the same regex and count as `csa-claude-connectors.py`, deliberately (A13);
  5. `mkstemp` in the same directory, `fchmod` to the original's mode before writing, write with the detected indent,
     `ensure_ascii=False` and the original's trailing newline, then fsync;
  6. stat again. If the inode, mtime or size moved, unlink the temp file and report
     `changed while this ran; not written — run again`;
  7. `os.replace`;
  8. read back and parse. If the entry is not exactly the intended one, restore the backup and warn.
- **`edit_codex(name, old_command, new_command, args_rule)`:**
  - Find the table `[mcp_servers.<name>]`, or `[mcp_servers."<name>"]`, exactly once.
  - Inside it, until the next header, find exactly one `command = "<old, TOML-escaped>"` line, and, for the
    interpreter form, exactly one single-line `args = ["-m", "<module>"]`.
  - Otherwise refuse with `its Codex entry is laid out in a way this cannot edit safely; left as it is`.
  - Write with steps 4–7 of `edit_json`. Read back with `codex mcp get <name> --json`, from an empty directory (A11):
    the command is new, and every other field equals the original. On a mismatch, restore.
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
  - `dead_local_scope_todo_names_rebuild_or_remove`, and `local_scope_repaired_when_enabled` (the constant flipped
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
  - drop the apply-time Desktop re-check: `desktop_started_after_plan_skipped`.
- [ ] **Step 5:** run the test and `./tools/check-all.sh`. All pass.
- [ ] **Step 6: Commit:**
  `feat: a dead CSA MCP registration is re-pointed at its standard binary in place, changing only its command, and only when the plan showed it`.

### Task 3: `verify` — each registered server answers an MCP `initialize` handshake, launched with its registered command and settings

**Depends on:** M3, M4 and M6. M5 for D5.

**Files:**
- Modify: `scripts/csa-mcp-registrations.py`, adding `verify [--run]`. Bump its version.
- Modify: `tests/test_mcp_registrations.py`, with stub MCP servers written as small Python scripts by the test.

**Interfaces:**
- **Held (D5).** Without `--run`, `verify` checks only the servers in `VERIFY_ON_RERUN`. While it is empty, it
  launches nothing and prints `info<TAB>server check held until its effect on tokens is measured (#179, D5); run
  "verify --run" to check by hand`.
- **What is launched.** Re-audit, and launch each `standard` or `elsewhere` registration that is a direct executable.
  - A `launcher` one is reported `not checked: launcher form`, and never launched (A12).
  - A `dead` one is reported `does not start: <reason>`, and never launched.
  - Launches are de-duplicated on `(command, args, launch env)`. The output names every client that shares a launch.
- **The launch env,** per client as M3 measured it. Where M3 could not measure a client, the approximation is labelled
  one in ENGINEERING.md and the evidence:
  - **Claude Code, Codex and Gemini:** the installer's environment, minus `CSA_TODO_FILE`, `CSA_LOG`, `CSA_DEBUG`,
    `CSA_NESTED` and `CSA_REGISTRATIONS_*`, plus the registration's env.
  - **Claude Desktop:** the key names and `PATH` M3 recorded, plus the registration's env.
  - **An env value containing `$`:** the launch is not made, and the output says `not checked: its environment uses
    $-expansion, which this check does not reproduce`.
- **The exchange:**
  - Send `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},
    "clientInfo":{"name":"csa-desktopsetup-check","version":SCRIPT_VERSION}}}` and a newline.
  - Read stdout until a JSON object with `id == 1` arrives, or 20 s pass (M4 checks the figure). Non-JSON lines are
    skipped and counted.
  - **Pass:** `result.serverInfo.name` is present. Report the name and the version.
  - **Failure messages:**
    - `answered with error <code>`;
    - `exited <code> before answering: <last stderr line>`, masked and cut to 200 characters;
    - `did not answer within 20s`.
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
  - `dollar_env_not_checked`, `dead_registration_not_launched`;
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
  - **Otherwise** it runs `plan --out "$CSA_REG_DIR/plan.json" </dev/null`, with
    `out="$(…)" || rc=$?`. It prints each `row` line under the 23-column indent, through the same helper as the rows
    around it, so `check-log-coverage.py` holds.
  - **A non-zero exit** prints `registration audit failed; nothing will be changed` and removes the plan file.
- **`repair_csa_registrations`:**
  - **Apply:** run `apply --approved "$CSA_REG_DIR/plan.json"`. When there is no plan file, pass an empty approved
    file, so every finding is reported, not acted on.
  - **Verify:** then run `verify`, without `--run`. The `.py` decides, by D5, whether anything is launched.
  - **Printing:** map `ok`, `info` and `warn` lines onto `success`, `info` and `warn`.
  - **Clean-up:** remove `$CSA_REG_DIR`. Never fail the run.
- **The plan's header row** in all three scripts, verbatim:

  ```
  then audit their registrations in Claude Code (user and local scopes), Claude Desktop, Codex and Gemini,
  and re-point a dead one at ~/.local/bin keeping every setting
  ```

  The per-finding rows follow it, and the `.py`'s check rows only for servers D5 allows.

- [ ] **Step 1: Failing tests:**
  - `preview_rows_under_internal_mcp_servers`, for each of the three scripts;
  - `repair_uses_the_previewed_plan`: the same path reaches `--approved`;
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
- Modify: `TODO.md`. The #184 row gains `1W`, `4W`, `G1W`, `G2W` and `6W`, and D3's answer.
- **On GitHub:**
  - comment on #184 with the W tasks;
  - comment on #179 with D1 to D5 as they stand, and the measurements;
  - link csa-zendesk#70 and csa-google-gmail-calendar#45.

- [ ] **Step 1:** write. Then run `check-todo-citations.py`, `check-paste-safety.py` and `./tools/check-all.sh`.
- [ ] **Step 2: Commit:**
  `docs: ENGINEERING says the installer re-points a dead CSA registration in place and holds its server check until measured, and the Windows halves are on #184`.

### Task G1 (CSA-Plugins, `.sh`): every client command runs from a fresh empty directory, so a local or project registration in the caller's directory can't stand in for the user's

**Depends on:** M7. CSA-Plugins PR <number TBD> (G2, G3) merged; rebase onto it.

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

### Tasks G2 and G3 (CSA-Plugins, `.sh`): done in CSA-Plugins PR <number TBD>; Plan 2 depends on it

Decided and specified in D6. Another session builds them as their own PR, which merges before anything in this plan
(merge order, step 1). This plan adds no G2 or G3 task, and its tests do not duplicate that PR's. Task 6 Step 2
checks the result end to end: the Desktop config is still `0600` after a real run.

### Task 6: Acceptance on macOS: from a seeded broken state, one run repairs exactly what the plan showed, and a second changes nothing

**Files:**
- Create: `plans/reviews/2026-11-12-registration-repair-acceptance.md`, scrubbed of secrets, personal data and
  names.

- [ ] **Step 1: An isolated run.**
  - **Environment:** a scratch `HOME`, `CODEX_HOME` and `TMPDIR`, with the real `codex` and `gemini` CLIs and the
    branch's `.py` (`CSA_REGISTRATIONS_PY`).
  - **Standard binaries:** `$HOME/.local/bin/<entry>` symlinks to the real installed entry points. Launched with
    the scratch `HOME`, they find no token.
  - **Seed, and the result expected under the safe defaults:**

    | # | Seed | Expected |
    |---|---|---|
    | 1 | Claude Code user scope: csa-zendesk, dead (a `.venv` whose `home` is a deleted Cellar directory), with a fake `CSA_ZD_ALLOWLIST_WRITE` | re-pointed; env and other fields identical |
    | 2 | The same shape in local scope, for a scratch project | left, with D2 (d)'s to-do |
    | 3 | Claude Code user scope: a working source-checkout csa-skilljar with fake secret env, built on a uv Python | left byte-identical, warned (D1) |
    | 4 | A Desktop config at `0600`: a skilljar entry with fake secrets, a gw entry with a bare command name, a `preferences` key | if a real Claude Desktop is running on this Mac, not written, with the quit to-do (D4); otherwise gw is re-pointed only if M3 measured Desktop's `PATH` and the name does not resolve on it, else left `not checked` (A8). The mode stays `0600`. |
    | 5 | A Codex entry that is dead and has `startup_timeout_sec = 30` | re-pointed; other fields identical |
    | 6 | A Gemini entry that is dead, with `trust` and `includeTools` | re-pointed; extras kept |
    | 7 | Claude Code user scope: csa-google-gmail-calendar as `uv run --directory <scratch checkout> …` | left; never launched: the checkout's listing and mtimes are unchanged |
    | 8 | Claude Code user scope: csa-google-workspace, dead, with a `PYTHONPATH` key | left, with A12's to-do |

    The real-Desktop case in row 4 is the D4 path. The Desktop write path is covered by Task 2's unit tests, with the
    detector stubbed.
  - **Run** `plan`, `apply --approved`, then `verify` (held: one `info` line, nothing launched), then `verify --run`.
  - **Compare in process,** printing only `identical: yes|no`:
    - the env and the other fields;
    - the modes and the backups.
  - **No fake secret appears in any captured output.**
  - **The servers' config directories:** their stat is unchanged.
  - **Run again,** and assert no write and no backup.
- [ ] **Step 2: The real run on this Mac is queued for the CINO's go-ahead,** after the merges.
  - **Under the safe defaults,** it repairs nothing: every user entry is standard. It reports the dead local-scope
    csa-zendesk with D2 (d)'s to-do, and launches no server (D5).
  - **Under D2 (b),** it re-points that entry, keeping `CSA_ZD_ALLOWLIST_WRITE`.
  - **Under D5 (a) or (c),** it checks the servers allowed.
  - **The Desktop config is still `0600`** after the gate setups and the repair (the G2 dependency).
  - **A second run must print no repair.**
- [ ] **Step 3: Commit:**
  `docs: acceptance evidence — one run re-points exactly the planned dead registrations with every setting kept, a second changes nothing`.

---

### Windows halves (held for the Windows session, #184)

These keep the platforms from drifting. They are specified now, and run only after #184's measurements. Whether macOS
waits for them is D3.

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
- **Config encodings.** Does any client write its config with a UTF-8 BOM or CRLF line endings? The reader must parse
  both, and a write must keep the file's own BOM and line endings.
- **`.cmd` shims.** `codex` and `gemini` are npm globals, so on Windows they are `.cmd` shims, which `subprocess` does
  not find or run without a shell. Resolve them with `shutil.which` (which honours `PATHEXT`), and pass arguments so
  `cmd.exe`'s quoting cannot alter them.
- **ACLs after `os.replace`,** for the `.py`'s own writes as well as the gate's: does the replaced file keep a
  user-only ACL, or inherit the directory's?
- **Argv visibility.** Can another account on Windows read a process's command line? A3's rule holds either way; the
  answer goes into FRICTION.md.

**Then:**
- Replace the `win32` "not audited" stubs with real readers and classifiers. The reasons stay verbatim, except that
  `Scripts\python.exe` takes the place of `bin/python3`.
- **The handshake:** `CREATE_NEW_PROCESS_GROUP`, then `taskkill /T /F /PID` on timeout.
- **Running-client detection** is by path, never by process name. Claude Code's updater renames its running image
  (AGENTS.md trap).
- **A locked file** gives `in use by <client>; not written — close it and run again`.

**Tests:** the same test file's Windows cases, run on `windows-latest` CI and on the machine, including a BOM file, a
CRLF file and a `.cmd` shim. A green CI run is not a Windows run (R5).

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
  scriptblock. Apply M7's measurement, repeated on Windows.
- **G2W:** measure whether a new file in Desktop's config directory inherits a user-only ACL. Change code only if it
  is wider than the file it replaces. Fold in CSA-Plugins#198, which is the same files. Also check whether
  `csa-skilljar-setup.ps1` passes the `claude mcp get` output as an argument, as G3 found in the `.sh`; if it does,
  fix it the same way.

**PRs:** drafts.

### Task 6W: acceptance on Windows

Task 6's seed and assertions, on the Windows machine, from the branches. Record the evidence on #184.

---

**After Task 6:**
- A whole-branch review per repo, on `fable`.
- A review brief (A1), `plans/2026-11-12-registration-repair-review-brief.md`, with claims to verify.
- The PRs, in the merge order above.
- A resumption summary.

## Spec review disposition

The spec review of 2026-11-12 (`fable`, at `a9ab5e4`). Every finding was accepted; none was rejected.

| Finding | Change made |
|---|---|
| **B1** `verify` launches `elsewhere` registrations, including `uv run --directory`, unconditionally | A12: a new `launcher` state; only a direct executable is launched, anything else is `not checked: launcher form`. Tasks 1 and 3; tests `launcher_form_left`, `launcher_form_not_launched`; Task 6 row 7. |
| **B2** the with-credentials startup path is never measured | M5 stats token files around one handshake under the real `HOME` and samples network connections. D5 holds `verify` until then. M6 measures the reviewer's mitigating fact (whether `claude mcp get` starts the server). |
| **B3** interpreter-shaping env kept on a re-point; any `-m` module accepted | A12: those keys make the finding `leave` plus a to-do; `SERVERS` pins each module, and another module is left. Tests `interpreter_env_keys_left`, `unknown_module_left`; Task 6 row 8. |
| **M1** one candidate Python, so the incident's state skips the preview | Task 4: five candidates, each `-x`-checked before it runs, `/usr/bin/python3` only with the Command Line Tools. Tests `python_candidates_in_order`, `dead_path_python_skipped`. |
| **M2** design-deciding measurements run after the build | Task 0 runs before Task 1, with a table of what waits for what. M3 records `PATH`'s value. A8 leaves bare-name Desktop entries until it is measured. |
| **M3** "worst case is today's state" is wrong while Desktop runs | Review Focus 5 rewritten (a false success is possible). D4: Desktop's config is not written while it runs, with a quit-and-rerun to-do. |
| **M4** Claude Code's own locking is not used | M1 records whether Claude Code takes a lock; Task 2 honours one if found (`claude_lock_honoured`). |
| **M5** symlinked configs are replaced by regular files | A10: a linked config is never written; test `symlinked_config_refused`. Refused rather than written through, because the target is usually a dotfile repository. |
| **M6** the `.py`'s own Codex and Gemini reads run from the installer's cwd | A11: they run from a fresh empty directory; test `client_reads_run_in_empty_dir`. |
| **M7** G1 on Gemini: folder trust in an empty directory | M7 adds the trust question, measured before G1 merges, because the gate's `HEAD` is live on merge. G1 Step 1 applies it. |
| **M8** `csa-skilljar-setup.sh` passes secret-bearing output as argv | G3, in the CSA-Plugins PR that ships first (D6). G2W checks the `.ps1` twin. |
| **M9** A6 routes a one-sided change around `check-parity.py`; "carried over" is the AI's | D3 is new, and his. "Carried over" is gone. A6 says plainly that `check-parity.py` does not see the change. |
| **M10** "launched as <clients> launch it" over-claims | Task 3 says "launched with its registered command and settings". |
| Minor: `import sys` does not reproduce the first stage | The probe imports `json` and `importlib.resources`; test `python_stdlib_partly_missing`. |
| Minor: `#!/bin/sh` + `'''exec'` launchers | Parsed (A12); test `sh_exec_launcher_shebang_parsed`. |
| Minor: "the standard binary exists and runs" is ambiguous | Task 2: it "classifies as not dead", and is never launched as a precondition. |
| Minor: whole-file JSON re-serialisation | Global Constraints: indent detected, trailing newline and key order kept; dropped extended attributes and ACLs stated. Test `json_format_preserved`. |
| Minor: backups share the prune namespace and hold secrets | A13 documents it and keeps the shared cap. Of the nine backups on this Mac, two match the pattern; the prune spares the rest (`prune_spares_other_backup_names`). |
| Minor: up to 20 s per launch on every `-update` run | Global Constraints and ENGINEERING.md state up to 24 s per distinct launch, about 96 s for four; M4 measures it; nothing while D5 holds. |
| Minor: G2's severity | D6: "group/other-readable mode; defence in depth", since `~/Library` is `0700`. |
| D1 | Agreed; unchanged, plus the launcher-form note. |
| D2: add (d) | (d) added and made the safe default; (b) only if he wants it; project files never touched. |
| D3, D4, D5 (new) | Added as decisions for the CINO, each with its safe default. |
| D6: G2 and M8 alone and first | Decided by the AI under P1; done in CSA-Plugins PR <number TBD>. |
| Four 1W additions (BOM/CRLF, `.cmd` shims, ACLs for the `.py`'s own writes, argv visibility on Windows) | Added to Task 1W's measurements and tests. |
| Codex 0.167 facts unverified by the reviewer | Said so in "What is already true". |
