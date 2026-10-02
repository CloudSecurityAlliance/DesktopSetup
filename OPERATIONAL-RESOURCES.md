# Operational resources

## There is no running service, and nothing to page

**Not applicable in the usual sense, and here is the reasoning rather than a bare N/A.** This
repository ships shell and PowerShell scripts that are fetched and executed on a laptop. Nothing
listens on a port, nothing is deployed, there is no instance to restart, no uptime to measure
and no endpoint to probe. The entire surface is source served by
`raw.githubusercontent.com` and the GitHub API.

So the conventional contents of this file — hosts, environments, dashboards, on-call rota,
runbooks for a degraded service — have no referent. [`RACI.md`](RACI.md) records that there is no
on-call because there is nothing to be on call for.

## But it has runtime dependencies, and they are worth naming

Writing the reasoning out produced something the heading did not: **these scripts fail in other
people's hands when a third party is unavailable, and two of those dependencies are CSA's own.**

| Dependency | What breaks without it | Whose it is |
|---|---|---|
| `raw.githubusercontent.com` serving `HEAD` | The documented one-liners fetch nothing. Total failure, before anything runs. | GitHub |
| `CloudSecurityAlliance-Internal/CSA-Plugins` | The four internal MCP servers are fetched from it per run via `gh api .../contents/internal-setup`. No gate repo, no servers. | **CSA** |
| The user's `gh` authentication | Gate-repo access is checked against the person's own GitHub identity. Without it the servers are skipped — correctly, and the run reports it ([#95](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/95) exists because it used to be skipped silently). | The user |
| PyPI | Every server installs with `uv tool install`. | Python packaging |
| winget / Homebrew / npm registries | Each installs its own layer. | Vendors |
| GitHub Actions `ubuntu-latest` / `windows-latest` | Not a runtime dependency of the *product*, but the only thing that gates a change before it reaches a laptop, which under [ADR-001](DECISIONS-ADR.md) is the whole safety net. | GitHub |

**The second row is the operationally interesting one.** It is a private CSA repository on the
hot path of every install, read live at run time with no pinned ref and no cached copy. If it is
renamed, made inaccessible, or has its `internal-setup/` directory restructured, every CSA
laptop quietly stops getting MCP servers — and the scripts are *designed* to continue past that,
because a missing server must not abort the whole run. The mitigation is that drift is now
reported rather than silent: the installer compares its own list against what the gate repo
actually holds and warns about either direction
([#95](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/95)).

That repository has its own operational note: **it must never be made public**, because it
carries OAuth client secrets in git. That is recorded in `CSA-Plugins/internal-setup/README.md`,
where the people who can change its visibility will see it.

## Recurring work

No schedule, no cron, nothing that runs on its own. The recurring work is human and is
externally triggered:

- **A new MCP server.** Add it to `$CSA_INTERNAL_SETUPS` — a list duplicated across six scripts,
  which `tests/test_internal_setup_lists.py` keeps in step.
- **A new release of anything installed.** The `*-update` scripts exist for this and are run by
  a person.
- **A runner-image or action deprecation.** Currently live: see
  [WAITING-FOR-003](WAITING-FOR.md), which has a date.

## What would make this file applicable

If any of these became true, this stops being a reasoning exercise and needs real content: a
hosted installer or web endpoint; a scheduled job that provisions or audits machines; telemetry
collected from runs; or a mirror of the gate repo that has to be kept in sync. None is true, and
none is planned ([`GOALS.md`](GOALS.md)).
