# Decision Log — ADR

Technical decisions local to this repository. Cross-project decisions live in
[CINO-PE `DECISIONS.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/DECISIONS.md)
and are referenced here rather than restated.

Status: Proposed | Active | Implemented | Superseded by ADR-NNN | Deprecated

```
ADR-001: main IS the release; there is no staging branch — Active — 2026-10-02
ADR-002: Target Windows PowerShell 5.1, not 7 — Active — 2026-10-02
ADR-003: The *-plugins filenames stay, despite being misleading — Active — 2026-10-02
ADR-004: One source of repo facts; CLAUDE.md and AGENTS.md are pointers — Active — 2026-10-02
ADR-005: A guard encodes the mistake it was written for, and self-tests — Active — 2026-10-02
ADR-006: Exit 77 means "could not run here", counted apart from passes — Active — 2026-10-02
```

Entries are inline rather than one file per decision. csa-skilljar uses a `DECISIONS-ADR/`
directory, which is right at seventeen entries and premature at six — the
[core principle](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/CORE-PRINCIPLE.md)
is that structure follows the experience that fills it. Split this when it becomes hard to read,
not before.

**Dated 2026-10-02 because that is when they were written down, not when they were made.** Each
was a working decision taken earlier and visible in the record; this file is the first place
they are stated. Where the original change is identifiable it is linked.

---

## ADR-001: `main` IS the release; there is no staging branch

**Status:** Active · **Date:** 2026-10-02 (practice since the first documented one-liner)

**Context.** Every documented install path is `curl`/`irm` against
`raw.githubusercontent.com/.../HEAD/scripts/...`, and the internal-setup fetch
(`gh api repos/.../contents/internal-setup/$name`) pins no ref either. A merge is live to the
next person who runs it.

**Decision.** Accept that and make it explicit everywhere, rather than introducing a release
branch or tags.

**Rationale.** A second branch needs a second set of documented URLs, and the record shows people
already struggle to choose between the scripts that exist —
[#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89) is an entire issue about
somebody taking the slow path because the fast one was misnamed. Adding "and which branch" to
that choice makes it worse. The honest alternative is to make `main` trustworthy.

**Rejected alternatives.**
- *A `release` branch the one-liners point at.* Not wrong in general — it is how most software
  ships — but unwarranted here: it doubles the URL surface for a consumer who is pasting one
  line into a terminal, and the thing being protected is a shell script, not a deployed service.
- *Git tags with versioned URLs.* Same objection, plus it puts the burden of knowing the current
  version on the person least able to look it up.

**Consequences, paid.** `main` carried a red test suite for six commits
([#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132)). The mitigations that
follow from this ADR: CI gates every PR, and
[#113](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/113) exists so a person can
say which version they ran. See [FRICTION-006](FRICTION.md).

## ADR-002: Target Windows PowerShell 5.1, not 7

**Status:** Active · **Date:** 2026-10-02

**Context.** Windows 11 ships Windows PowerShell 5.1. PowerShell 7 is an optional install and
this installer does not perform it.

**Decision.** Every `.ps1` here must parse and run under 5.1. CI runs the PowerShell jobs under
both `powershell` (5.1) and `pwsh` (7), as separately named steps.

**Rationale.** The scripts' job is to bootstrap a machine that has nothing yet. Requiring a
shell in order to run the installer that installs things is circular. And the failure mode is
not graceful: 7-only syntax — a ternary, `??`, `?.`, `&&` — fails at **parse** time, so the
whole file is dead rather than one branch of it.

**Rejected alternatives.**
- *Install PowerShell 7 first.* Circular, as above, and adds a reboot-shaped step to a flow
  whose selling point is one command.
- *Write for 7 and document the requirement.* Tried implicitly and it failed silently: a
  behaviour suite in the sibling CSA-Plugins repo ran under `pwsh` while its scripts run under
  5.1, contained a ternary, and therefore **all 41 of its checks had never once executed on the
  runtime they protect** — with CI green throughout.

**Consequences.** `tools/check-powershell-native.py` enforces it, including the four 7-only
syntax forms, with a self-test that breaks each rule on purpose. Non-obvious 5.1 facts are
documented in `ENGINEERING.md`: `Sort-Object` is not stable (`-Stable` is 7-only),
`Set-Content -Encoding utf8` writes a BOM.

## ADR-003: The `*-plugins` filenames stay, despite being misleading

**Status:** Active · **Date:** 2026-10-02 ·
**Change:** [#139](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/139)

**Context.** `macos-plugins.sh` and `windows-plugins.ps1` install plugins **and** every CSA MCP
server. Every string that named them said "plugins", which is why
[#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89) was filed.

**Decision.** Rename the user-facing strings — header, banner, README, prompts — to say "CSA
plugins **and MCP servers**". Leave the filenames alone, and say in each header why the name
disagrees with the content.

**Rationale.** Per ADR-001, the filenames are in documented one-liners that fetch `HEAD`. A
rename breaks every copy of those URLs in a chat log, a bookmark or somebody's notes, and the
forwarder that would keep them working is a seventh and eighth script for
`check-duplication.py` to police. The issue itself called a rename a judgement call that fixing
the strings might make unnecessary.

**Rejected alternatives.**
- *Rename to `*-csa-sync` with a thin forwarder at the old path.* The honest option, and
  reconsider it if the naming still confuses someone after #139. Deferred, not refused.
- *A separate "MCP servers only" script.* Refused outright in #89: the plugin work is fast, both
  halves come from the same gate-repo access check, and the saving is measured in seconds.

## ADR-004: One source of repo facts; `CLAUDE.md` and `AGENTS.md` are pointers

**Status:** Active · **Date:** 2026-10-02 ·
**Context:** [#115](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/115)

**Context.** An `AGENTS.md` was briefly published that was a mechanical `Claude` → `Codex`
substitution of `CLAUDE.md`. It renamed things that were never Claude — *"AI coding CLIs (Codex,
Codex, Gemini)"*, *"`Codex update`"*, *"Codex Desktop"* — and was actively misleading about what
these scripts install, in a public repository. Measured afterwards: `CLAUDE.md` was 368 lines, of
which **36** named Claude at all.

**Decision.** `ENGINEERING.md` holds the repo's facts, agent-neutral, naming each tool by its
real name. `CLAUDE.md` and `AGENTS.md` are short pointers carrying only what is specific to
their reader. `README.md` addresses humans arriving at the repository.

**Rationale.** Roughly 90% of the content belongs to whoever is editing, not to one assistant.
This repository has `tools/check-duplication.py` precisely because duplicated content drifts
silently, and that argument applies to its own documentation at least as strongly — a drifting
instruction file is worse than drifting code, because nothing runs it.

**Rejected alternatives.**
- *Two complete standalone documents.* Reads better for whoever lands first, and that is a real
  benefit. Rejected because it puts two copies of "`main` is the release", the 5.1 hazards and
  the parity contract in one repository, which is the failure
  [#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111) is about.
- *`AGENTS.md` canonical, `CLAUDE.md` the pointer.* Identical content; rejected only because
  `CLAUDE.md` is what Claude Code loads automatically, which argues for it being the cheap file
  rather than the expensive one.

## ADR-005: A guard encodes the mistake it was written for, and self-tests

**Status:** Active · **Date:** 2026-10-02

**Context.** Eleven checkers in `tools/` and ten test files in `tests/`. The temptation with a
growing guard layer is to write general-purpose linting.

**Decision.** A new guard is added only for a mistake that actually shipped, it names the issue
in the file, and it carries a self-test that breaks its own rule on purpose. Where possible it is
validated against the commit where the real defect lived, not only against a synthetic fixture.

**Rationale.** This is [`ZERO-DEFECT.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/ZERO-DEFECT.md)
applied locally, and it is also the bus-factor mitigation in [`RACI.md`](RACI.md): the rules are
inherited with the code rather than held by the author. The self-test requirement is not
ceremony — [#71](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/71) and
[#72](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/72) are both guards that ran,
passed, and could not have failed.

**Known exceptions, which are a gap and not an exemption.** `check-duplication.py` and
`check-paste-safety.py` are the two oldest checkers and carry no self-test. They predate the
rule rather than being excused from it; logged in [`TODO.md`](TODO.md). Nine of eleven comply.

**Rejected alternatives.**
- *An off-the-shelf linter instead.* `shellcheck` and `PSScriptAnalyzer` both run, and neither
  knows that `Sort-Object` is unstable on 5.1 or that a plan must cover what `main()` does. The
  specific rules are the point; the general ones are already covered.
- *Guards without self-tests.* Cheaper per guard and the thing that produced #71 and #72.

**Consequences.** Validating against history has repeatedly found *more* than predicted:
`check-plan-covers-steps.py`, run against the commit before #76, reported the two steps the
issue predicted plus the missing "Internal MCP servers" row in six scripts — the defect found by
hand three weeks later in #99 and #101.

## ADR-006: Exit 77 means "could not run here", counted apart from passes

**Status:** Active · **Date:** 2026-10-02

**Context.** Several checks cannot run on every platform: a PowerShell-only hazard scan on a
Mac, a BOM-byte test under PowerShell 7, a diff-scoped check with no base ref.

**Decision.** Such a check exits **77**. `tools/check-all.sh` counts those separately from
passes, and **names them** in its summary.

**Rationale.** A check that could not run has not passed, and conflating the two makes a gate
look stronger than it is. The naming half was added after a bare `1 check(s) SKIPPED` proved to
be a number people read past.

**Rejected alternatives.**
- *Exit 0 with a printed note.* What most suites do, and it makes "passed" mean two different
  things.
- *Exit non-zero.* Correct in spirit and unusable in practice — it fails the suite for everyone
  on the other platform, and a check that fails during normal work gets commented out
  ([#72](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/72) records that
  reasoning).

**See also.**
[`a-green-check-is-only-evidence-about-what-it-ran-on`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/insights/a-green-check-is-only-evidence-about-what-it-ran-on.md),
practice 2.
