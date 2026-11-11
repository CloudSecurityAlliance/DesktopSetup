# Review brief: Python 3.14, the standard build, everywhere the installers touch (#179 Plan 1)

Written 2026-11-10 by the AI that ran the build (Claude Code), for a reviewer who should not take its word for any of
this. Template: CINO-Project-Management-Tools `system/templates/REVIEW-BRIEF.md`.

## 1. What this is

- **The goal.** A rerun of DesktopSetup's macOS installers, and of the CSA gate repo's `internal-setup` scripts they
  run, puts every CSA Python environment the installers own on a **verified CPython 3.14 standard build**:
  - the four MCP-server `uv` tools;
  - `~/.default_venv`, which becomes a relative link to `~/.default_venv-3.14`.
- **What it repairs:** environments whose interpreter is free-threaded, deleted, the wrong version or Cellar-pinned.
  A second run changes nothing.
- **A finding added along the way:** the document dependencies were pulling in Microsoft telemetry, through markitdown
  and pymupdf 2.x requiring onnxruntime. The installer no longer does.
- **State: two open PRs.** **CSA-Plugins #203 merges first**, then the DesktopSetup PR. The Windows halves are held
  for a Windows session (#184).

## 2. Where everything is

| What | Where |
|---|---|
| Spec | DesktopSetup #179 (body + 2026-11-10 comments), CSA-Plugins #197; policy: CINO-Engineering DEC-025, 2026-11-10 amendment (#312) |
| Plan | `plans/2026-11-10-python-314-standard-build.md` (decisions D1–D7 and the venv-layout decision at its top) |
| DesktopSetup branch | `feat/python-314-standard-build`, `40ee0d4..<head>` (the PR names the head) |
| CSA-Plugins branch | `feat/python-314-standard-build`, `235277d..bd986a5`, PR #203 |
| Acceptance evidence | `plans/reviews/2026-11-10-python-314-acceptance.md` (first run 43/43, re-run after the final review 59/59) |
| Execution ledger | `plans/reviews/2026-11-10-python-314-sdd-ledger.md`: every ruling, finding, fix round and deferred minor, in order |
| Windows handoff | #184 (task 1 is to measure; it also carries the live Windows privacy gap); Windows document deps #183 |

## 3. How to review it, in stages

A stage table stands in for a review map: the work is two PRs with one dependency between them.

| Stage | Question | Paths | Claims |
|---|---|---|---|
| A. Resolver | Does the installer always name one verified 3.14 standard build, without installing before consent? | `scripts/macos-ai-tools.sh` (`python_is_csa_build`, `find_csa_python`, `ensure_csa_python`), `tests/test_csa_python.py` | 1–3 |
| B. `~/.default_venv` | Is the link layout safe: no data loss, no dangling link, idempotent, honest plan rows? | `ensure_default_venv` and friends in `macos-ai-tools.sh` / `macos-update.sh`, `tests/test_venv_replacement.py` | 4–7 |
| C. No telemetry | Does any install path still bring onnxruntime? | `CSA_DOC_PY_DEPS`, `update_pip`, `tools/check-doc-deps-resolve.py`, `tests/test_python_pins.py` | 8–9 |
| D. Gate scripts | Are servers rebuilt onto the verified path, and left alone, with an honest message, offline? | CSA-Plugins `internal-setup/csa-*-setup.sh`, `internal-setup/test-tool-interpreter.py`, `check-setup-scripts.py` rule 28 | 10–12 |
| E. End to end | Does one rerun fix this exact broken machine, and a second change nothing? | acceptance doc | 13 |

## 4. How to run it

- **DesktopSetup.**
  - `./tools/check-all.sh`: read the tail and the exit code. On a macOS host, the only failures expected are 8 Claude
    Desktop Pester tests (#169; they need `$env:TEMP`).
  - The focused files: `python3 tests/test_csa_python.py`, `python3 tests/test_venv_replacement.py`,
    `python3 tests/test_python_pins.py --self-test`, `python3 tools/check-doc-deps-resolve.py --self-test`.
  - The last one needs PyPI. The real-uv and BSD-`mv` cases run only on macOS, or in CI's `venv-macos` job.
- **CSA-Plugins.**
  - `python3 internal-setup/test-tool-interpreter.py` (153 cases; on a Mac it uses `/bin/bash` 3.2 by itself, and CI
    runs it on bash 5);
  - `python3 internal-setup/check-setup-scripts.py --self-test` (28 invariants, called "defects" in the checker).
- **CI:** DesktopSetup's `lint.yml` (bash, duplication, powershell, venv-macos) and the new `doc-deps.yml`.
  CSA-Plugins' `checks.yml`.
- **Nothing here needs credentials or money.** The acceptance harness reads only the gh config **path** (its contents
  are never read). It downloads Python and `csa-zendesk` from PyPI into a scratch directory, which it deletes.

## 5. The bar

- **The policy is #179 and DEC-025 (2026-11-10):** 3.14 everywhere, the standard build, never `+gil`, and the build
  verified by running the interpreter.
- **The non-negotiables:**
  - no credential, token or OAuth state is read, moved or deleted;
  - a plan row the user consents to names what runs, truthfully;
  - nothing the user owns is deleted, and old venvs are kept beside the new one;
  - **no install path brings in software with telemetry switched on** (the CINO's order puts safety and privacy first).
- **Platform:** bash 3.2 and `set -euo pipefail` (macOS); PowerShell 5.1 for the one behavioural `.ps1` change.
  Three `.ps1` files change; the other edits are a no-op constant, comments and version bumps (claim 15).

## 6. Claims to verify

| # | Claim | Where | How to check | "True" means |
|---|---|---|---|---|
| 1 | The resolver never returns a free-threaded, non-3.14 or dead interpreter, and never PATH's `python3` | `find_csa_python` | `tests/test_csa_python.py` cases `only_freethreaded_installed`, `wrong_minor_rejected`, `dead_interpreter_rejected`, `path_python_ignored` | pass |
| 2 | Looking up the CSA Python never installs anything, because the preflight runs it before consent | same | `find_never_installs` | no `install` in the stub's call log |
| 3 | An active venv or an exported `UV_PYTHON_PREFERENCE` can't blind the resolver | `--system`, the subshell `unset` | `find_passes_system_flag`, `uv_python_preference_exported`, `flags_dropped_are_caught`, and `real_uv_resolver` in the `venv-macos` job | pass, with real uv |
| 4 | `~/.default_venv` becomes a **relative** link to `~/.default_venv-3.14`; an existing directory is kept under a versioned name and never deleted | `ensure_default_venv` | `tests/test_venv_replacement.py` layout cases; acceptance A-rows | pass; old directory present |
| 5 | The flip works on BSD `mv` (`mv -h`), so the new link is never dropped inside the old target | same | `control_plain_mv_caught`, run on `macos-latest` | pass on macOS |
| 6 | A second run rebuilds nothing | everything | `second_run_noop` (venv: content and call log; gate: call log); acceptance run 2 (inode/mtime) | no `uv venv` or `--force`. The gate still calls `uv tool upgrade --python <path>`, a no-op by measurement ("Nothing to upgrade"), which may touch `uv-receipt.toml`'s mtime |
| 7 | Plan rows match what the run does, in the 15 tested state/mode pairs | `default_venv_plan` | `plan_agrees_with_run` in `tests/test_venv_replacement.py` | pass. **Untested:** ai-tools mode, no Python found, a Cellar-pinned venv, with Homebrew's fallback returning a Cellar path (the ledger defers it as unreachable) |
| 8 | No install path names markitdown, magika or onnxruntime, and pymupdf is pinned `<2` as one argument | `CSA_DOC_PY_DEPS`, both copies, plus the Windows string | `tests/test_python_pins.py` (+ `--self-test`), `doc_deps_cases` in `tests/test_venv_replacement.py` | pass; the plain `test_python_pins.py` fails on 495ad6b (exit 1, 4 problems) |
| 9 | What the dependency set **resolves to** has no onnxruntime | the pin | `tools/check-doc-deps-resolve.py` (`uv pip compile`) | no `onnxruntime`; the self-test proves unpinned pymupdf still drags it in |
| 10 | `-update` never re-upgrades pymupdf to 2.x in an active CSA venv, yet still keeps the other CSA deps current | `update_pip`, `csa_venv_held_names`, `update_default_venv` | `update_pip_leaves_the_pinned_deps_alone_in_the_csa_venv`, `update_pip_preview_agrees`, `upgrade_cases`, all in `tests/test_venv_replacement.py` | pass |
| 11 | **When a verified path exists,** a gate tool with an interpreter problem is rebuilt with `--force --python <verified path>`, never `--python 3.14`, even when `uv tool list` omits it. Without one, see claim 12: a broken tool gets `--python 3.14`, and a sound tool keeps the fallback upgrade | CSA-Plugins `csa_python_path`, routing | `e2e_rebuild_uses_verified_path`, `e2e_dead_interpreter_routes_force`, `e2e_fresh_install_uses_verified_path`, `e2e_upgrade_uses_verified_path` | pass, ×4 scripts |
| 12 | Offline, a working tool with a problem is left untouched and **reported as "left as it is … not checked for updates"**; a broken one gets one honest best-effort reinstall | routing | `e2e_offline_wrong_version_left_alone`, `e2e_offline_no_force`, `e2e_offline_dead_interpreter_best_effort`, `e2e_offline_sound_tool_keeps_fallback_upgrade` (the `_left_alone` helper asserts the message) | pass; "already current" absent |
| 13 | From the CINO's exact broken state, one run repairs both the venv and a 3.14t tool onto the verified 3.14, and a second run rebuilds nothing | all | the acceptance doc's re-run section (real uv 0.13.7, real `csa-zendesk`) | 59/59 |
| 14 | No credential, token or OAuth file is touched | — | **No automated check.** Read the diffs: no change touches credential paths, and the gate scripts' credential code is unchanged | the reviewer's own reading |
| 15 | Windows behaviour is unchanged apart from the pymupdf pin string and the Task 1 constant and comments | `scripts/windows-*.ps1` | `git diff 40ee0d4..<head> -- 'scripts/*.ps1'` | only those lines change, plus version bumps |

## 7. Review history

- **The spec review (B11, fable)** found 3 blockers and 8 majors:
  - check-parity compares only `main()` steps;
  - the Homebrew `opt/` home would have looped;
  - `update_pip`'s early returns made the venv block unreachable.

  All were folded into the plan. Two plan re-reviews followed: one that required 12 fixes, including measured `mv -h`,
  `--relocatable` and `find --system` (plan commits 5dd4b57 and 660feb3), and one with 3 more fixes. Both approved.
- **The per-task reviews (fable)** are in the ledger, task by task: the reviews, every fix round and the CI catches.
  Notable catches:
  - the plan row promised a rebuild `-update` couldn't do;
  - markitdown broke the Intel build;
  - shellcheck 0.9.0 in CI against 0.11.0 locally (#186);
  - the offline fallback's message was false.
- **Acceptance (real uv)** found two things:
  - `UV_PYTHON_PREFERENCE` blinds the resolver;
  - onnxruntime telemetry, which on checking also comes in through pymupdf 2.x.
- **The final reviews (fable).**
  - DesktopSetup: C1–C3 (the telemetry routes) and I1–I6. All were addressed, and the re-review confirmed it.
  - That re-review found a regression the fix introduced: an active CSA venv's pyyaml and csa-google-workspace were no
    longer upgraded by anything. It was fixed in a targeted pass (see the ledger), with a scoped re-review.
  - CSA-Plugins: 2 Important findings, both addressed, re-review clean.

## 8. Known limits and deliberate choices

- **Windows is held** by the CINO's decision D5. It is unmeasured, and **its privacy gap is live**:
  - `Install-DocPythonDeps` installed unpinned pymupdf;
  - `windows-update.ps1` upgrades everything;
  - an existing 2.x is never downgraded.

  All of this is recorded on #184 as the first Windows task.
- **Registrations are Plan 2** (#179 Part 2 items 1, 2, 6–8). This PR repairs interpreters, not client registrations.
- **markitdown is out of the default venv** (#157), until there is a route without telemetry (the magika stub used by vate, the `valid-ai-ted-evidence-based` plugin, CINO-Plugins #144) or
  the CINO says yes.
- **The Intel-Mac path is proven by stubs only** (`macos-latest` is arm64). After the pin, pymupdf 1.28.2 has a real
  Intel wheel.
- **CI covers less than the tests do:** the gate tests run on bash 5 in CI and on bash 3.2 only locally. A macOS job
  in the private repo bills minutes, which is the CINO's call.
- **uv's `--upgrade` also moves the deps' own dependencies to their newest versions** (the pip fallback does not), so a
  person's own cap on a shared package in `~/.default_venv` isn't honoured.
- **The new `doc-deps.yml` workflow has run only as part of this PR,** and its weekly schedule has no alerting beyond
  GitHub's default.
- **The acceptance re-run recorded the code at `5150947`.** Its row C-U2 quotes the info line from before the targeted
  fix.
- **An existing venv keeps onnxruntime until the person acts (ruling I6).** A venv that already holds onnxruntime,
  pymupdf-layout or pymupdf4llm keeps them. The run warns and adds a to-do with the exact uninstall line, and never
  uninstalls silently, so telemetry stays on such a machine until the person acts. A fresh or rebuilt `-3.14` venv
  never has them.
- **A torn migrate under `-update`:** a kill between moving the old directory aside and writing the link leaves no
  `~/.default_venv`. `-update` never creates one, so only the next `macos-ai-tools.sh` run heals it (the window is
  one rename). This bears on claim 4.
- **A mid-download failure in the gate's new `--force` branch exits 1.** The tool is left intact, because uv resolves
  before teardown, but registration is skipped for that run.
- **GitHub disables a scheduled workflow after 60 days of repository inactivity,** which affects `doc-deps.yml`'s
  weekly run.
- **`Find-UsablePython` and the Windows summary assertion are untouched** (ledger Ruling 2): that is Windows work, #184.
- **The deferred minors,** all in the ledger with can-wait reasons: the to-do title case, the leftovers wording, the
  kept-aside venv label, and others.

## 9. Where the author is least confident

1. **The telemetry facts come from upstream documentation and a third-party code reading,** not from captured network
   traffic. The build only verified the dependency metadata.
2. **The real run on the CINO's Mac hasn't happened.** The acceptance used an isolated scratch HOME that reproduced
   his state. His `~/.default_venv` was hand-migrated earlier the same day, and the four tools on his Mac are still on
   3.14t until the installer runs.
3. **The behaviour depends on uv's version.** The resolver relies on `--system`, `--managed-python` and the JSON
   listing, as in uv 0.13.7. `install_uv` keeps uv current, but no minimum uv version is enforced.
4. **The CSA-Plugins scripts go live on every Mac at merge,** and their bash-3.2 coverage is local only.

## 10. What to assess, and how to report

**The dimensions:** correctness, safety (data loss, `set -e` aborts, loops), privacy (telemetry, credentials),
honesty of the plan rows and docs against behaviour, and fitness for a staff Mac.

**For each finding:** severity (blocker, should-fix or minor), location (`file:line`), a concrete failure scenario,
a suggested fix, and whether you verified it by running something.
