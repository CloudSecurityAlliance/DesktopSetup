# Business case

## Why this exists

**To move the question from "can the AI do this?" to "should we do this?"**

The AI is already technically capable of editing a Zendesk ticket, replying to an email,
publishing a course in Skilljar, reading a comment thread on a Google Doc. Those capabilities
exist, they are built, and CSA owns the servers that expose them. What stops a member of staff
from using them is never the capability — it is that the server is not installed, or installed
against the wrong Python, or installed but never signed in, or signed in but Claude Desktop was
not restarted so it cannot see it.

While that is true, every conversation about AI-native work is a conversation about plumbing.
Someone asks "could the AI triage this queue?" and the honest answer is "probably, once we work
out why `csa-zendesk` is not showing up on your laptop". The interesting question — *is routing
customer replies through an AI a good idea, under what review, with what audit trail* — never
gets asked, because the prerequisite never arrives.

DesktopSetup's job is to make capability the assumption rather than the achievement. When one
command takes a laptop handed over an hour ago to a state where every CSA MCP server is
installed, current and authenticated, then "can it edit a ticket" stops being a question anyone
asks. What is left is a business judgement: **should it, in this case, with whose sign-off, and
how would we know afterwards.** That is a question worth the organisation's attention. The other
one is not.

## What it costs to not have this

Measured, not estimated. All from this repository's own record:

- **The maintainer took the slow path.** To pick up one new MCP server, the person who owns this
  repository ran the full installer — Xcode CLI tools, Homebrew, Node, Python, pandoc, typst,
  1Password, Claude Desktop, ChatGPT — because the fast path that does exactly that job was
  named "plugins only" and never mentioned MCP servers
  ([#89](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/89)). If the author pays
  that cost, everyone does.
- **A stock Mac never got Python at all.** The check looked for `python3` rather than for a
  *usable* version, so a machine with Apple's 3.9 passed and then failed later, elsewhere
  ([#53](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/53)).
- **Windows users got no local MCP servers**, for an entire release, because one script was
  missing one call ([#65](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/65)).
- **An unaccepted Xcode licence became five confusing symptoms** instead of one actionable stop
  ([#87](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/87)).
- **Nobody could tell what they had run.** Six of ten scripts reported a stale version and no
  version reached the debug log ([#113](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/113)).

Each of those is a person stopped, and each one converts an AI question into an IT question.

## Who it is for, in order

Per [`BUILD-FOR-YOURSELF-FIRST.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/BUILD-FOR-YOURSELF-FIRST.md):

1. **The person building the AI tooling** — because when the builder is the constraint, every
   hour spent re-provisioning a laptop is an hour not spent building.
2. **CSA staff who are handed a laptop and expected to work AI-natively** — the case above.
3. **Wider CSA, and eventually volunteers**, which is a different and harder problem: it adds
   people who cannot be asked to open a terminal, and it is deliberately not what this is yet.

## Why a script rather than something else

A managed-device profile (MDM, Intune) is the conventional answer and is not available for this:
CSA laptops are not uniformly managed, the fleet spans macOS and Windows, and the thing being
installed is partly *CSA-private* — four MCP servers fetched from a private gate repository
against the user's own GitHub identity. An MDM push cannot carry a per-person credential
handshake, and that handshake is the point: each server ends up authenticated as that person,
not as a shared identity.

The honest alternative is a written runbook, and the record above is what a runbook produces. A
runbook cannot check that `uv` picked the right interpreter, cannot notice that `python3` is
Apple's 3.9, and cannot tell the reader which version of itself they followed.

## How we would know this was the wrong call

Stated plainly, because a business case that cannot be falsified is an advertisement:

- If staff stop needing the MCP servers — if the work routes through hosted connectors or a
  web UI instead — then provisioning laptops is the wrong layer and this should be retired
  rather than maintained.
- If the servers become installable from a public registry with no CSA-private step, most of
  this collapses into `uv tool install` and a one-page README.
- If the fleet becomes uniformly managed, an MDM profile is a better vehicle for everything
  except the per-person credential handshake.

None of those is true today. The first would be good news for CSA and should be welcomed rather
than resisted.

## Related

- [`GOALS.md`](GOALS.md) — what success looks like, read off this repository's record
- [`RACI.md`](RACI.md) — who is accountable
- [`README.md`](README.md) — what it installs and how to run it
