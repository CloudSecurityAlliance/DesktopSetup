# Acceptance on macOS: one rerun repairs a dangling venv and a free-threaded tool, a second changes nothing

Task 6 of [`plans/2026-11-10-python-314-standard-build.md`](../2026-11-10-python-314-standard-build.md)
(#179 Plan 1). It was recorded 2026-11-10 by the AI implementing the task. Every statement below is
either measured in the run described here or labelled as not measured.

**Result: 43 of 43 assertions pass** on the final run. An earlier run of the same harness failed four
assertions, all of them wrong expectations in the harness, not defects in the code. They are listed
with their evidence under [Harness corrections](#harness-corrections).

> **Superseded in part, 2026-11-10:** this record describes the branch at `97108e7`. The final
> whole-branch review removed markitdown, pinned pymupdf below 2 and changed two plan rows, so the
> rows below that quote markitdown, an unpinned `pymupdf` or the old `-update` wording no longer
> describe the branch. The harness was re-run against the fixed head: see
> [Re-run after the final review](#re-run-after-the-final-review-2026-11-10), which lists exactly
> which rows are stale.

**Code under test:**
- DesktopSetup `feat/python-314-standard-build` at `97108e7`: `scripts/macos-ai-tools.sh` and
  `scripts/macos-update.sh`.
- CSA-Plugins `feat/python-314-standard-build` at `8f92de4`: `internal-setup/csa-zendesk-setup.sh`.

**Tools:** uv 0.13.7 (Homebrew build), real and unstubbed. `/bin/bash` 3.2.57. macOS 27.2 on arm64.
Python 3.14.10 (standard and free-threaded) and 3.13.18 were downloaded by uv, and `csa-zendesk` 0.3.1
and every document dependency came from PyPI.

## Method

**Isolation.** Everything ran under one scratch root (`$SCRATCH` below), created with `mktemp -d`
in the session scratchpad and deleted at the end. Each world had its own `HOME` (written `~` below),
`UV_PYTHON_INSTALL_DIR`, `UV_TOOL_DIR` and `TMPDIR`, with `UV_PYTHON_BIN_DIR` and `UV_TOOL_BIN_DIR`
set to the scratch `~/.local/bin`. One `UV_CACHE_DIR` under the root was shared between the worlds.

- **PATH:**
  `~/.default_venv/bin:$WORLD/bin:~/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin`.
  - `$WORLD/bin` held only two wrappers. `uv` logged its arguments and ran the real uv; `gh` is
    covered below.
  - `claude`, `codex`, `gemini`, `brew` and `pipx` did not resolve on it (checked). So nothing was
    registered (Plan 2), Homebrew was never reached, and the only non-uv Python on PATH was
    `/usr/bin/python3` 3.9.6.
- **The shell had `~/.default_venv` active,** as the CINO's shells do (his `~/.zshrc` activates it):
  `VIRTUAL_ENV=~/.default_venv`, with its `bin` first on PATH. This makes every `uv python find`
  face the `--system` hazard for real.
- **The scripts are not run whole,** because `main` needs Homebrew and prompts. The functions under
  test were extracted the same way `tests/test_venv_replacement.py` does it, and run under
  `/bin/bash` 3.2 with `set -euo pipefail`. The same assignments were extracted (`CSA_PYTHON_PREFERRED`, `CSA_VENV`,
  `CSA_DOC_PY_DEPS`, `CSA_DOC_PY_DEPS_OPTIONAL`, `CSA_INTERNAL_SETUPS`) and the scripts' own
  output helpers, minus colour.
  - From `macos-ai-tools.sh`: `install_doc_python_deps`, `default_venv_plan` and
    `csa_tool_repairs`, with everything they call.
  - From `macos-update.sh`: `update_default_venv` and `default_venv_plan --no-create`.
- **The gate script ran whole:** `/bin/bash internal-setup/csa-zendesk-setup.sh`, with
  `CSA_NESTED=1 CSA_PYTHON_PREFERRED=3.14`, as `setup_csa_internal_tools` runs it.
- **The to-do ledger:** `CSA_TODO_FILE` was set for the `macos-ai-tools.sh` steps and the gate
  script under them, as `macos-ai-tools.sh` exports it. It was unset for every `macos-update.sh`
  step and for the gate script under `-update`, which keeps no ledger.
- **Assertions** are in the harness, and none is a manual judgement:
  - each interpreter's build is decided by running it and reading
    `sysconfig.get_config_var('Py_GIL_DISABLED')`;
  - "unchanged" means the same `lstat` inode and mtime;
  - uv calls are read from the wrapper's log.

**Deviations from the brief, each with its reason:**

1. **gh runs with the real HOME.** The brief said to point `GH_CONFIG_DIR` at the real gh config
   path, and that alone was not enough: with a scratch `HOME`, `gh auth status` exits 1 (measured),
   because gh finds its token through the login keychain, located from `HOME`. So the `gh` wrapper,
   and nothing else, runs the real gh with the real `HOME` and `GH_CONFIG_DIR`.
   - The gate script made two read-only calls: `gh auth status` and
     `gh api repos/CloudSecurityAlliance-Internal/CSA-Plugins --jq .full_name`.
   - Their output went into the script's `CSA_OUT`, which this run never printed or logged
     (`CSA_LOG` unset). The gh config directory was never read, printed or copied by the harness.
2. **`UV_PYTHON_PREFERENCE=only-managed` was set only for the seed, not for the runs.** uv 0.13.7
   refuses `--managed-python` alongside a Python preference, and the environment variable counts:
   `error: the argument '--managed-python' cannot be used with '--python-preference'` (measured).
   Both resolvers under test pass `--managed-python`, so under the variable they find nothing (see
   [Observations](#observations-not-assertions-from-the-brief)). The isolation it was meant to
   give is kept three other ways:
   - the PATH above;
   - the code under test only ever discovers interpreters with `--managed-python`, and otherwise
     names explicit paths;
   - **X1** asserts that every `--python` path used, and every `pyvenv.cfg` `home` recorded, lies
     inside the scratch root.
3. **`install_python` was not run.** It calls `ensure_brew_in_path`, which would put Homebrew on
   PATH. So run 1's `install_doc_python_deps` met a machine with no standard 3.14, and
   `ensure_default_venv` reached `ensure_csa_python` itself. On a real `macos-ai-tools.sh` run, the
   Python step would have installed it a few steps earlier. That is why run 1's plan row begins "on
   the Python 3.14 the Python row installs".

## The seeded state (the CINO's Mac before the 2026-11-10 repairs)

Seeded identically in both worlds, with uv commands going through the logging wrapper:

```
uv python install 3.14t                                   # the only uv-managed 3.14: free-threaded
uv python install 3.13
<uv 3.13>/bin/python3.13 -m venv ~/.default_venv          # as this installer built it until now
~/.default_venv/bin/python3 -m pip install pyyaml cowsay  # cowsay: a package nothing else needs
uv python uninstall 3.13                                  # its interpreter deleted: bin/python3 dangles
uv tool install --python 3.14 csa-zendesk[server]         # UV_PYTHON_DOWNLOADS=never, preference only-managed
```

The last line is how the servers really reached 3.14t (#197): with only `cpython-3.14+freethreaded`
installed, `--python 3.14` took it. The seed checks (A-S1..3, B-S1..3) assert that state.

| Environment | Kind | `home` | `version` | `bin/python3` | Runs as (`X.Y` and GIL-disabled flag) |
|---|---|---|---|---|---|
| `~/.default_venv` | directory | `$UV_PYTHON_INSTALL_DIR/cpython-3.13-macos-aarch64-none/bin` | `3.13.18` (`version`, from `python -m venv`) | dangling link | does not exist |
| csa-zendesk tool | directory | `$UV_PYTHON_INSTALL_DIR/cpython-3.14+freethreaded-macos-aarch64-none/bin` | `3.14.10` (`version_info`) | present | `3.14 1` (free-threaded) |

- **uv-managed Pythons:** `cpython-3.14.10+freethreaded-macos-aarch64-none` only. uv lists it twice,
  the managed install and its `~/.local/bin` shim.
- **`uv tool list --show-python`:** `csa-zendesk v0.3.1 [CPython 3.14.10]`. It says the same after
  the tool is rebuilt on the standard build, which is why nothing infers the build from it (Global
  Constraints).

## World A: `macos-ai-tools.sh`'s order, run twice

Each run, in order. Plan rows first, then the three steps.

```
ai.sh  default_venv_plan                  # the Preflight deps row, macos-ai-tools.sh
upd.sh default_venv_plan --no-create      # the Default venv row, macos-update.sh
ai.sh  csa_tool_repairs                   # the Internal MCP servers row's repairs
ai.sh  install_doc_python_deps            # macos-ai-tools.sh, ledger set
upd.sh update_default_venv                # macos-update.sh, no ledger
/bin/bash csa-zendesk-setup.sh            # CSA_NESTED=1 CSA_PYTHON_PREFERRED=3.14, ledger set
```

### Run 1

**Plan rows, as printed:**

- `macos-ai-tools.sh`: "on the Python 3.14 the Python row installs: build ~/.default_venv-3.14 on
  Python 3.14, move the directory ~/.default_venv to ~/.default_venv-3.13 (its Python no longer
  exists), link ~/.default_venv to .default_venv-3.14; install/refresh pyyaml pymupdf
  csa-google-workspace (then markitdown[all]>=0.1.9, best effort) in it"
- `macos-update.sh`: "leave ~/.default_venv as it is (its Python no longer exists): there is no
  Python 3.14 standard build installed, and this script installs none - run macos-ai-tools.sh to
  repair it; nothing is installed into it"
- Tool repairs: "csa-zendesk: it is the free-threaded build"

**Warnings and to-dos printed** (stderr; info lines omitted unless they carry a decision):

```
# install_doc_python_deps
==> Ensuring Python 3.14 (uv-managed, standard build)
Installed Python 3.14.10 in 1.76s
 + cpython-3.14.10-macos-aarch64-none (python3.14)
==> Building ~/.default_venv-3.14 on $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14
Warning: ~/.default_venv now links to .default_venv-3.14; the directory that was there (its Python no longer exists) is kept at ~/.default_venv-3.13
Warning: Not reinstalled from ~/.default_venv-3.13: cowsay
# update_default_venv: no warning; stdout "==> Refreshing document deps (...) in ~/.default_venv"
# csa-zendesk-setup.sh
Warning: csa-zendesk runs on a Python that is the free-threaded build; rebuilding it on $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14
==> csa-zendesk already current: 0.3.1 (Python 3.14.10)
==> Claude Code not found; csa-zendesk is installed but not registered
```

**Ledger records added by run 1:**

```
43  Reinstall what the previous ~/.default_venv had: cowsay   (terminal: ~/.default_venv/bin/python3 -m pip install cowsay)
10  Open a new terminal to use the rebuilt ~/.default_venv
10  restart Claude Code, Claude Desktop, Codex and Gemini
20  Sign in to Zendesk                                          (no token in the scratch HOME; not a repair)
```

**After run 1:**

| Environment | Kind | `home` | `version_info` / `version` | `bin/python3` | Runs as |
|---|---|---|---|---|---|
| `~/.default_venv` | relative link to `.default_venv-3.14` | `$UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin` | `3.14` | present | `3.14 0` |
| `~/.default_venv-3.14` | directory | `$UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin` | `3.14` | present | `3.14 0` |
| `~/.default_venv-3.13` | directory (the old one, kept) | `$UV_PYTHON_INSTALL_DIR/cpython-3.13-macos-aarch64-none/bin` | `3.13.18` (`version`) | dangling link | does not exist |
| csa-zendesk tool | directory | `$UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin` | `3.14.10` | present | `3.14 0` |

- **uv-managed Pythons:** `cpython-3.14.10-macos-aarch64-none` (default) beside
  `cpython-3.14.10+freethreaded-macos-aarch64-none`.
- Both environments record uv's **minor-version** directory `cpython-3.14-macos-aarch64-none`, never
  the patch directory, which a patch upgrade replaces. Their interpreters resolve into
  `cpython-3.14.10-macos-aarch64-none`.
- uv writes `version_info = 3.14`, with no patch, for a venv built on that directory.

### Run 2

**Plan rows:** both scripts print "install/refresh pyyaml pymupdf csa-google-workspace (then
markitdown[all]>=0.1.9, best effort) in ~/.default_venv (Python 3.14, standard build)". The tool
repairs row prints nothing.

**Warnings:** none from any of the three steps. Stdout was only the deps lines, and the gate's
`csa-zendesk already current: 0.3.1 (Python 3.14.10)` and its sign-in banner. The ledger gained only
a second "Sign in to Zendesk". That comes from this harness reusing one ledger across both runs: the
real installer renders and removes its ledger at the end of every run.

**Stamps:** unchanged, in inode and mtime:
- the link;
- `~/.default_venv-3.14/pyvenv.cfg` and `bin/python3`;
- the tool's `pyvenv.cfg` and `bin/python3`;
- both directories, inode and mtime.

The one difference: the tool's `uv-receipt.toml` kept its inode and its exact content, and its mtime
moved. The gate's plain `uv tool upgrade --python <verified path> csa-zendesk` answers "Nothing to
upgrade" and still rewrites the receipt in place. This was measured separately: same inode, same
bytes, new mtime, with `pyvenv.cfg` and `bin/python3` untouched. That is not a rebuild (A-N2b).

### uv command log, world A

Every uv call made by the seed and the code under test, as the wrapper logged it.
- The harness's state listings (`uv python list`, `uv tool list`) called uv directly, so they are
  not here.
- Four `[obs-preference]` lines, made for Observation 1 after run 2, are left out.

```
[seed] uv python install 3.14t
[seed] uv python install 3.13
[seed] uv python list --only-installed 3.13 --output-format json
[seed] uv python uninstall 3.13
[seed] uv tool install --python 3.14 csa-zendesk[server]
[run1-plan] uv python find --system --managed-python 3.14
[run1-plan] uv python list --only-installed --managed-python 3.14 --output-format json
[run1-plan] uv python find --system --managed-python 3.14
[run1-plan] uv python list --only-installed --managed-python 3.14 --output-format json
[run1-plan] uv tool dir
[run1-ai] uv python find --system --managed-python 3.14
[run1-ai] uv python list --only-installed --managed-python 3.14 --output-format json
[run1-ai] uv python install 3.14
[run1-ai] uv python find --system --managed-python 3.14
[run1-ai] uv venv --quiet --seed --python $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14 ~/.default_venv-3.14
[run1-ai] uv pip install --quiet --python ~/.default_venv-3.14/bin/python3 pyyaml pymupdf csa-google-workspace
[run1-ai] uv pip install --quiet --python ~/.default_venv-3.14/bin/python3 markitdown[all]>=0.1.9
[run1-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf csa-google-workspace
[run1-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 markitdown[all]>=0.1.9
[run1-update] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf csa-google-workspace
[run1-update] uv pip install --quiet --python ~/.default_venv/bin/python3 markitdown[all]>=0.1.9
[run1-gate] uv tool list
[run1-gate] uv tool dir
[run1-gate] uv tool dir
[run1-gate] uv tool dir
[run1-gate] uv python install 3.14
[run1-gate] uv python find --system --managed-python 3.14
[run1-gate] uv python list --only-installed --managed-python 3.14 --output-format json
[run1-gate] uv tool dir
[run1-gate] uv tool install --force --python $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14 csa-zendesk[server]
[run1-gate] uv tool list
[run1-gate] uv tool dir
[run2-plan] uv tool dir
[run2-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf csa-google-workspace
[run2-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 markitdown[all]>=0.1.9
[run2-update] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf csa-google-workspace
[run2-update] uv pip install --quiet --python ~/.default_venv/bin/python3 markitdown[all]>=0.1.9
[run2-gate] uv tool list
[run2-gate] uv tool dir
[run2-gate] uv tool dir
[run2-gate] uv tool dir
[run2-gate] uv python install 3.14
[run2-gate] uv python find --system --managed-python 3.14
[run2-gate] uv python list --only-installed --managed-python 3.14 --output-format json
[run2-gate] uv tool dir
[run2-gate] uv tool dir
[run2-gate] uv tool upgrade --python $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14 csa-zendesk
[run2-gate] uv tool list
[run2-gate] uv tool dir
```

What to read in it:
- **Run 1 rebuilt both** (`uv venv`, `uv tool install --force`), each onto
  the path the resolver verified. Neither was rebuilt onto the version `3.14`.
- **Run 2 rebuilt neither.** No `uv venv`, no `--force`, no `uv tool install`.
- **Run 2's `uv python install 3.14`** is the gate's deliberate every-run no-op.
- **Before run 1's `uv python install 3.14`, `find_csa_python` found nothing.** The only 3.14 uv had
  was free-threaded, and it runs and verifies every candidate. That is why run 1's plan row deferred
  to "the Python 3.14 the Python row installs". What `uv python find` printed in that state was not
  captured.

## World B: `macos-update.sh`'s order, from the same seed

`macos-update.sh` runs `update_default_venv` and later `setup_csa_internal_tools`. Here the gate
script met a uv whose only 3.14 was free-threaded.

```
upd.sh default_venv_plan --no-create
upd.sh update_default_venv
/bin/bash csa-zendesk-setup.sh            # no ledger, as under -update
```

**Plan row:** "leave ~/.default_venv as it is (its Python no longer exists): there is no Python 3.14
standard build installed, and this script installs none - run macos-ai-tools.sh to repair it;
nothing is installed into it".

**The run agreed.** It printed:

```
Warning: ~/.default_venv, a directory from before the versioned layout (its Python no longer exists), needs a Python 3.14 standard build to build on, and there is no Python 3.14 standard build - left as it is
Warning: Not refreshing the document deps: ~/.default_venv cannot take them (its Python no longer exists)
```

- **Nothing installed:** its uv calls were only `uv python find --system --managed-python 3.14` and
  the JSON listing.
- **Nothing moved:** `~/.default_venv` kept its inode and mtime, with a byte-identical `pyvenv.cfg`
  and no `-3.14` beside it.
- **Wording:** the plan row is what tells the person to run `macos-ai-tools.sh`. The run's own
  warning says why it left the venv, but does not repeat that advice.

**The gate script, from a 3.14t-only uv:** installed the standard build and rebuilt the tool onto it.

```
[b-gate] uv python install 3.14
[b-gate] uv python find --system --managed-python 3.14
[b-gate] uv python list --only-installed --managed-python 3.14 --output-format json
[b-gate] uv tool install --force --python $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14 csa-zendesk[server]
Warning: csa-zendesk runs on a Python that is the free-threaded build; rebuilding it on $UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14
==>   csa-zendesk was rebuilt: restart Claude Code, Claude Desktop, Codex and Gemini to pick it up.
```

The tool's `bin/python3` then reported `3.14 0`. With no ledger, the restart instruction was
printed.

## Assertions

| ID | Claim | Result |
|---|---|---|
| A-S1 | seeded: every uv-managed 3.14 is free-threaded, and there is no 3.13 | PASS |
| A-S2 | seeded: `~/.default_venv` is a real directory on 3.13 whose `bin/python3` dangles | PASS |
| A-S3 | seeded: the csa-zendesk tool's own `bin/python3` reports 3.14 free-threaded (`Py_GIL_DISABLED=1`) | PASS |
| A-P1 | run-1 plan row (`macos-ai-tools.sh`) names the build, the move to `-3.13` and why | PASS |
| A-P2 | run-1 plan: `csa_tool_repairs` lists csa-zendesk as the free-threaded build | PASS |
| A-V1 | `~/.default_venv` is now a RELATIVE link to `.default_venv-3.14` | PASS |
| A-V2 | `~/.default_venv/bin/python3` runs, 3.14, `Py_GIL_DISABLED` falsy | PASS |
| A-V3 | `-3.14`'s interpreter resolves into uv's standard 3.14 install (not `+freethreaded`); `version_info` 3.14[.x] | PASS |
| A-V4 | core document deps import in `~/.default_venv`: `yaml`, `pymupdf`, `csa_google_workspace` | PASS |
| A-V5 | markitdown imports in `~/.default_venv` (arm64, so expected) | PASS |
| A-V6 | the old dangling venv is kept, renamed to `~/.default_venv-3.13` (`pyvenv.cfg` byte-identical, cowsay still in it) | PASS |
| A-V7 | run 1 installed uv's 3.14 (`ensure_csa_python`) and built `-3.14` with `uv venv --seed --python <path>`; that path verifies as standard 3.14 | PASS |
| A-V8 | with `VIRTUAL_ENV` set, every `uv python find` in run 1 carried `--system` | PASS |
| A-V9 | run 1 warned: the link flipped, the old directory kept at `-3.13` and why, and what was not reinstalled (cowsay, which the new venv indeed lacks) | PASS |
| A-V10 | run 1 (the shell had `~/.default_venv` active) added the open-a-new-terminal to-do, and the reinstall-cowsay to-do | PASS |
| A-V11 | `update_default_venv` on the just-repaired venv: no `uv venv`, no move, link and `-3.14` unchanged; it only refreshes deps | PASS |
| A-V12 | `install_doc_python_deps` exited 0 and never fell back to pip (uv did every install) | PASS |
| A-T1 | the csa-zendesk tool's `bin/python3` reports 3.14 standard (`Py_GIL_DISABLED` falsy) | PASS |
| A-T2 | the tool's interpreter resolves into uv's standard 3.14 install, not `+freethreaded`; `version_info` 3.14[.x] | PASS |
| A-T3 | the gate rebuilt it with `uv tool install --force --python <verified path>`, never `--python 3.14` | PASS |
| A-T4 | the gate warned why it rebuilt: free-threaded, rebuilding on `<path>` | PASS |
| A-T5 | the restart to-do fired once (ledger, as under `macos-ai-tools.sh`) | PASS |
| A-T6 | the rebuilt tool imports `csa_zendesk` and its `csa-zendesk-mcp` entry point is in `~/.local/bin` | PASS |
| A-T7 | the gate script exited 0 and skipped registration (no claude/codex/gemini on PATH) | PASS |
| A-N0 | run-2 plan rows: the venv is fine (both scripts) and `csa_tool_repairs` lists nothing | PASS |
| A-N1 | run 2 ran no `uv venv`, no `--force` and no `uv tool install` | PASS |
| A-N2 | run 2 replaced nothing: same inode and mtime for the link and for `-3.14`'s and the tool's `pyvenv.cfg` and `bin/python3`; same inode for both directories | PASS |
| A-N2b | run 2: the tool's `uv-receipt.toml` has the same inode and byte-identical content (its mtime may move: `uv tool upgrade` rewrites it in place) | PASS |
| A-N3 | run 2 printed no repair (no rebuild/link/kept/runs-on-a-Python-that line) | PASS |
| A-N4 | run 2 added no restart and no open-a-new-terminal to-do | PASS |
| A-N5 | run 2: the old `-3.13` is still there, byte-identical `pyvenv.cfg` | PASS |
| A-N6 | run 2: all three steps exited 0 | PASS |
| B-S1..3 | the same seed checks as A-S1..3 | PASS |
| B-U1 | `-update`'s plan row: leave it (its Python no longer exists), no 3.14 standard build, run `macos-ai-tools.sh` | PASS |
| B-U2 | the run left it, saying why, and refreshed nothing into it | PASS |
| B-U3 | the run installed nothing: no `uv python install`, no `uv venv`, no `uv pip` | PASS |
| B-U4 | `~/.default_venv` untouched: same inode and mtime, byte-identical `pyvenv.cfg`, no `-3.14`, no link | PASS |
| B-U5 | plan row and run agree: both leave the venv | PASS |
| B-G1 | from a 3.14t-only uv, the gate installed 3.14 and rebuilt the tool with `--force --python <verified standard path>` | PASS |
| B-G2 | the tool's `bin/python3` now reports 3.14 standard; the restart line was printed (no ledger under `-update`) | PASS |
| X1 | no interpreter outside the scratch root was used (`--python`) or recorded (`pyvenv.cfg` `home`): no Homebrew or system Python leaked in | PASS |

## Observations (not assertions from the brief)

1. **`UV_PYTHON_PREFERENCE` breaks both resolvers.**
   - Measured: with `UV_PYTHON_PREFERENCE=only-managed` exported, `find_csa_python` exits 1 and
     prints nothing on a machine where it otherwise returns the standard 3.14. The cause is uv
     rejecting `--managed-python` alongside a preference (exit 2).
   - **Not measured end to end, inferred from the code:** `csa_python_path` in the gate scripts
     makes the same uv calls, so it would read as offline, leave a free-threaded tool as it is and
     warn "offline?". In DesktopSetup, `ensure_csa_python` would then reach its Homebrew fallback.
   - The variable is not set in this session's environment.
   - A fix might pass `--python-preference only-managed` instead, or clear the variable for those
     calls; neither was tried.
2. **`-update` itself repairs the venv on its next run, for CSA-internal members.** In world B, the
   gate step of the same `macos-update.sh` flow installed the standard 3.14. So a second
   `update_default_venv` repaired the venv, and its plan row first said so: "build
   ~/.default_venv-3.14 on Python 3.14, move the directory ~/.default_venv to ~/.default_venv-3.13 (its
   Python no longer exists), link ~/.default_venv to .default_venv-3.14; install/refresh ... in it".
   It then built, moved and linked as world A's run 1 did, with the same warnings. It printed the
   reinstall hint and "Open a new terminal" itself, because `-update` keeps no ledger. A third run
   was a no-op.
   - The first run's row ("this script installs none - run macos-ai-tools.sh to repair it") is true
     of `update_default_venv`, but not of the whole `macos-update.sh` run for a CSA-internal member,
     whose gate scripts install a 3.14.
3. **Importing markitdown makes onnxruntime write a device id.** markitdown pulls in onnxruntime
   through magika. Importing it (assertion A-V5) created
   `~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime/` in the scratch HOME,
   holding `deviceid` and `onnxruntime.db`.
   - Installing does not import it, so the installer itself writes nothing there. Any use of
     markitdown would.
   - Whether anything is sent anywhere was **not** measured. Raised for #157.
4. **`uv tool list --show-python` cannot tell the builds apart.** It printed `[CPython 3.14.10]` for
   the tool both on 3.14t and after its rebuild on the standard build.

## Harness corrections

The first complete run of the harness passed 38 of 42. Its four failures were wrong expectations in
the harness, each shown by evidence before anything was changed. The harness was then corrected,
both worlds were deleted and re-seeded, and the run above is that rerun. The first run's other 38
results agreed with it.

| First run | What the evidence showed | Correction |
|---|---|---|
| A-V3 FAIL | `pyvenv.cfg` said `version_info = 3.14`; the check expected `3.14.x`. The interpreter was right: `3.14 0`, resolving into `cpython-3.14.10-macos-aarch64-none`. uv records no patch for a venv on its minor-version directory. | Accept `3.14` or `3.14.x`. |
| A-V9, A-V10 FAIL | No "Not reinstalled" warning or to-do for the seed's extra package, `tabulate`. The new venv had tabulate: pandas and pymupdf require it. The code was right to report nothing missing. | Seed `cowsay`, which nothing requires, and assert the new venv lacks it. |
| A-N2 FAIL | Only the tool's `uv-receipt.toml` mtime moved, with the same inode. A separate measurement found identical content, and `pyvenv.cfg` and `bin/python3` untouched, after `uv tool upgrade` answered "Nothing to upgrade". | The receipt is judged by inode and content in its own assertion, A-N2b. A-N2 checks what its claim names. |

## What this does not prove

- **Windows.** Tasks 4W and 5W wait for a Windows session (#184, decision D5).
- **Registrations.** `claude`, `codex` and `gemini` were absent, so nothing was registered. That is
  Plan 2.
- **The real run on the CINO's Mac.** It is queued for the CINO's go-ahead. It would rebuild four
  tools off 3.14t under running clients, so a restart follows. Its `~/.default_venv` was
  hand-migrated to the `-3.14` link on 2026-11-10, so the venv part must be a no-op there. That
  state is covered by `tests/test_venv_replacement.py`'s `cinos_mac_state_noop`, not by this run.
- **The other three gate scripts** (google-workspace, gmail-calendar, skilljar). Only `csa-zendesk`
  ran end to end here; `test-tool-interpreter.py` covers all four with stubs.
- **The scripts' `main()`.** Preflight, consent, `install_python` and the plan rendering ran only as
  the extracted functions listed under Method.
- **Not exercised:**
  - the Homebrew fallback, an Intel Mac (markitdown's best-effort path), and offline behaviour (all
    three are covered by stubbed tests);
  - a `.new-$$` replacement of a broken `-3.14`, because run 1 was a migration;
  - a server process running during the rebuild;
  - the CINO's `~/.zshrc` stanza.
- **Package downloads ran on a warm cache.** The final run reused the scratch uv cache filled by the
  first run. The Python downloads were fresh in both runs.

## Re-run after the final review (2026-11-10)

Recorded by the AI fixing the final whole-branch review's findings. Every statement is measured in
this re-run unless labelled otherwise.

**Result: 59 of 59 assertions pass,** on the first run of the updated harness. That is the 43
above, with A-V5 and B-U1 rewritten for the fixed code, plus A-V13, world C's 14 and X2.

**Code under test:**
- DesktopSetup `feat/python-314-standard-build` at `5150947`. The fix commits since `495ad6b`:
  - `62a21cc`: markitdown dropped, pymupdf pinned `>=1.24.3,<2` (C1, C2);
  - `9771139`: `update_pip` leaves the pinned deps alone in `~/.default_venv` (C3);
  - `676bab5`: the Windows pin (I1);
  - `ea72364`: "Not reinstalled" built from every old distribution's requirements (I2);
  - `63d4816`: `UV_PYTHON_PREFERENCE` no longer blinds `find_csa_python` (I3);
  - `79c9968`: the `-update` and Internal MCP servers plan rows (I4);
  - `5e6c5d8`: leftovers reported, never uninstalled (I6);
  - `5150947`: README.
- CSA-Plugins `feat/python-314-standard-build` at `bd986a5`, which includes that branch's own fixes
  since `8f92de4` (`87e0a5d`, its `UV_PYTHON_PREFERENCE` fix; `6688f4a`).

**Tools:** uv 0.13.7 (Homebrew build), `/bin/bash` 3.2.57, macOS 27.2 on arm64, as before. This time
the scratch uv cache was new, so every Python and every package was downloaded fresh. 0.8 minutes.

**Isolation, unchanged from [Method](#method):**
- a new scratch root, made with `mktemp -d` in the session scratchpad and deleted at the end;
- scratch `HOME`, uv directories and `TMPDIR` per world;
- the same gh deviation: `GH_CONFIG_DIR` set as a path only, never read by the harness;
- the real `~/.default_venv*`, `~/.zshrc`, `~/.local/share/uv` and `~/.local/bin` untouched. Their
  inode and mtime were recorded before and after the run, and match.

### What changed in the harness

- **Extraction follows the code.** `CSA_DOC_PY_DEPS_OPTIONAL` and `csa_venv_optional_install` are
  gone. `default_venv_leftovers` joins the shared functions, and the `-update` harness also extracts
  `csa_venv_held_names`, `pip_upgrades` and `update_pip`.
- **The uv wrapper also logs argument boundaries,** one per line, so "one argument" is checkable.
- **A-V5** now asserts that `~/.default_venv-3.14` holds no onnxruntime, markitdown or magika and
  that its pymupdf is 1.x. It reads the venv's metadata and imports nothing.
- **A-V13 (new):** every uv install of the document deps passed `pymupdf>=1.24.3,<2` as one
  argument, and no uv command named onnxruntime, markitdown or magika.
- **B-U1** expects the new `-update` row wording (I4).
- **A-N3** also counts a leftovers warning ("still has") as a repair.
- **World C (new, 14 assertions):** the state the final review found on staff Macs, which the
  first run did not cover.
  - The seed: a sound `-3.14` that an earlier installer filled with unpinned pymupdf, i.e.
    `uv pip install pyyaml pymupdf==2.1 csa-google-workspace`, which brought in onnxruntime 1.31.1,
    pymupdf-layout and pymupdf4llm.
  - The runs: `install_doc_python_deps` and `update_default_venv`, then `update_pip` with that venv
    active, on real pip against real PyPI.
  - Then the to-do's command, run verbatim.
- **X2 (new):** no world's `HOME` holds onnxruntime's telemetry directory, so nothing loaded
  onnxruntime.

### Plan rows, as printed now

- **World A, run 1, `macos-ai-tools.sh`:** "on the Python 3.14 the Python row installs: build
  ~/.default_venv-3.14 on Python 3.14, move the directory ~/.default_venv to ~/.default_venv-3.13
  (its Python no longer exists), link ~/.default_venv to .default_venv-3.14; install/refresh pyyaml
  pymupdf>=1.24.3,<2 csa-google-workspace in it".
- **World A run 1 and world B, `macos-update.sh`:** "leave ~/.default_venv as it is (its Python no
  longer exists); nothing is installed into it: there is no Python 3.14 standard build installed,
  and this step installs none. For CSA-internal members the Internal MCP servers step installs one
  and the next update repairs this; otherwise run macos-ai-tools.sh".
- **World A, run 2, both scripts:** "install/refresh pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
  in ~/.default_venv (Python 3.14, standard build)".
- **World B, after the gate step installed the standard 3.14:** the next `-update` row said build,
  move and link, and its run did exactly that. The one after was a refresh only, as before
  (Observation 2).

### uv commands that installed the document deps, world A

```
[run1-ai] uv pip install --quiet --python ~/.default_venv-3.14/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
[run1-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
[run1-update] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
[run2-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
[run2-update] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
```

Every other line of world A's uv log is identical to the first run's, apart from the
`[obs-preference]` calls (diffed). The five markitdown lines are gone. The argument log shows
`pymupdf>=1.24.3,<2` as a single argument in each (A-V13). `~/.default_venv-3.14` ended with
pymupdf 1.28.2, csa-google-workspace 0.55.1 and pyyaml 6.0.3, plus their dependencies, and no
onnxruntime, markitdown or magika (A-V5).

### World C: a venv that already had pymupdf 2.1

```
[seed] uv pip install --quiet --python ~/.default_venv-3.14/bin/python3 pyyaml pymupdf==2.1 csa-google-workspace
[c-ai] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
[c-update] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
[c-todo] uv pip uninstall --python ~/.default_venv/bin/python3 onnxruntime pymupdf-layout pymupdf4llm
[c-ai2] uv pip install --quiet --python ~/.default_venv/bin/python3 pyyaml pymupdf>=1.24.3,<2 csa-google-workspace
```

- **`install_doc_python_deps`** put pymupdf 1.28.2 back. It uninstalled nothing: no uv command was
  an uninstall, and onnxruntime, pymupdf-layout and pymupdf4llm were still there (C-L1, C-L2). It
  warned:

  ```
  Warning: ~/.default_venv still has onnxruntime pymupdf-layout pymupdf4llm, which pymupdf 2 brought in. onnxruntime's official macOS builds send Microsoft telemetry by default; nothing was uninstalled
  ```

  It also added to-do 44, "Remove what pymupdf 2 left in ~/.default_venv: …", whose command column
  is the line in `[c-todo]`, with the venv's absolute path quoted (C-L3). Nothing was reported as
  "not reinstalled" (C-L4).
- **`update_default_venv`**, which keeps no ledger, printed that line instead (C-L5).
- **`update_pip`, with the venv active, on real pip and PyPI:**
  - Real `pip list --outdated` in the venv reported
    `[{"name": "pymupdf", "version": "1.28.2", "latest_version": "2.1", ...}]` (C-U0).
  - `update_pip` printed "Not upgrading pyyaml pymupdf csa-google-workspace: the Default venv step
    installs them, pinned" and then "All pip packages are up to date". pymupdf was still 1.28.2
    afterwards (C-U1, C-U2).
  - `pip_upgrades`, the list the plan row prints, was empty, as was the run's (C-U3).
  - No `csa-pip-constraints.*` file was left in `TMPDIR` (C-U4).
- **The to-do's command, run verbatim** in `/bin/bash -c`, uninstalled exactly
  onnxruntime 1.31.1, pymupdf4llm 2.1 and pymupdf-layout 2.1. yaml, pymupdf and
  csa_google_workspace still imported (C-L6). The next `install_doc_python_deps` said nothing about
  leftovers (C-L7).
- **X2:** no world's `HOME` had `~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime`.
  This run imported no onnxruntime, unlike the first run's A-V5.

### `UV_PYTHON_PREFERENCE`, re-observed

With `UV_PYTHON_PREFERENCE=only-managed` exported in world A after run 2:
- `find_csa_python` exited 0 and printed
  `$UV_PYTHON_INSTALL_DIR/cpython-3.14-macos-aarch64-none/bin/python3.14`, the same path as without
  the variable. In the first run it exited 1 and printed nothing (Observation 1).
- Raw `uv python find --system --managed-python 3.14` under the same variable still exited 2 with
  "the argument `--managed-python` cannot be used with `--python-preference`". The subshell `unset`
  is what makes the difference.

### Rows of the first record that no longer describe the branch

- **Method:** the extracted assignments list `CSA_DOC_PY_DEPS_OPTIONAL`, which no longer exists.
- **Run 1 plan rows:** the `macos-ai-tools.sh` row's "pymupdf csa-google-workspace (then
  markitdown[all]>=0.1.9, best effort)", and the whole `macos-update.sh` row ("this script installs
  none - run macos-ai-tools.sh to repair it").
- **Run 2 plan rows:** "(then markitdown[all]>=0.1.9, best effort)".
- **uv command log, world A:** every `uv pip install` line names an unpinned `pymupdf`, and the
  five `markitdown[all]>=0.1.9` lines are no longer run.
- **World B's plan row,** and assertion **B-U1**'s claim: the old `-update` wording.
- **Assertion A-V5**, "markitdown imports": markitdown is no longer installed.
- **Observation 1:** fixed in DesktopSetup (`63d4816`) and, per its own branch, in CSA-Plugins
  (`87e0a5d`).
- **Observation 2's last bullet:** the row now says what a CSA-internal member's run does (`79c9968`).
- **Observation 3:** markitdown is no longer installed, so nothing the installer puts there imports
  onnxruntime. A venv an earlier run filled still holds it, and is now told so.
- **"What this does not prove":** "an Intel Mac (markitdown's best-effort path)" no longer exists.
  The Intel resolution of the pinned list is checked by `tools/check-doc-deps-resolve.py`
  (pymupdf 1.28.2, no onnxruntime), not run on an Intel Mac.

### Still not proven by this re-run

Everything under [What this does not prove](#what-this-does-not-prove), apart from the markitdown
item, and also:
- **Windows** has only the one-line pin (I1), untested on Windows.
  - Not measured, read from the code: `Install-DocPythonDeps` returns early when `import yaml,
    pymupdf` already succeeds, so it does not downgrade an existing pymupdf 2.
  - `windows-update.ps1`'s pip step upgrades every outdated package, pymupdf included. Both are
    left to the Windows session (#184) by the controller's ruling.
- **Telemetry itself.** That onnxruntime sends anything was taken from the final review's finding
  and was not measured here: this run took care never to load it.
