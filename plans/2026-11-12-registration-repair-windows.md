# CSA MCP registrations, the Windows halves: Implementation Plan (held for #184)

> **For agentic workers:** this is the Windows companion to
> [`2026-11-12-registration-repair.md`](2026-11-12-registration-repair.md). That plan's decisions, AI decisions,
> Global Constraints and Review Focus apply here unchanged; this file adds only what is Windows-specific. Use
> superpowers:subagent-driven-development (B1), and run every review on `fable` (B12).

**Goal:** the same as the macOS plan's, on Windows: a rerun of `windows-ai-tools.ps1`, `windows-update.ps1` or
`windows-plugins.ps1` audits every CSA MCP registration, re-points a dead one in place after consent, and checks
servers as D5 allows. A second rerun changes nothing.

**When this runs:** only in a session on a real Windows machine (#184), after its measurements. These tasks keep the
platforms from drifting. They are specified now so the macOS half is built with them in view. Whether macOS waits for
them was the macOS plan's D3, answered 2026-11-13: the CINO chose, verbatim, *"Ship macOS first (Recommended)"*.
So macOS ships without them, and the gap is on #184 and `TODO.md` P1. A green `windows-latest` CI run is not a
Windows run (R5).

**Branches:**

| Repo | Branch | Tasks |
|---|---|---|
| DesktopSetup | `feat/registration-repair-windows` | 1W, 4W, 6W |
| CSA-Plugins | `fix/registration-probes-windows` | G1W, G2W |

Every PR here is a draft until the Windows session has measured and run it end to end.

**Not here:** G2's and G3's `.ps1` code fixes. CloudSecurityAlliance-Internal/CSA-Plugins#213 makes them in the
`.sh` and the `.ps1` together (macOS plan, D6). Its Desktop writer skips `fchmod` on Windows, so G2W's ACL
measurement below still applies.

## PowerShell 5.1 constraints

- No `?:`, `??`, `?.`, `&&` or `||`.
- Every native command goes through `Invoke-Native*`.
- Python is run from a file, never from `-c` code containing `"`.
- Shared functions are byte-identical in the three `.ps1` entry scripts (`check-duplication.py`).
- Bump `SCRIPT_VERSION` in every changed `.ps1`.

### Task 1W: the `.py` audits, repairs and checks on Windows

**Measure first, on a real Windows machine:**
- **Claude Desktop's config path.** Is it `%APPDATA%\Claude\` or the MSIX-virtualised
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`? Which one does Desktop actually read (#156, #168)?
- **Interpreters behind entry points.** How do you find the interpreter behind a uv trampoline
  `~\.local\bin\<entry>.exe`, and behind a pip console-script `.exe` in a venv's `Scripts\`? What does
  `pyvenv.cfg` `home` look like for each?
- **Bare names.** How does each client resolve a bare name: `PATHEXT`, and Desktop's environment?
- **The env Desktop passes** to a stdio server.
- **Locking.** Does `os.replace` fail while Desktop or a Claude Code session holds the file?
- **M1 on Windows.** Does Claude Code take `<config>.lock` around its writes there, as it does on macOS, and does it
  honour one somebody else holds? `ClaudeLock` assumes so.
- **Config encodings.** Does any client write its config with a UTF-8 BOM or CRLF line endings? *Today the `.py`
  reports a file that starts with a BOM `not audited` and never writes it; it keeps CRLF when it writes.* If a
  client writes a BOM, the reader must parse it, and a write must keep the file's own BOM and line endings.
- **`.cmd` shims.** `codex` and `gemini` are npm globals, so on Windows they are `.cmd` shims, which `subprocess` does
  not find or run without a shell. Resolve them with `shutil.which` (which honours `PATHEXT`), and pass arguments so
  `cmd.exe`'s quoting cannot alter them.
- **ACLs after `os.replace`,** for the `.py`'s own writes as well as the gate's: does the replaced file keep a
  user-only ACL, or inherit the directory's?
- **Argv visibility.** Can another account on Windows read a process's command line? A3's rule holds either way; the
  answer goes into FRICTION.md (FRICTION-007 is macOS's).
- **`Confirm-Step` under Windows PowerShell 5.1.** `tests/ConfirmStep.Tests.ps1` pins that end of input at the
  consent prompt is a no. `Read-Host` returning `$null` at end of input was measured on pwsh 7.6 only.
- **M5 on Windows,** before D5 lets any server check run by default there: one launch per server, as `verify`
  makes it, with its token files `stat`ed (never opened) before and after, and its connections sampled.

**Then:**
- Replace the `win32` "not audited" stubs with real readers and classifiers. The reasons stay verbatim, except that
  `Scripts\python.exe` takes the place of `bin/python3`.
- **The handshake:** `CREATE_NEW_PROCESS_GROUP`, then `taskkill /T /F /PID` on timeout.
- **Running-client detection** is by path, never by process name. Claude Code's updater renames its running image
  (AGENTS.md trap).
- **A locked file** gives `in use by <client>; not written — close it and run again`.
- **The POSIX-only parts of the `.py` as built,** each to work on Windows or refuse in one line:
  - `run_bounded`, `spawn` and `end` use `start_new_session`, `os.killpg` and `preexec_fn`: on Windows,
    `CREATE_NEW_PROCESS_GROUP` and `taskkill /T /F /PID` (above);
  - `exchange` reads a server through `selectors`, which on Windows works on sockets only, not pipes;
  - `desktop_running` reads `ps -axo comm=`. With no `ps` it answers "could not tell", so Desktop's config is
    never written: safe, but it needs the path-based detection above;
  - `write_temp` calls `os.fchmod`, which Windows has only from Python 3.13;
  - `run_alive` answers "alive" on Windows, so `sweep_temps` never removes a stopped run's temp file there:
    decide whether that stands;
  - `signals_held` and `exits_on_signals` already fall back where there are no signal masks: check what a Ctrl-C
    does mid-write.

**Tests:** the same test file's Windows cases, run on `windows-latest` CI and on the machine, including a BOM file, a
CRLF file and a `.cmd` shim. `tests/test_mcp_registrations.py` runs only in the ubuntu and macOS jobs today; add it
to the `windows-latest` job.

**PR:** a draft, listing the measurements.

### Task 4W: the three `.ps1` entry scripts wire it as Task 4 does

**Files:** `windows-ai-tools.ps1`, `windows-update.ps1` and `windows-plugins.ps1`.
- **Add, byte-identical in all three:**
  - `Get-CsaRegistrationsPy`;
  - `Show-CsaRegistrationsPreview`, called from each `Show-Preflight`;
  - `Repair-CsaRegistrations`, the last call in `Invoke-CSAInternalSetup`;
  - the twins of the rest of what the macOS functions do. *Corrected 2026-11-15:* the macOS build has eight
    (`csa_registrations_dir`, `_py`, `_bounded`, `_python`, `_usable`, `_log`, `_preview` and
    `repair_csa_registrations`, under "CSA MCP registrations" in each `macos-*.sh`). Its reviews added:
    - an interface check: `--version` must print a version of the scripts' form, and `--interface` exactly
      `csa-mcp-registrations interface 1: plan apply verify`. The `.py` writes both itself, so no environment
      changes them. A sign-in page or another file fetched in its place is skipped in one line;
    - a 10 s bound on each Python probe and each interface question. macOS uses a perl alarm, in the
      foreground, so a Ctrl-C reaches the probe. Windows has no perl; its twin bounds them with the
      `ProcessStartInfo` helper below;
    - removal of the directory on every exit path.
- **The working directory and plan file** are created once per run in the script's own scope, never inside a
  function whose output is captured (the macOS Task 4 defect the re-review found).
- **Python:** a self-contained resolver, byte-identical in all three, as macOS's `csa_registrations_python` is.
  *Corrected 2026-11-15:* this said "the CSA Python from Plan 1's Task 4W, `Find-CsaPython`", but Plan 1 adds
  `Find-CsaPython` to `windows-ai-tools.ps1` only, so `windows-update.ps1` and `windows-plugins.ps1` would have
  none: the gap macOS's spec review M1 found for `-plugins`. The `.py` is stdlib-only, so any Python 3.9 or later
  will do.
- **The `.py` runs through a bounded `ProcessStartInfo` helper** that captures stdout. Its arguments are paths and
  flags only, quoted for paths with spaces.
- **Temp directories:** `[IO.Path]::GetTempPath()` plus a GUID directory.

**Tests:** Pester cases that mirror the `wiring_` cases. Once these land in all three, `wiring_windows_twin_exists`
passes instead of skipping; in some but not all, it fails. Then run PSScriptAnalyzer, `check-powershell-native.py`
and `check-duplication.py`.

**PR:** a draft.

### Task G1W and G2W (CSA-Plugins, `.ps1`)

- **G1W:** every `claude`, `codex` and `gemini` `mcp` call in the four `.ps1` runs with its working directory set to
  a fresh empty temp directory. Use `Push-Location`/`Pop-Location` in `try`/`finally`, inside `Invoke-CsaNative`'s
  scriptblock. Apply the macOS plan's M7, repeated on Windows.
- **G2W:** measure whether a new file in Desktop's config directory inherits a user-only ACL. Change code only if it
  is wider than the file it replaces. Fold in CloudSecurityAlliance-Internal/CSA-Plugins#198, which is the same
  files.

**PRs:** drafts.

### Task 6W: acceptance on Windows

The macOS Task 6's seed and assertions, on the Windows machine, from the branches. Record the evidence on #184.
