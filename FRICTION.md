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
[`a-green-check-is-only-evidence-about-what-it-ran-on`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/a-green-check-is-only-evidence-about-what-it-ran-on.md).
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
