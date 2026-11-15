# Friction Log

Work that is harder than it should be — for a human or an AI. Low bar: if it feels like an
annoyance, log it. The papercuts worth acting on are the ones that repeat.

| ID | Title | Status | Type | Date |
|----|-------|--------|------|------|
| FRICTION-001 | Every change is made twice and can only be tested once | Accepted | Process overhead | 2026-10-02 |
| FRICTION-002 | Patching a script through a shell heredoc mangles backslashes | Open | AI-inefficient | 2026-10-02 |
| FRICTION-003 | Git Bash cannot exercise the macOS process logic | Accepted | Technology | 2026-10-02 |
| FRICTION-004 | The authoring machine is not a clean machine, in a way that matters | Open | Technology | 2026-10-02 |
| FRICTION-005 | A verification step that fails silently reads as a pass | Open | AI-inefficient | 2026-10-02 |
| FRICTION-006 | `main` is the release, so there is nowhere to be wrong | Accepted | Process overhead | 2026-10-02 |
| FRICTION-007 | macOS shows every account's command lines, so a secret never goes on one | Accepted | Technology | 2026-11-12 |
| FRICTION-008 | Claude Code's narrowest scope wins, so a dead entry outlives the repair of the user's | Accepted | Technology | 2026-11-12 |
| FRICTION-009 | A check that launches a server can act on its account | Open | Process overhead | 2026-11-13 |

---

## FRICTION-001 — Every change is made twice and can only be tested once

**Accepted.** The parity contract means a behavioural change goes into a `.sh` and a `.ps1`
together, and whichever platform the author is sitting at is the only one that can be run. The
other half is written, syntax-checked, and shipped unexercised.

Recurrence is the evidence: **thirteen open issues are single-platform**, enough that
[#119](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/119) exists purely to index
the ones needing a Mac. It is accepted rather than open because the alternative — one
cross-platform implementation — would mean a runtime this bootstrap cannot assume is present.

Partially mitigated: `check-parity.py` proves a step exists on both sides, and two newer checks
compare *labelled* artifacts. The residue is free prose, which is
[#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111).

## FRICTION-002 — Patching a script through a shell heredoc mangles backslashes

**Open.** Four times in one session, editing these files via `python - <<'PY'` from Bash
produced a silently wrong patch, because every layer — heredoc, shell, Python string literal —
takes a turn at the backslashes. The failure mode is the bad one: `assert s.count(old) == 1`
fires with `0`, nothing is written, and the *next* command's output looks like the edit worked.
One instance left a half-replaced line and a Python `SyntaxError` on an adjacent line.

These scripts are unusually full of escapes — `printf '\n\033[1m'`, PowerShell backticks, regex
in string literals — so this is not generic.

**What works:** write the patch to a file with an editor tool and run it, or avoid backslashes
entirely (`chr(10)`, `chr(92)`). Worth promoting to an insight if it recurs outside this repo,
since the general claim is about layered quoting rather than about Bash.

## FRICTION-003 — Git Bash cannot exercise the macOS process logic

**Accepted.** `pgrep` and `ps -o ppid=` are both absent from Git Bash, so the macOS
running-client detection cannot be run at all from the Windows box — not merely untested, but
unrunnable. Its Windows twin was fixed in
[#109](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/109) and the macOS
specification had to be written out in prose for a future Mac session instead of implemented
against a test.

The shell logic *can* be exercised, which is the partial mitigation:
`tests/test_summary_interpreter.py` lifts a span out of `macos-ai-tools.sh` and runs it under
whatever `bash` exists, and says in its own docstring that this is not macOS.

**Update 2026-11-12:** the macOS detection was written on a Mac (TODO.md H1) and now reads image
paths with `lsof` rather than names with `pgrep`. `tests/test_running_clients.py` runs it against
`ps` and `lsof` stubs built from a measured process table, so the logic runs under Git Bash too;
only its live check of the real tools is macOS-only.

## FRICTION-004 — The authoring machine is not a clean machine, in a way that matters

**Open.** On the authoring Windows box, `python` and `python3` both resolve to
`%LOCALAPPDATA%\Microsoft\WindowsApps\`, and they *work* — a real 3.14.3 forwarding to a genuine
install. So `Test-PythonStoreStub`, whose whole premise is that a WindowsApps path is not a real
interpreter, is being exercised against a case where the premise is false, and the resolver
returns a WindowsApps path that it was written to refuse
([#136](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/136)).

This is friction rather than just a bug: it means the one machine available for testing cannot
distinguish the two behaviours the guard exists to separate. Tracked as
[WAITING-FOR-001](WAITING-FOR.md).

## FRICTION-005 — A verification step that fails silently reads as a pass

**Open.** Four instances in one afternoon, each a step taken *to check a fix* that returned a
reassuring answer about something else: a `set -e` control called as an `if` condition, where
`set -e` is suspended, so it could not fail; a mutation harness whose `bash` failed to fork, so
it mutated nothing and reported three misses that were not real; a self-test whose search string
sat inside the line doing the searching; and a run grepped for `all checks passed` — which
sub-checks also print — and piped through `head`, which is how
[#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132) left `main` red for six
commits.

Already generalised at fleet level:
[`a-green-check-is-only-evidence-about-what-it-ran-on`](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/insights/a-green-check-is-only-evidence-about-what-it-ran-on.md).
Kept here because the *project-local* remedy is concrete and partly done: `check-all.sh` now
names the checks that exited 77 rather than only counting them, and `check-script-versions.py`
can see uncommitted work instead of passing about the empty set. What remains is habit — read
the tail and the exit code, never a grep for a string sub-steps also emit.

## FRICTION-006 — `main` is the release, so there is nowhere to be wrong

**Accepted.** Every documented one-liner fetches `HEAD`, and the internal-setup fetch pins no
ref, so a merge ships immediately to the next person who runs it. There is no staging step and
deliberately so — a second branch would need a second set of documented URLs, and the record
shows people already struggle to pick between the scripts that exist
([#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89)).

The cost is real and was paid: `main` carried a red test suite for six commits
([#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132)). The mitigation is
that CI gates the PR and the version check refuses a changed script that did not bump, so a
person can at least say what they ran — which is
[#113](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/113), and is why that issue
existed.

## FRICTION-007 — macOS shows every account's command lines, so a secret never goes on one

**Accepted.** Measured on the CINO's Mac on 2026-11-12: as a standard user, `ps -axo user,args`
printed the full arguments of root's processes and of system daemons. A value put on a command
line is readable by every local account for as long as that process runs. That is the operating
system, not a bug to fix, so the rule is ours: **no secret goes into an argv.**

What it rules out, and where it bit:
- **Client CLI writes.** `claude mcp add -e KEY=value` and `codex mcp add --env KEY=value` take
  env values as arguments, so `scripts/csa-mcp-registrations.py` never uses them. It edits each
  client's own file instead (Plan 2, A3), and passes a launched server's env through
  `subprocess`'s `env`, never its argv.
- **A gate script piping a secret through argv.** `csa-skilljar-setup.sh` passed the
  `claude mcp get` output it parses secret values from as an argument to `python3`. Fixed in
  CloudSecurityAlliance-Internal/CSA-Plugins#213 (Plan 2's G3).

The cost is that every repair is a hand edit of a config file, with its own lock, backup and
read-back, where a CLI call would have been one line.

## FRICTION-008 — Claude Code's narrowest scope wins, so a dead entry outlives the repair of the user's

**Accepted.** Claude Code merges three scopes, and the narrowest wins: a project's local entry
(inside `~/.claude.json`), then an approved `.mcp.json`, then the user's. Measured on 2026-11-12
(M7): `claude mcp get` from a project with a local entry reports, and starts, the local one.

So repairing the user entry did not end #179's incident. On the CINO's Mac the user registration
of csa-zendesk had been corrected, but one project's local entry still pointed at the same dead
checkout venv, carrying a write allowlist. Plan 1's acceptance checked user scope only, and missed
it. Anything that reads "the" registration has to say which scope it read.

Mitigated, not removed:
- **The registration audit reads local scope too,** and reports a dead local entry with a to-do
  (Plan 2, D2): rebuild that checkout's venv, or remove the local entry. It does not re-point it,
  because that would move the checkout's policy onto the release binary.
- **The gate's probes now ask from an empty directory**
  (CloudSecurityAlliance-Internal/CSA-Plugins#215), so a project entry where the installer
  stands cannot stand in for the user's.

## FRICTION-009 — A check that launches a server can act on its account

**Open.** #179 asks for a check that each server answers an MCP `initialize` handshake. To launch
a server with its registered settings is to launch it under the real `HOME`, with its real token
and, for csa-skilljar, the client credentials in its env. A server might refresh a token, rewrite
its token file or call its service before it answers. Then a check run on every rerun would act on
the person's accounts every time.

So the check was measured before it was allowed to run by default (Plan 2, M5, with the CINO's
go-ahead, 2026-11-13). Each of the four servers was launched once, as the check launches it. Its
token files were `stat`ed before and after, never opened, and its network connections were
sampled. **For all four: no token file changed, and no connection was seen.** The record says
what that does not show: work a server does later in a session, a connection shorter than the
sampling interval, and whether a server *read* its token.

It stays open because the decision is not made: `verify` is built and tested, but a rerun
launches nothing until the CINO answers D5. Until then, `verify --run` checks by hand
([ENGINEERING.md → Running it by hand](ENGINEERING.md#running-it-by-hand)). The general cost: a
check that exercises a real integration has to be measured against the real account before it
becomes a default, and that measurement needs a go-ahead.
