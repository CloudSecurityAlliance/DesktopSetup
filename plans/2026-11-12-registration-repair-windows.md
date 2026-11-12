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
them is the macOS plan's D3. A green `windows-latest` CI run is not a Windows run (R5).

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
- **Config encodings.** Does any client write its config with a UTF-8 BOM or CRLF line endings? The reader must parse
  both, and a write must keep the file's own BOM and line endings.
- **`.cmd` shims.** `codex` and `gemini` are npm globals, so on Windows they are `.cmd` shims, which `subprocess` does
  not find or run without a shell. Resolve them with `shutil.which` (which honours `PATHEXT`), and pass arguments so
  `cmd.exe`'s quoting cannot alter them.
- **ACLs after `os.replace`,** for the `.py`'s own writes as well as the gate's: does the replaced file keep a
  user-only ACL, or inherit the directory's?
- **Argv visibility.** Can another account on Windows read a process's command line? A3's rule holds either way; the
  answer goes into FRICTION.md.

**Then:**
- Replace the `win32` "not audited" stubs with real readers and classifiers. The reasons stay verbatim, except that
  `Scripts\python.exe` takes the place of `bin/python3`.
- **The handshake:** `CREATE_NEW_PROCESS_GROUP`, then `taskkill /T /F /PID` on timeout.
- **Running-client detection** is by path, never by process name. Claude Code's updater renames its running image
  (AGENTS.md trap).
- **A locked file** gives `in use by <client>; not written — close it and run again`.

**Tests:** the same test file's Windows cases, run on `windows-latest` CI and on the machine, including a BOM file, a
CRLF file and a `.cmd` shim.

**PR:** a draft, listing the measurements.

### Task 4W: the three `.ps1` entry scripts wire it as Task 4 does

**Files:** `windows-ai-tools.ps1`, `windows-update.ps1` and `windows-plugins.ps1`.
- **Add, byte-identical in all three:**
  - `Get-CsaRegistrationsPy`;
  - `Show-CsaRegistrationsPreview`, called from each `Show-Preflight`;
  - `Repair-CsaRegistrations`, the last call in `Invoke-CSAInternalSetup`.
- **The working directory and plan file** are created once per run in the script's own scope, never inside a
  function whose output is captured (the macOS Task 4 defect the re-review found).
- **Python** is the CSA Python from Plan 1's Task 4W, `Find-CsaPython`, which must land first.
- **The `.py` runs through a bounded `ProcessStartInfo` helper** that captures stdout. Its arguments are paths and
  flags only, quoted for paths with spaces.
- **Temp directories:** `[IO.Path]::GetTempPath()` plus a GUID directory.

**Tests:** Pester cases that mirror the `wiring_` cases. Once these land, `windows_twin_exists` passes instead of
skipping. Then run PSScriptAnalyzer, `check-powershell-native.py` and `check-duplication.py`.

**PR:** a draft.

### Task G1W and G2W (CSA-Plugins, `.ps1`)

- **G1W:** every `claude`, `codex` and `gemini` `mcp` call in the four `.ps1` runs with its working directory set to
  a fresh empty temp directory. Use `Push-Location`/`Pop-Location` in `try`/`finally`, inside `Invoke-CsaNative`'s
  scriptblock. Apply the macOS plan's M7, repeated on Windows.
- **G2W:** measure whether a new file in Desktop's config directory inherits a user-only ACL. Change code only if it
  is wider than the file it replaces. Fold in CSA-Plugins#198, which is the same files.

**PRs:** drafts.

### Task 6W: acceptance on Windows

The macOS Task 6's seed and assertions, on the Windows machine, from the branches. Record the evidence on #184.
