# Execution ledger — #179 Plan 1 (Python 3.14 standard build)

Copied from the subagent-driven-development workspace at the end of the build (2026-11-10), as the review history
the review brief cites. Paths into the session's scratch space are replaced with `<session-scratch>` and home
paths with `~`. Every `Ruling:` line is a decision the AI made on the CINO's behalf; every `CINO decision` line is
his.

# SDD ledger — plan: plans/2026-11-10-python-314-standard-build.md

Spec: #179 (body + 2026-11-10 comments), CSA-Plugins#197, #157, DEC-025 2026-11-10 amendment (#312). Reachable.
Scope this run: Tasks 1, 2, 3 (DesktopSetup worktree `scratchpad/ds-py314`, branch feat/python-314-standard-build), Task 5 (CSA-Plugins scratch clone, branch feat/python-314-standard-build), Task 6. Tasks 4W/5W handed to a Windows session (#184, CINO D5).
Models: implementers opus (Task 1 sonnet); every review fable (CINO rule B12).

## Pre-flight scan

| Pair / task | Produces → consumes | Found |
|---|---|---|
| T1 ↔ T2 | T1: `CSA_PYTHON_PREFERRED` in 6 scripts → T2 resolver reads it | consistent |
| T1 ↔ T3 | T1 test `doc_deps_copies_agree` (vacuous) → T3 adds 2nd `CSA_DOC_PY_DEPS` copy | consistent; T3 must keep copies identical |
| T2 ↔ T3 | T2: `python_is_csa_build`/`find_csa_python`/`ensure_csa_python`, repoints `install_doc_python_deps` → T3 rewrites it, copies resolver into macos-update.sh | consistent |
| T2 ↔ T5 | T5 `csa_python_path` mirrors T2 `find_csa_python` (uv-only, `--system`) | consistent (separate repo, no shared code) |
| T3 ↔ T5 | Cellar recorded-path rule shared in wording | consistent |
| T2 ↔ 4W | T2 plan-row change "all six scripts" for the MCP line | **conflict with D5** — see Ruling 1 |
| T6 ↔ T3,T5 | consumes all | consistent |
| T1 self | test cases vs files | consistent |
| T2 self | deletes `find_usable_python` after repoint; `test_summary_interpreter.py` line 146 asserts the Windows name `Find-UsablePython` | see Ruling 2 |
| T3 self | `.new-$$` build uses uv pip only; ledger guard; PLAN_LABEL | consistent |
| T5 self | helpers identical ×4; routing tests | consistent |

Ruling 1: Task 2 changes the "Internal MCP servers" plan row in the three macOS scripts only, not the three Windows ones — the Windows wording would be false until Task 5W lands (D5 holds Windows); the Windows rows change with 5W (#184) — cost if wrong: a Windows plan row stays generic a few days longer.
Ruling 2: Task 2 leaves `Find-UsablePython` and test_summary_interpreter.py's Windows assertion (line 146) untouched; only the macOS `find_usable_python` assertion (line 134) moves — Windows resolver is Task 4W — cost if wrong: none; 4W updates line 146.

## Progress
Task 1: dispatched (base 40ee0d4, implementer sonnet)
Task 1: implemented 57411fd (DONE_WITH_CONCERNS: six scripts bumped, not four — required by check-script-versions since all six runner comments changed; matches brief). Review dispatched (fable).
Task 1: review (fable) Needs fixes — 2 Important (floor check passes with one platform's floor deleted; DEPS_RE misses indented/local copies). Fix round 1 sent to implementer.
Task 1: minor (deferred): a second assignment spelled differently (unquoted/other quote/indented/PS case) is not counted, hiding a later override.
Task 1: minor (deferred): floor self-test doesn't isolate the "differs between scripts" branch.
Task 1: minor (deferred): deps_problems treats first copy as reference (order-dependent blame).
Task 1: minor (deferred): success line prints "all checks passed" (string AGENTS.md warns not to grep).
Task 1: minor (deferred): new constant comments carry history that will age.
Task 1: minor (deferred): runner comments' "never empty here" slightly overclaims (code keeps `:-}`).
Task 1: fix round 1/5 (2 addressed, 0 open; commits 57411fd..d4de4f6)
Task 1: minor (deferred): missing-platform message prefixed with group[0] file name, reads as that file's fault.
Task 1: minor (deferred): DEPS_RE still misses `local -a`/`export`/`typeset -a` prefixes.
Task 1: minor (deferred): MIN_RE/PREFERRED_RE anchored at column 0 (indented/local declaration invisible; platform check would flag missing floor).
Task 1: complete (commits 40ee0d4..d4de4f6, review clean)
Task 2: dispatched (base d4de4f6, implementer opus)
Task 2: implemented 956b798 (DONE_WITH_CONCERNS: MCP row true only after Task 5 lands — plan merges gate first; install_python now warns not aborts when no Python; ensure_csa_python runs twice per ai-tools run → carry to Task 3; test_venv_replacement.py stub renamed). Review dispatched (fable).
Task 2: review (fable) — spec ✅; 1 Important: "Internal MCP servers" row claims "(standard build)", enforced only once CSA-Plugins Task 5 lands.
Task 2: Ruling: keep the plan-mandated wording; HARD MERGE GATE — the CSA-Plugins Task 5 PR merges before the DesktopSetup PR (state it in both PR bodies; check at finish) — because main is the release and the consent line must be true at every commit users run; the plan already orders it so — cost if wrong: if DesktopSetup merged first, the row would overclaim until the gate PR lands.
Task 2: minor (deferred): install_uv runs `uv self update` for every non-Homebrew uv (brief: standalone only) — pip/pipx/cargo/mise uv warns every run.
Task 2: minor (deferred): Homebrew ownership is "brew has a uv formula", not "PATH uv is brew's" — wrong one upgraded when both exist.
Task 2: minor (deferred): find_csa_python spawns /usr/bin/python3 to parse `[]` before consent — CLT install dialog on a Mac without CLT (preflight already runs bare python3; skip parse on empty list).
Task 2: minor (deferred): stub ignores `python list` flags; dropping --only-installed/--managed-python wouldn't fail a test.
Task 2: minor (deferred): ensure_csa_python runs twice per ai-tools run (carried into Task 3 dispatch: pass the path through).
Task 2: minor (deferred): tests/test_summary_interpreter.py:88 comment still names find_usable_python.
Task 2: complete (commits d4de4f6..956b798, review clean after ruling; 0 fix rounds)
Task 3: dispatched (base 956b798, implementer opus)
Task 3: implemented 0acbc92 (DONE_WITH_CONCERNS: deleted python_meets/python_meets_floor + a floor test; +6 helper fns; fresh-build failure also aborts the switch; update row wording may overclaim when no 3.14; mv -h / real-uv cases macOS-only, ubuntu CI skips). Review dispatched (fable).
Task 3: review (fable) Needs fixes — 3 Important (plan row promises rebuild -update can't do with no CSA Python / Cellar-only; CI never runs mv -h or real-uv case → macos-latest job; MCP row lists every csa-* tool, not the setups'). Fix round 1 sent.
Task 3: minor (deferred): torn migrate under -update (kill between mv aside and link) leaves no ~/.default_venv; -update never heals it (ai-tools does).
Task 3: minor (deferred): reinstall hint `$CSA_VENV/bin/python3 -m pip install $extras` unquoted — breaks with a space in HOME.
Task 3: minor (deferred): kill mid-replacement leaves `.new-<pid>` litter; same-second `.broken-<ts>` collision nests the dir.
Task 3: minor (deferred): venv_extra_packages hides packages required by other missing packages (extras-only/mutual deps).
Task 3: minor (deferred): "no Homebrew fallback" wording imprecise — find_csa_python accepts an already-installed brew opt 3.14 (never installs one).
Task 3: minor (deferred): README.md:75 still lists only pyyaml and pymupdf.
Task 3: minor (deferred): to-do title capitalised ("Open a new terminal…") vs brief lowercase.
Task 3: open risk (⚠️): markitdown[all] on Intel Macs (onnxruntime x86_64 wheels) unverified; one unresolvable dep blocks the whole -3.14 build.
Task 3: ⚠️ confirmed as real gap by controller: onnxruntime 1.31.1 has no macOS x86_64 wheels; markitdown requires magika→onnxruntime unconditionally; single-invocation deps install → Intel Mac gets no -3.14 venv. Added as finding 4 to fix round 1 (core deps must-succeed, markitdown best-effort separate call).
Task 3: fix round 1 commits 4693fd6,0bde1fd; CI run 42939492752: venv-macos SUCCESS (real mv -h + real uv), bash/shellcheck FAIL (SC2120 x2 — optional --no-create never passed in ai-tools). Sent back to implementer before re-review.
Task 3: shellcheck fix 97108e7; CI run 42940422524 all green (bash, duplication, powershell, venv-macos). Scoped re-review dispatched (fable).
Task 3: minor (deferred → issue candidate): check-all uses the locally installed shellcheck (0.11.0 here) while CI uses 0.9.0 — SC2120 passed locally, failed CI; pin or print the version.
Task 3: fix round 1/5 (4 addressed + CI SC2120 fixed, 0 open; commits 0acbc92..97108e7; CI 42940422524 green incl. venv-macos)
Task 3: minor (deferred): "The other document deps are installed" sentence in the optional-install warning contradicts a preceding core-install failure (core-fail + optional-fail at caller untested).
Task 3: minor (deferred): on x86_64 every optional failure is attributed to onnxruntime (incl. network) — true on Intel, acceptable.
Task 3: minor (deferred): macos-latest is arm64; Intel path proven only by stubs.
Task 3: minor (deferred): ai-tools + no Python found + Cellar-pinned venv: plan says rebuild; if brew fallback returned a /Cellar/ path the run would leave it (untraced, untested).
Task 3: minor (deferred): fresh Intel build attempts markitdown twice (quiet in build, warning in caller).
Task 3: complete (commits 956b798..97108e7, review clean)
Task 5: dispatched (CSA-Plugins clone scratchpad/csa-plugins-py314, branch feat/python-314-standard-build, base 235277d, implementer opus)
Controller: filed CSA-Plugins#202 by mistake (duplicate of #175, search result not read before create); closed #202, added the 2026-11-10 repro to #175. Lesson: search and create in separate steps.
Task 5: implemented 3aac31a (DONE_WITH_CONCERNS: offline = no rebuild even if a good 3.14 exists; restart to-do macOS-only parity exception under D5; restart to-do now also after husk/sticky rebuilds; bash 3.2 covered locally only — macOS CI in a private repo bills minutes, CINO's call). Controller measured: uv tool upgrade --python <same verified path> → 'Nothing to upgrade', pyvenv.cfg inode/mtime unchanged → no churn. Review dispatched (fable).
Task 5: review (fable) — spec ✅, quality Approved; 1 Important (plan-mandated): offline fallback `uv tool upgrade --python 3.14` rebuilds a wrong-version tool (measured) right after warning it won't; README repeats it.
Task 5: Ruling: problem + no verified path → working tool (wrong version / free-threaded / Cellar): no uv tool call, truthful warning; broken tool (no longer exists / does not run): best-effort reinstall with --python 3.14, warning that it may land on any 3.14 build; no-problem tools keep the fallback upgrade — because the plan's fallback contradicted its own "warn only (offline)" and could land a tool on 3.14t — cost if wrong: an offline machine keeps a wrong-version tool one run longer.
Task 5: minor (deferred): install failure with a standard 3.14 present → no rebuild (defensible, tested); README "when none can be verified" looser than behaviour; "(offline?)" hint misleading (offered as optional in round 1).
Task 5: minor (deferred): offline detected only by install failure; mid-download failure in the new --force branch exits 1 where the old upgrade path was non-fatal (uv resolves before teardown — measured — so the tool survives).
Task 5: minor (deferred): rule 28 doesn't check what --force passes (end-to-end test does).
Task 5: minor (deferred): PATH python3 tried before $first as JSON parser (CLT dialog on a Mac without CLT; unlikely after Homebrew).
Task 5: minor (deferred): dead interpreter with intact site-packages rebuilds without the husk warning (cosmetic).
Task 5: minor (deferred): to-do title lowercase "restart" (verbatim from brief).
Task 5: minor (deferred): CI runs the new test on bash 5 only; bash 3.2 local only (macOS CI on the private repo bills minutes — CINO's call, queued).
Task 5: fix round 1 sent.
Task 5: fix round 1 commit 8f92de4; scoped re-review dispatched (fable).
Task 5: fix round 1/5 (1 addressed, 0 open; commits 3aac31a..8f92de4)
Task 5: minor (deferred, honesty): leave route ends in a false "<pkg> already current: <ver> (Python 3.15)" — no upgrade was attempted; `_left_alone` asserts stderr only. Final review should triage (honesty ranks above wording).
Task 5: minor (deferred): one new comment line overruns the wrap in each script.
Task 5: minor (deferred): README table row for the interpreter-problem case shows only the verified-path form; exceptions are in the paragraph below.
Task 5: complete (commits 235277d..8f92de4 in CSA-Plugins clone, review clean)
Task 6: dispatched (acceptance; DesktopSetup worktree @97108e7 + CSA-Plugins clone @8f92de4; implementer opus)
Task 6: complete (commit 495ad6b; 43/43 assertions with real uv 0.13.7 + real csa-zendesk in isolated scratch HOME; run 1 rebuilt dangling venv + 3.14t tool onto verified 3.14; run 2 no-op; scratch root deleted)
Task 6: finding (load-bearing, for final fix wave): exported UV_PYTHON_PREFERENCE makes uv refuse --managed-python → find_csa_python finds nothing (measured); gate csa_python_path breaks the same way (by code).
Task 6: minor (deferred, honesty): -update plan row "this script installs none" incomplete for CSA members (same run's gate step installs 3.14; next -update repairs).
Ruling: markitdown is removed from the default ~/.default_venv install (and the optional-deps machinery with it, if it becomes dead) — because onnxruntime >=1.29 official macOS/Linux builds ship 1DS telemetry ON by default (persistent device id + event cache under ~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime, uploads to mobile.events.data.microsoft.com; off only with ORT_DISABLE_TELEMETRY=1 before load), and markitdown requires magika→onnxruntime unconditionally; privacy ranks first (P1) and reverses the AI's own D6 — cost if wrong: #157's markitdown waits for a no-telemetry route (vate's magika stub) or the CINO's explicit yes.
Ruling (extends the markitdown ruling): pin `pymupdf<2` in CSA_DOC_PY_DEPS — pymupdf 2.0/2.1 requires onnxruntime unconditionally (telemetry on by default; no macOS x86_64 wheel), pymupdf 1.28.2 has no deps and Intel wheels; document-pipeline uses only core pymupdf — cost if wrong: staff miss pymupdf 2.x features nothing here uses. Filed CSA-Document-Pipeline#198 for its own unbounded pin.
CINO decision (2026-11-10, "Remove it + its cache (Recommended)"): on his Mac, markitdown/magika/onnxruntime/pymupdf-layout/pymupdf4llm removed from ~/.default_venv-3.14, pymupdf → 1.28.2, ~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime deleted (it dated from Sep 22: other software loads onnxruntime — his `markitdown` uv tool on 3.13 carries onnxruntime 1.31.1; not touched, to raise with him).
Final review: dispatched for both repos (fable).
CINO decision (2026-11-10, "Uninstall the uv tool (Recommended)"): his `markitdown` uv tool (3.13, onnxruntime 1.31.1) uninstalled.
Final review DesktopSetup (fable): With fixes — C1 markitdown still installed; C2 pymupdf unpinned (2.1→onnxruntime); C3 update_pip re-upgrades pymupdf to 2.1 in an active CSA venv every run (undoes pin + the CINO's cleanup); I1 Windows Install-DocPythonDeps unpinned pymupdf; I2 "not reinstalled" to-do steers to pymupdf-layout/pymupdf4llm (→onnxruntime); I3 UV_PYTHON_PREFERENCE blinds resolver; I4 -update row incomplete for members; I5 acceptance evidence stale after fixes; I6 decision: existing venvs keep onnxruntime after pin.
Final review CSA-Plugins (fable): With fixes — I1 UV_PYTHON_PREFERENCE blinds csa_python_path + false "(offline?)" warning; I2 leave route ends in false "already current".
Ruling: Windows pymupdf pin (DesktopSetup I1) is applied in this branch despite D5 — it is a dependency-spec string in already-bumped windows-ai-tools.ps1, not the held resolver work, and privacy ranks first — cost if wrong: an unmeasured one-string Windows change (single-quoted, no embedded quotes).
Ruling: I6 — when an existing CSA venv still carries onnxruntime / pymupdf-layout / pymupdf4llm after the pin, warn and add a to-do with the exact `uv pip uninstall` line; never uninstall silently — the person may have installed them on purpose — cost if wrong: telemetry stays on a machine until the person acts on the to-do.
Final fix wave: one fixer per repo dispatched (DesktopSetup: C1-C3, I1-I6 + must-fix minors README.md:75, stub list flags, /usr/bin/python3 on [] guard; CSA-Plugins: I1, I2 + ADR-002 amendment).
CSA-Plugins final fix wave: commits 87e0a5d, 6688f4a, bd986a5 (153 cases pass bash 3.2 + 5.2). Scoped re-review dispatched (fable).
CSA-Plugins final fix wave: re-review clean (3 addressed, no new breakage).
CSA-Plugins PR #203 opened (head bd986a5; merge gate: before DesktopSetup's PR). Release authority (RULES P2) not adopted for DesktopSetup/CSA-Plugins → large, live changes stay open for the CINO's merge go (global CLAUDE.md).
DesktopSetup final fix wave: 10 commits 495ad6b..a6fab67 (C1-C3, I1-I6, README); acceptance re-run 59/59 real uv. Windows pin doesn't hold (windows-update upgrades all; Install-DocPythonDeps never downgrades) → recorded on #184 as do-first privacy item. Scoped re-review dispatched (fable).
DesktopSetup CI run 42964519568 on a6fab67: all green (bash, duplication, powershell, venv-macos).
DesktopSetup final fix wave re-review (fable): all 9 findings ADDRESSED. New: Important — in an active CSA venv, pyyaml + csa-google-workspace are no longer upgraded by anything (update_pip holds them; csa_venv_pip_install's uv path lacks --upgrade); Minor — hold also applies to kept-aside ~/.default_venv-* venvs (mislabel); Minor — pip inherits the here-string stdin in update_pip's loop; Minor — leftovers warning can misattribute a person's own older pymupdf4llm; CI — PyPI resolution guard inside venv-macos should be its own job/workflow + schedule (outage hides mv -h/real-uv results; --self-test expires when upstream drops the dep).
Ruling: one targeted second fix (upgrade gap + pip stdin + resolution guard in its own workflow with a weekly schedule) despite the skill's single-wave rule — because it is a regression on the CINO's own setup and P1 ranks correctness above cost — cost if wrong: one more fixer + scoped re-review.
Parked: hold applies to kept-aside -X.Y venvs — Ruling: conservative (never pymupdf 2), only the label is wrong; can wait.
Parked: leftovers warning may misattribute a person's own older pymupdf4llm — Ruling: wording only, nothing removed; can wait.
Targeted fix: fc1dfc5 (--upgrade on uv path of csa_venv_pip_install, both copies; </dev/null in update_pip loop), e5f5efd (resolution guard → .github/workflows/doc-deps.yml, PR paths + weekly). Scoped re-review dispatched (fable).
Targeted fix re-review (fable): all 3 ADDRESSED, no new breakage; lint CI run 42966669394 green on e5f5efd; doc-deps.yml runs on the PR (can't be dispatched until on main).
Parked: uv `--upgrade` also upgrades transitive deps to newest, unlike the pip fallback — Ruling: CSA venv is CSA's place for these deps; a person's own cap on a shared package isn't honoured — can wait, note in review brief.
Parked: scheduled doc-deps run upkeep (GitHub disables after 60 days of inactivity; failures notify only the cron's last editor) — Ruling: can wait; turning a weekly failure into an issue is a follow-up.
Parked: acceptance doc row C-U2 quotes the pre-fix info line (accurate for 5150947) — Ruling: the doc records what ran at that commit; the review brief says so.
DesktopSetup final review: complete (fix wave + targeted fix, all addressed). Next: review brief + ledger copy, PR, brief check, then the CINO's merge go.
