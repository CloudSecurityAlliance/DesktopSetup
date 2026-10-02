# RACI

**Accountable: Kurt Seifried.** One name, deliberately — this repository has had one author
across 167 commits and 102 merged pull requests, and a shared accountability line would be a
fiction.

| Role | Who | What it means here |
|---|---|---|
| **Responsible** | Kurt Seifried, with AI assistance | Writes the scripts, the guards and the docs. Every merged PR to date. |
| **Accountable** | Kurt Seifried | Owns the decision to ship, and owns it when a laptop is left broken. `main` is the release, so this is not theoretical: a merge reaches the next person who runs the one-liner. |
| **Consulted** | Whoever is being onboarded next | The only reliable source of what is actually confusing. Most of the closed issues in [`GOALS.md`](GOALS.md) started as somebody stuck, not as a design review. |
| **Informed** | CSA staff who run these scripts | Through the scripts' own output: the preflight plan before anything happens, and the to-do ledger at the end. |

## The bus factor is one, and that is the main organisational risk

Worth writing down rather than implying. If this repository needed a second maintainer tomorrow,
the obstacles are known:

- **Windows PowerShell 5.1 knowledge.** The non-obvious constraints are documented
  (`ENGINEERING.md`), but they are not common knowledge: `Sort-Object` is not stable, ternaries
  fail at *parse* time, `Set-Content -Encoding utf8` writes a BOM.
- **Both platforms, genuinely.** The parity contract means a change usually has to be made twice
  and can only be fully tested on two machines. Thirteen open issues are macOS-only or
  Windows-only for exactly this reason.
- **Private gate-repo access.** The four internal MCP servers come from
  `CloudSecurityAlliance-Internal/CSA-Plugins`, so anyone maintaining the internal-setup path
  needs access to it.

The mitigation in place is that the guards encode the knowledge rather than the author holding
it: twelve checkers in `tools/` and eleven tests in `tests/`, each one pinning a mistake that
was actually made, with the issue number in the file. A second maintainer inherits the rules
along with the code. That is the deliberate answer to a bus factor of one — not documentation
anyone has to remember to read, but checks that fail.

## What is not covered by anyone

- **No on-call, no paging, and nothing to page.** See
  [`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md) — there is no running service.
- **No formal review of the business case.** [`BUSINESS-CASE.md`](BUSINESS-CASE.md) states how
  it would be falsified, and nobody is assigned to check those conditions on a schedule. That is
  a real gap, not a rhetorical one.
