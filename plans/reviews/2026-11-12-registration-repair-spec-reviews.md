# Plan 2 spec reviews: how each finding was disposed of

Plan: [`plans/2026-11-12-registration-repair.md`](../2026-11-12-registration-repair.md), with its Windows companion
[`plans/2026-11-12-registration-repair-windows.md`](../2026-11-12-registration-repair-windows.md).

Two independent spec reviews (B11), both on `fable`, both on 2026-11-12. Every finding of both was accepted; none
was rejected. Where the re-review moved something the first review placed, the first table says where it is now.

## Review 1, at `a9ab5e4`: 3 blockers, 10 majors, 7 minors, four 1W additions

| Finding | Change made |
|---|---|
| **B1** `verify` launches `elsewhere` registrations, including `uv run --directory`, unconditionally | A12: a `launcher` state; only a direct executable is launched, anything else is `not checked: launcher form`. Tasks 1 and 3; Task 6 row 7. |
| **B2** the with-credentials startup path is never measured | M5 stats token files around one handshake under the real `HOME` and samples network connections. D5 holds `verify` until then. M6 measures the reviewer's mitigating fact (whether `claude mcp get` starts the server). |
| **B3** interpreter-shaping env kept on a re-point; any `-m` module accepted | A12: those keys make the finding `leave` plus a to-do; `SERVERS` pins each module, and another module is left. Task 6 row 8. |
| **M1** one candidate Python, so the incident's state skips the preview | Task 4: five candidates, each `-x`-checked before it runs, `/usr/bin/python3` only with the Command Line Tools. |
| **M2** design-deciding measurements run after the build | Task 0 runs before Task 1, and every task's "Depends on" names its measurement in the measurements file. M3 records `PATH`'s value. A8 leaves bare-name Desktop entries until it is measured. |
| **M3** "worst case is today's state" is wrong while Desktop runs | Review Focus 5 rewritten (a false success is possible). D4: Desktop's config is not written while it runs, with a quit-and-rerun to-do. |
| **M4** Claude Code's own locking is not used | M1 records whether Claude Code takes a lock; Task 2 honours one if found. |
| **M5** symlinked configs are replaced by regular files | A10: a linked config is never written. Refused rather than written through, because the target is usually a dotfile repository, which D2 rules out. |
| **M6** the `.py`'s own Codex and Gemini reads run from the installer's cwd | A11: they run from a fresh empty directory. |
| **M7** G1 on Gemini: folder trust in an empty directory | M7 adds the trust question, measured before G1 merges, because the gate's `HEAD` is live on merge. G1 Step 1 applies it. |
| **M8** `csa-skilljar-setup.sh` passes secret-bearing output as argv | G3, in the gate PR that ships first (D6). Its `.ps1` twin is a static read, so the same PR checks it (re-review, item 2). |
| **M9** A6 routes a one-sided change around `check-parity.py`; "carried over" is the AI's | D3 is new, and the CINO's. "Carried over" is gone. A6 says plainly that `check-parity.py` does not see the change. D3 covers G1 too (re-review, item 2). |
| **M10** "launched as <clients> launch it" over-claims | Task 3 says "launched with its registered command and settings". |
| Minor: `import sys` does not reproduce the first stage | The probe imports `json` and `importlib.resources`. |
| Minor: `#!/bin/sh` + `'''exec'` launchers | Parsed (A12). |
| Minor: "the standard binary exists and runs" is ambiguous | Task 2: it "classifies as not dead", and is never launched as a precondition. |
| Minor: whole-file JSON re-serialisation | Global Constraints: indent detected, trailing newline and key order kept; dropped extended attributes and ACLs stated. |
| Minor: backups share the prune namespace and hold secrets | A13 documents it and keeps the shared cap. Of the nine `~/.claude.json` backups on the CINO's Mac (names read, contents not), two match the pattern; the prune spares the rest. |
| Minor: up to 20 s per launch on every `-update` run | Global Constraints and ENGINEERING.md state up to 24 s per distinct launch, about 96 s for four; M4 measures it; nothing while D5 holds. |
| Minor: G2's severity | D6: "group/other-readable mode; defence in depth", since `~/Library` is `0700`. |
| D1 | Agreed; unchanged, plus the launcher-form note. |
| D2: add (d) | (d) added and made the safe default; (b) only if the CINO wants it; project files never touched. The constant became three-valued in the re-review. |
| D3, D4, D5 (new) | Added as decisions for the CINO, each with its safe default. |
| D6: G2 and M8 alone and first | Decided by the AI under P1. |
| Four 1W additions (BOM/CRLF, `.cmd` shims, ACLs for the `.py`'s own writes, argv visibility on Windows) | In the Windows companion's Task 1W. |
| Codex 0.167 facts unverified by the reviewer | Said so in the plan's "What is already true". |

## Review 2 (re-review), at `762347a`: 5 majors, 7 minors, a size ruling

The re-review found all 13 of review 1's blockers and majors resolved in the text, and D1 to D3 complete. The
coordinator's rulings on its findings are in the right-hand column where they set the fix.

| Finding | Change made |
|---|---|
| **1.** D6 and merge order step 1 rest on a PR that does not exist; step 1 blocks Task 0 needlessly | D6 cites the gate PR once, by number if it exists, otherwise by branch (`fix/desktop-config-0600-no-secret-argv`). Only Task 6 Step 2 depends on it. Task 0 starts at once. |
| **2.** D3 and the gate PRs are incoherent: G1 merges with no D3 condition, and G3's `.ps1` twin check waits in held G2W | D3 now covers every macOS-only behaviour change in either repo, G1 included. D6's PR is the one exception, decided under P1 (safety first). G3's `.ps1` static check is in the gate PR; G2W no longer holds it. |
| **3.** Task 1 tests `dead` before `standard`, so a dead standard binary gets a re-point aimed at itself | The standard path is tested first, before any liveness check. A dead standard binary gets no action: "its setup reinstalls it". Test `dead_standard_binary_no_self_repoint`. |
| **4.** M4 and Task 6 Step 1 launch real servers before M5, assuming a scratch `HOME` means no token, which fails for a keychain token | M5's step 1 became M0, run first from public source only. If any token is outside `HOME`, that server's real launch in M4 and Task 6 Step 1 waits for a go-ahead and uses the stub server meanwhile. |
| **5.** `CSA_REG_DIR` is set inside a function run in a command substitution, so it is lost; and never set under the override | A new `csa_registrations_dir`, called directly, sets it in the caller's shell, under the override too. Tests `reg_dir_set_in_caller_shell`, `reg_dir_created_under_override`. |
| Minor: M2's cleanup expects `identical: yes` after changing a preference on purpose | The comparison excludes `preferences` and the dummy entry; the changed preference is reported by key name and set back by the CINO. |
| Minor: M2 doesn't say who clicks | The CINO changes the preference and quits Desktop; the AI edits and reads the file. |
| Minor: M2's dummy entry needs an absolute interpreter | Every dummy entry runs an absolute, verified Python with the probe script's absolute path (Task 0 rules). |
| Minor: M4 and M6 don't state the result that changes the design | Each measurement now has a "Changes the design if" line. |
| Minor: M5's go-ahead should say the launch may rotate a token | Task 0 Step 2's ask says it. |
| Minor: Task 6 row 4 depends on whether Desktop happens to be running | The `.py` runs `ps` from `PATH`; Task 6 stubs it and runs both branches. |
| Minor: an abandoned write still makes a backup and prunes older ones | Task 2: the backup is made only after the last pre-write stat check, is removed if the write is then abandoned, and pruning runs only after a successful replace and read-back. Test `abandoned_write_leaves_no_backup`. |
| Minor: D2 has three options and one boolean | `LOCAL_SCOPE_ACTION`, one of `"report"`, `"repoint"`, `"todo"`. |
| Size (88 KB) | This file holds both dispositions; the W tasks moved to the Windows companion; Review Focus no longer repeats the tasks' test lists. Every "Depends on" names the measurements file, and Task 0 Step 3 records results there instead of rewriting the plan. |
