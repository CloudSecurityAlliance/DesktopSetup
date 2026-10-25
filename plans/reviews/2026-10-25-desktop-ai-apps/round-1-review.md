# Round 1: independent review of #162 at `94e298a`

**Reviewer:** a separate Claude Code agent (`pr-review-toolkit:code-reviewer`). It got the diff, the
requester's asks, and pointers to `ENGINEERING.md` and `docs/desktop-ai-apps.md`, and was asked to
treat every statement in the doc as a claim. It was not given the author's reasoning. It worked
read-only, and ran `check-all.sh`, both test files, shellcheck, and the state functions under
bash 3.2.

**Result:** no blockers, four should-fix, five minor. Its report follows, with local paths made
repo-relative. The author's response to each finding, with how the fix was verified, is in the
review brief's "Review history".

---

**Should-fix**

1. **`scripts/windows-update.ps1` (Update-Winget): a "no", or `NONINTERACTIVE`, still upgrades the
   running app.** `Wait-ForAppExit` returning `$false` only prints a warning; `winget upgrade --all`
   then runs and includes that app. Example: Claude running with an update pending, the person answers
   "n" (or nobody is there), and winget replaces it anyway, right after the script printed "leaving it
   as it is". This contradicts the doc ("Declining leaves the app as it is", "An app is never replaced
   while it runs") and the ask ("wait for the user to exit out fully"). Suggested: `winget pin add` for
   each declined app before `upgrade --all`, removed in a `finally`. *Verified by reading.*
2. **`scripts/macos-ai-tools.sh` (migrate_copilot, install_copilot_desktop): the Homebrew Copilot is
   removed before the new one is downloaded and verified.** The cask's uninstall step is
   `pkgutil: com.microsoft.m365copilot`, so it deletes the app. A failed download, a failed signature
   check, or `sudo -n` failing after a long download in a `NONINTERACTIVE` run would leave no Copilot.
   Separately, if `copilot_app_path` returned nothing while the cask was installed, the wait was skipped
   and the app uninstalled: failing open, since only the unified app's receipt layout had been
   measured. Suggested: download and verify first, then uninstall, then install; check `sudo -n true`
   up front; refuse the migration when no bundle is found. *Cask uninstall step verified with
   `brew info`; the rest by reading.*
3. **`scripts/windows-ai-tools.ps1` (Test-ClaudeLegacyExe): any leftover `AnthropicClaude\Update.exe`
   counts as a live install.** Squirrel's uninstall often leaves `Update.exe` and a `.dead` marker
   behind (the reviewer was recalling this, not observing it). Someone who followed the to-do, and
   whose MSIX reinstall then failed, would see "installed (the old .exe build…)" on every run, and
   Claude Desktop would never be installed. Suggested: also require `app-*\claude.exe` and no `.dead`.
   *Not verified.*
4. **Test gaps.** No test covered `install_copilot_desktop` or `migrate_copilot` (download, signature,
   sudo, cleanup, ordering), the decline path in `Update-Winget`, or `Test-ClaudeLegacyExe` /
   `Test-GeminiDesktop` / `Test-CopilotDesktop`. The two highest-risk findings sit exactly there.

**Minor**

5. **`app_running` and the doc ("Frameworks… which exit with it") were not measured.** On the
   review machine, three `msedge_crashpad_handler` processes ran under `Copilot.app/Contents/Frameworks/`
   with ppid 1. If one outlives Copilot, the wait never ends by itself. Also, `ps -o comm=` is not
   always absolute: a launchd job appeared as `Contents/Library/LoginItems/…`. Suggested: match only
   `Contents/MacOS/`, or measure.
6. **`scripts/windows-update.ps1`: the Gemini pattern `*\Gemini.exe` is a name match**, though the
   code comment and the doc claim matching by path or install location. Suggested: use the uninstall
   entry's `InstallLocation`.
7. **`scripts/macos-ai-tools.sh`: the signature check is a substring search over `pkgutil` output**,
   with no requirement for `Status: signed by a developer certificate issued by Apple`. An unsigned
   package exits 1 and is refused (verified with a locally built package). An untrusted certificate
   with a matching name was not tested. Suggested: `spctl -a -t install` or check the Status line.
8. **The size claims were already stale:** both links now resolve to `Copilot-156.0.4314.41.pkg`, 531 MB
   (arm64) and 576 MB (Intel), against the plan's and doc's "about 400 MB" and "about 410 MB".
   *Verified with a HEAD request.*
9. **Small robustness gaps:**
   - no `trap` cleans up the downloaded package on Ctrl-C;
   - `curl` has no stall timeout;
   - a "no" given after the app had already quit still abandoned the migration;
   - on Windows the plan's upgrade check ran before `winget source update`.
