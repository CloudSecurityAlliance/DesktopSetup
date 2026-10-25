## Task State Summary — 2026-10-25 (session of 2026-10-23 to 2026-10-25)

**Objective:** Install the Gemini and Microsoft Copilot desktop apps beside Claude Desktop and
ChatGPT Desktop on macOS and Windows, from the sources that keep them current, and never replace
one while it is running.

Kurt's asks, verbatim, in order:

1. "can you look at https://gemini.google/desktop/"
2. "ok also can you look at https://www.microsoft.com/en-ca/copilot/download-copilot-app"
3. "I meran the copilot desktop app for windows/macos. Download the Microsoft Copilot app. look
   in Applications locally and you will see the instlled CoPilot app and the Gemini App
   alongside Claude desktop and ChatGPT"
4. "ok I want you to research the best way to install them so we get the most up to date and
   updated version, e.g. some have built in updaters (or do they all?) on both mac os and
   windows and linux"
5. "yes to all those changes, also it means we need to detect them running and wait for the
   user to exit out fully. also make a note of the windows testing needed in an issue."
6. "ok try again,. there was a power outage" (work resumed from the intact working tree)

**Current status:** PR [#162](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/162)
is open and deliberately left open for review: it changes the release scripts, and its Windows
half has never run on Windows. Issue
[#161](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/161) lists the Windows checks.

**What changed:** see the PR description and `docs/desktop-ai-apps.md`. In short: Gemini and
Copilot install steps on both platforms; a wait for an app to be quit before the macOS Copilot
cask migration and before `winget upgrade --all` replaces a running desktop app; detection of
Claude Desktop's old `.exe` build on Windows (to-do only, no migration); a corrected ChatGPT
comment; two new test files; the design note.

**How it was done.** Each app's vendor pages, the winget and Homebrew manifests, and the four
apps installed on Kurt's Mac were read directly (bundle IDs, updater frameworks, launchd jobs,
updater logs, package receipts). Two installers were downloaded to scratch and inspected without
being run: Gemini's Windows offline installer (checksum against the manifest, then its strings
for the update client) and Microsoft's Copilot `.pkg` (signature). Verification:
`./tools/check-all.sh` exit 0; the new tests were mutation-checked (seven in-memory mutations of
the shipping code across two rounds, each caught by its intended check); CI green, including the
new Pester suite under real Windows PowerShell 5.1. An independent review agent read the diff at
`94e298a` and found no blockers, four should-fix and five minor, among them two real bugs:
declining to quit on Windows still let winget replace the app, and the macOS Copilot migration
deleted the old app before the new one was verified. All nine were fixed in `5cd697d`, each with a
test that fails without the fix. Report: `plans/reviews/2026-10-25-desktop-ai-apps/round-1-review.md`;
outcomes: `plans/2026-10-25-desktop-ai-apps-review-brief.md`.

**Key findings:**

- All four apps update themselves on macOS and Windows; none do on Linux. Claude and ChatGPT have
  official Linux builds (apt/dnf repositories); Gemini and Copilot have none.
- In-app updaters (Claude, ChatGPT on macOS) only run while the app is open: Kurt's ChatGPT was
  two releases behind because it had not been opened since 10-20.
- Package-name traps: `brew --cask gemini` is MacPaw's cleaner; `brew copilot` is AWS Copilot;
  the `microsoft-365-copilot` cask installs Microsoft's *former* app with its updater deselected.
- winget's `Anthropic.Claude` is now an MSIX, which Anthropic says fails to install without admin
  rights, and `windows-ai-tools.ps1` refuses to run as admin. **Possibly an existing defect on
  fresh Windows machines** (#161 item 1).
- `OpenAI.ChatGPT` appeared in the winget source on 2026-10-23.

**Decisions made (2026-10-24, by Kurt in chat, recorded in #162 and #161):** add both apps; wait
for a running app to be quit fully; file the Windows testing as an issue. Made by the author
under those: no automated migration of Claude's old `.exe` build until measured; never quit an
app on the person's behalf; ask every minute whether to keep waiting; no wait when
non-interactive; an app still running is left as it is (on Windows, held back from winget with a
temporary pin); nothing is removed before its replacement is verified; the new `OpenAI.ChatGPT`
package is not used until tested.

**Assumptions used:** the Windows process paths and install locations in `windows-update.ps1`
and `windows-ai-tools.ps1` come from documentation, manifests and installer bytes, not from a
Windows machine. Gemini's winget install updating itself is inferred from the update client in
its installer.

**Risks / uncertainties:** the Windows half as a whole (#161), including whether `winget pin`
holds an app back the way it is used. If a Copilot user-session process survives quitting, the
Windows wait would only end through its "keep waiting?" prompt.

**Human input needed:** review and merge #162 (Kurt), and decide whether the wait policy is right
— see the review brief's "least confident" section. Run #161 on a Windows machine.

**Recommended next action:** a Windows session works through #161. Item 1 (Claude MSIX from a
non-elevated prompt) first, because it may already affect new machines.

**Files / artifacts changed:** `scripts/macos-ai-tools.sh`, `scripts/windows-ai-tools.ps1`,
`scripts/windows-update.ps1`, `scripts/macos-update.sh`, `tools/check-parity.py`,
`tools/check-plan-covers-steps.py`, `tools/check-all.sh`, `.github/workflows/lint.yml`,
`tests/test_desktop_apps.py`, `tests/DesktopApps.Tests.ps1`, `docs/desktop-ai-apps.md`,
`README.md`, `ENGINEERING.md`, `plans/2026-10-25-desktop-ai-apps-review-brief.md`,
`plans/reviews/2026-10-25-desktop-ai-apps/round-1-review.md`, this file. Commits `94e298a`
(feature), `5cd697d` (review fixes). Issue #161 (Windows checks, updated after the review).

**Not on GitHub, and why:** the session transcript (it holds tool output) and a local Claude
Code memory note about the package traps (machine-local by design). The downloaded installers
were deleted after inspection.

**Confidence level:** macOS: high for the decision logic (tested, mutation-checked, independently
reviewed, run against the live apps), medium for the Copilot install path itself (download,
signature and Gatekeeper verdict verified on the real package; the `sudo installer` step and the
cask migration have not run end to end). Windows: low until #161 — the logic passes under real
Windows PowerShell 5.1 in CI, but the facts it rests on are not measured.
