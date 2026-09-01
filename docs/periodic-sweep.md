# Periodic source sweep

**Cadence: weekly.** Run `./tools/sweep-csa-sources.sh`.

## Why this exists

DesktopSetup wires CSA tooling into new machines, but nothing in CSA tells DesktopSetup
when there is new tooling to wire. A plugin marketplace gets created, a plugin ships into
an existing marketplace, an MCP server becomes ready — and this repo carries on installing
the set it knew about the day someone last edited it. The gap is invisible from inside the
repo: every script parses, every check passes, and new hires quietly get a smaller toolset
than the people who set their own machines up by hand.

The sweep exists to make that gap visible on a schedule instead of on a coincidence.

## What drifts, and where it has to be fixed

Three different extension points, and knowing which one a finding belongs to is most of
the work:

| # | What appeared | Where it gets wired | Cost of the change |
|---|---|---|---|
| 1 | A new plugin **marketplace** repo | `CSA_MARKETPLACES` + `plugin_marketplace_repo` — **5 scripts** | script edit + `SCRIPT_VERSION` bump in each |
| 2 | A new **plugin** in a registered marketplace | `scripts/csa-plugins.txt` or `scripts/csa-plugins-internal.txt` | one commit to `main`, **no** version bump |
| 3 | A new **MCP server** | `setups=()` in `setup_csa_internal_tools` — **5 scripts** | script edit + `SCRIPT_VERSION` bump in each |

The five scripts for #1 and #3 are `macos-ai-tools.sh`, `macos-update.sh`,
`macos-plugins.sh`, `windows-ai-tools.ps1`, `windows-plugins.ps1`. `check-duplication.py`
will catch you if you update four of them.

Category 2 is the cheap one and the one that matters most in practice — a list-only change
reaches every existing user on their next `macos-update.sh` run without them reinstalling
anything.

## Reading the output

```
$ ./tools/sweep-csa-sources.sh
```

Exit codes: `0` no drift, `1` drift found, `2` **could not complete** — missing `gh`, not
authenticated, or a probe failed. Treat `2` as "I learned nothing", never as "no drift".

Four kinds of line:

- **`UNREGISTERED marketplace`** — a real marketplace with plugins in it that no script
  knows about. Category 1.
- **`not in the install lists`** — published plugins nobody installs. Category 2. This
  will usually be non-empty and that is fine: not every plugin is meant for every hire.
  The question to ask each week is whether any of them have *become* ready, not whether
  the list is empty.
- **`READY TO WIRE`** — an MCP server whose `internal-setup/<name>-setup.sh` exists in the
  gate repo but is not in `setups=()`. Category 3. This is the highest-signal line the
  sweep produces: someone finished a server and it is sitting there unused.
- **`not ready`** — an MCP server repo with no setup script yet. Informational. `csa-zendesk`
  sits here today ("Research and design phase — no implementation yet"). Nothing to do.

## What the sweep deliberately does not flag

- **Forks of registered marketplaces.** `CloudSecurityAlliance/Research-Plugins` is a private
  fork of the internal one and is *behind* it. Registering a fork shadows the real
  marketplace with stale content, so the sweep names it and moves on.
- **Empty marketplaces.** `accounting-plugins` declares `"plugins": []`. It is registered by
  all five scripts and installs nothing. Correct, and not worth a weekly reminder.
- **`csa-*` repos with no "MCP" in the description.** The org has a dozen `csa-ai-exam-*`
  and `csa-research-*` data repos that are not servers. See the caveat below.

## The two ways this sweep can lie to you

Both are under-reporting — it will tell you there is no drift when there is. Neither
produces a visible error, which is why they are written down here.

**1. Parallel probing produces false negatives.** An early version used `xargs -P 12` and
reported three repos as having no `marketplace.json` when all three demonstrably do. A
probe that fails under load is indistinguishable from a repo that genuinely lacks the
file. The script now probes sequentially and separates 404 from every other error,
exiting `2` if any probe fails. **Do not "optimise" it back into parallelism.** A minute
a week is not a problem worth solving.

**2. The MCP heuristic depends on repo descriptions.** A candidate must be named `csa-*`
*and* mention "MCP" in its GitHub description. A new server whose description omits the
word is skipped silently. The script prints how many repos it skipped for this reason, so
if a server you expect is missing from the list, check its description first.

Also worth knowing: **GitHub code search does not work for this.** Querying
`org:CloudSecurityAlliance path:.claude-plugin filename:marketplace.json` returns
`total_count: 0` despite seven manifests existing — code search does not reliably index
dotfile directories or private repos. The contents API is the only trustworthy probe.

## Acting on findings

For category 2 (the common case), the whole change is an edit to
`scripts/csa-plugins-internal.txt` and a PR. For 1 and 3, edit all five scripts, bump each
`SCRIPT_VERSION` to the current `YYYY.MMDDHHSS`, and run `./tools/check-all.sh` before
pushing.

Judgement required, and the sweep cannot make it for you: **a plugin existing is not a
plugin being ready for every new hire.** The sweep reports what is published; deciding
what belongs in a default install is a human call.
