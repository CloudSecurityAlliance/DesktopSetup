# Review brief: a rerun audits every CSA MCP registration, re-points a dead one in place, and holds its server check (#179 Plan 2, macOS)

Written 2026-11-15 by the AI that coordinated and documented the build (Claude Code), for a reviewer who should
not take its word for any of this. Template: CloudSecurityAlliance-Internal/CINO-Project-Management-Tools
`system/templates/REVIEW-BRIEF.md`.

## 1. What this is

- **The goal (#179 Part 2, items 1, 2, 5, 6, 7 and 8).** On macOS, a rerun of `macos-ai-tools.sh`,
  `macos-update.sh` or `macos-plugins.sh` finds every registration of the four CSA MCP servers in Claude Code
  (user and local scope), Claude Desktop, Codex and Gemini. Before consent, it shows what is wrong with each.
  After consent it re-points a **dead** one at the standard `~/.local/bin/<entry>`, changing only its command and
  keeping every setting. A second rerun changes nothing.
- **What does the work:** one new stdlib-only Python file, `scripts/csa-mcp-registrations.py`, with three
  subcommands: `plan` (read-only), `apply` and `verify`. Eight new bash functions, byte-identical in the three
  macOS entry scripts, wire it in.
- **What is held:** `verify`, the MCP `initialize` check, is built and tested, but a rerun launches no server
  until the CINO answers D5.
- **State:** one open PR from `feat/registration-repair` (the PR links this brief). Windows is not built; it is
  handed to #184 under the CINO's D3. The real run on the CINO's Mac (Task 6 Step 2) waits for his go-ahead
  after the merge.

## 2. Where everything is

| What | Where |
|---|---|
| Spec | #179 Part 2, and its comments; csa-zendesk#70; #175, #176 and #177 for what is absorbed (the plan's table) |
| Plan | [`plans/2026-11-12-registration-repair.md`](2026-11-12-registration-repair.md): decisions D1–D6, the AI's decisions A1–A13, Global Constraints, Review Focus, Tasks 0–6 |
| Windows companion | [`plans/2026-11-12-registration-repair-windows.md`](2026-11-12-registration-repair-windows.md): Tasks 1W, 4W, G1W, G2W and 6W, for #184 |
| Spec-review dispositions | [`plans/reviews/2026-11-12-registration-repair-spec-reviews.md`](reviews/2026-11-12-registration-repair-spec-reviews.md) |
| Measurements (Task 0) | [`plans/reviews/2026-11-12-registration-repair-measurements.md`](reviews/2026-11-12-registration-repair-measurements.md): M0–M7, the CINO's go-aheads, and "What the plan got wrong" |
| Acceptance (Task 6 Step 1) | [`plans/reviews/2026-11-12-registration-repair-acceptance.md`](reviews/2026-11-12-registration-repair-acceptance.md): 204 of 204 assertions |
| What a run does, for maintainers | `ENGINEERING.md` → "Registration audit and repair" |
| Branch and range | DesktopSetup `feat/registration-repair`, `87d4280..<head>` (26 commits up to `5389e97`, then this brief). The commit bodies hold each review round's findings |
| Gate-repo dependencies, merged | CloudSecurityAlliance-Internal/CSA-Plugins#213 (G2/G3: Desktop config written `0600`, no secret on argv) and CloudSecurityAlliance-Internal/CSA-Plugins#215 (G1: the gate's client probes run from an empty directory) |

**Review SHAs in the commit bodies are pre-rebase.** The branch was rebased onto `main` `87d4280` (#196, #197) in
`c5308c3`. A body that says "the review of `d39f719`" names the tree as reviewed then; the fixing commit is the one
in this branch.

## 3. How to review it, in stages

A stage table stands in for a review map. The work is one PR, and each stage depends only on earlier ones.

| Stage | Question | Paths | Claims |
|---|---|---|---|
| A. Evidence | Do the measurements support the design choices made on them? | the measurements record | 1 |
| B. Audit (`plan`) | Does it read only, print no value, and classify truthfully? | `.py`: readers, `classify`, `decide`, `render`, `plan`, `create_private` | 2–6 |
| C. Repair (`apply`) | Does it change only what the plan showed, only `command`, safely, under every interruption? | `.py`: `apply`, `edit_json*`, `edit_codex`, `replace_file`, `ClaudeLock`, `signals_held`, `exits_on_signals`, `sweep_temps` | 7–17 |
| D. Check (`verify`) | Does it launch only what it should, bounded, and print nothing of a server's? | `.py`: `check_of`, `launch_env`, `run_check`, `exchange`, `end`, `report`, `verify` | 18–21 |
| E. Entry scripts | Is the plan shown before consent, is the agreed plan the one applied, and is the probe sound? | `scripts/macos-*.sh`: `csa_registrations_*`, `repair_csa_registrations`, `confirm`, `csa_on_exit` | 22–26 |
| F. End to end | From a seeded broken state, does one run repair exactly the plan, and a second change nothing? | the acceptance record | 27 |
| G. Docs and the gap | Do the docs say what the code does, and is the Windows gap visible? | `ENGINEERING.md`, `AGENTS.md`, `TODO.md` P1, `FRICTION.md` 007–009, `README.md`, `BACKUP-RESOURCES.md`, the companion | 28–30 |

## 4. How to run it

All on a Mac, from the branch, in the repo root. Nothing here needs a credential or money, and nothing touches the
real `HOME`: every case builds a fixture `HOME`, stub clients and stub servers. One case,
`wiring_real_py_passes_the_probe`, runs the real `.py`'s `--version` and `--interface` only.

| Command | Expected | Time (this Mac) |
|---|---|---|
| `./tools/check-all.sh` | tail: `the checks must not change the working tree — unchanged`, then `all checks passed — note this does NOT prove the .ps1 scripts work on Windows`; exit 0 | ~12 min (701 s on 2026-11-15) |
| `python3 tests/test_mcp_registrations.py` | `all 168 case(s) run passed; 1 SKIPPED, not passed: wiring_windows_twin_exists` | ~2 min |
| `/usr/bin/python3 tests/test_mcp_registrations.py` (needs the Command Line Tools) | the same, on Apple's Python 3.9 | ~3 min |
| `python3 tests/test_mcp_registrations.py --self-test` | 182 mutations, each `caught by <case>`; `self-test passed` | ~4.5 min |
| `python3 tests/test_mcp_registrations.py --only <case>` | one case | seconds |
| `python3 tests/test_headless.py` | every `confirm`: end of input → no, Enter → yes | seconds |
| `pwsh -NoProfile -c 'Invoke-Pester tests/ConfirmStep.Tests.ps1'` | `Confirm-Step` answers no to end of input, in all four `.ps1` | seconds |

The wiring cases need `/bin/bash` 3.2 and `perl`, both stock on macOS. CI runs the suite on ubuntu, and on
`macos-latest` under `python3` and `/usr/bin/python3` (`lint.yml`).

**To see it by hand without touching your configs**, run `plan` in a scratch home:
`HOME=$(mktemp -d) CLAUDE_CONFIG_DIR= CODEX_HOME= python3 -I scripts/csa-mcp-registrations.py plan`. It prints
`not installed` or `no config yet` rows. To see real rows, seed configs there as the acceptance record's table does.
Running `plan` against your real `HOME` is read-only but reads your real configs in memory.

## 5. The bar

- **The spec** is #179 Part 2 and the plan's Global Constraints. Its requests verbatim: the CINO's *"get python
  updated to 3.15, and on rerun fix everything, including already installed mcp servers"* (3.15 became 3.14 by his
  later decision, recorded on #179), and the rule of 2026-10-23, *"we want to check state, make sure we are up to
  date before we reply."*, which A4 applies to the plan and the run.
- **The non-negotiables:**
  - no env **value** is printed, logged, put on a command line, or written anywhere but its own config and that
    config's backup (or the env of a server `verify --run` launches);
  - no token, OAuth-state or credential file is opened, moved or deleted, and no login or logout is run;
  - the person sees every change before agreeing, and only those are made;
  - a working registration is a choice and is not changed (D1); a dead one may be;
  - nothing is created or removed, only re-pointed;
  - files inside repositories (`.mcp.json`, Codex's and Gemini's project configs) are never read or written.
- **Platform:** bash 3.2 under `set -euo pipefail`; Python 3.9 to 3.14, stdlib only, run with `-I`.
- **The order goals are traded in** (the CINO, 2026-11-09): safety and privacy, honesty of claims,
  correctness, wording, speed, cost. Each AI decision below names the rule it was made under.

## 6. Claims to verify

"Case" means a case in `tests/test_mcp_registrations.py`, run with `--only <case>`. Most cases also have a
mutation in `--self-test` that proves they can fail.

| # | Stage | Claim | Where | How to check | "True" means |
|---|---|---|---|---|---|
| 1 | A | Every constant set from a measurement cites it, and each departure from a measurement's branch is recorded as a ruling | the `.py`'s constants; the measurements record | Read `HANDSHAKE_TIMEOUT`, `CLAUDE_LOCK_WAIT`, `LOCK_HOLD_MAX`, `CODEX_ENV`, `DESKTOP_ENV`, `DESKTOP_PATH`, `INHERITS_PATH`, `PASSES_INHERITED_ENV` against M1, M3, M4, M5 | each cites its M; `DESKTOP_PATH = None` and "never break the lock" are labelled AI rulings |
| 2 | B | `plan` writes nothing but its own new plan file at `0600`, and no bytecode | `plan`, `create_private`, `interpreter_runs` (`-I -B`) | cases `plan_writes_nothing`, `probe_writes_no_bytecode`, `token_dirs_unreadable_still_plans` | pass; the bytecode case's control shows the same interpreter writes `.pyc` without `-B` |
| 3 | B | No env value or arg reaches the screen, the log lines or the plan file; the fingerprint hashes key **names** | `Registration.fingerprint`, `plan_document` | cases `plan_file_has_no_values`, `secret_values_never_emitted` | pass |
| 4 | B | `--out` never replaces or removes a file it did not create, and refuses any client's config path, however the volume spells it | `out_refusal`, `create_private`, `config_at`, `discard` | cases `existing_out_left_untouched`, `out_refuses_client_configs`, `out_config_spelled_otherwise_refused`, `discard_spares_a_file_swapped_in`, `failure_removes_only_its_own_plan` | pass |
| 5 | B | A client that cannot be read is `not audited`, never "fine"; one hostile config cannot fail the others; config text cannot forge a row | readers, `audit`, `clean` | cases `codex_list_failure_is_not_absence`, `client_absent_not_installed`, `client_failure_contained`, `hostile_input_contained`, `torn_claude_json_untouched`, `jsonc_gemini_not_audited`, `control_chars_cannot_forge_rows` | pass |
| 6 | B | Its own client calls run from a fresh empty directory, bounded | `run_bounded`, `empty_dir` | cases `client_reads_run_in_empty_dir`, `codex_timeout_kills_its_group` | pass |
| 7 | C | `apply` changes only the approved entry's `command` (and `args` from `["-m", <module>]` to `[]`); every env var and other field, and every other entry, is unchanged | `repointed`, `only_command_changed`, `edit_json_held`, `codex_line_edits` | cases `dead_user_scope_repointed_env_kept`, `json_format_preserved`, `codex_line_edit_keeps_other_fields`, `gemini_extra_fields_kept`, `interpreter_module_form_repairable`, `confinement_check_refuses_a_damaged_entry` | pass; the last one patches the edit four ways and each is refused |
| 8 | C | Only what the agreed plan showed as a re-point, unchanged since, in the same file, is acted on (A4) | `load_approved`, `approval_key`, `apply` | cases `unapproved_finding_not_repaired`, `changed_since_plan_not_written`, `unreadable_plan_file_applies_nothing`, `approval_binds_config_path`, `duplicate_plan_row_resolves_to_leave`, `standard_binary_missing_no_repoint`, `unaudited_plan_reason_is_honest` (a plan the scripts mark `"audited": false` approves nothing, and its reason is not "found after you agreed") | pass |
| 9 | C | The mode is kept; each written config gets exactly one backup, at its mode, never looser; the prune touches only `<name>.bak-<14 digits>`, as `csa-claude-connectors.py` does | `make_backup`, `prune_backups`, `write_temp` | cases `desktop_mode_0600_kept`, `backup_same_mode_and_pruned_to_3`, `prune_spares_other_backup_names`, `backup_looser_than_file_abandons`, `backup_name_never_overwritten`, `backup_rule_matches_connectors` | pass |
| 10 | C | Nothing is written through a symlink (the config or any directory up to `HOME`) or to a hard-linked config | `linked_config`, `other_names` | cases `symlinked_config_refused`, `linked_parent_dir_refused`, `codex_write_time_link_refused`, `hard_linked_config_refused`, `system_links_are_not_config_links` | pass |
| 11 | C | Desktop's config is never written while Desktop runs, or while `ps` cannot tell (D4); Desktop is found by executable path, never by name; it is asked again just before the write | `desktop_running`, `decide`, `apply` | cases `desktop_running_skipped_with_quit_todo`, `desktop_started_after_plan_skipped`, `desktop_state_unknown_at_write_skipped`, `desktop_detected_by_path_not_name` | pass; the config's bytes, inode and mtime unchanged, no backup |
| 12 | C | Claude Code's `<config>.lock` is honoured: waited for at most 10 s, **never broken**, removed only on proof this run made it; a hold past 5 s abandons the write; a locked config gets a to-do naming the lock | `ClaudeLock` | cases `claude_lock_honoured`, `lock_never_removed_without_proof`, `lock_held_too_long_abandons`, `lock_taken_over_is_left` | pass; the holder's lock is still there afterwards |
| 13 | C | A change to the file between read and replace abandons the write with no backup; a read-back that differs restores the backup | `replace_file`, `identity`, `restore` | cases `concurrent_change_aborts_write`, `abandoned_write_leaves_no_backup`, `readback_mismatch_restores`, `codex_readback_mismatch_restores` | pass |
| 14 | C | SIGTERM, SIGHUP or SIGINT at any point leaves no temp file, no lock of its own, no unused backup, no printed value, and exits 143, 129 or 130; a second signal cannot cut the clean-up short; the next run sweeps only a dead run's temp files | `exits_on_signals`, `signals_held`, `new_temp`, `sweep_temps` | cases `signal_mid_write_leaves_nothing`, `signals_held_keeps_the_callers_mask`, `temp_files_are_this_runs_alone`, `stale_temp_files_swept` | pass. The reviewers' matrices (20 points × TERM/HUP/INT, and 80 double-signal runs) are in `d8530bb`'s body |
| 15 | C | No client CLI ever writes; `codex` is asked only `mcp list --json` and `mcp get <name> --json` | `read_codex`, `codex_get` | case `no_client_cli_writes`; acceptance: the real `codex`'s argv log | pass; 7 calls per world, all reads |
| 16 | C | Left alone, with a reason: a working one elsewhere (D1, byte-identical), a launcher form (also behind a renamed link), an interpreter-shaping env key, another module, a dead local-scope entry (D2), a bare-name Desktop entry (A8) | `classify`, `decide`, `executable_kind` | cases `working_elsewhere_byte_identical`, `working_elsewhere_left_and_warned`, `launcher_form_left`, `launcher_behind_another_name_left`, `interpreter_env_keys_left`, `unknown_module_left`, `dead_local_scope_todo_names_rebuild_or_remove`, `desktop_bare_name_unmeasured_left` | pass |
| 17 | C | A second `apply` writes nothing and makes no backup | everything | case `second_run_noop`; acceptance "Run 2 changed nothing" | inode, mtime, bytes unchanged; no new backup |
| 18 | D | `verify` prints none of a server's own text: not its stdout or stderr, name, version or error message. Only fixed lines with a CSA name, a client, a bounded integer and the command | `report`, `exchange`, `answered`, the `F_*` and `OK_CHECK` strings | cases `no_server_text_printed`, `exits_before_answering_masked`, `junk_count_capped`, `interpreter_form_todo_names_its_module` | pass: every printed and ledger line matches `FIXED_LINES`, and no 4-character run of any value appears |
| 19 | D | One launch at a time, each bounded at 24 s (20 + 2 + 2), its process group stopped and reaped, a child it leaves stopped too; all launches held to `VERIFY_BUDGET` 120 s; a stop signal stops the server | `run_check`, `end`, `verify` | cases `silent_server_times_out_and_is_killed`, `orphan_child_is_stopped`, `one_process_at_a_time`, `time_budget_bounds_the_launches`, `signal_during_check_leaves_no_server` | pass; no process of the stub's group survives |
| 20 | D | Never launched: a dead registration, a dead standard binary, a launcher form, an interpreter-shaping key, `$`-expansion, an own `cwd`, a bare-name Desktop entry | `check_of`, `classify` | cases `dead_registration_not_launched`, `dead_standard_binary_not_launched`, `launcher_form_not_launched`, `interpreter_keys_not_launched`, `dollar_env_not_checked`, `own_cwd_not_checked`, `bare_name_desktop_never_launched` (under `verify --run`, with a stub server of the entry's name first on the installer's `PATH`; its mutation resolves Desktop on that `PATH`, and the stub is launched) | pass; for bare-name Desktop, the line `not checked: Claude Desktop's PATH differs …` and no launch |
| 21 | D | D5 is held: `VERIFY_ON_RERUN` is empty, so `verify` without `--run` reads no config and launches nothing, and the plan prints no check row | `VERIFY_ON_RERUN`, `verify`, `render` | `grep -n '^VERIFY_ON_RERUN' scripts/csa-mcp-registrations.py`; cases `verify_held_by_default`, `no_check_rows_while_held`, `rerun_checks_only_allowed_servers`, `token_files_untouched` | `VERIFY_ON_RERUN = frozenset()`; pass |
| 22 | E | The rows are shown in the plan, inside the `Internal MCP servers` block, before consent, and `apply` runs on exactly that plan file after the gate setups; `verify` runs without `--run` | `csa_registrations_preview`, `repair_csa_registrations`, `setup_csa_internal_tools` | cases `wiring_preview_rows_under_internal_mcp_servers`, `wiring_repair_uses_the_previewed_plan`, `wiring_verify_called_without_run`, `wiring_non_member_silent` | pass, for each of the three scripts |
| 23 | E | End of input at the consent prompt is a no, on both platforms | `confirm`, `Confirm-Step` | `python3 tests/test_headless.py`; `tests/ConfirmStep.Tests.ps1` | end of input → DECLINED; each has a control that shows the old form answering yes |
| 24 | E | The fetched `.py` is used only if `--version` prints a version of the scripts' form and `--interface` prints exactly `csa-mcp-registrations interface 1: plan apply verify`, each in the foreground under a 10 s `perl` alarm; anything else, a hang or a missing `perl` is one skip line | `csa_registrations_usable`, `csa_registrations_bounded` | cases `wiring_not_the_audit_skipped`, `wiring_download_not_python_skipped`, `wiring_interface_probe_bounded`, `wiring_ctrl_c_stops_a_hung_probe`, `wiring_perl_missing_skipped`, `wiring_real_py_passes_the_probe` (seven environments, `FORCE_COLOR` and `COLUMNS=12` among them) | pass; after a Ctrl-C no Python survives |
| 25 | E | The Python is found by trying five candidates in order, never running a dangling link, never Apple's stub without the Command Line Tools | `csa_registrations_python` | cases `wiring_python_candidates_in_order`, `wiring_dead_path_python_skipped`, `wiring_apple_python_stub_not_invoked_without_clt`, `wiring_python_probe_bounded` | pass |
| 26 | E | The run directory comes from `mktemp -d`, is removed on every exit path (a declined plan included), and is never taken from the environment | `csa_registrations_dir`, `csa_on_exit`, `unset CSA_REG_DIR` | cases `wiring_reg_dir_removed_when_declined`, `wiring_inherited_reg_dir_never_removed`, `wiring_no_fixed_temp_path`, `wiring_reg_dir_set_in_caller_shell` | pass |
| 27 | F | From a seeded broken state, one run re-points exactly what the plan showed, keeps every setting, mode and backup rule, prints no secret, and a second run changes nothing | all | the acceptance record: its table, "One run re-points exactly what the plan showed", "Run 2 changed nothing" | 204 of 204; the re-pointed set equals the planned set in both worlds |
| 28 | G | The macOS-only gap is recorded, not hidden: no `.ps1` runs the `.py`; the `.py` says `not audited: Windows support is #184 (Task 1W)` on Windows; the twin test SKIPs | `WINDOWS`, `wiring_windows_twin_exists`; `TODO.md` P1; #184 | case `windows_not_audited`; the suite's tail; `git diff 87d4280..HEAD -- 'scripts/*.ps1'` | the SKIP line; the `.ps1` diffs are `Confirm-Step` and version bumps only |
| 29 | G | `ENGINEERING.md` → "Registration audit and repair" says what the code does: every reason string, constant and to-do it quotes comes from the `.py` or the scripts | `ENGINEERING.md` | Compare each backticked span of four or more words in that section with the `.py`'s string constants and `macos-ai-tools.sh`. Run on 2026-11-15: 60 spans; 46 matched verbatim. The other 14 were each traced by hand: a template filled at run time, two constants joined, a tuple shown space-separated, or a CLI command the section says is never used | every span traces to the code; anything the section labels unmeasured is unmeasured in the records |
| 30 | G | The `.py` runs on Python 3.9 with the stdlib only, and its server list matches the six `CSA_INTERNAL_SETUPS` | `SERVERS` | cases `py39_syntax`, `servers_table_matches_spec`, `servers_match_internal_setups`, `no_invisible_characters_in_source`; the suite under `/usr/bin/python3` | pass |

**Two claims that rested on reading now have automated checks** (final review of `fc9614d`). Each has a
mutation in `--self-test` that it catches:
- **The `.py` never opens a token, OAuth-state or credential file.**
  - **The check:** case `token_file_never_opened`. It runs `plan`, `apply` (which re-points a registration
    carrying a token path) and `verify --run` under a Python audit hook, which records any `open` of four
    seeded token files. Two of the four are named by `CSA_ZENDESK_TOKEN_FILE` and `CSA_GW_TOKEN`, in the
    registrations' env and in the installer's own. A control shows the hook records an open.
  - **Its mutation** opens a token path named in a registration's env.
  - **Still a matter of reading:** the hook sees only the `.py`'s own process. Its `open(` and `os.open(`
    calls each open one of these: a client config, that config's backup or temp file, a plan file, a
    `pyvenv.cfg`, a script's first 4 KB (the shebang), the `CSA_TODO_FILE` ledger (appended to, in
    `Todos.flush`), or `/dev/null` (in `show`, once its stdout is lost).
  - **The servers it launches:** case `token_files_untouched` covers the stub servers `verify` launches, and
    M5 covers the real ones, for that launch only.
- **No value reaches the screen or the debug log through the shell.**
  - **The check:** case `wiring_no_value_reaches_the_screen_or_debug_log`. With the real `.py`, under
    `CSA_DEBUG`, it audits a fixture `HOME` whose registrations carry secret values. It re-points the dead
    one, logs a skipped local entry and repairs. It finds no value on the screen or in the log, and the
    repaired config still holds them.
  - **Its mutation** puts a registration's values into a log line.
  - **Also:** case `wiring_log_lines_to_debug_log_only` pins that `log` lines go through the redactor, and
    only when `CSA_DEBUG` made a log.

## 7. Review history

The plan requires every review to run on the strongest model, `fable` (B12). The commit bodies record each
round's findings and rulings, but not the model per round.

**The plan (2026-11-12):** three independent spec reviews and two delta checks, every finding accepted. Review 1
found 3 blockers, 10 majors and 7 minors. Among them: `verify` would have launched `uv run --directory`
registrations; the startup with credentials was never measured; Desktop could overwrite an edit and print a false
success; symlinked configs would be replaced by files. Review 2 found 5 majors (a dead standard binary
re-pointed at itself; `CSA_REG_DIR` lost in a command substitution) and review 3 one (M2's order meant Desktop
never started with the dummy). Dispositions: the spec-review file.

**Task 0, the measurements:** the measurement review's six docs-only findings (`49f1502`), a wording check
(`b96efa6`). M2 and M5 ran with the CINO's go-ahead, verbatim *"Both, now (Recommended)"* (2026-11-13).

**Task 1, `plan`: four review rounds.**

| Round (tree as reviewed) | Main findings | Fixed in |
|---|---|---|
| 1 (`fba8c54`) | the liveness probe wrote a `.pyc` per module into the interpreter's own stdlib; a config behind a **linked parent directory** read as a plain file and would have been written through; one hostile client failed all four; control characters in a project path could **forge a plan row**; a plan nobody saw could be left for `apply` | `bec1e59` |
| 2 (`01e07cf`) | a lone surrogate failed the whole audit; a failed run left its plan file; macOS's `/tmp` read as a config link; invisible characters were written into the source by the edit tool | `fe0b1b5` |
| 3 (`e62c775`) | **`--out ~/.claude.json` replaced that config**; an entry's `type` reached the plan file raw; invisible characters cleaned by list, not by category | `b731cc6` |
| 4 (`a9f9a94`) | on a case-insensitive volume `--out ~/.CLAUDE.json` passed the check; a failed run could delete a file swapped in for the plan | `e80b933` |

Then the A8 ruling (`543f1c7`, below).

**Task 2, `apply`: four review rounds.**

| Round | Main findings | Fixed in |
|---|---|---|
| 1 (`d39f719`) | SIGTERM or SIGHUP mid-write **left a `0600` temp file holding the env values, and the lock**; six guards had no test; a header look-alike in a multi-line TOML string; a hard-linked config silently detached; the lock removed without checking it was still this run's | `b9be376` |
| 2 (`b417a67`) | a signal between the lock's `mkdir` and its record left the lock; `restore` leaked a temp on a signal; the sweep could delete a concurrent run's live temp; SIGINT printed a traceback | `c6794e0` |
| 3 (`79aa251`) | **a regression that broke "never break Claude Code's lock":** an interrupt from `os.mkdir` made the clean-up remove the holder's lock (deterministic in process; 6 in 300 real-signal runs on 3.9); five surviving mutants; a second signal aborted the clean-up | `d8530bb`: create and record in one signal-held step; 0 in 300 afterwards |
| 4 (`f566ac2`) | approved, three lows: the suite failed with SIGINT ignored; a mask-restore mutant survived; the cost of holding signals undocumented | `c3972b5` |

**Task 3, `verify`: two review rounds.**

| Round | Main findings | Fixed in |
|---|---|---|
| 1 (`bbb6f82`) | **four ways past the masking of server text** (an unmasked arg echoed by argparse, a value split over two lines, an escaped value, a value cut at the 64 KB tail), so the subject's "no secret in what it prints" was false; an orphan grandchild survived; total run time unbounded; a renamed link to `pipx` was launched | `76cee8b`: the ruling (P1) to print **none** of a server's text; `VERIFY_BUDGET`; realpath launcher check |
| 2 (`c2678ee`) | approved, two lows: the interpreter-form to-do opened a bare Python prompt; the skipped-line count was unbounded | `c290771` |

**Task 4, the entry scripts: three review rounds.**

| Round | Main findings | Fixed in |
|---|---|---|
| 1 (`f18337c`) | **Ctrl-D at `Proceed? [Y/n]` was taken as yes** and a run went on to re-point a config (all four bash `confirm`s; the `.ps1` answered no but logged it wrongly); the held line named a command the run deletes; an HTML sign-in page gave three tracebacks; a left finding was printed twice | `cc4cf45` |
| 2 (`8dc8699`) | a file that parses but is not the audit ran and failed noisily, or did nothing and said nothing | `c5308c3` (an interface probe with `--help`) |
| 3, delta (`c5308c3`) | the **real** `.py` failed that probe under `FORCE_COLOR` (3.14 colours argparse) or `COLUMNS=40`, so the audit was skipped as "a sign-in page"; a Ctrl-C during a hung probe left the Python running; the comment claiming every pre-consent run was bounded was false | `548c18d`: `--version` and `--interface` written outside argparse; a foreground `perl` alarm |

**Task 5, the docs:** reviewed with `548c18d`: approved, with doc follow-ups (D3 recorded in both plans, the
companion's Task 1W completed, two nits), fixed in `628f000`. A follow-up comment on #179 corrected the probe
description and D6's attribution.

**Task 6 Step 1, acceptance (`5389e97`):** 204 of 204. Two harness bugs and one seed error (a non-URL
allowlist that csa-google-workspace refuses) are recorded under its "Harness corrections"; no code changed.

**The whole branch (`fc9614d`, PR #201): approved,** with every promise held under test. Three changes came of
it, in the commit after `fc9614d`:
- **A minor.** `wiring_ctrl_c_stops_a_hung_probe` failed whenever the suite ran with SIGINT ignored (a `&` job,
  `nohup`), because the shell it starts inherited the ignore. `Rig.start` now resets SIGINT. Verified under
  `trap '' INT` on both Pythons: it fails at `fc9614d` and passes now.
- **A nit.** When the audit was skipped before consent, a dead entry was reported "found after you agreed to
  the plan". The scripts now mark the plan they hand `apply` `"audited": false`, and `apply` says
  `found by the repair's own check, because the plan you agreed to could not audit the registrations; not
  changed — run again` (case `unaudited_plan_reason_is_honest`).
- **The brief's two hand-checked claims and claim 20's gap** now have automated cases, each with a mutation
  (section 6).

**Mutation testing throughout:** the suite's `--self-test` applies 188 mutations, each caught by the case named
for it. Survivors kept by design: dropping `O_NOFOLLOW` (equivalent under `O_CREAT|O_EXCL`), and dropping the
in-memory confinement assert (`repointed` cannot break it unless itself broken; case
`confinement_check_refuses_a_damaged_entry` shows the assert catches a broken one).

## 8. Decisions and known limits

**The CINO's decisions.**
- **D3, decided** 2026-11-13. His choice, verbatim: *"Ship macOS first (Recommended)"*. So this PR merges when
  reviewed and green, and Windows is #184.
- **D1, D2, D4 and D5 are unanswered,** so the build ships each safe default, one constant each:
  `REPOINT_WORKING_ELSEWHERE = False`, `LOCAL_SCOPE_ACTION = "todo"`, `WRITE_DESKTOP_WHILE_RUNNING = False`,
  `VERIFY_ON_RERUN = frozenset()`. An answer changes the constant and its pinning test.

**The AI's decisions** (each with the rule it was made under):
- **D6** (2026-11-12, P1): the gate's G2/G3 fixes shipped first and alone, as
  CloudSecurityAlliance-Internal/CSA-Plugins#213, merged on the CINO's go.
- **Never break Claude Code's lock** (2026-11-12, P1): the measurement review's departure from M1's "same
  protocol". Cost: a crashed session's leftover lock blocks Claude Code's repair until removed; the to-do names it.
- **Bare-name Desktop entries stay "not checked"** (2026-11-13, P1): M3's Desktop `PATH` is one Mac's, and possibly
  Desktop's fallback. `DESKTOP_PATH = None`.
- **D4 keeps its default after M2** (2026-11-13, P1): the edit survived a running Desktop and its quit, but the
  preference-change case was not measured.
- **`verify` prints no server text** (2026-11-13, P1, privacy): masking is a deny-list and cannot be made complete.
- **A pre-existing `--out` file is refused and left, never removed** (2026-11-12, P1), where two review items
  conflicted.
- **Reworded from the plan, under P2 (honesty):** the bare-name Desktop reason (M3 had measured one Mac) and the
  held-check line (M5 had measured the launch).

**Known limits, deliberate:**
- **Windows:** nothing runs. A dead Windows registration stays dead and unreported, as before. Tracked: #184,
  `TODO.md` P1, the SKIP. `check-parity.py` cannot see this (A6).
- **A working registration elsewhere is left** (D1), so the incident's shape is repaired only once it is dead.
- **A dead local-scope entry is left with a to-do** (D2): the incident's surviving local entry on the CINO's Mac will
  be reported, not fixed.
- **Re-serialising JSON can change a file's bytes without changing a value** (whitespace, `\u` escapes, number
  forms), and `os.replace` drops extended attributes and ACLs. Documented in `ENGINEERING.md`.
- **Claude Code's own backups in `~/.claude/backups/`** are not counted in the three-copy cap.
- **The `plan` and `apply` processes run under no overall bound;** their child calls do (`ENGINEERING.md` → Run
  time).
- **#200** (pre-existing): a `set -u` abort under bash 3.2's EXIT trap exits 0. Not fixed here.
- **#199:** `-update`'s and `-plugins`'s plans do not list the tool rebuilds their setups make (a Plan 1 gap, filed
  by Task 4).

## 9. Where the author is least confident

1. **Real-machine run time is unmeasured.** The isolated acceptance took about 2 s a run, with the gate setups,
   the plugin sync and the network stubbed out. Task 6 Step 2, on the CINO's Mac, records the real figure.
2. **Windows.** No line of the Windows half exists. The companion's assumptions (Desktop's config path, `.cmd`
   shims, locks, ACLs, `selectors` on pipes, process groups) are all unmeasured.
3. **Claude Desktop writing an old copy back.** M2 showed an edit survives Desktop running and quitting, not
   whether a preference change while it runs rewrites the file. D4 never writes while Desktop runs, but `ps` is
   asked a few milliseconds before the replace, and a Desktop started in that window, or installed outside
   `/Applications` and `~/Applications`, is not seen.
4. **`setsid` grandchildren.** `verify` stops a server's process group. A process that leaves the group escapes the
   stop. No CSA server does that today, and nothing checks that one never will.
5. **Client versions move.** Codex's `mcp list --json` shape was measured on 0.167.2 and passed on 0.169.0; Gemini's
   secret-name rule was read from 0.67's bundle, and 0.68 was present but never run; Claude Code's lock was measured
   on 2.1.323, and its stale limit was not measured.
6. **Linux.** The scripts are macOS-only, but CI runs the suite on ubuntu, in fixtures. The `.py`'s paths (Desktop
   under `~/Library`, `ps -axo comm=`) are macOS's, and nothing claims it is right on a Linux desktop.
7. **The acceptance ran `macos-plugins.sh` only, with the gate setups and `claude` stubbed.** `-ai-tools` and
   `-update` are covered by the byte-identical functions and the `wiring_` cases, and the `CSA_TODO_FILE` ledger
   path was not exercised end to end.

## 10. What is not verified

- **Task 6 Step 2, the real run on the CINO's Mac,** after the merge, with his go-ahead.
- **Whether a server reads its token at startup.** M5 saw no change and no connection, but `atime` does not move on
  that volume, so a read is invisible.
- **A server's behaviour after the first `initialize`** (tool calls, later refreshes): outside M5's window.
- **Desktop's `PATH` on any other Mac,** and a successful shell-environment extraction on this one.
- **Windows PowerShell 5.1's `Read-Host` at end of input** (measured on pwsh 7.6 only).

## 11. What to assess, and how to report

**Dimensions:** correctness; safety (data loss, a config left torn or more permissive, a lock broken); privacy (a
value on screen, in a log, on argv, in a file, or a token touched); honesty of the plan rows, to-dos and docs
against behaviour; fitness for a staff Mac running a client while the installer runs.

**For each finding:** severity (blocker, should-fix or minor), location (`file:function` or `file:line`), a concrete
failure scenario with its input, a suggested fix, and whether you verified it by running something.
