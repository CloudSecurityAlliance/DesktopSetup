# Plan 2 acceptance on macOS, Step 1: one run re-points exactly the planned dead registrations with every setting kept, a second changes nothing

Task 6 Step 1 of [`plans/2026-11-12-registration-repair.md`](../2026-11-12-registration-repair.md)
(#179 Plan 2): the isolated run. It was recorded 2026-11-15 by the AI implementing the task. Every
statement below is either measured in the run described here or labelled as not measured.

**Step 2, the real run on the CINO's Mac, is not part of this record.** It waits for his go-ahead
after the merge.

**Result: 204 of 204 assertions pass** on the final run (20:53Z): 92 in the world where Claude
Desktop runs (row 4a), 93 where it does not (row 4b), and 19 on the real machine. Every seeded row
behaved as the plan expects. An earlier run of the same harness failed no assertion about the code
but showed a seed error; it is under [Harness corrections](#harness-corrections).

**Code under test:** DesktopSetup `feat/registration-repair` at `628f000`.
- `scripts/macos-plugins.sh`, `SCRIPT_VERSION` `2026-11-15T18:17Z`, run whole.
- `scripts/csa-mcp-registrations.py`, `SCRIPT_VERSION` `2026-11-15T18:17Z`, through
  `CSA_REGISTRATIONS_PY`.

**Tools:**
- `/bin/bash` 3.2.57, and `perl` from `/usr/bin`. macOS 27.2 on arm64.
- `python3` on `PATH` was uv's CPython 3.14.10, so Apple's `/usr/bin/python3` shim was never run.
- The real Codex CLI, codex-cli 0.169.0. The measurements used 0.167.2.
- The real Gemini CLI, 0.68.0. It was present on `PATH` and never run (below).
- The real installed CSA servers, by symlink: csa-google-workspace 0.55.1, csa-google-gmail-calendar
  0.5.1, csa-skilljar 0.16.1 and csa-zendesk 0.3.1.

## Method

**Isolation.**
- Everything ran under one scratch root, made with `mktemp -d` in the session scratchpad.
- Each world made its own directory with `mkdtemp` for each of these:
  - `HOME`, written `~` below;
  - `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and `TMPDIR`;
  - `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME` and `XDG_STATE_HOME`;
  - the directory a stub `getconf` gives for `DARWIN_USER_CACHE_DIR`.
- **The env was built from nothing.** It held those keys, plus:
  - `PATH`: the world's stub directory, then Node's `bin` (for `codex`), then
    `/usr/bin:/bin:/usr/sbin:/sbin`;
  - `TERM`, `LANG`, `SHELL`, `USER` and `LOGNAME`;
  - `CSA_REGISTRATIONS_PY`, set to the branch's `.py`;
  - `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` and
    `GEMINI_FORCE_FILE_STORAGE=true`.

  So no exported `CLAUDE_CONFIG_DIR` and no inherited `XDG_CONFIG_HOME` could reach the real ones
  (M0's caveat). No token-path override key was set.
- **The standard binaries:** `~/.local/bin/<entry>` is a symlink to the real installed entry point
  (`<real home>/.local/share/uv/tools/<pkg>/bin/<entry>`). Its Python is the real tool venv's.
- **The servers' own config directories** were made empty, at `0700`:
  `$XDG_CONFIG_HOME/csa-zendesk`, `~/.csa_google_workspace` and `~/.csa_google_gmail_calendar`. No
  token is under the scratch `HOME`, so a real launch has none to use (M0).
- **Claude Desktop counts as installed** through a scratch `~/Applications/Claude.app` directory,
  whatever the real Mac has.

**Stubs, first on `PATH`.** Each logs its argv to the world's log.

| Name | What it does |
|---|---|
| `ps` | prints a fixed process list. It always has decoys: launchd, cfprefsd, Claude Code's versioned binary, Claude Code's renamed image `claude.exe.old.<n>`, and `/opt/elsewhere/Claude`. Row 4a adds `/Applications/Claude.app/Contents/MacOS/Claude` |
| `gh` | `auth status` and the gate probe `api repos/CloudSecurityAlliance-Internal/CSA-Plugins` succeed. The gate's `contents/internal-setup` listing is empty, and each setup-script fetch fails, so **the four gate setups do not run** (deviation 2) |
| `claude` | `mcp list` shows `csa-mcp` already registered, `plugin marketplace list` shows the six CSA marketplaces, and every other call succeeds and does nothing (deviation 3) |
| `curl` | fails (exit 22): the plugin lists are not fetched, and the `.py` is not fetched either, since `CSA_REGISTRATIONS_PY` is set |
| `uv`, `uvx`, `brew`, `npm`, `pip`, `pip3`, `pipx` | fail, and log the call. None was called |
| `security` | answers "not found" (exit 44). None was called |
| `getconf` | returns scratch directories for `DARWIN_USER_CACHE_DIR` and `DARWIN_USER_TEMP_DIR`. Nothing called it |
| `codex`, `gemini` | log the call, then run the real CLI |
| `python3` | a symlink to uv's CPython 3.14.10 |

**The two worlds** share one seed, below. They differ only in what the stub `ps` reports: 4a,
Desktop running; 4b, not running. Each world ran four steps, one process tree at a time:

1. **Run 1:** `/bin/bash scripts/macos-plugins.sh`, whole, in a pseudo-terminal, from an empty working
   directory. The harness answered `y` at `Proceed with the CSA plugin and MCP server sync? [Y/n]`, as
   a person would. That one run makes the plan (`plan --out`), asks, re-points (`apply --approved`
   on that plan file), then checks (`verify`, held).
2. **`verify --run`, by hand:** `python3 -I csa-mcp-registrations.py verify --run`, with the same env.
3. **Run 2:** the same as run 1.
4. **The comparisons:** after each step, the configs were parsed in process and compared with the
   seed. The harness printed only `identical: yes|no` and `PASS|FAIL`, never a value.

Every captured screen, and every stub's argv log, was searched for the 13 fake secret values.

**Bounded.** Each run had a 300 s timeout, and `verify --run` 240 s. Each ran in its own process group,
which was killed and reaped afterwards. After each step, `ps` found no process whose command line
named the world.

## The seed, and what each run did

The fake values were random strings made per run; the record shows key names only. Every config
held more than its CSA entries:
- **Claude Code** (`$CLAUDE_CONFIG_DIR/.claude.json`, `0600`, indent 2): `numStartups`,
  `hasCompletedOnboarding`, `userID`, the hosted `csa-mcp` (HTTP), and a project with `allowedTools`
  and `hasTrustDialogAccepted`. A backup made by hand, `.claude.json.bak-by-hand`, sat beside it.
- **Codex** (`config.toml`, `0600`): a comment and a `model` key.
- **Gemini** (`settings.json`, `0644`, as measured on the CINO's Mac): a `general` table.

| # | Seed | Expected | Observed, 4a (Desktop running) | Observed, 4b (Desktop not running) |
|---|---|---|---|---|
| 1 | Claude Code user scope: csa-zendesk, dead (`~/GitHub/csa-zendesk/.venv`, whose `home` is a Cellar directory that never existed), with fake `CSA_ZD_ALLOWLIST_READ`, `CSA_ZD_ALLOWLIST_WRITE` and `CSA_ZENDESK_SUBDOMAIN` | re-pointed; env and other fields identical | **pass:** re-pointed at `~/.local/bin/csa-zendesk-mcp`. Env: identical. Other fields (`type`, `args`): identical | **pass**, the same |
| 2 | The same shape in local scope, for `~/GitHub/some-project` | left, with D2's rebuild-or-remove to-do | **pass:** the project entry is identical. The plan row and the to-do name D2's two fixes and the key names, no value | **pass**, the same |
| 3 | Claude Code user scope: a working source-checkout csa-skilljar (`~/GitHub/csa-skilljar/.venv`, built on uv's 3.14), with fake `CSA_SKILLJAR_V1_API_KEY`, `CSA_SKILLJAR_V2_CLIENT_ID` and `CSA_SKILLJAR_V2_CLIENT_SECRET` | left byte-identical, warned (D1) | **pass:** the entry is identical. The plan says it points elsewhere and its Python runs, with the D1 to-do | **pass**, the same |
| 4 | Desktop config at `0600` in a `0700` `~/Library`: a dead csa-skilljar (its shebang Python a dangling link) with three fake secrets; a csa-google-workspace with the bare command `csa-google-workspace-mcp`; `preferences`; `coworkUserFilesPath` | 4a: not written, with the quit to-do. 4b: skilljar re-pointed. gw left `not checked`, since `DESKTOP_PATH` is `None` (A8 ruling). The mode stays `0600` in both | **4a pass:** bytes, inode and mtime identical, and no backup. The plan row says `Claude Desktop is running; csa-skilljar will not be re-pointed there this run — quit it and run again`. The to-do is `Quit Claude Desktop and run again`, with no `Restart Claude Desktop` | **4b pass:** skilljar re-pointed at `~/.local/bin/csa-skilljar-mcp`. Env and other fields identical. One backup, `.bak-<14 digits>`, at `0600`. A `Restart Claude Desktop` to-do |
| 4, both | | | gw entry, `preferences` and every other top-level key identical; mode `0600`; gw row `not checked: Claude Desktop's PATH differs from machine to machine, …` | the same |
| 5 | Codex: csa-google-workspace, dead (its command does not exist), `args = []`, `startup_timeout_sec = 30`, and an `env` sub-table with a fake `CSA_GW_ALLOWLIST_READ` | re-pointed; other fields identical | **pass:** re-pointed. Parsed with `tomllib`, `args`, `startup_timeout_sec`, `env` and every other key are identical. The file differs in exactly one line, the `command` line | **pass**, the same |
| 6 | Gemini: csa-zendesk, dead, in the interpreter form (`<gone venv>/bin/python3 -m csa_zendesk.server`), with fake env, `trust`, `includeTools` and `timeout` | re-pointed; extras kept | **pass:** command `~/.local/bin/csa-zendesk-mcp`, `args` `[]`. Env, `trust`, `includeTools` and `timeout` identical. Mode `0644` kept; the backup is `0644` | **pass**, the same |
| 7 | Claude Code user scope: csa-google-gmail-calendar as `uv run --directory ~/GitHub/csa-google-gmail-calendar csa-google-gmail-calendar` | left; never launched: the checkout's listing and mtimes unchanged | **pass:** the entry is identical. The plan says it runs through uv and is left. `verify --run` says `not checked: launcher form`. The stub `uv` was never called. The checkout's listing and every mtime are unchanged after run 1, after `verify --run` and after run 2 | **pass**, the same |
| 8 | Claude Code user scope: csa-google-workspace, dead, with `PYTHONPATH` and a fake `CSA_GW_ALLOWLIST_READ` | left, with A12's to-do | **pass:** the entry is identical. The plan says `left as it is: its PYTHONPATH setting would point the release binary at another tree`, and the to-do ends `fix it by hand` | **pass**, the same |

**One run re-points exactly what the plan showed.** The harness parsed the plan's
`it will be re-pointed at` rows and apply's `re-pointed in` lines into sets of server, client and
entry. The two sets are equal in both worlds:
- **4a:** rows 1, 5 and 6;
- **4b:** rows 1, 4b, 5 and 6.

**Modes and backups (both worlds).**
- Every config kept its mode: Claude Code `0600`, Desktop `0600`, Codex `0600`, Gemini `0644`.
- Each config that was written got exactly one `<config>.bak-<14 digits>`, at the config's mode.
- The backup named by hand was untouched.
- No `.csa-registrations-*` temp file was left beside any config. The run's `csa-registrations.*`
  directory was gone from `TMPDIR` after each run.

**The servers' config directories** kept their inode, mtime, mode, link count and (empty) listing
through run 1, `verify --run` and run 2.

**The credential rule.**
- None of the 13 fake values appears in any captured screen, in either `verify --run` output, or in
  any stub's argv log (four files per world).
- The values are still in the configs they came from.
- **No client CLI wrote anything.** `claude` was only asked `mcp list` and `plugin marketplace
  list|update`.
- The real `codex` was called 7 times per world, only as `mcp list --json` and
  `mcp get csa-google-workspace --json`. The `get` calls are apply's read-back.
- `gemini` was never run: the `.py` reads Gemini's file, and only checks that `gemini` is on `PATH`.

### What run 1 printed, world 4b

The plan rows inside the `Internal MCP servers` block, before consent:

```
then audit their registrations in Claude Code (user and local scopes), Claude Desktop, Codex and Gemini,
and re-point a dead one at ~/.local/bin keeping every setting
csa-google-workspace in Claude Code (user scope): its command does not exist; left as it is: its PYTHONPATH setting would point the release binary at another tree
csa-google-gmail-calendar in Claude Code (user scope): it runs through uv, which this does not inspect; left as it is
csa-skilljar in Claude Code (user scope): it points at ~/GitHub/csa-skilljar/.venv/bin/csa-skilljar-mcp, not ~/.local/bin/csa-skilljar-mcp; its Python runs, so it is left as it is
csa-zendesk in Claude Code (user scope): its Python no longer exists; it will be re-pointed at ~/.local/bin/csa-zendesk-mcp, keeping its settings (CSA_ZD_ALLOWLIST_READ, CSA_ZD_ALLOWLIST_WRITE, CSA_ZENDESK_SUBDOMAIN)
csa-zendesk in Claude Code (local scope, ~/GitHub/some-project): its Python no longer exists; left as it is: rebuild that checkout's venv, or remove the local entry so your user entry applies there; removing it drops its settings (CSA_ZD_ALLOWLIST_WRITE, CSA_ZENDESK_SUBDOMAIN)
csa-google-workspace in Claude Desktop: not checked: Claude Desktop's PATH differs from machine to machine, so a bare command name can't be resolved here
csa-skilljar in Claude Desktop: its Python no longer exists; it will be re-pointed at ~/.local/bin/csa-skilljar-mcp, keeping its settings (CSA_SKILLJAR_V1_API_KEY, CSA_SKILLJAR_V2_CLIENT_ID, CSA_SKILLJAR_V2_CLIENT_SECRET)
csa-google-workspace in Codex: its command does not exist; it will be re-pointed at ~/.local/bin/csa-google-workspace-mcp, keeping its settings (CSA_GW_ALLOWLIST_READ)
csa-zendesk in Gemini: its command does not exist; it will be re-pointed at ~/.local/bin/csa-zendesk-mcp, keeping its settings (CSA_ZD_ALLOWLIST_READ)
9 CSA registrations in 4 clients; 0 need nothing
```

After `y`, last in the run, after the (empty) setup loop:

```
==> CSA MCP registrations: re-pointing what the plan showed, if anything (csa-mcp-registrations.py)
==> csa-zendesk re-pointed in Claude Code (user scope) at ~/.local/bin/csa-zendesk-mcp; its 3 settings kept; Claude Code sessions started after this use it
==> csa-skilljar re-pointed in Claude Desktop at ~/.local/bin/csa-skilljar-mcp; its 3 settings kept
==> csa-google-workspace re-pointed in Codex at ~/.local/bin/csa-google-workspace-mcp; its 1 setting kept
==> csa-zendesk re-pointed in Gemini at ~/.local/bin/csa-zendesk-mcp; its 1 setting kept
==> Restart Claude Code
==> Restart Claude Desktop
==> Restart Codex
==> Restart Gemini
==> csa-google-workspace in Claude Code (user scope) is dead, and its PYTHONPATH setting would point the release binary at another tree; fix it by hand
==> csa-skilljar in Claude Code (user scope) points at ~/GitHub/csa-skilljar/.venv/bin/csa-skilljar-mcp, not ~/.local/bin/csa-skilljar-mcp; if that is not deliberate, re-point it
==> csa-zendesk in Claude Code (local scope, ~/GitHub/some-project) is dead: rebuild that checkout's venv, or remove the local entry so your user entry applies there; removing it drops its settings (CSA_ZD_ALLOWLIST_WRITE, CSA_ZENDESK_SUBDOMAIN)
==> server check held: this run launched no CSA server; whether a rerun should is not decided yet (#179, D5)
```

**World 4a's run 1 differs only in the Desktop lines.**
- **The plan:** the row `Claude Desktop is running; csa-skilljar will not be re-pointed there this
  run — quit it and run again` stands where 4b has skilljar's re-point row.
- **After consent:** there is no Desktop `re-pointed` line. `Quit Claude Desktop and run again`
  stands where 4b has `Restart Claude Desktop`.

**The held check (D5).** In every entry-script run, `verify` printed exactly one held line and
launched no server. No plan row mentions a server check.

### `verify --run`, by hand (world 4b)

```
warn  csa-google-workspace in Claude Code (user scope): does not start: its command does not exist
info  csa-google-gmail-calendar in Claude Code (user scope): not checked: launcher form
ok    csa-skilljar answers an MCP initialize handshake, launched with its registered command and settings (Claude Code (user scope))
ok    csa-zendesk answers an MCP initialize handshake, launched with its registered command and settings (Claude Code (user scope))
warn  csa-zendesk in Claude Code (local scope, ~/GitHub/some-project): does not start: its Python no longer exists
info  csa-google-workspace in Claude Desktop: not checked: Claude Desktop's PATH differs from machine to machine, so a bare command name can't be resolved here
ok    csa-skilljar answers an MCP initialize handshake, launched with its registered command and settings (Claude Desktop)
ok    csa-google-workspace answers an MCP initialize handshake, launched with its registered command and settings (Codex)
ok    csa-zendesk answers an MCP initialize handshake, launched with its registered command and settings (Gemini)
```

- **Five real launches answered** in 4b, every standard or elsewhere direct executable: row 3's checkout
  included, with its fake credentials. 4a made four, because Desktop's skilljar was still dead there
  and was reported `does not start`, not launched.
- The dead and launcher-form registrations were reported, and never launched.
- **The `ok` lines name no server version.** The plan's Task 3 text has `(<clients>; <server>
  <version>)`. The `.py` as built prints none of a server's own text, version included, by design
  (its docstring). That is noted here, not changed.

### Run 2 changed nothing

In both worlds, after `verify --run` and again after run 2, the four configs kept their sha256, inode,
mtime, mode and size, and their backups kept their names, modes and mtimes: **no write, no backup.**
- **The plan:** run 2 printed no re-point row. Its count line was
  `9 CSA registrations in 4 clients; 4 need nothing` in 4b, and `3 need nothing` in 4a, where
  Desktop's skilljar is still dead.
- **After consent:** no `re-pointed` line, and no `Restart` to-do.
- **Every to-do run 2 printed, run 1 printed too.**
  - Both worlds: the PYTHONPATH entry (row 8), the elsewhere checkout (row 3) and the dead local
    entry (row 2).
  - 4a also: `Quit Claude Desktop and run again`.

### Run times (isolated; Step 2 records the real machine's)

| World | Run 1 (`macos-plugins.sh`, whole) | `verify --run` | Run 2 |
|---|---|---|---|
| 4a | 1.9 s | 2.8 s (4 launches) | 1.0 s |
| 4b | 1.8 s | 3.2 s (5 launches) | 1.1 s |

These include the pseudo-terminal and the stubbed steps. They exclude the gate setups, the plugin
sync and every network call, so they say what the audit, the repair and the check add, not what a real
run takes.

### The real machine was not touched

These were `lstat`ed before and after, and are identical:
- the real Claude Desktop config;
- `~/.codex/config.toml`, `~/.gemini/settings.json` and `~/.gemini/trustedFolders.json`;
- the four real `~/.local/bin/<entry>` links, each tool's entry point and its `pyvenv.cfg`;
- the real `~/.config/csa-zendesk`, `~/.csa_google_workspace` and `~/.csa_google_gmail_calendar`
  directories (`stat` only, never opened).

Two were not compared:
- **The real `~/.claude.json`,** because the session running the harness writes it. No process in the
  run was given its path: `CLAUDE_CONFIG_DIR` and `HOME` were scratch.
- **The real per-user cache** (`getconf DARWIN_USER_CACHE_DIR`) was not redirected for programs that
  ask the OS directly. No top-level entry there changed during the run. Five entries are sandboxed
  and could not be `stat`ed. No `xcrun` shim was run.

**Not measured:** whether a real launch wrote bytecode into the real tool venvs' `site-packages`.
That is what any start of those binaries does, and no client config or token is there.

## Deviations from the plan's Step 1 text

1. **Only `macos-plugins.sh` was run end to end.**
   - `-ai-tools` and `-update` install and upgrade Homebrew packages, npm globals and Claude Code,
     which this run may not do.
   - The eight registration functions are byte-identical in all three (`check-duplication.py`), and
     `tests/test_mcp_registrations.py`'s `wiring_` cases cover each script's own call path.
   - `-ai-tools` is the only one that sets `CSA_TODO_FILE`, so the ledger path was not exercised end
     to end here. The to-dos were printed as `info` lines.
2. **The four gate setups did not run.** They install or upgrade the servers. So `apply` ran right
   after an empty setup loop, against binaries that were already in place.
3. **`claude` was a stub.** The plugin and marketplace steps would clone from GitHub, and
   `setup_csa_mcp_server` would write `csa-mcp` into the seeded config. The `.py` never runs `claude`.
4. **The plan names `plan`, `apply --approved`, `verify`, then `verify --run`.** The first three ran
   inside the entry script, as a person's run makes them. `verify --run` was run by hand, as
   ENGINEERING.md documents it.
5. **The real launches used the real installed binaries under a scratch `HOME`,** with no go-ahead
   needed: M0 places every token under `HOME`. The launches carried the seeded fake credentials.

## Harness corrections

There were four harness runs; the final one is the record.

**The first complete harness run** (20:50Z) made 164 assertions, and all of them passed. It then
crashed at its last step, listing the real per-user cache, because a sandboxed entry refused `lstat`.
The screen checks were added after it, and the third run passed 200 of 200. The `codex` and `gemini`
argv wrappers were added after that, and the fourth run is the final one. In the first complete run,
one `verify --run` line in both worlds was a seed error:

```
warn  csa-google-workspace, launched with its registered command and settings (Codex): exited (code 1) before answering
info  csa-google-workspace did not answer when launched with its Codex registration's command and settings; to see its own messages, run ~/.local/bin/csa-google-workspace-mcp in a terminal
```

- **The cause was the seed.** The fake `CSA_GW_ALLOWLIST_READ` was a bare string, and
  csa-google-workspace 0.55.1 refuses an allowlist that is not a list of document URLs. Run by hand in
  the same scratch world, it ended in a traceback in `_scope_from_env`. With an unset allowlist, or a
  URL-shaped fake one, it answered `initialize`.
- **The fix:** the three gw seeds became document URLs carrying the fake value. The final run's Codex
  gw answers.
- **What it also showed:** the failure path behaves as specified. It printed one fixed line and a
  to-do, none of the server's own text, and no fake value.

**Before that, the harness itself crashed** after the first entry-script run. `killpg` on the exited
child's process group returned `EPERM` on macOS. That is a harness bug, fixed by reaping first. The
cache-listing crash was fixed by skipping an entry that cannot be `stat`ed and counting it. Nothing in
the code under test was involved in either crash.

## Where the evidence is

- **The harness and the scrubbed screens and argv logs** stay in the session scratchpad, as the
  measurement harness did. They are not committed. Every value they would show is above.
- **Scrubbing:**
  - the scratch `HOME` is `~`, as the `.py` itself prints it;
  - the real home is `<real home>`;
  - no account name and no fake value appears here.
