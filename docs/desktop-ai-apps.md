# Desktop AI apps: where each one comes from, and how it stays current

Four desktop AI apps are installed by `macos-ai-tools.sh` and `windows-ai-tools.ps1`: Claude
Desktop, ChatGPT Desktop, Gemini Desktop and Microsoft Copilot. This note records why each
comes from the source it does. It was researched on 2026-10-23 and 2026-10-24, from a Mac with
all four apps installed, from the vendors' own documentation, and from the package manifests
themselves. Most of the Windows half was then measured on a Windows 11 machine on 2026-10-25;
[#161](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/161) holds the results and
what is still open.

**What is supported.** The current build of each app, from a source that keeps it current. On
Windows that assumes the **Microsoft Store is present**: ChatGPT comes from it, and there is no
no-Store fallback yet; that is deferred to
[#164](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/164). Old builds are not
detected or migrated.

## The rule

**Every one of these apps updates itself, on macOS and on Windows. On Linux, none of them do.**
So the installer's job is narrow: put the vendor's own build on the machine, in a way that
registers it with the vendor's updater, and then stay out of the way. Whether a package manager
carries the newest version matters much less than whether the source is official and hooked up
to that updater. A winget manifest three days behind is harmless. A Homebrew cask that installs
a retired build with its updater switched off is not.

## What is installed, by platform

| App | macOS | Windows | Updated by |
|---|---|---|---|
| Claude | `brew install --cask claude` | Anthropic's `ClaudeSetup.exe`, from `api.anthropic.com` (installs the MSIX; asks for admin) | its own updater, about every 4 h; a restart is forced within 72 h of a download |
| ChatGPT | `brew install --cask chatgpt` | Microsoft Store `9PLM9XGG6VKS` via `--source msstore` | Sparkle on macOS; the Store plus a built-in updater on Windows |
| Gemini | `brew install --cask google-gemini`, Apple Silicon and macOS 15+ only | `winget install --exact --id Google.GeminiDesktop` | Google's updater (Keystone/GoogleUpdater) on macOS; a Google update client built into the app on Windows |
| Copilot | Microsoft's own `.pkg`, per architecture, signature-checked, `sudo installer` | `winget install --exact --id Microsoft.Copilot` (machine-wide MSI) | Edge's updater on both platforms |

## Two kinds of updater, and why the difference matters

| | Runs with the app closed? | Apps |
|---|---|---|
| Inside the app | No, only while it is open | Claude, ChatGPT on macOS |
| A system service | Yes, a launchd job or Windows service | Gemini on macOS (Google's updater), Copilot on both (Edge's updater) |

Seen on this Mac on 2026-10-23. Claude's updater log showed an update applied the day before.
Copilot was registered with Edge's updater at the current version. ChatGPT's Sparkle had last
checked on 10-20, while the app was closed, and sat two releases behind one published that day.
An in-app updater keeps an app current only if the app gets opened. A status report should
compare against the vendor's feed, not just confirm the app exists.

## Per app

### Claude

- The macOS cask matched Anthropic's update feed exactly (3.6556.2, 2026-10-22).
- On Windows, **winget cannot install the current build from a non-elevated script.**
  Measured 2026-10-25 on Windows 11 under Windows PowerShell 5.1 (#161 item 1):
  - Every current `Anthropic.Claude` manifest (2.26454.2 to 2.42304.2) carries both an MSIX and
    the old Squirrel `.exe` (`ProductCode: AnthropicClaude`, `Scope: user`). Non-elevated,
    winget **selects the `.exe`**, the old build without Cowork.
  - `--installer-type msix` is **refused with `0x80073D28`**, even as an upgrade. The MSIX never
    installs without its Cowork service, and that service needs admin.
  - `windows-ai-tools.ps1` refuses to run as Administrator, so winget is a dead end here.
- So Windows uses **Anthropic's `ClaudeSetup.exe`**, their documented route. It raises its own UAC
  prompt and installs the MSIX. Measured: an in-place update, 2.26454.2.0 to 3.6556.2.0, exit 0
  in 26 s, with the Cowork service intact and no second copy. It removes a Squirrel build if it
  finds one, and it opens Claude when done. It also handles a standard user who approves with
  another account's admin credentials, which `Start-Process winget -Verb RunAs` would get wrong.
  - It must be the **current** `ClaudeSetup.exe`, downloaded from
    `api.anthropic.com/api/desktop/win32/<arch>/setup/latest/redirect`.
    - The fixed URL `downloads.claude.ai/releases/win32/ClaudeSetup.exe` serves a build from
      2026-03-26. Its signing certificate expired 2026-10-20, and it pins that certificate, so
      it rejects every current MSIX: "MSIX signer does not match bootstrapper", although both
      subjects read the same.
    - The same redirect on `claude.ai` sits behind a bot check that answered 403.
  - It is run only if its Authenticode signature is valid and names `O="Anthropic, PBC"`. The
    check uses the subject, not a thumbprint, because the certificate rotates.
  - UAC's prompt gives up after 2 minutes, and that counts as a refusal (setup exits 1). The
    first measured attempt timed out because the prompt was never noticed, so the script says
    to watch for it **before** it appears. With nobody at the keyboard, it is skipped and
    becomes a to-do.
- winget lags. On 2026-10-23 it offered 2.42304.2 while five 3.x submissions sat in review. The
  app updates itself within hours of installing, so the lag costs little.
- **The old `.exe` build is not supported.** The script neither detects nor migrates it;
  `ClaudeSetup.exe` removes it.

### ChatGPT

- OpenAI's current desktop app is built from its Codex app. On macOS the bundle identifier is
  `com.openai.codex`, and the `chatgpt` cask downloads from `codex-app-prod`. Nothing here keys
  on bundle identifiers, so nothing broke.
- On Windows the Store is OpenAI's documented route. **On 2026-10-23 a community manifest,
  `OpenAI.ChatGPT`, appeared in the regular winget source.** It installs the same Store-signed
  MSIX straight from OpenAI's CDN. **It is not used to install.** The Store is assumed, so there
  is no no-Store fallback for now; #164 is where that is picked up.
- winget **correlates the Store copy with `OpenAI.ChatGPT`** (measured 2026-10-25): `winget
  upgrade` lists ChatGPT under that id, not under `9PLM9XGG6VKS`. So `winget upgrade --all` may
  upgrade it through the community package. That is intended: that run upgrades everything it
  can. The wait before it asks winget about both ids, and holds back whichever one is pending.

### Gemini

- macOS: `google-gemini`. **Never `gemini`**, which is MacPaw's duplicate-file cleaner. Google's
  app is also named `Gemini.app`, so `gemini_desktop_state` checks the bundle identifier
  (`com.google.GeminiMacOS`). A `Gemini.app` that is not Google's is neither counted as
  installed nor installed over.
- Windows: `Google.GeminiDesktop` is a **community** manifest, but every installer it names is
  pinned by SHA-256 to Google's own `dl.google.com` download. The checksum was confirmed by
  downloading the 1.16.0 x64 installer. That file is the full electron-builder NSIS installer
  (per-user). Its bytes contain Google's update client (`gemini_helper` with
  `OmahaUpdateCheckResult`, and a "Restart to update" string), so a winget install should update
  itself. That is inferred, not observed yet; #161 item 3.
- Measured 2026-10-25: a non-elevated `winget install` exits 0 with no UAC prompt, and writes
  `HKCU\…\Uninstall\Gemini` (`Publisher: Google LLC`, `InstallLocation:
  %LOCALAPPDATA%\Google\Gemini`). The app runs from `<InstallLocation>\app-<version>\Gemini.exe`.
- The macOS app bundles its own MCP servers (`autodesk_mcp_server`, `blender_mcp_server`) and an
  Antigravity launcher (`agy`). They are its own, not CSA's.
- No official Linux app exists. The snap and AppImage "Gemini Desktop" packages are unofficial
  web wrappers.

### Copilot

- Microsoft merged "Microsoft Copilot" and "Microsoft 365 Copilot" into one app
  ([deploy-unified-copilot-app](https://learn.microsoft.com/en-us/windows/client-management/deploy-unified-copilot-app)).
  The merged app is built on Edge's engine and updated by Edge's updater. On macOS it keeps the
  bundle identifier and package receipt `com.microsoft.m365copilot`, at version 153.x.
- **The `microsoft-365-copilot` cask installs the *former* app**: the Microsoft AutoUpdate build,
  1.2609, with AutoUpdate deselected. The cask had not moved since 2026-09-30. Its `homepage`
  is the Copilot download page, but its `url` is a different binary, so following the cask's own
  link is what exposed the mismatch. A Copilot already installed from that cask is replaced, only
  after the person quits it (below). A Copilot from anywhere else is left to its own updater.
- macOS source: Microsoft's per-architecture links from the deployment doc (`fwlink 2375510`
  for arm64, `2375509` for Intel). Sizes move with each release: 413 MB for arm64 on 2026-10-24
  (v153); 531 MB for arm64 and 576 MB for Intel on 2026-10-25 (v156). The download page's own
  link was a 764 MB universal package. The arm64 package checked on 2026-10-24 was signed
  `Developer ID Installer: Microsoft Corporation (UBF8T346G9)` and notarized, with payload
  `./Copilot.app`. The script runs `sudo installer` on the package, so it installs only when all
  three of these hold:
  - `pkgutil` says Apple issued the certificate for distribution;
  - the certificate chain names that identity;
  - Gatekeeper (`spctl`) accepts the package with that origin, which also checks notarization.
- **Nothing is removed before its replacement is verified.** The cask's own uninstall deletes the
  app (`pkgutil: com.microsoft.m365copilot`), so the order is:
  1. wait for the person to quit Copilot;
  2. download Microsoft's package;
  3. verify it;
  4. wait again, in case it was reopened during the download;
  5. remove the cask;
  6. install.

  A Homebrew Copilot whose app cannot be found is refused rather than replaced unwatched. In a
  non-interactive run, `sudo -n` is checked before anything is downloaded.
- Windows: `Microsoft.Copilot` is published by Microsoft's own pipeline (`esrp-winget-prod[bot]`).
  It is the same `CopilotStableEnterprise*.msi` Microsoft documents for offline deployment, and
  it installs machine-wide. Detection also checks `Program Files (x86)\Microsoft\Copilot\Application`,
  because Edge's updater installed Copilot on many machines by itself in April 2026. winget lists
  that copy as **`Microsoft.365Copilot`**, not `Microsoft.Copilot` (measured 2026-10-25), so the
  wait asks about both.
- Windows: **Copilot pre-launches at sign-in** (`copilotapp.exe --no-startup-window`), with no
  window and no tray icon, and stays resident after its window is closed. So on Windows Copilot
  counts as open only while it has a window. Its updates are Chromium-style, one folder per
  version beside the running one, and land while it runs.

## Look-alikes that were rejected

| Name | What it actually is |
|---|---|
| `brew install --cask gemini` | MacPaw's duplicate-file cleaner ("Gemini 2") |
| `brew install copilot` (formula) | AWS Copilot, a CLI for Amazon ECS and Fargate |
| `brew install --cask microsoft-365-copilot` | The *former* Microsoft 365 Copilot app, with its updater deselected |
| winget `Microsoft.365Copilot` | The former app: the Office hub, renamed (`Microsoft.MicrosoftOfficeHub`) |
| winget `j178.ChatGPT`, `lencx.ChatGPT`, `sonnylab.chatgpt` | Third-party ChatGPT wrappers |
| snap `gemini-desktop`, `bwendell/gemini-desktop` | Unofficial Gemini web wrappers |

## Replacing an app that is running

An app is never replaced while it runs: its files would be swapped underneath it. The scripts
replace a desktop app in exactly two places:

- `macos-ai-tools.sh`, when it swaps a Homebrew `microsoft-365-copilot` for Microsoft's own
  Copilot (`install_copilot_desktop`, `copilot_ready_to_replace`).
- `windows-update.ps1`, when `winget upgrade --all` is about to upgrade a desktop app that is
  running (`Update-Winget`). The plan names any such app before the person agrees to the run.
  After the sources are refreshed it asks again, because the refresh can reveal an update the
  plan could not see.

`macos-update.sh` has no equivalent. `brew upgrade` without `--greedy` skips casks that update
themselves, and all of these do.

**What counts as running.**

- **macOS:** the app's main executable (`Contents/MacOS/`), for the current user. Nothing else in
  the bundle counts, because nothing else is reliably gone once the app is quit:
  - the vendors' launchd jobs: Copilot's `LoginItems/CopilotAppHost`, Gemini's
    `GeminiAppLauncher`, updaters under `LaunchServices`;
  - not even everything under `Frameworks`: on 2026-10-25, three of Copilot's crash handlers
    there had launchd, not Copilot, as their parent, so they may outlive it.

  The window and renderer processes exit with the main one. `ps -o comm=` gave absolute paths
  for all four main executables, and relative ones for some launchd jobs, which therefore never
  match.
- **Windows:** a process whose image path matches the app's install location, in the current
  session. The session-0 services (Claude's Cowork service, Copilot's proxy) are excluded.
  Gemini's folder is read from its uninstall entry: `InstallLocation`, else the folder of its
  `DisplayIcon`. Only when the entry names no folder does it fall back to the file name
  `Gemini.exe`, the one name match. A false match costs a needless prompt; no match would let
  winget replace a Gemini that is open.

A wait that counted a process that never exits would never end. The vendor's installer stops and
restarts its own agents. Apps are otherwise identified by path, not by process name, for the
reasons recorded at `Get-RunningAiClients`.

**How the wait behaves.**

- It never quits the app on the person's behalf. An app can hold unsaved work, and only they know.
- It explains how to quit fully: from the menu or menu-bar icon on macOS, from the tray icon on
  Windows. Closing the window leaves all of these apps running.
- It polls every two seconds, and every minute asks whether to keep waiting, so an app that will
  not exit cannot trap the run. An app quit while that question is on screen counts as quit.
- **Declining leaves the app as it is**, and so does nobody being at the keyboard
  (`NONINTERACTIVE`, where it does not wait at all).
  - macOS: the Copilot migration stops and adds a to-do.
  - Windows: the app is **held back from `winget upgrade --all` with a temporary `winget pin`**,
    which is removed afterwards, even if the upgrade fails. A pin the person already had is
    theirs and is never removed.

Tested by `tests/test_desktop_apps.py` and `tests/DesktopApps.Tests.ps1`.

- The macOS tests cover the wait, the states, and the Copilot install's order. Their control
  shows that a naive name match fails them, and in-memory mutations of the shipping code
  (including the exact ordering bug the review found) are each caught.
- The Windows tests cover the wait, the hold and its release, every winget id an app may be
  upgraded through, Copilot's window rule, and Gemini's location rule.

The tests do not prove the Windows paths or winget's behaviour. Those were measured on
2026-10-25 for ChatGPT, Gemini, Copilot and `winget pin`; #161 holds the results.

## Linux

Not installed by anything here. The Linux tier is headless, for AI agents
([DEC-013](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/DECISIONS.md)),
and a desktop app has no place on it. If a Linux desktop tier is ever added:

| App | Status (2026-10-23) |
|---|---|
| Claude | Official beta since 2026-06-30. Anthropic's APT repository, Ubuntu 22.04+ and Debian 12+, amd64 and arm64. No self-update: `apt upgrade` delivers it (3.6556.2, the same as macOS) |
| ChatGPT | Official preview since 2026-08-11. The `.deb`/`.rpm` sets up OpenAI's signed repository; there is a script for Arch. Updated by apt, dnf or pacman |
| Gemini, Copilot | No official Linux app |

## Sources

- Claude: [Installation and setup](https://claude.com/docs/third-party/claude-desktop/installation),
  [Deploy Claude Desktop for Windows](https://support.claude.com/en/articles/12622703-deploy-claude-desktop-for-windows),
  [Claude Desktop on Linux](https://code.claude.com/docs/en/desktop-linux)
- ChatGPT: [Deploy the Windows app](https://learn.chatgpt.com/docs/enterprise/windows-deployment),
  [Manage app updates](https://learn.chatgpt.com/docs/enterprise/manage-app-updates),
  [Linux app](https://learn.chatgpt.com/docs/linux/linux-app)
- Gemini: [gemini.google/desktop](https://gemini.google/desktop/),
  [Use the Gemini app for Windows](https://support.google.com/gemini/answer/18263854)
- Copilot: [Deploy the unified Microsoft Copilot application](https://learn.microsoft.com/en-us/windows/client-management/deploy-unified-copilot-app),
  [Microsoft Copilot update policies](https://learn.microsoft.com/en-us/windows/client-management/copilot-update-policy-control)
- Manifests: `microsoft/winget-pkgs` (`Anthropic.Claude`, `OpenAI.ChatGPT`, `Google.GeminiDesktop`,
  `Microsoft.Copilot`, `Microsoft.365Copilot`) and `Homebrew/homebrew-cask` (`claude`, `chatgpt`,
  `google-gemini`, `gemini`, `microsoft-365-copilot`), read 2026-10-23.
