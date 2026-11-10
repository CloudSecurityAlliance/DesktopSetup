## Task State Summary — 2026-11-10 (Python: 3.15 move reversed, 3.14 everywhere)

**Objective:** The session started as "install Python 3.15 for the MCP servers" (#179). It became "document that CSA stays on
Python 3.14, and file issues so every repo picks 3.14".

Kurt's asks, verbatim, in order:
1. "ok check the issues but we need to update desktopsetup to install python 3.15 for all the mcp servers/etc"
2. "ok wait. do we need to stick to python 3.14? we can do that if 3.15 is still not ready with wheels/etc"
3. "ok lets docum,ent we're sticking to 3.14 and file issues against everything to pick 3.14, CINO-Engineering, the mcp
   servers, etc."
4. Asked whether to keep 3.15 under DEC-025 or reverse the fleet, he chose **"Reverse to 3.14"**.
5. "lets make it 100% consistent, 3.14, and we'll upgrade to 3.15 in a few months once it is fully ready"

**Current status:** the documentation and the issues are done. **No script has changed.** #179's work (the standard-build
guard, and the rerun repair) is open and is the next step.

**What changed:**
- **Repo tidy-up on entry:** merged PR #166 (ISO 8601 script versions). It was green, mergeable and waiting on nobody, and
  it sets the version format any later script change will use.
- **Decision recorded:** DEC-025 gained a 2026-11-10 amendment, the 2026-11-06 amendment is marked superseded in place,
  and DEC-032's Python row is corrected (CINO-Engineering PR #313, merged).
- **Tracker:** CINO-Engineering #312, with the sweep script in a comment. #277 (the 3.15 move) is closed as superseded.
- **22 per-repo issues, all linked from #312.** Two were closed on filing because they were already consistent:
  csa-google-workspace #532 and csa-google-gmail-calendar #51. Open:
  - Moving back from 3.15: CSA-Document-Pipeline #194, CINO-Plugins #176 (vate).
  - Stray pins: csa-zendesk #94 (`uv.lock` says `>=3.10`), csa-skilljar #132 (`.python-version` 3.12).
  - Free-threaded guard: CSA-Plugins #197.
  - Below 3.14: Customer360-Backend #1005, Customer360-Frontend #199, Training-Plugins #137, CINO-Scout #23,
    SecID #277, SecID-Client-SDK #43, SecID-Data-disa.mil #6, SecID-Server-API #35, SecurityControlsCatalog #44,
    ai-landscape #25, CSA-IT-Support-CPE-Cert-Maker #8, openclaw-audit #5.
  - Dormant since 2025: ai-integration-airtable #1, customgptai_manager #1, marketing-events-database #2.
- **Comments:** CSA-Document-Pipeline #191 (hold the 3.15 check out of the plugin release); #179 (retitled; Part 1
  re-scoped, with Part 2 findings); #157 (markitdown is doable on 3.14).
- **This repo:** PR #180 (merged) corrected `ENGINEERING.md`, which still said `CSA_PYTHON_MIN=3.10`. It also records the
  free-threaded trap.

**Key findings** (measured 2026-11-10, macOS arm64):
- **3.15's blocker is a wheel.** `onnxruntime` 1.31.1 has no cp315 wheel, so `markitdown` cannot install on 3.15.
  Unpinned, `markitdown[all]` silently resolves to **0.0.2** instead of failing.
- **3.14 has everything.** pyyaml, pymupdf, csa-google-workspace and markitdown 0.1.9 (with onnxruntime 1.31.1) all
  install on the standard 3.14.10.
- **The free-threaded trap.** In an isolated uv install directory, `uv python find 3.14` returns `python3.14t` when that
  is the only uv-managed 3.14, and once the standard 3.14 is installed too, it returns the standard build.
  `3.14+gil` never downloads (uv 0.13.7). `uv tool list --show-python` prints the same thing for both builds.
- **The gate's literal decides on most runs.** DesktopSetup's `-update` and `-plugins` never set
  `CSA_PYTHON_PREFERRED`, so the gate's literal `3.14` decides there. Only `-ai-tools` passes a version.
- **Nothing checks that a registered MCP command still runs,** in any client, in either repo. The macOS venv repair also
  skips a venv whose interpreter was deleted (`-x` is false for a dangling link). Details with file:line are on #179.

**Decisions made:**
- **2026-11-10, Kurt:** 3.14 everywhere, then 3.15 "in a few months once it is fully ready", all at once. Recorded in
  DEC-025 and on #312 the same day.
- **The AI's, under the goal order (correctness, then wording):**
  - Install sites use plain `3.14` plus a free-threaded check, never `+gil`.
  - Already-consistent repos got an issue closed on filing rather than an open issue with nothing to do.
  - Dormant repos got issues too, because "everything" was the ask.

**A mistake to own:** my first recommendation to stay on 3.14 came before I had read DEC-025, and it presented the
onnxruntime gap as new. It wasn't: DEC-025 had already recorded it and handled it per package. I corrected that, and
put the per-package option back to Kurt. He chose to reverse anyway.

**Assumptions used:**
- **Wheel availability was measured on macOS arm64 only.** Windows and Linux are inferred from onnxruntime's published tag
  list.
- **The sweep sees only what GitHub's tree API returns for default branches.** Repos with no Python pin are not covered.

**Risks / uncertainties:**
- **CSA-Document-Pipeline's plugin release (#191) must not ship the 3.15 check** before #194 lands, or every staff user
  breaks.
- **vate's 0.3.x releases are on 3.15** until CINO-Plugins #176 lands.

**Human input needed (Kurt):**
1. **The floor question** on three public packages: SecID-Client-SDK #43 (`>=3.9`), SecID-Server-API #35 (3.10–3.13)
   and openclaw-audit #5 (`>=3.10`). Raising them to 3.14 locks out outside users on older Pythons.
2. **Go or wait on implementing #179 on 3.14:** the standard-build guard, and the rerun repair across both repos.
3. **Two unrelated gate-repo defects, not filed:** `csa-zendesk-setup.ps1` never defines `$CsaDebug`/`$CsaLog`, so it
   writes no Windows debug log; and its "KEEP IN SYNC … check-duplication.py" comments are enforced by nothing.

**Recommended next action:** implement #179 Part 1 (the standard 3.14 build, plus `CSA_PYTHON_PREFERRED` in the
`-update`/`-plugins` scripts) together with CSA-Plugins #197, then Part 2 (the rerun repair). Do it subagent-driven, with
an independent review per task.

**Not on GitHub, and why:** the issue-generator script and the measurement scratch venvs. They lived in a session scratch
directory and are reproducible from #312's sweep script and the commands quoted in #179 and #157. No transcripts.

**Confidence:** high for what is filed and recorded (each issue's table was read from the repo's default branch the same
day). Medium for Windows wheel availability on 3.14, which was not measured.
