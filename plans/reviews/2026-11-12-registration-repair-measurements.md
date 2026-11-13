# Plan 2 measurements: Task 0

Plan: [`plans/2026-11-12-registration-repair.md`](../2026-11-12-registration-repair.md), Task 0.

**Step 1 is recorded here:** the measurements that need nothing from the CINO. These are M0, M1 (isolated), M3's
isolated parts, M4, M6 and M7, all taken on 2026-11-12 on the CINO's Mac.

**Step 2 so far:**
- **M5 is recorded below.** It ran with the CINO's go-ahead on 2026-11-13.
- **M2 and M3's Desktop part are recorded below.** They were approved in the same answer, and the coordinating
  session ran them with him on 2026-11-13.

Until a measurement is recorded, its safe default stands (D4, A8, D5).

Scrubbing: home is shown as `~`, a scratch directory as `<scratch>`, a scratch `HOME` as `<HOME>`, and the account
name as `<user>`. No secret was read, so none can appear here.

## How Step 1 was run

- **Isolation.** Each run made its own `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and `TMPDIR` with `mktemp -d`, under
  the session scratchpad. Each run then got a fresh project directory and a fresh empty directory, also from
  `mktemp -d`.
- **The child env** was built from nothing: `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `TMPDIR`, `PATH`, `TERM`,
  `LANG`, `SHELL`, `USER`, `LOGNAME`, plus:
  - `DISABLE_AUTOUPDATER=1`;
  - `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`;
  - `ANTHROPIC_BASE_URL=http://127.0.0.1:9`, a closed local port;
  - `SECURITY_STUB_LOG`.

  `PATH` was the stub directory, then `/usr/bin:/bin:/usr/sbin:/sbin`, with Node's `bin` first for Codex and Gemini.
- **The keychain was never reached.**
  - A stub `security` came first on `PATH`. It logs only the subcommand and the `-s` service name, never reads stdin,
    and answers "item not found" (exit 44).
  - Claude Code calls `security` by bare name, so the stub caught every lookup. They were
    `find-generic-password` for `Claude Code-<8 hex>` and `Claude Code-credentials-<8 hex>`, where the suffix
    varies with the config directory.
  - Gemini ran with `GEMINI_FORCE_FILE_STORAGE=true`, its own switch away from the OS keychain. Codex made no
    `security` call.
- **No credential and no real config were read or written.** Every value in a seeded config or env is fake.
  - The real `~/.claude.json`, `~/.codex`, `~/.gemini`, the Claude Desktop config and the local CSA-Plugins
    checkout were not touched.
  - Mtimes, read with `stat` only: `~/.codex/config.toml`, `~/.gemini/settings.json`, `~/.gemini/trustedFolders.json`
    and the Desktop config were unchanged across the runs.
  - `~/.codex`'s own directory mtime did move. A Codex session, started before this work and running from the real
    `CODEX_HOME`, writes its SQLite logs there. No isolated run pointed at it.
- **The model endpoints were a closed local port.** Claude Code's `ANTHROPIC_BASE_URL` and Codex's model provider
  pointed there, so no login was needed and no model request left the machine. Other traffic was not sampled. No
  isolated home held a credential, so none could be sent.
- **Bounded.** One client ran at a time, with its dummy server and, for Codex, its native child: at most three
  harness-launched processes at once. The clients' own short-lived helpers, such as Claude Code's `security`
  lookups, are not counted. Every launch
  ran in its own process group under a timeout and was killed and reaped at the end, and a `ps` check after each
  run found no survivor. One exception was caught and fixed. The first `codex exec` overran its 90 s timeout, and
  `subprocess.run` killed only Codex's Node wrapper. The native `codex` and its dummy child survived and were killed
  by hand. Later runs killed the whole process group.
- **The dummy server**, `csa-plan2-probe`, is built to Task 0's spec. Each entry's command was an absolute,
  verified Python, uv's `cpython-3.14.10` interpreter, with args `-I <probe_server.py> --marker <label>`. The dummy
  departs from the spec in two ways:
  - it also answers `tools/list`, `prompts/list`, `resources/list` and `ping` with empty results, so that every
    client treats it as healthy;
  - it also logs its parent's executable.
- **The harness stays out of the repo**: the dummy server, the `security` stub, a pseudo-terminal driver, and one
  script per measurement. The driver stands in for the plan's `script -q`. It does the same job, but it can also
  send keystrokes and poll the config directory.

## M0: where each server keeps its token and credentials

**Method.** Public source only, read at the tag of the version installed here (`uv tool list`), in fresh scratch
clones. The package each gate script installs was found in a fresh scratch clone of
CloudSecurityAlliance-Internal/CSA-Plugins at `5083d16`, `internal-setup/csa-*-setup.sh`:
- `PKG_SPEC="csa-zendesk[server]"`;
- `PKG="csa-skilljar"`;
- `'csa-google-workspace[mcp]'`;
- `'csa-google-gmail-calendar[mcp]'`.

No file on this Mac was read. No server's `src/` contains `keyring`, `keychain` or `find-generic-password` at the
cited tag. The search was re-run for all four, csa-skilljar included. Outside `src/`, csa-google-workspace names
`keyring` in `requirements/build.txt` and in two design documents, and csa-zendesk names it in
`DECISIONS-ADR/ADR-009.md`. None of that is server code.

| Server | Repo, tag, commit | Token | Other credential | Override keys (registration env) |
|---|---|---|---|---|
| csa-zendesk | CloudSecurityAlliance/csa-zendesk `v0.3.1` `dca5b92` | `$XDG_CONFIG_HOME/csa-zendesk/tokens.json`, else `~/.config/csa-zendesk/tokens.json` (`src/csa_zendesk/auth/_store.py:46-52`) | none: a public PKCE client that reads no `client_secret` (`auth/_flow.py:4-7`) | `CSA_ZENDESK_TOKEN_FILE` (`_store.py:47`), `XDG_CONFIG_HOME` (`:50`) |
| csa-google-workspace | CloudSecurityAlliance/csa-google-workspace `v0.55.1` `cfb27bb` | `~/.csa_google_workspace/token.json` (`src/csa_google_workspace/mcp/_config.py:32`); read-only posture uses `token.readonly.json` (`auth.py:40`, `token_path_for`) | OAuth client JSON `~/.csa_google_workspace/client_secret.json` (`mcp/_config.py:33`) | `CSA_GW_TOKEN` (`mcp/_config.py:331`), `CSA_GW_CLIENT_SECRETS` (`:326`) |
| csa-google-gmail-calendar | CloudSecurityAlliance/csa-google-gmail-calendar `v0.5.1` `fb38d7a` | `~/.csa_google_gmail_calendar/token.json` (`src/csa_google_gmail_calendar/auth.py:753-757`) | OAuth client JSON `~/.csa_google_gmail_calendar/client_secret.json` (`mcp/_config.py:38-40`) | `CSA_GGC_TOKEN_PATH` (`auth.py:753`), `CSA_GGC_CLIENT_SECRETS` (`mcp/_config.py:38`) |
| csa-skilljar | CloudSecurityAlliance/csa-skilljar `v0.16.1` `aee5ca4` | **none on disk.** A `client_credentials` access token is held in memory (`src/csa_skilljar/auth.py:108-112`); `src/` has no `open(` call | the credentials are the registration env itself: `CSA_SKILLJAR_V2_CLIENT_ID`, `CSA_SKILLJAR_V2_CLIENT_SECRET`, `CSA_SKILLJAR_V1_API_KEY`, or a file named by `CSA_SKILLJAR_ENV_FILE` (`mcp/_config.py:74,104-109`) | `CSA_SKILLJAR_ENV_FILE` |

Each repo's `main` has moved past its tag, but the token constants cited are the same at `main`:
- csa-zendesk `e0ac555`;
- csa-google-workspace `060bb8f`;
- csa-google-gmail-calendar `a655ec3`;
- csa-skilljar `56f4d04`.

**Result.** By default, every token is under `HOME`, and none is in the keychain. csa-skilljar keeps no token on
disk. Its secret lives in the registration's env.

**Branch triggered.** None: no token is outside `HOME`. M4 ran all four servers, and Task 6 Step 1's real launches
need no go-ahead on M0's account. **Two caveats bind Task 3 and Task 6 Step 1:**
- **A scratch `HOME` isolates a server only when its launch env carries none of the override keys above.** That
  includes an inherited `XDG_CONFIG_HOME`, which Claude Code and Gemini pass through (M3). M5 read the four
  Claude Code user-scope registrations in memory, and none carries an override key. Other clients' and other scopes'
  registrations were not checked; Task 1's plan output shows their key names.
- **A csa-skilljar launch with its registration env carries a real credential.** That is a question for M5, not for
  `HOME`. M5 saw no connection at that launch.

## M1 (isolated): does a running Claude Code session write an old `.claude.json` over an external edit, and does it lock?

**Method.**
- Claude Code 2.1.323, in an isolated `CLAUDE_CONFIG_DIR`. The seeded config:
  - `hasCompletedOnboarding`;
  - the scratch project trusted;
  - a user entry `csa-plan2-probe` (marker A).
- An interactive session was started in the scratch project, in a pseudo-terminal, bounded at 150 s. It came up at
  its prompt showing `Not logged in · Run /login`, so **no login was needed** and the real-config fallback is not
  needed.
- A watcher polled the config directory, and its `backups/` subdirectory, every 10 ms. It recorded every new or
  removed name, and every change of the config's inode or size.
- The edit was an atomic replace of the entry's `command` with a second absolute path (`probe-b.sh`, marker B).
- The run, three times:

| Run | After the edit | Entry after the session's next config write | After `/exit` |
|---|---|---|---|
| main | `/theme` → pick → Enter; the session rewrote `.claude.json` (new inode, 1936 → 2045 bytes) under its lock | **`probe-b.sh`: the edit survived** | `probe-b.sh` (rewritten again, under the lock) |
| lock held | the harness held `.claude.json.lock` for 13.6 s, refreshing its mtime every 0.5 s, then made the edit and changed the theme | the session did **not** write `.claude.json` while the lock was held (it wrote `settings.json`, which takes no lock); it wrote `.claude.json` 2.1 s after the release, under its own lock, and the edit survived | `probe-b.sh` |
| `CLAUDE_CONFIG_DIR` unset, scratch `HOME` | (no edit; locations only) | lock `<HOME>/.claude.json.lock`, temp `<HOME>/.claude.json.tmp.<pid>.<hex>`, backups `<HOME>/.claude/backups/.claude.json.backup.<ms>` | — |

The main run's watcher, around the setting change (seconds from spawn):

```
32.442 dir_new  .claude.json.lock (directory)
32.467 dir_new  .claude.json.tmp.<pid>.<hex>
32.480 dir_gone .claude.json.lock
32.480 dir_gone .claude.json.tmp.<pid>.<hex>
32.480 file_stat new inode, 2045 bytes
```

At start, the session also copied the config to `<config dir>/backups/.claude.json.backup.<ms>`, at mode `0600`. In the smoke run, one rewrite at 11.6 s showed no lock directory; a lock held for under 10 ms can fall
between polls.

**Result.**
- **The edit was never lost.** Each of the session's writes re-read the file under its lock, so it kept the edit.
- **Claude Code takes a lock:** `<config>.lock`, a *directory*, created before the write and removed after it.
- The write is a temp file in the same directory, then a rename.
- **It honours a lock someone else holds.** The write due at the setting change (29.4 s) waited until the release
  (38.1 s), and landed 2.1 s after it.
- **Supporting, inferred:** the binary bundles `proper-lockfile` (``r.lockfilePath||`${e}.lock` ``, `mkdir`). That
  library treats a lock whose mtime is older than its stale limit (10 s by default) as abandoned. Claude Code's own
  stale setting was not measured.
- **A running session kept using the command it started with.** The dummy was never relaunched as marker B. A
  repair reaches sessions started after it.

**Branch triggered: "a lock is found: Task 2 takes it with the same protocol."**
1. `mkdir` the `.lock` directory beside the config (`~/.claude.json.lock` when `CLAUDE_CONFIG_DIR` is unset); hold
   it across the read, the stat check and the replace; then `rmdir` it.
2. If the lock exists, wait a bounded time and retry. Never break it. If it is still held at the timeout, skip
   Claude Code's config this run, with the to-do `Claude Code's config is locked; close Claude Code and run again`,
   naming the lock path. The next run's audit is the check.
3. Keep the hold well under 10 s.

**Step 2 departs from "the same protocol". This is the AI's decision (2026-11-12, the measurement review's ruling,
under P1: safety).**
- `proper-lockfile` breaks a stale lock, and Claude Code's stale handling was not measured.
- Breaking a lock that a live session holds could let two writers race, so Task 2 never breaks one.
- **The cost:** a crashed session's leftover lock blocks the repair of Claude Code's config until somebody removes
  it. The to-do names the lock's path, and every other client is still repaired.

The "edit lost with no lock" branch is not triggered. The `ok` wording should say that the change applies to
sessions started after it.

## M3 (isolated parts): which env key names and `PATH` each client passes a stdio server

**Method.** From the dummy's log, against the child env above. One follow-up run added fake inherited keys whose
names look secret (`PLAN2_FAKE_TOKEN`, `PLAN2_FAKE_API_KEY`), a plain one (`PLAN2_PLAIN`), and `XDG_CONFIG_HOME` and
`PYTHONPATH`. It also added a fake registered env, `CSA_PLAN2_FAKE_CLIENT_SECRET` and `CSA_PLAN2_PLAIN`.
`__CF_USER_TEXT_ENCODING` appears in every record, the dummy's self-test with a bare env included. That macOS adds
it to every process is inferred from that self-test, not measured.

| Client, and the path that launched the server | Env key names the server got | `PATH` | Working directory | Methods sent |
|---|---|---|---|---|
| Claude Code, interactive session (M1) | **every inherited key** (of the base env; the follow-up keys were run through `mcp get`) + `AI_AGENT`, `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PROJECT_DIR`, `COREPACK_ENABLE_AUTO_PIN`, `NoDefaultCurrentDirectoryInExePath` | inherited, unchanged | the session's directory | `server/discover`, `initialize`, `notifications/initialized`, `tools/list`, `prompts/list`, `resources/list` |
| Claude Code, `claude mcp get` / `claude mcp list` (M6) | **every inherited key**, secret-looking names, `XDG_CONFIG_HOME` and `PYTHONPATH` included; **+ the registered env**; + the same added keys minus the two `MESSAGING` ones | inherited, unchanged | the caller's directory | `server/discover`, `initialize`, `notifications/initialized`, `tools/list` |
| Codex 0.167.2, a session start (`codex exec`, model provider a closed local port, no login) | **only** `HOME`, `LANG`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `TMPDIR`, `USER` of the inherited keys, **+ the registered env**. `XDG_CONFIG_HOME`, `PYTHONPATH` and the rest were dropped. | inherited, with two Codex directories prepended: `$CODEX_HOME/tmp/arg0-macos/codex-arg0<rand>` and the npm package's `vendor/aarch64-apple-darwin/codex-path` | the caller's directory | `initialize`, `notifications/initialized`, `tools/list` |
| Gemini 0.67.0, `gemini mcp list` in a **trusted** folder | inherited keys **except names that look secret** (`PLAN2_FAKE_TOKEN` and `PLAN2_FAKE_API_KEY` were dropped; `PLAN2_PLAIN` passed), **+ the registered env** (`CSA_PLAN2_FAKE_CLIENT_SECRET` passed) + `GEMINI_CLI`, `GEMINI_CLI_NO_RELAUNCH` | inherited, unchanged | the caller's directory | `initialize`, `notifications/initialized`, `ping` |
| Gemini, `gemini mcp list` in an **untrusted** folder | not launched | — | — | — |
| Claude Desktop, at its start (M2's session, 2026-11-13) | `HOME`, `LC_CTYPE`, `LOGNAME`, `PATH`, `SHELL`, `USER`, `__CF_USER_TEXT_ENCODING`, **+ the registered env** | its own, which may be a fallback (see "M2 and M3's Desktop part") | `/` | `initialize`, `notifications/initialized`, `tools/list` |

Not measured: a Codex TUI session, and a Gemini chat session. A Gemini session needs a login or an API key, and
`gemini mcp list` was the path the plan allows. Codex's allowlist was tested only against the keys passed; it may
keep others, such as `TZ` or `LC_*`.

**Result.** The three CLIs pass the caller's `PATH` through. Codex prepends two Codex-internal directories that
hold no CSA binary. So for these clients, a bare command name resolves on the `PATH` of the shell that started the
client. The env differs by client:
- **Claude Code passes everything.**
- **Codex passes an allowlist plus the registered env.**
- **Gemini passes everything but secret-looking names, plus the registered env.**

The dummy's self-test also showed that Python itself adds `LC_CTYPE` under a bare env (PEP 538). That key is an
artefact of the interpreter, not of a client.

**Branch triggered: "Task 3 builds each client's launch env from the recorded key names; A8 resolves bare names on
each recorded `PATH`."**
- **Claude Code:** the caller's env plus the registered env.
- **Codex:** its allowlist plus the registered env. **The allowlist is a lower bound:** only the eight keys above
  were seen to pass, and only keys in the input were tested. Codex may also pass others, such as `TZ` or `LC_*`.
- **Gemini:** the caller's env minus secret-looking names, plus the registered env.
- **Desktop:** recorded in M2's session. The seven key names observed, plus the registered env, and its `PATH`,
  which carries an extraction caveat. See "M2 and M3's Desktop part" for the branch.
- **A12's interpreter-shaping keys can arrive from the client's own env,** not only the registration. Claude Code
  and Gemini pass an inherited `PYTHONPATH`.

## M4: how long each standard binary takes to answer `initialize`

**Method.** For each `~/.local/bin/<entry>`, three exchanges, one process at a time.
- **Env:** a scratch `HOME` and `TMPDIR`, `PATH=/usr/bin:/bin` and `LANG`. No registration env, so no credential.
- **Each exchange:** an `initialize` (`protocolVersion` `2025-06-18`), timed from spawn to the answer; then stdin
  closed; the process group killed after 2 s at the latest, and reaped.

| Server (installed version) | Answer, runs 1 / 2 / 3 | Min | Max | Exit after stdin closed |
|---|---|---|---|---|
| csa-google-workspace 0.55.1 | 0.61 / 0.54 / 0.54 s | 0.54 s | 0.61 s | ≤ 0.12 s, by itself |
| csa-google-gmail-calendar 0.5.1 | 2.94 / 0.51 / 0.52 s | 0.51 s | 2.94 s (cold first run) | ≤ 0.12 s, by itself |
| csa-skilljar 0.16.1 | 0.48 / 0.43 / 0.43 s | 0.43 s | 0.48 s | 0.11 s, by itself |
| csa-zendesk 0.3.1 | 0.38 / 0.35 / 0.35 s | 0.35 s | 0.38 s | 0.06 s, by itself |

The scratch `HOME` was empty afterwards: no server created anything under `HOME` at a start with no credential.
Each server wrote only its policy banner to stderr. For example, csa-google-gmail-calendar reported its missing
client JSON and download directories.

**Result.** The largest maximum is 2.94 s, under 10 s, half the timeout.

**Branch triggered.** The 20 s timeout stands. The figures go into ENGINEERING.md's run time, under Task 3: 0.35
to 0.61 s warm, and up to about 3 s cold. These are starts with no credential. A start with one is M5's question.

## M6: does `claude mcp get <name>`, the gate's probe, start the server?

**Method.** The isolated config was seeded with a user entry `csa-plan2-probe`. `claude mcp get csa-plan2-probe`,
then `claude mcp list`, were run from an empty directory, with stdin closed, each under a 60 s timeout.

```
Scope: User config (available in all your projects)
Status: ✔ Connected
probe log: START marker=user parent=~/.local/share/claude/versions/2.1.323
           RECV server/discover / initialize / notifications/initialized / tools/list
```

`claude mcp list` started it too ("Checking MCP server health…"). On a fresh config, the first `mcp get` rewrote the
config to add Claude Code's first-start keys (`firstStartTime`, `machineID`, `userID`, migration flags); the second
call wrote nothing. Neither call added a `projects` entry, which confirms the spec review's observation.

**Result.** Yes. The gate's probe starts the server and runs `initialize` through `tools/list`. Its env is the
caller's whole env plus the registered env, and its working directory is the caller's.

**Branch triggered: every gate run already launches each Claude Code user-registered server once.** D5's question
says a `verify` launch is one more of that kind. No constant changes on M6 alone.

## M7: does each CLI report a project or local entry instead of the user's? Does Gemini's folder trust change `mcp list` or `mcp add`?

**Method.** Isolated `HOME`, `CLAUDE_CONFIG_DIR` and `CODEX_HOME`, the real CLIs, and the dummy. The user entry,
and each project or local entry, carried different markers.

| Client | From | Reports | Starts |
|---|---|---|---|
| Claude Code `mcp get` | empty directory | user | user |
| | a project with a **local** entry (`projects[<dir>].mcpServers`) | **local** | **local** |
| | a project with `.mcp.json`, not approved | user | user |
| | a project with `.mcp.json` approved (`enabledMcpjsonServers`) | **project** | **project** |
| Codex `mcp get --json` | empty directory | user | nothing (`mcp get` and `mcp list` start no server) |
| | a project with `.codex/config.toml`, untrusted, not a git repo | user | — |
| | the same, a git repo, untrusted | user | — |
| | the same, trusted (`[projects."<dir>"] trust_level = "trusted"` in `CODEX_HOME`) | **project** (`mcp list --json` also lists only the project entry) | — |
| Gemini `mcp list` (folder trust on by default in 0.67) | empty directory, untrusted | user, `Disabled`, with a warning that user-level servers are suppressed in untrusted folders | nothing |
| | a project with `.gemini/settings.json`, untrusted | **project**, `Disabled` | nothing |
| | the same project, trusted (`~/.gemini/trustedFolders.json`) | **project**, `Connected` | **project** |
| | empty directory, trusted | user, `Connected` | user |
| Gemini `mcp add --scope user --transport stdio` (as the gate runs it) | untrusted empty directory | written to user settings | — |
| | trusted empty directory | written to user settings | — |

Neither `mcp add` created a `.gemini/` in the directory it ran from.

**Result.**
- **All three CLIs report a narrower entry in place of the user's** when the caller stands in a directory that
  has one:
  - **Claude Code:** a local entry, or an approved `.mcp.json`.
  - **Codex:** a project `.codex/config.toml`, but only in a trusted project.
  - **Gemini:** a project `.gemini/settings.json`, whether trusted or not.
- **Gemini in an untrusted empty directory:**
  - `mcp list` still names every server, so the gate's name match still finds it;
  - it marks them `Disabled` and starts none, where a trusted folder would start them;
  - `mcp add --scope user` behaves identically.

**Branch triggered (G1 Step 1).**
- **Shadowing is shown for every client,** so none is left out of `csa_client`.
- **Gemini, as the rule is written:** an untrusted empty directory *does* change what `gemini mcp list` does. It
  starts nothing and prints `Disabled`, so Step 1 says Gemini's calls stay where they are, with the finding added
  to #155.
- **The measured effect, though, is benign for the gate's probe.** The name still matches, and `add --scope user`
  is unchanged. It also removes a server launch. See "What the plan got wrong" below.

## M5 (real `HOME`): does a server change a token file, or open a connection, between spawn and 2 s after its answer?

**Go-ahead.** The CINO's answer, verbatim: *"Both, now (Recommended)"* (2026-11-13). It answered a question that
described M5 as launching each of the four CSA servers once, as Claude Code would. The question also said that M5
reads the real `~/.claude.json` in memory for their env, only `stat`s token-file metadata before and after, samples
network connections for 2 s, and that a launch may refresh a token. M2 was approved in the same answer. It is being
run interactively with him by another session, and this run touched neither the Desktop config nor the Desktop app.

**Method.** Run on 2026-11-13 at 02:39Z, one server at a time, each launched exactly as Task 3 will launch it.
- **The entry:** each user-scope Claude Code registration was read from the real `~/.claude.json`, in memory. Only
  its command, its arg count and its env key names were printed.
- **The launch env:** this session's environment, standing in for the installer's, minus `CSA_TODO_FILE`, `CSA_LOG`,
  `CSA_DEBUG`, `CSA_NESTED` and `CSA_REGISTRATIONS_*`, plus the registration's env. It was passed through
  `subprocess`'s `env`, never argv. No registration value uses `$`.
- **The launch:** working directory a fresh `mktemp -d`, `start_new_session=True`. One `initialize`. On the answer,
  stdin was closed; after 2 s, SIGTERM to the process group; after 2 s more, SIGKILL; then reaped.
- **Token paths:** each one M0 names was `stat`ed before and after (inode, mtime, size, mode), with its directory,
  and never opened. No registration carries a token-path override key (`CSA_ZENDESK_TOKEN_FILE`, `CSA_GW_TOKEN`,
  `CSA_GGC_TOKEN_PATH`, `CSA_SKILLJAR_ENV_FILE`), and the launch env had no `XDG_CONFIG_HOME`, so every path is the
  default, under `HOME`. The Google servers' `client_secret.json` was `stat`ed too.
- **Keychain:** not applicable. M0 found no keychain use in any server.
- **Network:** `lsof -nP -a -g <pgid> -i` every 0.1 s or more (each run took about 0.02 s), from spawn until the
  group was killed. Only remote `host:port` was kept.
- **Cleanup:** afterwards, `pgrep -g` found nothing in any of the four process groups. `pgrep -f` for the four
  binaries listed only processes that open clients (Claude Desktop and Claude Code sessions) were already running:
  84 of them.

| Server | Registration env keys | Answer | Token and credential files (inode, mtime, size, mode) | Remote hosts contacted |
|---|---|---|---|---|
| csa-zendesk 0.3.1 | `CSA_ZD_ALLOWLIST_READ`, `CSA_ZD_ALLOWLIST_WRITE`, `CSA_ZENDESK_MCP_SERVER_IDENTIFIER`, `CSA_ZENDESK_SUBDOMAIN` | 0.49 s | `~/.config/csa-zendesk/tokens.json` (`0600`) and its directory (`0700`): **unchanged** | **none observed** (44 samples) |
| csa-google-workspace 0.55.1 | `CSA_GW_ALLOWLIST_MODIFY`, `CSA_GW_ALLOWLIST_READ`, `CSA_GW_CAPABILITIES` | 0.64 s | `~/.csa_google_workspace/token.json` (`0600`), `client_secret.json` (`0600`) and the directory (`0700`): **unchanged**; `token.readonly.json` absent before and after | **none observed** (46 samples) |
| csa-google-gmail-calendar 0.5.1 | `CSA_GGC_ATTACH_DIR`, `CSA_GGC_DOWNLOAD_DIR` | 1.84 s | `~/.csa_google_gmail_calendar/token.json` (`0600`), `client_secret.json` (`0600`) and the directory (`0700`): **unchanged** | **none observed** (57 samples) |
| csa-skilljar 0.16.1 | `CSA_SKILLJAR_PROFILE`, `CSA_SKILLJAR_V1_API_KEY`, `CSA_SKILLJAR_V2_CLIENT_ID`, `CSA_SKILLJAR_V2_CLIENT_SECRET` | 0.55 s | no token file (M0); no `CSA_SKILLJAR_ENV_FILE` | **none observed** (45 samples), although its launch carried its real client credentials |

Every server exited by itself 0.06 to 0.11 s after stdin closed. No token changed, so the plan's "repeat once" did
not apply.

**What this does not show:**
- **The window is the launch Task 3 makes,** not a client's long-lived session. Because stdin closes on the answer
  and each server exits about 0.1 s later, the observed window ran from spawn to about 0.1 s after the answer, not a
  full 2 s with the server alive. Work that a server does later in a session, such as on its first tool call, is
  outside it.
- **`lsof` can miss a connection shorter than its interval.** It also shows no DNS lookup, because those go through
  `mDNSResponder`.
- **Whether a server *read* its token at startup is not measured.** Access times were recorded, but a test file in
  the scratchpad showed that this volume does not update `atime` on a read, so `atime` proves nothing here.
- **The launch env was this session's,** standing in for the installer's. It carries `VIRTUAL_ENV`, which does not
  change how the entry points' absolute-shebang Python starts.

**Branch triggered: "a server with no token change and no connection becomes a candidate for D5 (c), and the
question to the CINO lists what each server touched."**
- **All four servers are candidates for D5 (c).** For the launch `verify` makes, each touched nothing observed: no
  token-file change, and no network connection.
- **D5's question to the CINO lists that, per server.** It also says what M6 showed: every gate run already makes a
  launch of this kind through `claude mcp get`.
- **The constant stays Task 3's.** `VERIFY_ON_RERUN` keeps its safe default until D5 is answered, or until the AI
  applies D5's own "what would let the AI decide next time" rule under P1, recording this measurement.
- **M4's timeout is confirmed.** With credentials present, the slowest answer was 1.84 s, so the 20 s timeout
  stands.

## M2 and M3's Desktop part (the real Claude Desktop config): does a running Desktop overwrite an edit, and what does it pass a server?

**Go-ahead.** The CINO's answer, verbatim: *"Both, now (Recommended)"* (2026-11-13). The coordinating session ran
this with him interactively, and every result below was observed by that session. This session did not touch the
Desktop config or the Desktop app.

**Method**, in the plan's order:
1. Desktop was quit.
2. The config was backed up beside itself, at mode `0600`.
3. The dummy `csa-plan2-probe` was added. Its command is the absolute uv `cpython-3.14.10` interpreter, with args
   `[probe_server.py, "A-original"]`.
4. The CINO started Desktop, which launched the dummy.
5. While Desktop ran, the dummy's command was edited in the file to a wrapper that runs the same probe with the
   marker `B-edited`.
6. The CINO quit Desktop. He was asked to change one preference first, and **did not**, so no preference changed.
7. The entry was read back.
8. The dummy was removed, and the config was compared with the backup.
9. The backup was deleted.

Desktop ran for about 14 minutes between its start and its quit.

### M3, Claude Desktop

| What | Observed |
|---|---|
| Launches at start | 3: two at once, then one 3 s later |
| Env key names the server got | `HOME`, `LC_CTYPE`, `LOGNAME`, `PATH`, `SHELL`, `USER`, `__CF_USER_TEXT_ENCODING`. The registered env is added to these; the dummy had none. |
| `PATH`, home as `~` | `~/.nvm/versions/node/v23.7.0/bin:~/.nvm/versions/node/v26.13.0/bin:/usr/local/bin:/opt/homebrew/bin:~/Library/pnpm:~/.local/bin:~/.pyenv/shims:/usr/bin:/bin:/usr/sbin:/sbin` |
| Working directory | `/` |
| Methods sent | `initialize`, `notifications/initialized`, `tools/list` |

- **The `PATH` may be a fallback.** At this start, Desktop's own log said
  `[CCD] Shell environment extraction failed (attempt 1), using process.env: Shell environment extraction timed out`.
  The `PATH` recorded may therefore be its fallback, `process.env`, and not what a successful login-shell extraction
  gives. One start was measured, so the successful-extraction case is not.
- **`LC_CTYPE` is probably Python's own, not Desktop's (inferred).** The server got no `LANG` and no other `LC_*`.
  With none of them set, Python coerces the C locale and sets `LC_CTYPE` itself (PEP 538), and the dummy's isolated
  self-test showed the same key.
- **`__CF_USER_TEXT_ENCODING` is probably the OS's own, not Desktop's (inferred)** from the same self-test.
- **Desktop passes far less than the CLIs.** Seven key names were observed. Five of them come from Desktop: `HOME`,
  `LOGNAME`, `PATH`, `SHELL` and `USER`. The other two are probably the interpreter's and the OS's own, as above.
  Claude Code passes its whole env (M3, isolated parts).
- **This session's observation.** M5's process listing showed Desktop starting each CSA server through
  `/Applications/Claude.app/Contents/Helpers/disclaimer --pgroup -- ~/.local/bin/<entry>`, so a server's parent under
  Desktop is that helper.

**Branch triggered (A8, Task 3): "A8 resolves bare names on each recorded `PATH`; Task 3 builds Desktop's launch env
from the recorded key names."**
- **A8:** a bare-name Desktop entry resolves on the `PATH` above, which includes `~/.local/bin`. That resolution
  is labelled with the extraction caveat: it is the `PATH` Desktop passed at a start whose shell extraction timed out.
  **Not applied — AI ruling 2026-11-13, P1: machine-specific, possibly fallback PATH; bare-name Desktop entries
  stay 'not checked'.**
- **Task 3, a labelled approximation:** Desktop's launch env is `HOME`, `LOGNAME`, `PATH`, `SHELL` and `USER`,
  with the `PATH` above, plus the registration's env.
  - It leaves out two of the seven recorded names, `LC_CTYPE` and `__CF_USER_TEXT_ENCODING`, on the inference above
    that the interpreter and the OS add them.
  - The plan says to build the env from the recorded names, so Task 3 labels this env an approximation in
    ENGINEERING.md, and says which two names it drops and why.

### M2

| Question | Observed |
|---|---|
| Did the edit of `command` survive Desktop running? | **Yes**, for the whole 14 minutes |
| Did it survive Desktop quitting? | **Yes**: the entry read back after the quit was the `B-edited` command |
| Did a running Desktop pick up the edit? | **No.** Desktop kept the command it started with, and the dummy never ran with marker `B`. |
| Does a preference change make Desktop write its old copy back? | **Not measured.** No preference was changed. |
| After the dummy was removed, was the config identical to the backup, excluding `preferences`? | **Yes**, and the mode stayed `0600`. |
| Did any preference change? | **No.** The `preferences` objects were also compared separately, key by key, and the helper printed `changed preference keys: []`. |
| Byte-identical? | **No:** 4636 → 4637 bytes, with identical values. The coordinating session's helper re-serialised the JSON when it removed the dummy. |

The backup was deleted after the comparison, and no probe process was left.

**Evidence for a spec-review minor.** The one-byte difference comes from re-serialising the whole file with
identical values. It is evidence for the spec review's minor, "whole-file JSON re-serialisation", and for its
Global Constraint: detect the indent, keep the trailing newline and key order, and use `ensure_ascii=False`. Even
then, the first repair of a file can change its bytes without changing a value. That is not a failure, since Task
2's read-back compares parsed values.

**Branch triggered (D4).**
- **The plan's rule** is "if the edit survives: D4's recommendation becomes (a), for him to confirm".
- **The edit survived a running Desktop and a quit,** but not the case D4 is about. A preference change, or another
  write Desktop makes while running, could still write its old copy back, and that case is unmeasured.
- **Decision.** This is the coordinating session's ruling, and so the AI's, made under P1 (safety):
  - **D4 keeps its safe default (b),** `WRITE_DESKTOP_WHILE_RUNNING = False`.
  - **D4's question to the CINO says what was and was not shown.** An external edit survived 14 minutes of Desktop
    running and its quit. Desktop keeps using its old command until restarted. Whether a preference change, or any
    other Desktop write, overwrites the edit was not measured.
- **What would settle it:** the same run with one preference changed while Desktop runs.

## Go-aheads (Step 2)

The CINO answered *"Both, now (Recommended)"* on 2026-11-13, covering M2 and M5.

- **M2, with M3's Desktop part, in one session.** Approved, run with him by the coordinating session, and recorded
  above. No preference was changed, so the last step below did not happen. It touches the real Claude Desktop config,
  `~/Library/Application Support/Claude/claude_desktop_config.json`:
  - **A backup** beside the config, `claude_desktop_config.json.bak-<14 digits>`, at the same mode. It holds the
    config's secrets.
    - It is deleted once the comparison with the restored config says `identical: yes`.
    - If the comparison says `no`, the backup stays. The AI changes nothing more and tells him which keys differ,
      then deletes it once he has decided.
  - **Add, edit and remove only `csa-plan2-probe`.**
  - **The dummy's log,** in the scratch directory, records the key names of the env Desktop passes, never their
    values, with its `PATH`, home shown as `~`. It also records the working directory and the method names. This is
    M3's Desktop record.

  It also needs four actions from him in Desktop: quit, start, change one named preference, quit. **Restoring that
  preference is his,** the next time he uses Desktop.
- **M5.** Approved, and recorded above. As approved, it launches each of the four standard binaries once under the
  real `HOME`, with its user-scope env passed through `subprocess`'s `env`. It touches:
  - **the real `~/.claude.json`, which holds secrets.** It is read in memory to get each user-scope entry's env, and
    nothing from it is printed or written;
  - **each token path:** a `stat` of the path and its directory, before and after. The defaults are
    `~/.config/csa-zendesk/tokens.json` (or under `XDG_CONFIG_HOME`), `~/.csa_google_workspace/token.json` and
    `token.readonly.json`, and `~/.csa_google_gmail_calendar/token.json`. A registration that carries
    `CSA_ZENDESK_TOKEN_FILE`, `CSA_GW_TOKEN` or `CSA_GGC_TOKEN_PATH` moves its token path, possibly outside `HOME`.
    The stat then follows that path;
  - **what each launched server may itself open at startup:** its token, the Google servers' `client_secret.json`
    (`~/.csa_google_workspace/`, `~/.csa_google_gmail_calendar/`, or wherever `CSA_GW_CLIENT_SECRETS` or
    `CSA_GGC_CLIENT_SECRETS` points), and any file named by `CSA_SKILLJAR_ENV_FILE`;
  - **the network:** remote `host:port` from `lsof` every 100 ms.

  A launch may refresh or rotate a token, as a client's start would. csa-skilljar has no token file, but its launch
  carries its real client credentials and may call Skilljar's token endpoint.
- **M4's and Task 6 Step 1's real launches of a server outside `HOME`:** none needed. M0 placed no server's token
  outside `HOME`.
- **M1's real-config fallback:** not needed. The isolated session reached its config writes without a login.

## What the plan got wrong, or left open

1. **G1 Step 1's Gemini rule is coarser than its purpose.** "If an untrusted empty directory changes what `gemini mcp
   list` … does" is literally met, but the change does not break the probe. Its name match still holds, and the
   change stops a server launch. G1's implementer and its review should decide by the effect, and record why.
   **Also,** an untrusted folder does *not* stop a project `.gemini/settings.json` from shadowing the user entry in
   `mcp list`. The plan's framing ("trust") and the shadowing are separate questions.
2. **Task 3's launch env differs per client, more than one "approximation" covers.** The registered env is not
   what a client passes:
   - Codex drops all but an allowlist of inherited keys;
   - Gemini drops inherited keys whose names look secret;
   - Claude Code passes everything, `PYTHONPATH` and `XDG_CONFIG_HOME` included.

   Task 3's per-client env and A12's interpreter-key rule need this, not one shared approximation.
3. **A scratch `HOME` is not isolation by itself** (M0 caveat). The four servers honour token-path override keys,
   including an inherited `XDG_CONFIG_HOME` under Claude Code and Gemini. Task 6 Step 1 should set them explicitly,
   or strip them.
4. **Claude Code keeps its own backups** of `.claude.json` in `<config dir>/backups/` (`~/.claude/backups/`), at
   mode `0600`, each holding the same secrets. A13's "one shared cap means fewer copies" counts only the `.bak-<14 digits>` files.
5. **Claude Code now sends `server/discover` before `initialize`.** Task 3's `initialize`-only check still matches
   what every client needs, but it is not byte-for-byte what Claude Code sends.
6. **The plan's `script -q`** was replaced by a pseudo-terminal driver, so the session could be given keystrokes;
   the measurement is the same.
