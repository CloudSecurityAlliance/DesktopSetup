# Goals

Read off this repository's record — 23 closed issues, 102 merged pull requests, 167 commits
across 42 active days — rather than written from intention. Every claim links its evidence, so
the next reader can check rather than trust. Method and its blind spot:
[`goals-decay-in-the-direction-that-flatters`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/goals-decay-in-the-direction-that-flatters.md).

## North star

**One command takes a laptop handed over an hour ago to a state where the AI is technically
capable of the organisation's work — so the remaining question is whether it should.** The
reasoning is in [`BUSINESS-CASE.md`](BUSINESS-CASE.md).

"Technically capable" has a specific meaning here, and it is the whole bar: every CSA MCP server
installed, on a deliberate interpreter, current, authenticated as that person, and visible to
the client that will use it. Four of those five fail silently when they fail, which is why most
of the record below is about silence rather than about installation.

## Achieved

Listed because the characteristic decay of a goals file is leaving shipped work filed as
upcoming.

| Goal | Evidence |
|---|---|
| Both platforms reach the same baseline from one command | Ten scripts, five pairs; `tools/check-parity.py` compares `main()` call sequences and reports stale allowlist entries |
| Every CSA MCP server installs and upgrades without being named by the user | Four servers fetched from the private gate repo and enumerated in the plan from one list ([#99](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/99), [#101](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/101) — both PRs) |
| The interpreter is chosen, not inherited | uv as the provider with `--python` on every call, per [DEC-012](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/DECISIONS.md); without it four servers landed on 3.10 by nobody's decision |
| The closing instructions are one ordered list, not five styles across 200 lines | [#110](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/110) — the `CSA_TODO_FILE` ledger; ten records from five sources render as seven items |
| A person can say which version they ran | [#113](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/113) — every script carries a UTC version, it reaches the debug log, and CI refuses a changed script that did not bump it |
| The debug log describes the machine, not just the commands | [#96](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/96), [#121](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/121) — screen output is logged, a state snapshot is taken, and base64 blobs are replaced by a hash and a size |
| The plan names every step that will run | [#80](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/80) — `tools/check-plan-covers-steps.py`, across all six entry points |
| The guards are themselves checked | Eleven checkers in `tools/`, **nine** of which carry a self-test that breaks their own rule on purpose; ten test files in `tests/` (nine Python, one Pester); exit **77** for "could not run here", counted apart from passes. The two without a self-test are the gap, logged in [`TODO.md`](TODO.md) |

That last row is the one that compounds. Each checker exists because a specific mistake shipped,
and the issue number is in the file — so the rules are inherited with the code rather than held
by the author. See [`RACI.md`](RACI.md) on why that is the mitigation for a bus factor of one.

## Near-term

What the open issues actually say, with the reason each is still open:

- **Prose parity has no mechanism** ([#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111)).
  Two mechanisms now exist for *labelled* artifacts — ledger records and plan rows — and both
  found real divergence on their first run. Free prose has no label, and the candidate approach
  needs an allowlist large enough to stop meaning anything.
- **A guard that is wrong in two directions at once**
  ([#136](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/136)). Deliberately not
  fixed: choosing between "parameterise it" and "delete it" needs a real Microsoft Store stub
  measured on a clean machine, and guessing would replace one unexamined rule with another.
- **Node and Python versions diverge between platforms by accident**
  ([#56](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/56)). macOS gets Current,
  Windows gets LTS, and nobody chose that.
- **Thirteen open issues, most of them single-platform.** Indexed in
  [#119](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/119) because they are only
  actionable on a Mac, which is itself the clearest statement of the parity problem.

## Explicitly not goals

Refusals carry more information than ambitions, and each of these was declined with a reason:

- **A separate "MCP servers only" script.** Proposed in
  [#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89) and refused there: the
  plugin work is fast, both come from the same gate-repo access check, and a fourth script per
  platform is more surface for `check-duplication.py` to police for a saving measured in
  seconds. The naming was fixed instead.
- **A Node version manager** (nvm, fnm, volta). Refused in
  [#56](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/56): a version manager
  needs shell-rc initialisation, which is wrong for a `curl | bash` bootstrap, and is what
  created the confusing toolchain split on the authoring machine.
- **Renaming `*-plugins` to something honest.** Considered in
  [#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89) item 3 and left alone:
  the filename is in documented one-liners that fetch `HEAD`, and `main` is the release. The
  strings were fixed and the header says why the name disagrees with the content.
- **Installing PowerShell 7.** The scripts target Windows PowerShell **5.1**, which is what
  Windows 11 ships. Targeting 7 would mean installing a shell in order to run the installer.

## Failure modes

Taken from incidents, not imagination — a premortem sourced from postmortems. Each has happened
at least once.

| Failure | It happened |
|---|---|
| **A check passes about nothing.** Its scope is implicit, so a true sentence about an empty set reads as success | `check-script-versions.py` was commit-scoped, printed `no scripts changed`, and two unbumped scripts failed that same check in CI |
| **A guard does not guard.** It runs, it passes, and it was never able to fail | [#71](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/71), [#72](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/72); and `check-plan-covers-steps.py` shipped covering two of six scripts |
| **One platform silently falls behind.** Whichever was touched last is ahead and nothing notices | [#65](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/65) — Windows users got no MCP servers for a release; [#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111) is the general case |
| **Resilience makes a defect invisible.** Skipping a missing thing is right, and saying nothing about it is not | [#95](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/95) — a missing setup script was skipped with no output at all |
| **`main` ships while red.** Every documented one-liner fetches `HEAD` | [#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132) — red for six commits, because the run was grepped for a string sub-checks also print |
| **The log misdiagnoses.** It records what ran and not what the machine was | [#96](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/96), [#121](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/121) — 82% of the log was base64 |
| **An exit code is read as a state** | Eight occurrences, generalised in [`an-exit-code-is-not-a-state`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/an-exit-code-is-not-a-state.md) |

## How to check this file

Per the method it was written with: **take the three most confident claims above and verify them
from the tracker.** If a claim cannot be verified it is an ambition; if it turns out to be
already achieved, this file has been decaying in the direction that flatters and there will be
more. The blind spot is structural — inference finds revealed preference, so a goal that was
intended and never reached looks identical to one that was never wanted.

Two things this repository's own record cannot tell you, and they are the ones worth asking a
person about:

1. **Whether staff actually use the servers once installed.** Nothing here measures that. The
   record proves provisioning works, not that it mattered.
2. **What the volunteer case needs.** Scope is CSA staff laptops today
   ([`BUSINESS-CASE.md`](BUSINESS-CASE.md)), and the record is silent about people who cannot be
   asked to open a terminal — which is silence meaning "not yet", not "declined".
