# Python 3.14, the standard build, everywhere the installers touch: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (CINO rule B1: always
> subagent-driven) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every
> review runs on the strongest model, `fable` (B12).

**Goal:** a rerun of the installers puts every CSA Python environment they own on a verified CPython 3.14 standard
build: the four MCP server tools and `~/.default_venv`. It repairs any environment whose interpreter is free-threaded,
deleted, the wrong version, or Homebrew-Cellar-pinned. A second rerun changes nothing.

**Architecture:**
- **One resolver per platform names "the CSA Python".** It prefers the uv-managed CPython at `CSA_PYTHON_PREFERRED`,
  accepts a Homebrew/winget `3.14` as fallback, and verifies every candidate by running it.
  - DesktopSetup provisions it and builds `~/.default_venv` on it.
  - The gate repo's `internal-setup` scripts resolve a verified 3.14 the same way, and rebuild a tool only onto a path
    they have verified.
- **Registrations are Plan 2** (#179 Part 2 items 1, 2, 6–8, plus item 5 for whatever venvs registrations point at).
- **Windows halves sit on separate branches until measured on Windows** (R5; decision D5 below).

**Tech stack:** bash 3.2, Windows PowerShell 5.1, uv (kept current), Python test harnesses that extract the shipping
functions, Pester 5.7.1.

**Spec:**
- [#179](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/179), including its 2026-11-10 comment;
- CloudSecurityAlliance-Internal/CSA-Plugins#197;
- #157 (markitdown);
- CINO-Engineering DEC-025's 2026-11-10 amendment (#312).

**Independent spec review (B11), 2026-11-10, on `fable`:** 3 blockers, 8 majors and 8 minors, all folded in below.
Its seven decisions, D1 to D7:
- **D1 is decided by the CINO (2026-11-10): rebuild `~/.default_venv` even when it is active.** He chose the option
  "Rebuild even if active (Recommended)".
- **The venv layout is decided by the CINO (2026-11-10):** *"lets build ~/.default_venv-3.14 and then switch to it
  with zshrc or whatever?"* `~/.default_venv` becomes a relative symlink to a versioned directory,
  `~/.default_venv-3.14`. The AI chose the symlink as the "whatever": `~/.zshrc` only tests `-d`/`-f` on the path,
  and both follow a symlink. It was applied by hand on the CINO's Mac the same day. Task 3 makes it the installer's
  behaviour, and this makes D1 hold by construction: the active venv's real directory never moves.
- **D5 is decided by the CINO (2026-11-10): hold the Windows halves as drafts for a Windows session.** He chose the
  option "Hold as drafts for a Windows session". macOS ships first, and the platforms diverge until a session on
  a real Windows machine runs Tasks 4W and 5W end to end. That divergence is recorded, not hidden: the Windows handoff
  is #184, and Windows document deps are #183.
- **D2, D3, D4, D6 and D7 were decided by the AI** under P1 (safety, then honesty, then correctness), and recorded in
  the PR (P4).
  - **D2:** a 3.15 venv or tool is rebuilt to 3.14, with a warning naming the moved directory.
  - **D3:** the uv-managed 3.14 is always installed, because uv is the one provider (DEC-012).
  - **D4:** `-update` repairs an existing venv but never creates one, and has no Homebrew fallback.
  - **D6:** markitdown goes into `~/.default_venv` here (#157).
  - **D7:** rebuild Cellar-pinned environments the installers own; warn about anything else.
- **D6 reversed, 2026-11-10, after the final whole-branch review (AI's decision, under P1: safety and privacy
  first):** markitdown is **not** installed into `~/.default_venv`, and `pymupdf` is pinned `>=1.24.3,<2`. Both
  brought in onnxruntime (markitdown → magika → onnxruntime; pymupdf 2.x requires it outright), whose official macOS
  and Linux builds from 1.29 on send Microsoft 1DS telemetry by default. The text below is the plan as it was
  executed; ENGINEERING.md (`~/.default_venv`) holds the current rule.

**Repos and branches:**

| Repo | Branch | Tasks |
|---|---|---|
| DesktopSetup | `feat/python-314-standard-build` | 1, 2, 3, 6 (macOS and shared) |
| DesktopSetup | `feat/python-314-standard-build-windows` | 4W |
| CSA-Plugins | `feat/python-314-standard-build` | 5, the `.sh` half |
| CSA-Plugins | `feat/python-314-standard-build-windows` | 5W, the `.ps1` half |

- **Work CSA-Plugins in a fresh clone under the session scratchpad,** never in
  `/Users/kurt/GitHub/CloudSecurityAlliance-Internal/CSA-Plugins`.
- **Start each repo only after its G4 conversion has merged** (DesktopSetup #182, CSA-Plugins #200). Rebase onto it.

## Global Constraints

- **The pins:**
  - `CSA_PYTHON_PREFERRED` / `$CsaPythonPreferred` = `3.14`;
  - `CSA_PYTHON_MIN` / `$CsaPythonMin` = `3.14`;
  - the gate scripts' fallback literal stays `3.14`.
- **Never request `+gil`,** and never infer the build from `uv tool list --show-python`. A build is standard iff
  running it reports `sysconfig.get_config_var('Py_GIL_DISABLED')` falsy. On Windows, see Task 4W, which measures
  that this holds there.
- **No credential, token file or OAuth state is read, moved or deleted.** Tests may point `GH_CONFIG_DIR` at a
  config path; they never read or print its contents (S3).
- **A function that returns a path on stdout writes all other output to stderr.** A test with a chatty stub pins this.
- **bash 3.2:** no `declare -A`, `set -euo pipefail`, `|| x=""` on pipeline assignments, no tail-position
  conditionals.
- **PowerShell 5.1:** no `?:`, `??`, `?.`, `&&`, `||`; every native command through an `Invoke-Native*` wrapper.
  **5.1 strips embedded `"` from native arguments:** in DesktopSetup, run Python via `Invoke-BoundedPython` (a temp
  script); in the gate `.ps1`, pass `-c` code containing no double quotes.
- **`tools/check-parity.py` compares only `main()` steps.** Don't add helpers to `EQUIV`/`PLATFORM_ONLY`, because an
  entry matching no `main()` step fails it. Cross-platform presence of helpers is asserted by tests instead.
- **Duplicated functions and the `CSA_DOC_PY_DEPS` array stay byte-identical.** `check-duplication.py` covers
  functions; `tests/test_python_pins.py` covers the array.
- **Bump the version of every changed script:** `date -u +%Y-%m-%dT%H:%MZ`.
- **uv 0.13.7 creates a `~/.local/bin/python3.14` shim** (measured 2026-11-10), and `uv python list --output-format json`
  may report that shim as `path`. ENGINEERING.md's "uv creates no PATH shims (uv 0.12.10)" is out of date; Task 2
  corrects it. Resolve and verify whatever path uv reports, and don't depend on whether a shim exists.
- **Plan lines name what runs, truthfully,** and keep their labels (`Python`, `uv`, `Preflight deps`,
  `Internal MCP servers`, `pip packages`) for `check-plan-covers-steps.py`.
- **New test files go into `tools/check-all.sh` and CI.** Read the tail and the exit code. The only allowed failures
  on this macOS host are the eight Pester tests from #169.
- **Temp paths come from `tempfile`; tests never touch the real `~`** (S1).
- **Commit subjects state the claim.** Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus (each pinned by a named test)

1. **The interpreter behind a venv or tool was deleted:** a dangling symlink, so `-x` is false and `-L` is true. It
   is treated as **broken**, never as absent. Tests: Task 3 `dangling_interpreter`; Task 5
   `dead_interpreter_routes_force` (where `uv tool list` omits the tool).
2. **PATH `python3` is Homebrew 3.15,** or the active venv's 3.13. Neither becomes the CSA Python. Tests: Task 2
   `path_python_ignored`; Task 3 `uses_csa_python_not_path_python3`.
3. **Only 3.14t is uv-managed.** The resolver installs and returns the standard build. A tool is never
   `--force`-rebuilt onto `--python 3.14` (which can resolve to 3.14t); it is rebuilt onto the verified *path*.
   Tests: Task 2 `only_freethreaded_installed`; Task 5 `rebuild_uses_verified_path`.
4. **Offline: `uv python install` fails.** Nothing is force-rebuilt or moved without a verified replacement
   interpreter, and a working tool is never destroyed. Warn only. Tests: Task 3 `no_csa_python_leaves_venv`;
   Task 5 `offline_no_force`.
5. **Rerun idempotence,** including on a Homebrew-fallback machine: its `opt/` interpreter verifies, so it is not
   flagged every run. Tests: Task 3 `second_run_noop` and `brew_fallback_stable`; Task 5 `second_run_noop`; Task 6
   acceptance.

---

### Task 1: All six entry scripts declare the CSA Python, and a test pins the six copies and `CSA_DOC_PY_DEPS`

**Files:**
- Modify: `scripts/macos-update.sh` and `scripts/macos-plugins.sh` (`CSA_PYTHON_PREFERRED="3.14"`), and
  `scripts/windows-update.ps1` and `scripts/windows-plugins.ps1` (`$CsaPythonPreferred = '3.14'`). Correct the
  comments in all six internal-setup runners that say only `-ai-tools` sets it; the code stays byte-identical.
- Create: `tests/test_python_pins.py`, wired into `tools/check-all.sh` and CI.
- Modify: `ENGINEERING.md` § Duplicated state.

**Interfaces:** Produces the constant in all six scripts.

- [ ] **Step 1: Failing test.** `tests/test_python_pins.py` extracts by regex.
  - `six_scripts_declare_preferred`: each script has exactly one assignment, and all six equal `3.14`.
  - `min_matches_across_platforms`.
  - `doc_deps_copies_agree`: every `CSA_DOC_PY_DEPS=(…)` in `scripts/*.sh` is identical. This passes vacuously with
    a single copy, and bites after Task 3.
  - `--self-test`: mutate one copy to `3.15` and delete another. Both must be reported, by file.
- [ ] **Step 2:** `python3 tests/test_python_pins.py`. Expected: FAIL, naming the four scripts that lack the constant.
- [ ] **Step 3:** add the constants and fix the comments. Bump the four versions.
- [ ] **Step 4:** the test and `--self-test` pass. `./tools/check-all.sh` fails only on #169.
- [ ] **Step 5: Commit:**
  `fix: -update and -plugins name the CSA Python too, so the gate scripts stop guessing it`.

### Task 2 (macOS): one CSA-Python resolver, uv-managed 3.14 standard build, verified by running it

**Files:**
- Modify: `scripts/macos-ai-tools.sh`.
  - Add `python_is_csa_build`, `find_csa_python` and `ensure_csa_python`.
  - Rewrite `install_python`, and `install_uv` (keeping uv current).
  - Point the `Python` and `uv` plan rows and the summary's Python row at the resolver.
  - Repoint `install_doc_python_deps`'s interpreter lookup (line ~1153) from `find_usable_python` to
    `ensure_csa_python`, then delete `find_usable_python`. Task 3 rewrites that function anyway; this keeps Task 2
    self-contained.
- Create: `tests/test_csa_python.py`. Modify `tests/test_version_floors.py` (move its Python cases; keep Node) and
  `tests/test_summary_interpreter.py` (it asserts `find_usable_python` at lines 134 and 146).
- Modify: `ENGINEERING.md` § Install strategy and `README.md` where they describe the old resolver. The new claim:
  the installer always ensures the uv-managed 3.14 standard build. It adds an interpreter and touches nothing else.

**Interfaces** (Task 3 consumes all three):
- **`python_is_csa_build <exe>`:** exit 0 iff `<exe>` runs, `sys.version_info[:2]` equals `CSA_PYTHON_PREFERRED`,
  and `Py_GIL_DISABLED` is falsy. Silent.
- **`find_csa_python`:** prints one path, or exits 1. **It never installs anything,** because the preflight calls it
  before consent. Order:
  1. `uv python find --system --managed-python "$CSA_PYTHON_PREFERRED"`, if it verifies. **`--system` is
     required.** Measured: with `VIRTUAL_ENV` set, `uv python find` without it returns the active venv's Python;
  2. otherwise each path from `uv python list --only-installed --managed-python "$CSA_PYTHON_PREFERRED"
     --output-format json` with `variant == "default"`. Parse it with `/usr/bin/python3 -c` or the step-1
     interpreter, not with awk, because paths may contain spaces;
  3. otherwise `$(brew --prefix)/opt/python@${CSA_PYTHON_PREFERRED}/bin/python${CSA_PYTHON_PREFERRED}`, if it
     verifies.

  Return uv's minor-version path as printed (`cpython-3.14-<platform>`), never a resolved patch directory.
- **`ensure_csa_python`:** runs `uv python install "$CSA_PYTHON_PREFERRED"`, then `find_csa_python`. If that fails,
  it runs `brew install "python@${CSA_PYTHON_PREFERRED}"` and `find_csa_python` again. It prints the path, or warns
  and exits 1. **Only the path goes to stdout.**
- **`install_uv` when uv is present:** `csa_brew_upgrade formula uv "uv"` if Homebrew owns uv; `uv self update` only
  for a standalone install (`uv self update` fails on Homebrew installs). A failure only warns. The `uv` plan row
  says `keep current`.

- [ ] **Step 1: Failing tests,** in `tests/test_csa_python.py`.
  - **Harness.** Extract the real functions. A stub `uv` answers `python find`, `python list … --output-format
    json` and `python install` from a scenario file, and logs each call. Stub interpreters answer the probe. The
    stub `uv`, `brew` and `info` write chatter to stdout.
  - **Cases,** asserting the stdout path (exactly one line) and the exit code:
    - `standard_found`;
    - `only_freethreaded_installed`: install adds the standard build, which is returned; the `t` path never is;
    - `path_python_ignored`: PATH `python3` is a 3.15 stub;
    - `wrong_minor_rejected`;
    - `dead_interpreter_rejected`;
    - `path_with_space`;
    - `brew_fallback_accepted`: uv absent, brew `opt` 3.14 verifies;
    - `uv_install_fails`: exit 1 with a warning, and the caller survives `set -e`;
    - `find_never_installs`: the call log has no `install`;
    - `find_passes_system_flag`: with `VIRTUAL_ENV` set to a fake venv, every logged `uv python find` carries
      `--system`;
    - `stdout_is_only_the_path`: chatty stubs;
    - `windows_twin_exists`: `windows-ai-tools.ps1` on the Windows branch defines `Test-CsaPythonBuild`,
      `Find-CsaPython` and `Install-CsaPython`. When that branch isn't merged yet, print a per-case
      `SKIP (Windows twin pending #184)` line and still exit 0 for the file. Exit 77 would mark the whole file
      skipped in `check-all.sh`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3:** implement. Bump the version.
- [ ] **Step 4:** run the new and the modified tests, `check-plan-covers-steps.py` and `./tools/check-all.sh`. All
  pass, apart from #169.
- [ ] **Step 5: Commit:**
  `feat: macOS provisions and names one CSA Python, a verified 3.14 standard build, never 3.14t or Homebrew's 3.15`.

### Task 3 (macOS): `~/.default_venv` is a symlink to `~/.default_venv-3.14`, built on the CSA Python; a dead, free-threaded, wrong-version or Cellar-pinned target is replaced; markitdown joins it

**Files:**
- Modify: `scripts/macos-ai-tools.sh`.
  - Add `venv_rebuild_reason` and `ensure_default_venv`, and `csa_tool_repairs`, a read-only helper for the plan.
  - `install_doc_python_deps` calls `ensure_default_venv`, then installs `CSA_DOC_PY_DEPS`. Add
    `"markitdown[all]>=0.1.9"` to that array (#157).
  - The `Preflight deps` row names this machine's repair and its reason. The `Internal MCP servers` row lists each CSA
    tool `csa_tool_repairs` reports, and why (#179 item 6).
- Modify: `scripts/macos-update.sh`.
  - A **new `main()` step,** `update_default_venv`, placed **before** `update_pip`: it repairs an existing venv,
    **never creates one, and has no brew fallback** (D4). It then refreshes `CSA_DOC_PY_DEPS`.
  - Delete the venv block at the end of `update_pip`, which its early returns made unreachable.
  - **Copy byte-identically from macos-ai-tools.sh:** `CSA_VENV`, `CSA_DOC_PY_DEPS`, `python_is_csa_build`,
    `find_csa_python`, `ensure_csa_python`, `venv_rebuild_reason`, `ensure_default_venv`.
  - **`macos-update.sh` has no ledger and no `csa_todo_add` function.** The shared `ensure_default_venv` must guard
    the call: `if declare -F csa_todo_add >/dev/null && csa_todo_add …; then :; else <print the to-do>; fi`.
    In `macos-ai-tools.sh` the function exists but returns non-zero when `CSA_TODO_FILE` is unset; the same
    guard handles that. Tests: `update_prints_todo_without_ledger` (function absent) and `ai_tools_prints_todo_when_ledger_unset`
    (function present, `CSA_TODO_FILE` unset).
  - **Add the plan row.**
- Modify: `tools/check-plan-covers-steps.py`. Add a `PLAN_LABEL` entry mapping `update_default_venv` to its plan
  row's label (`Default venv`).
- Modify: `tools/check-parity.py`. The new `main()` step needs a `PER_PAIR`/`PLATFORM_ONLY` entry with this reason:
  "Windows has no `~/.default_venv`: document-pipeline's launchers are bash and probe
  `$HOME/.default_venv/bin/python3`, a POSIX layout; Windows document deps are #183."
- The Windows document-deps issue is #183, and the Windows halves' handoff is #184.
- Modify: `tests/test_venv_replacement.py` and `ENGINEERING.md`.

**Interfaces:**
- **`venv_rebuild_reason <dir>`:** prints one reason and exits 0 when the venv must be rebuilt. Exits 1, silently,
  when it is absent or fine. Reasons, verbatim:
  - `its Python no longer exists`: `bin/python3` is dangling or not executable;
  - `its Python does not run`;
  - `it is Python <X.Y>, not 3.14`;
  - `it is the free-threaded build`;
  - `it is built on a Homebrew Cellar path, which the next brew upgrade deletes`: decided from the **recorded**
    path, not `realpath`. That is the first symlink hop out of the venv (`readlink bin/python3`), or `pyvenv.cfg`
    `home`, literally containing `/Cellar/`. A Homebrew `opt/python@3.14` path is stable across upgrades and is
    **not** Cellar-pinned, even though its realpath is (this supersedes the earlier "realpath" wording). Rebuild
    only when `find_csa_python` returns a non-Cellar path; otherwise warn, and don't rebuild.
- **`ensure_default_venv [--no-create]`:** returns 0 always.
  - **Layout:** `$CSA_VENV` (`~/.default_venv`) is a **relative** symlink to `${CSA_VENV}-${CSA_PYTHON_PREFERRED}`,
    the versioned directory. Old versioned directories are kept for rollback and never deleted.
  - **Build:** `uv venv --seed --python <csa-python> ${CSA_VENV}-3.14` (or `<csa-python> -m venv` when uv is
    absent), onto `ensure_csa_python`'s path (`find_csa_python` under `--no-create`). Then install
    `CSA_DOC_PY_DEPS`.
  - **States it handles:**
    - **A real directory at `$CSA_VENV` (pre-symlink machines):** build the versioned venv first. Then rename the
      directory to `${CSA_VENV}-<X.Y>`, or `-unknown`, adding `-<YYYYmmddHHMMSS>` on a name collision. Then link.
      Read X.Y from `pyvenv.cfg`'s `version_info` (written by uv) **or** `version` (written by `python -m venv`,
      which this installer used until now).
    - **A link whose resolved target is a sound `${CSA_VENV}-3.14`,** relative or absolute: no-op.
    - **A link to an older `${CSA_VENV}-<X.Y>`, or dangling:** build `-3.14` if needed, then flip.
    - **A link the installer didn't make** (its target is not a `${CSA_VENV}-<X.Y>` directory): if the target is
      sound (passes `venv_rebuild_reason`), leave it, with a one-line note. Otherwise build `-3.14`, flip, and name
      the old target in the warning. Never delete it.
    - **A dangling link** also breaks the CINO's `~/.zshrc` stanza: its `python -m venv` fails with `File exists`
      at every shell start. One more reason the installer repairs it.
    - **A `-3.14` target that fails `venv_rebuild_reason`:** build `${CSA_VENV}-3.14.new-$$` **with `uv venv
      --seed --relocatable`**, install the deps **with `uv pip` only, never the venv's `pip`**. Do not call
      `csa_venv_pip_install` for the `.new-$$` build: if `uv pip` fails, delete `.new-$$`, keep the broken target,
      and warn. Then rename the broken one to `${CSA_VENV}-3.14.broken-<ts>`, then rename the
      new one into place. Measured: a venv built at one path and renamed breaks `activate` and every console
      script, because both hardcode the creation path, while `--relocatable` survives the rename. When uv is
      absent (`python -m venv` fallback), rename the broken one away first, then build at the final path and
      accept the brief gap. Fresh builds (no existing `-3.14`) always build at the final path.
  - **Flip atomically:** `ln -sfn <target> ${CSA_VENV}.link-new && mv -h ${CSA_VENV}.link-new ${CSA_VENV}`.
    **`-h` is required.** Measured: plain `mv` onto a link to a directory exits 0, leaves the link unchanged, and
    drops the new link inside the old target. `ln -sfn` overwrites a leftover `.link-new`. A real directory has
    already been renamed away at that point, so the gap is one rename.
  - **`~/.zshrc` is never edited.** The CINO's stanza auto-creates a Homebrew-3.12 venv only when `-d` fails, and
    the link satisfies it.
  - On a rebuild, it warns with the moved path and the names of packages the old venv had beyond
    `CSA_DOC_PY_DEPS` that it did not reinstall. Without a ledger it prints that list; with one, it adds it as a
    to-do.
  - **When `$VIRTUAL_ENV` is the venv (D1):** decide that with `[[ "$VIRTUAL_ENV" -ef "$CSA_VENV" ]]` or
    `-ef` against any `${CSA_VENV}-<X.Y>`, never by string. `activate` records the creation path
    (`~/.default_venv-3.14`), while shells opened before migration hold `~/.default_venv`. Then proceed. The active shell's real directory never moves, so nothing
    dangles. Add the to-do `open a new terminal to use the rebuilt ~/.default_venv` (order 10), or print it when
    there is no ledger.
  - With no CSA Python, it warns and leaves the venv untouched.
- **`csa_tool_repairs`:** for each `$(uv tool dir)/csa-*`, checks `<tool>/bin/python3`. Read-only. Prints
  `<tool>: <reason>` lines, with these reasons:
  - `its Python no longer exists`, when it is dangling;
  - `its Python does not run`;
  - `it is Python <X.Y>`, when not 3.14;
  - `it is the free-threaded build`;
  - `it is on a Homebrew Cellar path`, by the recorded-path rule above.

- [ ] **Step 1: Failing tests,** in `tests/test_venv_replacement.py`.
  - **Real-shaped fixtures:** a `bin/python3` symlink chain imitating `opt/python@3.14 → Cellar/python@3.14/3.14.10`.
  - **Layout cases:** `real_dir_migrated_to_versioned_and_linked`, `link_is_relative`, `link_current_noop`,
    `dangling_link_reflipped`, `broken_314_target_replaced`, `old_versions_kept`, `migration_name_collision`,
    `zshrc_d_test_passes_on_link`, `link_to_older_version_flipped` (the old directory gains no stray entry),
    `absolute_link_to_sound_314_noop`, `users_own_link_sound_left_alone`, `users_own_link_broken_flipped_named`,
    `replaced_target_console_script_runs` (after a broken-target replacement, run a **dependency's** console
    script, e.g. `bin/markitdown --version`, not only seed `bin/pip`. Measured: a script installed by the venv's own
    pip keeps the `.new-$$` shebang and fails, exit 127, while `uv pip` and seed scripts survive the rename),
    `version_key_from_python_m_venv`, `home_with_space`, `virtual_env_creation_path_matches`,
    `cinos_mac_state_noop`. The last is a link to a sound `-3.14` plus a real
    `-3.13` directory: nothing changes.
  - **Cases:** `dangling_interpreter`, `venv_on_315_rebuilt`, `venv_on_313_rebuilt`, `freethreaded_venv_rebuilt`,
    `cellar_with_uv_python_rebuilt`, `cellar_without_uv_python_warns_only`, `brew_fallback_stable`,
    `healthy_314_untouched`, `second_run_noop`, `no_csa_python_leaves_venv`,
    `uses_csa_python_not_path_python3`, `moved_packages_reported`, `active_venv_flipped_with_todo`,
    `builder_fails_keeps_old`.
  - **Through the real entry points:** `update_default_venv_runs_without_outdated_pip`, which drives macos-update's
    `main` step list with no outdated pip packages and asserts the venv was repaired;
    `update_never_creates_venv`.
  - **Plus:** `csa_tool_repairs_lists_freethreaded_tool`.
- [ ] **Step 2:** run. Expected: FAIL.
- [ ] **Step 3:** implement. Remove `install_doc_python_deps`' "some other python3 already satisfies them" early
  return. Bump both versions.
- [ ] **Step 4:** run the test, `check-duplication.py`, `check-parity.py`, `check-plan-covers-steps.py`,
  `test_python_pins.py` and `./tools/check-all.sh`. All pass, apart from #169.
- [ ] **Step 5: Commit:**
  `fix: a rerun rebuilds ~/.default_venv on the CSA Python when its interpreter is gone, free-threaded, the wrong version or Cellar-pinned, and adds markitdown (#157)`.

### Task 4W (Windows, separate branch, held for a Windows run): the same resolver in PowerShell 5.1

**Files:**
- Modify: `scripts/windows-ai-tools.ps1`. Add `Test-CsaPythonBuild`, `Find-CsaPython` and `Install-CsaPython`, all
  using `Invoke-BoundedPython`. Rewrite `Install-Python` and `Install-Uv` (keep it current: `winget upgrade` when
  winget owns uv, else `uv self update`). Update the plan and summary rows. Delete `Find-UsablePython` once orphaned.
- Create: `tests/CsaPython.Tests.ps1`, wired into check-all and CI. Modify `tests/test_summary_interpreter.py`'s
  Windows half.
- Modify: `docs/windows-ai-tools-*.md`, where they describe the old resolver.

**Interfaces:** Task 2's three, with PowerShell names and types: `[bool]`, path-or-`$null`, path-or-`$null`. The
winget fallback is `Python.Python.$CsaPythonPreferred`, and the accepted path is that install's `python.exe`, verified.

- [ ] **Step 1:** Pester cases mirroring Task 2's, plus `probe_survives_quote_stripping`. It asserts the probe's Python
  source is passed as a file, never as a `-c` argument containing `"`.
- [ ] **Steps 2–4:** fail, implement, then run Pester, PSScriptAnalyzer, `check-powershell-native.py` and
  `./tools/check-all.sh`.
- [ ] **Step 5: Commit** on `feat/python-314-standard-build-windows`. Open the PR as a **draft**, with a Windows
  measurement list in its body. Its first item: on Windows, does `sysconfig.get_config_var('Py_GIL_DISABLED')`
  return 0 for the standard build and 1 for free-threaded, and does uv prefer the standard build once both exist?
  It merges only after a Windows session has run it end to end (D5).

### Task 5 (CSA-Plugins, `.sh` half): servers land on a verified standard 3.14; a tool on a dead, free-threaded, wrong-version or Cellar interpreter is rebuilt onto that verified path

**Files** (in the fresh scratch clone):
- Modify the four `internal-setup/csa-*-setup.sh`:
  - **Add `csa_python_path`:** run `uv python install "$csa_py"`, then resolve and verify, exactly as Task 2's
    `find_csa_python` does: `uv python find --system --managed-python "$csa_py"` (**`--system` required**, or an
    active venv's Python comes back), then uv's JSON listing with `variant == "default"`, every candidate probed by
    running it. No Homebrew fallback here. Print the path or nothing.
  - **Add `uv_tool_interpreter_problem <tool-dir>`:** probe the tool's own `bin/python3`, never `<home>/python3`.
  - **Routing:** if a problem exists **and** `csa_python_path` produced a path, warn
    `"<tool> runs on a Python that <reason>; rebuilding it on <path>"` and run
    `uv tool install --force --python "<path>" "$PKG_SPEC"`. This holds even when `uv tool list` omits the tool,
    because its directory exists. If a problem exists **without** a verified path, warn only (offline).
  - **Fresh install and plain upgrade also use the verified path** (`--python "<path>"`; today
    `csa-zendesk-setup.sh` lines 293 and 329 pass `"$csa_py"`). Fall back to `"$csa_py"` only when
    `csa_python_path` produced nothing (offline), with a warning.
  - **After any install, re-run the problem check once.** If it persists, warn, with no loop.
  - **After any rebuild,** add the to-do `restart Claude Code, Claude Desktop, Codex and Gemini` (order 10), or print
    it when there is no ledger.
  - Both helpers are **identical in all four scripts,** marked KEEP IN SYNC.
- Modify: `internal-setup/check-setup-scripts.py`. Add a rule, with a self-test mutation that deletes the call: every
  `.sh` calls `csa_python_path` before its first `uv tool install|upgrade`, and its `--force` condition uses the
  problem result.
- Create: `internal-setup/test-tool-interpreter.py`, wired into `.github/workflows/checks.yml`.

**Interfaces:**
- `csa_python_path`: a path on stdout, nothing else.
- `uv_tool_interpreter_problem <tool-dir>` prints one of:
  - `no longer exists`;
  - `does not run`;
  - `is <X.Y>, not ${csa_py}`;
  - `is the free-threaded build`;
  - `is on a Homebrew Cellar path`: the recorded path (first hop out of `bin/python3`, or `pyvenv.cfg` `home`)
    literally contains `/Cellar/`. An `opt/` path is fine (Task 3's rule);
  - nothing.

- [ ] **Step 1: Failing tests,** in `test-tool-interpreter.py`.
  - **Reason cases:** a stub `uv` and a fake tool dir, with real-shaped symlinks: `healthy`, `home_missing`,
    `freethreaded_tool`, `on_315`, `on_313`, `cellar_home`, `homebrew_opt_home_is_fine` (the review's B2 shape).
  - **Behavioural cases,** for each of the four scripts, run end-to-end with stub `uv`, `gh`, `claude`, `codex`
    and `gemini`, asserting the logged uv commands:
    - `dead_interpreter_routes_force`: the tool dir exists and `uv tool list` omits it;
    - `rebuild_uses_verified_path`: `--python` is the verified path, never `3.14`;
    - `fresh_install_uses_verified_path` and `upgrade_uses_verified_path`;
    - `csa_python_path_passes_system_flag`: with `VIRTUAL_ENV` set, every logged `uv python find` carries `--system`;
    - `offline_no_force`: `uv python install` fails, so no `--force` call;
    - `postcheck_warns_no_loop`: one install call;
    - `second_run_noop`;
    - `restart_todo_after_rebuild`.
  - **Plus:** `helpers_identical_in_four_scripts`.
- [ ] **Step 2:** run, plus `python internal-setup/check-setup-scripts.py --self-test`. Expected: FAIL.
- [ ] **Step 3:** implement in the four `.sh` scripts.
- [ ] **Step 4:** run the tests, the self-test, and DesktopSetup's `check-powershell-native`,
  `check-shell-tail-conditionals`, `check-pipeline-assignments` and `check-line-endings` against `internal-setup/`.
  All pass.
- [ ] **Step 5: Commit:**
  `fix: internal-setup lands every server on a verified standard 3.14 and rebuilds one whose Python is gone, free-threaded, wrong or Cellar-pinned (#197)`.

### Task 5W (CSA-Plugins, `.ps1` half, separate branch, held for a Windows run)

**What:** Task 5's two helpers and its routing, in the four `.ps1` scripts.
- **Probe:** `Scripts\python.exe` of the tool, with `-c` code that contains no `"`.
- **Routing:** a problem makes `$wouldRebuild` true, so the existing lock probe and wait apply. Route explicitly to
  the `--force` branch with the verified path. Fix the wait message so it names the reason, not "must move to
  Python 3.14".

**Test:** `internal-setup/test-tool-interpreter.ps1`, with the same cases. Open the PR as a draft, listing the
Windows measurements. It merges only after a Windows session has run it end to end (D5).

### Task 6: Acceptance on macOS: from this Mac's broken state, one rerun repairs, and a second changes nothing

**Files:**
- Create: `plans/reviews/2026-11-10-python-314-acceptance.md`, scrubbed of secrets, personal data and names.

- [ ] **Step 1: An isolated run.** Point a scratch `HOME`, `UV_PYTHON_INSTALL_DIR`, `UV_TOOL_DIR`,
  `UV_CACHE_DIR` at tempdirs under the scratchpad, and set `UV_TOOL_BIN_DIR=$HOME/.local/bin` (scratch `HOME`),
  because the gate script hardcodes `${HOME}/.local/bin` for the entry point (line 347). Point `GH_CONFIG_DIR` at the real gh
  config **path**, so the gate script gets past its `gh auth status` check (`zd.sh:147`); never read the file.
  Stub `claude`, `codex` and `gemini` away (Plan 2 owns registrations).
  - **Seed:** a free-threaded-only uv 3.14; a dangling 3.13 `~/.default_venv`; a `csa-zendesk` tool on 3.14t.
  - **Run** `install_doc_python_deps`, `update_default_venv` and the branch's `csa-zendesk-setup.sh`.
  - **Assert that run 1 rebuilt both.** The test is worthless if run 1 did nothing.
  - **Run again,** and assert no rebuild.
- [ ] **Step 2: Record:** each environment's `home` before and after, `version_info`, `Py_GIL_DISABLED`, the
  warnings, and the uv command log.
- [ ] **Step 3: The real run on this Mac** is queued for the CINO's go-ahead. It rebuilds four tools off 3.14t under
  running clients (a restart follows), and leaves `~/.default_venv` alone. It was hand-migrated to the `-3.14` link on 2026-11-10 (the old venv is
  `~/.default_venv-3.13`), so the venv part must be a no-op there.
- [ ] **Step 4: Commit:**
  `docs: acceptance evidence — one rerun repairs a dangling venv and a free-threaded tool, a second changes nothing`.

---

**After Task 6:** a whole-branch review per repo (fable); a review brief (A1),
`plans/2026-11-10-python-314-review-brief.md`; and PRs.
- **Order:** the CSA-Plugins `.sh` half first, then DesktopSetup.
- **Windows halves stay drafts until a Windows session runs them (D5).** They're tracked in #184.
- Then Plan 2.
