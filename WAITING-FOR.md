# Waiting For

Conditions that need to be true before it makes sense to proceed. Each entry has a **specific,
observable trigger** — without one it is a wish, not a WAITING-FOR.

| ID | Title | Status | Type | Date |
|----|-------|--------|------|------|
| WAITING-FOR-001 | A Windows machine with a real Microsoft Store Python stub | Open | Technology | 2026-10-02 |
| WAITING-FOR-002 | A macOS session | Open | Person/Response | 2026-10-02 |
| WAITING-FOR-003 | A decision on pinning the CI runner image | **CLOSED 2026-10-02** | Person/Response | 2026-10-02 |
| WAITING-FOR-004 | An upstream `node@24` release that moves the keg-only link | Open | Technology | 2026-10-02 |
| WAITING-FOR-005 | A Windows session for the desktop-app work | **CLOSED 2026-10-26** | Person/Response | 2026-10-25 |
| WAITING-FOR-006 | A week of Gemini Desktop on Windows: on or after 2026-11-01 | Open | Time | 2026-10-26 |
| WAITING-FOR-007 | A Windows machine without the Microsoft Store | Open | Technology | 2026-10-26 |

**WAITING-FOR-001 is the one that blocks a filed issue**; 002 is the whole macOS queue. 006 and
007 hold the desktop-app work's remaining checks, whose handoff is
[#168](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/168).
WAITING-FOR-003 closed the day it was opened — see below, and note what it cost to answer: a
measurement, not a discussion.

---

## WAITING-FOR-001 — A Windows machine with a real Microsoft Store Python stub

**Blocks:** [#136](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/136).

`Test-PythonStoreStub` refuses any `python` whose path contains `WindowsApps`, on the premise
that such an entry is the Store stub rather than an interpreter. On the authoring machine the
premise is false — that path is a working Python 3.14.3 forwarding to a real install — so the
guard cannot be observed doing the thing it exists to do. It is also wrong in the other
direction: it inspects only the name `python` while the resolver tries seven, and `python3` from
the same directory is accepted.

**Observable trigger:** a Windows machine where `python` resolves under `WindowsApps` **and**
executing it fails or opens the Microsoft Store rather than printing a version. On such a
machine, `& $cand --version` is the discriminator and the right fix becomes decidable — most
likely deleting the guard, because `Test-PythonMeets` already runs the candidate and is the
honest test.

**Why not guess:** replacing an unexamined rule with another unexamined rule is the failure this
repository keeps logging. See [FRICTION-004](FRICTION.md).

## WAITING-FOR-002 — A macOS session

**Blocks:** thirteen open issues, indexed in
[#119](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/119). The ones that are
purely macOS edits: [#56](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/56)
(pin `node@24` to match the Windows LTS line),
[#78](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/78) (the core app list is
written in six places), [#81](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/81),
[#82](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/82),
[#93](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/93).

Also waiting: the macOS half of
[#100](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/100) ships **unverified on
macOS**, which matters because macOS is where that bug was reported. The four specific things to
confirm are listed in a comment on #119 rather than repeated here.

**Observable trigger:** a session on the Mac. Not a wish — the work is specified, the issues are
written, and #119 exists so nothing has to be rediscovered.

## WAITING-FOR-003 — A decision on pinning the CI runner image — **CLOSED 2026-10-02**

**Decided: accept the migration, do not pin.** `ubuntu-latest` is taken as it comes; whatever
breaks after 2026-10-19 gets fixed then. Reasoning recorded on
[CINO-PE#178](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/issues/178):
the exposure is CI rather than production, a breaking job is visible and attributable, and an
unexpiring pin is the same silent drift that left `actions/checkout` three majors behind until a
deprecation notice happened to be read. The rollover is staged rather than a cutover, so
breakage arrives on some runs before all of them.

**What to watch for**, so a red build is diagnosed in a minute: the four MCP servers gate
coverage at 100% measured on ubuntu, with ~27 `icacls` lines carrying `# pragma: no cover`
because they cannot execute on Linux. A different interpreter or toolchain can move which lines
are reachable, and the symptom is `--cov-fail-under=100` failing on a PR that changed nothing
related. After the 19th, suspect the image before the diff.

Kept rather than deleted, because the useful part is not the answer but what answering cost: the
34-job measurement is what turned this from a worry into a decision.

**Original entry, for the record.** Blocked: nothing yet, and that was the hazard.
[CINO-PE#178](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/issues/178)
holds the measurement: 34 `ubuntu-latest` jobs across six repositories, none pinned, with
`ubuntu-latest` beginning to mean Ubuntu 26 from **2026-10-19**
([runner-images#14748](https://github.com/actions/runner-images/issues/14748)).

Two of this repository's three CI jobs are affected. The wider risk is the four MCP servers,
which gate coverage at 100% *measured on ubuntu* with roughly 27 `icacls` lines carrying
`# pragma: no cover` because they cannot execute on Linux — so the image those decisions were
calibrated against is the one changing, and the Windows job measures no coverage at all.

**Observable trigger, either of:** a decision recorded on CINO-PE#178, **or** 2026-10-19
arriving with no pin in place — at which point the first unrelated red build is the trigger,
which is the outcome the issue exists to avoid. The recommendation there is to pin
`ubuntu-24.04` fleet-wide and add a single `26.04` matrix leg to find out what breaks on a
branch.

**Why it is here and not just there:** a cross-repository change needs an owner, and this file is
the honest place to record that it has none.

## WAITING-FOR-004 — An upstream `node@24` release that moves the keg-only link

**Blocks:** [#81](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/81).

Since [#74](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/74) the macOS side
installs the keg-only `node@24` formula and force-links it. Whether that link survives a real
`brew upgrade` cannot be simulated — it needs an actual version bump to land.

**Observable trigger:** Homebrew ships a new `node@24` patch release, and a `brew upgrade` on a
machine that has the force-link. Then either `node --version` still reports 24.x and the
question is closed, or it does not and the relink needs to move into `macos-update.sh`.

## WAITING-FOR-005 — A Windows session for the desktop-app work — **CLOSED 2026-10-26**

**Happened on 2026-10-25.** A Windows 11 session ran #161's checks under Windows PowerShell 5.1.
It found and fixed four defects on #162, the ChatGPT hold among them, and the Claude install
fixed in #165, then closed #161. What it could not measure is task 4 of
[#168](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/168), with 006 and 007 below.
The entry as it was opened:

**Blocks:** [#161](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/161), the
handoff. Behind it is the confidence of
[#162](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/162), whose Windows half was
written on a Mac.

#162 adds Gemini Desktop and Copilot Desktop to `windows-ai-tools.ps1`, and makes
`windows-update.ps1` wait for a running desktop app to be quit before `winget upgrade --all`
replaces it, holding the app back with a temporary `winget pin` when the person will not quit it.
Its decision logic passes under real Windows PowerShell 5.1 in CI. The facts that logic rests on
are not measured: install paths, uninstall entries, winget's `list --upgrade-available` and `pin`
behaviour, and what keeps running after Quit.

One item may matter before #162 does. winget's `Anthropic.Claude` is now a per-user MSIX, which
Anthropic says will not install without administrator rights, and this installer refuses to run
as Administrator. That is #161 section 1, and it is first in its order for that reason.

**Observable trigger:** a session on a Windows machine. As with WAITING-FOR-002, the work is
specified, and #161 orders it.

## WAITING-FOR-006 — A week of Gemini Desktop on Windows: on or after 2026-11-01

**Blocks:** the one claim about Gemini Desktop on Windows that is inferred, not observed: that a
copy installed through winget (`Google.GeminiDesktop`) **updates itself**. Task 4 of
[#168](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/168).

The inference: the installer's bytes carry Google's update client (`gemini_helper`,
`OmahaUpdateCheckResult`, a "Restart to update" string), and Google's help page describes in-app
updates. If the inference is wrong, winget-installed copies go stale, and `windows-update.ps1`'s
`winget upgrade --all` becomes the only thing updating them. That would still work, but only when
someone runs it.

**Observable trigger:** the calendar reaching 2026-11-01, a week after the 2026-10-25 install of
1.16.0 on the Windows machine #161 was measured on. Then compare the `DisplayVersion` in Gemini's
uninstall entry (`HKCU\…\Uninstall\Gemini`) with the newest `Google.GeminiDesktop` manifest in
`microsoft/winget-pkgs`. Newer than 1.16.0, without anyone running winget, closes it.

## WAITING-FOR-007 — A Windows machine without the Microsoft Store

**Blocks:** [#164](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/164), the no-Store
fallback for ChatGPT Desktop. That is deferred by decision (2026-10-25, #161): the Store is
assumed today.

**Observable trigger:** a Windows 10/11 machine or VM where the Store is removed or blocked by
policy, and a session to run #164's three questions on it.
