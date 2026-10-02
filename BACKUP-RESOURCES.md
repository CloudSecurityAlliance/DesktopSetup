# Backup resources

## This project holds no state of its own

**Not applicable in the direction the question is usually asked, and here is the reasoning.**
The repository is source. Its own recovery story is git and GitHub: clone it and you have
everything. There is no database, no object store, no volume, no uploaded artifact. Nothing here
would need restoring, because nothing here is the only copy of anything.

The debug logs the scripts write (`~/Library/Logs/CSA-DesktopSetup/`,
`%LOCALAPPDATA%\CSA-DesktopSetup\`) are deliberately disposable — written to be read or emailed
once, and no part of the system reads them back.

## But it writes backups onto other people's machines, and nothing cleans them up

Writing the reasoning out turned up the finding this heading would have hidden. **The only
backup behaviour in this project is performed on a user's laptop, against a file that holds
credentials, with no retention policy at all.**

`scripts/csa-claude-connectors.py:73`:

```python
def write_json(path, data, stamp):
    """Back up, then replace atomically, so a crash never leaves half a config file."""
    shutil.copy2(path, f"{path}.bak-{stamp}")
```

The file is `~/.claude.json`. Measured on the authoring machine on 2026-10-02: **94,540 bytes,
84 top-level keys**, among them `oauthAccount` and `customApiKeyResponses`. (Key *names* only —
reading the values would be the thing being warned about.)

So every run that changes something leaves another timestamped copy of a credential-bearing file
beside the original. Nothing removes them, nothing ages them out, and the user is told the suffix
but not that the copies persist:

```
Done. Backups end in .bak-<stamp>. Restart Claude Code to pick up the changes.
```

The backup itself is correct and should stay — it is paired with an atomic `os.replace`, so a
crash cannot leave a half-written config, and that is the right design for a file Claude Code
depends on. The gap is retention.

**This has already happened in the sibling repository, with worse content.** Two files were
found on this machine during the same session:

```
~/.csa_google_gmail_calendar/client_secret.json.20260929-pre-bom-fix.bak
~/.csa_google_workspace/client_secret.json.20260929-pre-bom-fix.bak
```

Those were written by an older version of a CSA-Plugins setup script during a one-off encoding
fix, and they contain **real OAuth client secrets**. The current CSA-Plugins scripts no longer
create them, so this is historical rather than ongoing — but it is the same pattern one step
further along, and it is why this is written down instead of dismissed.

## What should change

Filed as [#143](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/143). Not fixed
here, because it is a behaviour change to a tool merged this week
([#130](https://github.com/CloudSecurityAlliance/DesktopSetup/pull/130)) and it deserves its own
review rather than being folded into a documentation pass. The shape of the fix:

1. **Keep one backup, not one per run** — a single `.bak` replaced each time, or prune to the
   most recent two or three.
2. **Say that the copy persists and holds credentials**, in the line that already names the
   suffix. A user who is told "backups end in `.bak-<stamp>`" has not been told to delete them.
3. **Create it with the source file's permissions.** `shutil.copy2` preserves mode, which is
   right — worth asserting rather than relying on, since the whole point is that this file is
   sensitive.

## Housekeeping for anyone reading this on their own machine

The two `client_secret.json.*.bak` files above are safe to delete, and should be. Rotation, if
ever needed, is by resetting the secret in the Google Console — never by committing a new file.
