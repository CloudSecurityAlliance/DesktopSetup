# Review brief: Gemini and Copilot desktop apps, and the wait before replacing a running app

## What this is

The installer (`macos-ai-tools.sh`, `windows-ai-tools.ps1`) now also installs Gemini Desktop and
Microsoft Copilot, each from the source that keeps it current. The scripts now wait for a running
desktop app to be quit before replacing it: the macOS Copilot cask migration, and
`windows-update.ps1` before `winget upgrade --all`. An app the person will not quit is left as it
is.

State: **open PR, not merged**, after one independent review round whose findings are all fixed.
The macOS half is tested and run against live apps. **The Windows half has never run on Windows**;
its decision logic has passed under Windows PowerShell 5.1 in CI.

## Where everything is

- PR [#162](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/162), branch
  `feat/gemini-copilot-desktop`, base `8799fbb`. Commits:
  - `94e298a`: the feature;
  - `5cd697d`: fixes from the review;
  - then this brief and the session record.
- [`docs/desktop-ai-apps.md`](../docs/desktop-ai-apps.md): the design note. It covers where each
  app comes from and why, the look-alikes that were rejected, the "fully quit" rule, and how the
  wait behaves. Every statement in it is a claim.
- Issue [#161](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/161): the Windows
  checks still owed.
- [`reviews/2026-10-25-desktop-ai-apps/round-1-review.md`](reviews/2026-10-25-desktop-ai-apps/round-1-review.md):
  the independent review, as reported.
- [`resumption-summaries/2026-10-25-desktop-ai-apps.md`](../resumption-summaries/2026-10-25-desktop-ai-apps.md):
  the asks, verbatim, and the session record.

One small PR; the claims table stands in for a review map.

## How to run it

```bash
./tools/check-all.sh                 # read the TAIL and the exit code; expect exit 0, "all checks passed"
python3 tests/test_desktop_apps.py   # expect "all desktop-app checks passed" (36 checks)
pwsh -NoProfile -c 'Import-Module Pester -RequiredVersion 5.7.1; Invoke-Pester tests/DesktopApps.Tests.ps1'   # 28 passed
```

None needs credentials or network. CI runs the Pester suites under pwsh 7 and Windows
PowerShell 5.1. Running the installers themselves installs software: don't, except on a machine
meant for it.

## The bar

The asks are quoted in the resumption summary: install from "the most up to date and updated
version", and "detect them running and wait for the user to exit out fully". The repository's own
rules are in [`ENGINEERING.md`](../ENGINEERING.md) and apply in full:

- `main` is the release.
- Bash 3.2 under `set -euo pipefail`.
- Windows PowerShell 5.1, with every native command wrapped.
- The plan must name what the run does.
- Both platforms change together.
- A changed script bumps its version.

## Claims to verify

| # | Claim | Where | Check | True when |
|---|---|---|---|---|
| 1 | `brew install --cask gemini` is never used; Google's app is `google-gemini` | `install_gemini_desktop` | `grep -nE -- '--cask gemini([^-]\|$)' scripts/*.sh` | one hit, the comment above `get_app_bundle_id` |
| 2 | A `Gemini.app` that is not Google's is neither counted as installed nor installed over | `gemini_desktop_state` | `python3 tests/test_desktop_apps.py` | the two MacPaw checks pass |
| 3 | The Copilot `.pkg` is installed only if Apple-issued, signed as Microsoft's installer, and accepted by Gatekeeper | `install_copilot_desktop`, `COPILOT_SIGNER` | `python3 tests/test_desktop_apps.py` | the forged-certificate and Gatekeeper-rejects checks pass; the signer string matched the real package on 2026-10-24 |
| 4 | **Nothing is removed before its replacement is verified** | `install_copilot_desktop` | same | the order check reads `curl, pkgutil-sig, spctl, brew-uninstall, installer`, and every failure case shows no `brew-uninstall` |
| 5 | The `microsoft-365-copilot` cask installs the former app, with AutoUpdate deselected | `detect_migrations` comment | `brew cat microsoft-365-copilot`; follow `aka.ms/M365CopilotForMac` | version 1.x; the `com.microsoft.autoupdate` choice is set to 0 |
| 6 | macOS counts only the main executable as "running": not launchd agents, not Frameworks | `app_running` | `python3 tests/test_desktop_apps.py` | the agent, crash-handler and look-alike checks pass, and the naive-matcher control fails |
| 7 | The wait never hangs a non-interactive run | `wait_for_app_exit`, `Wait-ForAppExit` | both test files | the "nobody at the keyboard" checks: no sleep, returns not-quit |
| 8 | The wait can always be left interactively, and an app quit during the question counts as quit | same | both test files | the "asks after a minute" and "quit while the question was on screen" checks pass |
| 9 | **An app still running is not replaced on Windows**: held back with a temporary pin, which is always removed; the person's own pin is never touched | `Update-Winget`, `Add-WingetHold` | `Invoke-Pester tests/DesktopApps.Tests.ps1` | the "held back from the upgrade" and "placing the hold" blocks pass, including "releases its pin even when the upgrade itself fails" |
| 10 | Nothing quits an app on the person's behalf | both waits | `git diff 8799fbb...feat/gemini-copilot-desktop -- scripts/ \| grep '^+' \| grep -E 'pkill\|killall\|Stop-Process\|osascript.*quit'` | no output |
| 11 | The plan names every new step and every running app the update expects to ask about | preflights | `python3 tools/check-plan-covers-steps.py`; read `Show-Preflight` in `windows-update.ps1` | passes. The run asks again after refreshing sources, so it can find more than the plan named, never fewer |
| 12 | Claude's old `.exe` build on Windows is detected only as a live install, and is not touched | `Test-ClaudeLegacyExe`, `Install-ClaudeDesktop` | the Pester block for it; read `Install-ClaudeDesktop` | five cases pass; no uninstall or install on that path, a to-do instead |
| 13 | `brew upgrade` never replaces a running desktop app | `update_brew` comment | `brew info --cask claude chatgpt google-gemini \| grep auto_updates` | all three `auto_updates` |
| 14 | Both platforms changed together | parity | `python3 tools/check-parity.py` | passes with the two new `EQUIV` pairs |
| 15 | Windows paths, IDs, and winget's `list`/`pin` behaviour are right on a real machine | `windows-ai-tools.ps1`, `windows-update.ps1` | **#161** | **not yet checkable from here; taken on trust** |

## Review history

**Round 0, the author's own checks during the work (before `94e298a`).**

- Three in-memory mutations of the shipping macOS code were each caught by the check meant for them:
  - counting the whole bundle;
  - dropping the non-interactive early return;
  - trusting the bundle name over the identifier.
- One false failure was a test artefact: `read -p` hides its prompt when stdin is not a terminal.
  The harness now records the question by wrapping the real `confirm`.

**Round 1, an independent review agent (`pr-review-toolkit:code-reviewer`) at `94e298a`.**

It got the diff, the asks and the repo rules, not the author's reasoning. It found no blockers,
four should-fix and five minor ([report](reviews/2026-10-25-desktop-ai-apps/round-1-review.md)).
All were fixed in `5cd697d`:

| # | Finding | Fix | Verified by |
|---|---|---|---|
| 1 | Windows: "no", or nobody there, still let `winget upgrade --all` replace the running app | temporary `winget pin`, released in a `finally`; the person's own pin untouched | Pester "held back" block; a release when the upgrade throws |
| 2 | macOS: the cask (which deletes the app) was removed before the new package was downloaded and verified; an unfound bundle skipped the wait | reordered: quit, download, verify, quit-check again, remove, install. An unfound bundle is refused; `sudo -n` is checked first when non-interactive | 9 order checks; mutation "uninstall before downloading" caught by 5 of them |
| 3 | Windows: a leftover `Update.exe` counted as a live old Claude | requires `app-*\claude.exe` and no `.dead` | 5 Pester cases. Squirrel's leftovers are as documented, not observed (#161 item 2) |
| 4 | Test gaps where the two worst findings were | install-order harness; Pester for the hold, Gemini's location, and old-build detection | test counts: 26 → 36 checks, 10 → 28 tests |
| 5 | Frameworks processes may outlive the app (three crash handlers have ppid 1) | main executable only | confirmed on this Mac 2026-10-25; the "crash handler" check; mutation caught |
| 6 | Gemini on Windows matched by name, contrary to the doc | folder from the uninstall entry; name only as the fallback; the doc says so | 4 Pester cases |
| 7 | Signature check was a name substring | adds the Apple-distribution Status line and `spctl` origin | forged-certificate check; mutation caught |
| 8 | Size claims stale within a day | dated sizes in comments and doc; the plan says "several hundred MB" | HEAD requests, 2026-10-25 |
| 9 | No cleanup on Ctrl-C, no stall timeout, a late "no" abandoned a quit app, plan check before source refresh | fixed cache path (the `EXIT` trap is taken); `--speed-limit/--speed-time`; re-check after "no" on both platforms; re-ask after refresh | "quit while the question was on screen" checks on both platforms |

**CI on `94e298a`:** all six checks green. Both Pester steps ran the new suite: pwsh 7 and
Windows PowerShell 5.1, 43 passed each.

## Known limits and deliberate choices

- **No automated Claude `.exe` → MSIX migration** on Windows. It is unmeasured, and it touches the
  file where CSA servers are registered (#161 item 2).
- **`OpenAI.ChatGPT` (winget) is not used** until it is tested without the Store (#161 item 5).
- **The wait never quits an app for the person**, and asks every minute whether to keep waiting.
  Declining leaves the app as it is: macOS adds a to-do; Windows holds it back from winget for
  that run.
- **Gemini on Windows falls back to a name match** when its uninstall entry names no folder.
  This is deliberate: a false match costs a prompt, while no match would let winget replace an
  open app.
- **No Linux install.** The Linux tier is headless (DEC-013); the status is recorded in the design
  note.
- **The Copilot download is 500+ MB and uses `sudo`.** It is the first non-cask desktop app in the
  macOS script.

## Where the author is least confident

1. **The Windows facts** (#161). The decision logic is tested on 5.1, but every path, ID, and
   winget `list`/`pin` behaviour it rests on came from documents, manifests and memory.
   - Item 1 may be a live defect today: the per-user Claude MSIX may refuse to install without
     admin rights.
   - The pin hold depends on `winget pin list` printing the id for an existing pin. If it does not,
     the person's pin would be treated as absent, and the run would try to add one. The author
     expects (from memory, unmeasured) that `winget pin add` then fails because a pin exists, so
     the run would warn that it could not hold the app back while the person's pin stays in place
     and still protects it. A misleading message, not a lost pin, but #161 item 6 has to confirm it.
2. **The "fully quit" boundary on macOS.** Main-executable-only is the conservative choice. Nobody
   quit each app and watched which processes remained, so a renderer that outlives its app by
   more than the time to the next check would be replaced while dying. That is low risk, but not
   observed.
3. **The wait policy itself.** One minute, then ask; never quit for the person; hold rather than
   replace. It is a judgment call, and Kurt may want it different.
4. **The macOS Copilot install has not run end to end.** The download, the signature and
   Gatekeeper's verdict were checked on the real package. `sudo installer` on a machine without
   Copilot, and the cask migration on a machine with the cask, were not.

## What to assess and how to report

- Correctness under `set -euo pipefail` and PowerShell 5.1.
- Whether the plan and the action can disagree.
- Whether anything is removed or replaced before it is safe to.
- Whether the docs claim more than the code does, or more than was measured.

Report each finding as: severity (blocker / should-fix / minor), file:line, a concrete failure
scenario, a suggested fix, and whether you verified it.
