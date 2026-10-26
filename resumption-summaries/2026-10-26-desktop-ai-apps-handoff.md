## Task State Summary — 2026-10-26 (handoff session for the desktop AI apps work)

**Objective:** Make the desktop-AI-app work transferable to a new AI or person, with one handoff
issue and an easy-to-find pointer at the top of `TODO.md`.

Kurt's ask, verbatim: "can you make sure we document everything, have a handoff issue, etc, so I
can transfer this work to a new AI/session? add a note to todo.md at the top so it's easy to
find."

**Current status:** done. The handoff is
[#168](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/168); `TODO.md` opens with a
"Start here: open handoffs" table pointing at it and at #119.

**What changed since the 2026-10-25 summary (found by re-reading state first, not assumed):**

- A **Windows session** measured #161 on 2026-10-25 and added four commits to #162. They fix four
  Windows defects:
  - winget upgrades the Store ChatGPT under `OpenAI.ChatGPT`, so the hold now pins that id;
  - Copilot from Edge Update is listed as `Microsoft.365Copilot`;
  - Copilot pre-launches windowless at sign-in, so "open" now means "has a window";
  - `*\gemini.exe` was mislabelled "Gemini CLI".

  They record two decisions: only the current Claude build is supported, and the Store is assumed
  (no-Store fallback deferred to #164). They add one fix: `sudo -v` before removing the Homebrew
  Copilot. **Kurt merged #162 on 2026-10-25** (`f2f6473`).
- **#165** (merged 2026-10-26, `e87689c`) installs Claude Desktop on Windows with Anthropic's
  current `ClaudeSetup.exe`. It was needed because non-elevated winget picked the old build
  without Cowork, and the MSIX is refused without admin (`0x80073D28`). #161 was closed as
  completed.
- **Found today, filed as #169:** `check-all.sh` is also red on a **macOS** host since #165, with
  eight Claude-install Pester tests failing (70 passed, 8 failed on untouched `main` `e87689c`).
  The cause is `Join-Path $env:TEMP`, and only Windows sets `TEMP`. CI is green because it runs
  Pester on Windows. It is the mirror image of #163, and the pair is #168's task 1.
- New issues: #163 (my `test_desktop_apps.py` builds Windows paths, so `check-all.sh` is red on a
  Windows host), #164 (no-Store fallback), #167 (Gemini CLI → Antigravity CLI: Google sign-in no
  longer works). PR #166 (ISO 8601 script versions) is open and was left alone.

**What was wrong with the handoff state this morning:**

- The open leftovers were scattered: some only in #161's closed comments, one date-bound (Gemini's
  self-update check after 2026-11-01).
- `TODO.md`'s "On Windows?" note and WAITING-FOR-005 pointed at a closed issue and said nothing
  had run on Windows.
- The review brief still read "open PR, not merged".

**What was done:**

- **#168 created**: the single resume point. It has the status, six tasks in order (first: #163),
  what needs Kurt, a file map, the reasoning, weak points, decisions with dates (and what was
  decided against), a "confirm the state first" block, and the conventions.
- `TODO.md`: a "Start here: open handoffs" table at the very top (#168, #119); the stale Windows
  note replaced.
- `WAITING-FOR.md`: 005 closed with what happened; 006 added (on or after 2026-11-01, Gemini's
  self-update check) and 007 (a Windows machine without the Store, for #164).
- The review brief records its final state at merge.
- Comments pointing to #168 were left on #161 (closed), #119 (with the `sudo -v` change to its
  item 2) and #167 (an unverified lead: `Gemini.app` ships a Google-signed `agy` binary).

**Decisions made:** none new. All of #168's decisions are dated to 2026-10-24 (Kurt) and
2026-10-25 (#161).

**Assumptions used:** that #161's measurements, made by another session, are as recorded in its
comments. They were read, not re-run.

**Open questions / human input needed:**

- Whether to tell Anthropic that `downloads.claude.ai/releases/win32/ClaudeSetup.exe` pins an
  expired certificate (#168, "Needs Kurt").
- The wait policy, if Kurt wants it different.

**Recommended next action:** the next session opens #168 and starts with task 1, #163 and #169.

**Files / artifacts changed:** `TODO.md`, `WAITING-FOR.md`,
`plans/2026-10-25-desktop-ai-apps-review-brief.md`, this file; issues #168 (the handoff) and #169 (new finding); comments on
#161, #119, #167.

**Not on GitHub, and why:** the session transcript (it holds tool output), and a local memory note
on this Mac that now points at #168.

**Confidence level:** high that #168 lists everything still open. It was assembled from #161's
comments, the four commit messages, #165, and the open-issue list, all re-read on 2026-10-26.
Medium on task 4's completeness, because it depends on #161's own "not tested" markers being
exhaustive.
