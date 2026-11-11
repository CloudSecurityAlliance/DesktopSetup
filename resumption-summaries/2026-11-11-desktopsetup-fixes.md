## Task State Summary — 2026-11-11 (DesktopSetup fixes after #179 Plan 1)

**Objective:** fix what was still broken for staff after #179 Plan 1 merged.

Kurt's asks, verbatim:
1. "ok what else do we need to fix in desktopsetup?"
2. "yes lets fix that", in answer to the recommended order: CSA-Plugins #175, ticking C2, #169, then #153.

**Current status: done for the Mac.** The Windows items are queued for the Windows session (#184).

**What changed:**
- **CloudSecurityAlliance-Internal/CSA-Plugins #204, merged (`5d0f79b`); closes #175.** gmail-calendar setup no longer crashes on macOS bash 3.2 when Codex or Gemini are installed. An empty `"${flags[@]}"` under `set -u` used to end the run before Codex, Gemini and Claude Desktop registration.
  - A new static rule, defect 29, flags any bare expansion of a declared array. It was validated against `main`, where it found 8 sites, and has a self-test.
  - Follow-up: CSA-Plugins #205 (the rule misses arrays made by `read -a`).
- **#189, merged (`ab716ef`); closes #169.** `./tools/check-all.sh` now exits 0 on a Mac. The Claude Desktop Pester tests set `$env:TEMP` themselves; it's a test-only change. TODO.md C2 is ticked: #187 had already fixed it.
- **#190, merged (`c934116`); closes #153.** On macOS:
  - "Whoever owns npm updates it": the installers use `npm install -g <pkg>@latest`, not `update -g || install -g`.
  - `macos-update.sh` updates outdated globals but leaves npm and corepack to Homebrew **only when they are Homebrew's own linked copy**. nvm's npm and the unversioned `node` formula's npm are still updated.
  - On Windows, only the installer change shipped.
- **Draft #191, not merged:** the Windows npm updater. It needs Windows measurements, listed on #184.
- **TODO.md's "Start here" row for #168** now names only #163 (Windows host).

**Rulings (the AI's, with what each costs if wrong):**
- **#169 was fixed in the test, not the script,** so the shipped Windows script didn't change. *If wrong:* none.
- **The Windows updater moved out of #190 into draft #191** (safety before speed): on a PC with a globally installed npm, skipping npm could freeze it. *If wrong:* Windows keeps the old updater one more day.
- **npm is skipped only when Homebrew owns it,** a regression the implementer flagged: nvm users' npm would otherwise have stopped updating. *If wrong:* none known.

**How:** each fix had a fresh implementer and an independent review on the strongest model. #190 had two fix rounds, and each round's re-review found a real misclassification. Every PR was merged only after its CI went green.

**Kurt's own Mac:** not affected by #175, because Codex and Gemini aren't installed. Claude Desktop has all four CSA servers.

**Next:**
- **Windows session (#184):** the do-first privacy item, the measurements, #191, then 4W and 5W.
- **After that:** #179 Plan 2 (registration repair), the Gemini → Antigravity research (#171), #156, and #154/#155.

**Not on GitHub:** agent transcripts and scratch clones, which are session-local.
