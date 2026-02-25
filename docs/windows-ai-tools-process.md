# How We Designed the Windows AI Tools Script

This document explains the process used to design `scripts/windows-ai-tools.ps1` and produce the AI instruction document that was used to write it. It is intended for humans who want to understand the methodology — or replicate it for future scripts.

## The Problem With Vibe Coding a Bootstrap Script

A bootstrap script that installs and migrates tools across many possible machine states is exactly the kind of task where vibe coding produces plausible-looking but subtly wrong results. The failure modes are not obvious:

- It looks like it works on a clean machine but silently does the wrong thing on a machine where tools were previously installed the wrong way
- It detects tools by the wrong signal (e.g. `python --version` succeeds but points at a Windows Store stub that is not a real Python)
- It installs things to system paths when they should go to user paths, requiring admin rights the user does not have
- It does not know which install methods are "correct" and which need migration

Getting this right requires verified facts about how tools actually behave on real Windows machines — not assumptions or documentation that may be out of date.

## Starting Point: The macOS Script as a Model

The existing `scripts/macos-ai-tools.sh` provided a proven structure to follow:

- Idempotent — safe to run multiple times
- Interactive by default, with `NONINTERACTIVE=1` for CI
- Shows a preflight plan before touching anything
- Detects tools installed via the wrong method and migrates them
- Preserves all config files during migration
- Checks for running processes before migrating

Rather than designing the Windows script from scratch, we asked: what does each part of the macOS script map to on Windows? This produced a concrete list of questions that needed verified answers before writing any code.

## Questions That Needed Real Answers

**Package manager**: macOS uses Homebrew. What is the Windows equivalent?
- Homebrew's role in the AI tools script is narrow: it only installs Node.js. Everything else uses native installers or npm.
- On Windows, `winget` fills this role. It ships with Windows 10/11 (no bootstrap problem), handles Node.js cleanly, and is fully automatable.

**Python**: macOS does not install Python in the AI tools script. Why would Windows?
- Claude Code skills are heavily Python-based. macOS has a system Python baseline. Windows does not.
- Python therefore belongs in the Windows AI tools script even though it is absent from the macOS equivalent.

**Bootstrap invocation**: macOS uses `bash -c "$(curl ...)"`. What is the Windows equivalent?
- `irm https://... | iex` — native PowerShell, same pattern already used by Claude Code's own installer.

## Interrogating the Actual Machine

Rather than relying on documentation, we ran detection commands against a real Windows 11 machine to verify actual install states and paths. This produced facts, not assumptions.

Key discoveries:

**Claude Code was installed via npm** (`$APPDATA\npm\claude`) — the wrong method. The correct method is Anthropic's native installer. This confirmed that migration logic is needed and is not hypothetical.

**Node.js was installed via winget** (`C:\Program Files\nodejs\`) — the correct method. This confirmed winget is a realistic install path for real users.

**Python was installed via the new Python install manager** at `$LOCALAPPDATA\Python\bin\python.exe`. This confirmed the install path anchor for detection logic. It also revealed that Windows has a second Python path to be aware of: `$LOCALAPPDATA\Microsoft\WindowsApps\python.exe` is a Store stub, not a real Python installation, and the two must not be confused.

**Codex and Gemini were both installed via npm** — correct. No migration needed.

Without running these checks, a developer writing the script would likely have guessed at paths and gotten some of them wrong.

## The Python Decision

Python had the most design complexity and is worth explaining in detail.

The traditional approach — `winget install Python.Python.3.13` — is fully automatable and would work. But it:
- Does not fix the Windows 260-character path limit (causes real problems with deep virtualenv trees)
- Does not handle multiple Python versions
- Is being phased out by the Python project itself

Python's new install manager (a Windows Store app) is the stated long-term direction and fixes all of these. The tradeoff is that it is **interactive by design** — it has a configuration TUI that makes system-level decisions on the user's behalf.

The macOS script has a precedent for this: installing Xcode CLI Tools triggers a GUI dialog. The script opens the dialog and waits, telling the user to follow the prompts. The same pattern works here.

The other Python decision: **never auto-migrate Python**. If Python is found installed via a wrong method, the script warns and continues rather than uninstalling and reinstalling. The reason: Python migrations break virtual environments and orphan pip packages. The cost of auto-migration exceeds the cost of asking the user to handle it manually.

## One Remaining Unknown

At the time the instruction document was written, the Claude Code native installer had not yet been run on the reference machine — so the exact path where it places the binary on Windows was not confirmed. The instruction document tells the AI writing the script to resolve this first by fetching and reading `https://claude.ai/install.ps1` before writing detection logic. This is preferable to guessing.

## Why Two Documents

The original design notes combined reasoning for humans with instructions for AI into a single document. This is suboptimal for both audiences.

An AI writing code from a design document works best when the document is precise, unambiguous, and structured as instructions rather than explanation. Rationale and tradeoff discussion adds noise.

A human reviewing the process works best with narrative explanation — the *why*, the alternatives considered, the discoveries made — rather than a list of detection commands.

Splitting into two documents lets each serve its audience cleanly. The instruction document tells the AI exactly what to build. This document tells humans how and why those instructions were arrived at.

## What This Process Produces

A script written from verified facts and explicit design decisions will:
- Handle the real machine states that exist in the wild, not just clean installs
- Migrate tools correctly without breaking user configuration
- Fail with clear, actionable messages rather than silent wrong behavior
- Be maintainable — future changes can be made with understanding of why each decision was made

The process is not complicated. It is: read the existing code, identify the analogues, verify the facts on a real machine, resolve the unknowns, write the instructions, then write the code.
