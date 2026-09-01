#!/usr/bin/env bash
# Weekly sweep for CSA sources this repo should be wiring up but isn't yet.
#
#   ./tools/sweep-csa-sources.sh              # the two CSA orgs
#   ./tools/sweep-csa-sources.sh --all-orgs   # every org your gh token can see
#   ./tools/sweep-csa-sources.sh --quiet       # only print drift
#
# Three things drift, in three different places, and nothing else notices:
#
#   1. A new plugin marketplace repo appears  -> CSA_MARKETPLACES (5 scripts)
#   2. A new plugin lands in a registered marketplace -> scripts/csa-plugins*.txt
#   3. A new csa-* MCP server repo appears    -> setups=() in setup_csa_internal_tools
#                                                (5 scripts)
#
# NOT part of check-all.sh, deliberately: this needs the network and a gh token with
# CSA-Internal access. CI has neither, and a check that cannot pass in CI is a check
# that gets deleted. Run it by hand, or from the scheduled routine — see
# docs/periodic-sweep.md.
#
# Exit codes:  0 = no drift   1 = drift found   2 = could not run (no gh / not authed)
#
# ── The one thing to know before you change the probing ───────────────────────────
# Probe repos SEQUENTIALLY. An earlier version of this sweep ran `xargs -P 12` and
# reported three repos as having no marketplace.json when all three demonstrably do.
# The failure mode here is silent and asymmetric: a probe that errors under
# parallelism looks exactly like a repo that legitimately has no manifest, so the
# sweep under-reports and you conclude "no drift" when there is drift. This script
# therefore probes one at a time and distinguishes 404 (a real absence) from any
# other error (a probe that failed), reporting the latter loudly rather than
# folding it into the "no" pile. ~200 repos takes about a minute. That is fine for
# something that runs weekly.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

# ── output ──────────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  B=$'\033[1m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; D=$'\033[2m'; N=$'\033[0m'
else
  B=''; R=''; G=''; Y=''; D=''; N=''
fi
QUIET=0
step()  { [[ $QUIET -eq 1 ]] || printf '\n%s==> %s%s\n' "$B" "$1" "$N"; }
ok()    { [[ $QUIET -eq 1 ]] || printf '    %s%s%s\n' "$G" "$1" "$N"; }
drift() { printf '    %s%s%s\n' "$Y" "$1" "$N"; }
err()   { printf '    %s%s%s\n' "$R" "$1" "$N"; }
note()  { [[ $QUIET -eq 1 ]] || printf '    %s%s%s\n' "$D" "$1" "$N"; }

ORGS="CloudSecurityAlliance CloudSecurityAlliance-Internal"
for arg in "$@"; do
  case "$arg" in
    --all-orgs) ORGS="" ;;
    --quiet)    QUIET=1 ;;
    -h|--help)  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) err "unknown argument: $arg"; exit 2 ;;
  esac
done

command -v gh >/dev/null 2>&1 || { err "gh not installed"; exit 2; }
gh auth status >/dev/null 2>&1 || { err "gh not authenticated — run: gh auth login"; exit 2; }

if [[ -z "$ORGS" ]]; then
  ORGS="$(gh api user/orgs --jq '.[].login' 2>/dev/null | tr '\n' ' ')"
fi

AI_TOOLS="scripts/macos-ai-tools.sh"
GATE_REPO="CloudSecurityAlliance-Internal/CSA-Plugins"
found_drift=0
probe_errors=0

# ── source of truth ─────────────────────────────────────────────────────────────
# Parsed out of the scripts rather than restated here. This file is a sixth place
# the lists could drift, and the whole point is to not have one.
registered_marketplaces() {
  sed -n '/^CSA_MARKETPLACES=(/,/^)/p' "$AI_TOOLS" \
    | grep -oE '"[^"]+/[^"]+"' | tr -d '"'
}

wired_mcp_servers() {
  sed -n '/^  local setups=(/,/^  )/p' "$AI_TOOLS" \
    | grep -oE '[a-z0-9-]+-setup\.sh' | sed 's/-setup\.sh$//'
}

listed_plugins() {
  cat scripts/csa-plugins.txt scripts/csa-plugins-internal.txt 2>/dev/null \
    | grep -v -E '^[[:space:]]*(#|$)' | sed 's/@.*//'
}

# ── repo enumeration ────────────────────────────────────────────────────────────
step "Enumerating repos"
ALL_REPOS="$(mktemp)"; trap 'rm -f "$ALL_REPOS"' EXIT
for org in $ORGS; do
  gh repo list "$org" --limit 1000 --json nameWithOwner --jq '.[].nameWithOwner' 2>/dev/null
done | sort -u > "$ALL_REPOS"
repo_count=$(wc -l < "$ALL_REPOS" | tr -d ' ')
note "$repo_count repos across: $ORGS"

# ── 1. marketplaces ─────────────────────────────────────────────────────────────
# One sequential probe per repo for .claude-plugin/marketplace.json. See the note at
# the top about why this is not parallel.
step "1. Plugin marketplaces"
REGISTERED="$(registered_marketplaces)"
unregistered=""
while read -r repo; do
  [[ -n "$repo" ]] || continue
  probe_out=$(gh api "repos/$repo/contents/.claude-plugin/marketplace.json" 2>&1 >/dev/null)
  case $? in
    0) ;;
    *) if echo "$probe_out" | grep -q "Not Found\|repository is empty"; then
         continue
       else
         err "probe failed: $repo :: $(echo "$probe_out" | head -1)"
         probe_errors=$((probe_errors + 1)); continue
       fi ;;
  esac
  if echo "$REGISTERED" | grep -qxF "$repo"; then
    note "registered: $repo"
  else
    unregistered="$unregistered$repo"$'\n'
  fi
done < "$ALL_REPOS"

if [[ -n "$unregistered" ]]; then
  while read -r repo; do
    [[ -n "$repo" ]] || continue
    # A fork of an already-registered marketplace is not a new marketplace — it is a
    # stale copy, and registering it would shadow the real one. Report it as noise,
    # not as drift. (CloudSecurityAlliance/Research-Plugins is exactly this.)
    parent=$(gh api "repos/$repo" --jq '.parent.full_name // empty' 2>/dev/null)
    if [[ -n "$parent" ]] && echo "$REGISTERED" | grep -qxF "$parent"; then
      note "fork of registered $parent — ignoring: $repo"
      continue
    fi
    count=$(gh api "repos/$repo/contents/.claude-plugin/marketplace.json" --jq '.content' 2>/dev/null \
              | base64 --decode 2>/dev/null \
              | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("plugins",[])))' 2>/dev/null || echo "?")
    if [[ "$count" == "0" ]]; then
      note "empty marketplace (0 plugins) — nothing to install yet: $repo"
      continue
    fi
    drift "UNREGISTERED marketplace: $repo ($count plugins)"
    drift "  -> add to CSA_MARKETPLACES + plugin_marketplace_repo in all 5 scripts, bump SCRIPT_VERSION"
    found_drift=1
  done <<< "$unregistered"
fi
[[ $found_drift -eq 1 ]] || ok "all marketplaces registered"

# ── 2. plugins inside registered marketplaces ───────────────────────────────────
step "2. Plugins in registered marketplaces"
LISTED="$(listed_plugins)"
plugin_drift=0
for repo in $REGISTERED; do
  manifest=$(gh api "repos/$repo/contents/.claude-plugin/marketplace.json" --jq '.content' 2>/dev/null \
               | base64 --decode 2>/dev/null)
  [[ -n "$manifest" ]] || { err "could not read manifest: $repo"; probe_errors=$((probe_errors + 1)); continue; }
  mkt=$(echo "$manifest" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name",""))' 2>/dev/null)
  missing=$(echo "$manifest" \
    | python3 -c 'import json,sys
d=json.load(sys.stdin)
for p in d.get("plugins",[]):
    print(p.get("name") if isinstance(p,dict) else p)' 2>/dev/null \
    | while read -r p; do
        [[ -n "$p" ]] || continue
        echo "$LISTED" | grep -qxF "$p" || echo "$p"
      done | tr '\n' ' ')
  if [[ -n "${missing// /}" ]]; then
    drift "$mkt: not in the install lists -> ${missing% }"
    plugin_drift=1
  fi
done
if [[ $plugin_drift -eq 1 ]]; then
  drift "  -> add the ones that are ready to scripts/csa-plugins-internal.txt"
  drift "     (list-only change: one commit to main, no SCRIPT_VERSION bump)"
  found_drift=1
else
  ok "every published plugin is referenced by an install list"
fi

# ── 3. MCP servers ──────────────────────────────────────────────────────────────
# Local per-user MCP servers follow a naming convention: lowercase csa-<thing> in the
# public org (csa-google-workspace, csa-skilljar, csa-zendesk). Each is wired up by a
# csa-<thing>-setup.sh in the gate repo's internal-setup/ directory, which is what
# setup_csa_internal_tools fetches. A server is "ready to wire" exactly when that
# setup script exists — that is the signal this section reports on, because a repo
# existing tells you nothing about whether it is finished.
#
# Two filters, because `csa-*` alone is far too broad — the org has a dozen csa-ai-exam-*
# and csa-research-* data repos that are not servers and never will be. A repo has to
# both carry the prefix AND say "MCP" in its description to be treated as a candidate.
# That is a heuristic and it can miss: a new server whose description omits "MCP" will
# be skipped silently, so the skipped count is printed rather than hidden. If a server
# ever goes missing from this list, the description is the first thing to check.
step "3. MCP servers"
WIRED="$(wired_mcp_servers)"
mcp_drift=0
skipped_noise=0
while read -r repo; do
  name="${repo##*/}"
  case "$name" in
    csa-[a-z0-9]*) ;;
    *) continue ;;
  esac
  # skip the hosted server's own infrastructure repos
  case "$name" in csa-mcp|csa-plugins*) continue ;; esac
  if echo "$WIRED" | grep -qxF "$name"; then
    note "wired: $name"
    continue
  fi
  desc=$(gh api "repos/$repo" --jq '.description // ""' 2>/dev/null)
  if ! echo "$desc" | grep -qi 'mcp'; then
    skipped_noise=$((skipped_noise + 1))
    continue
  fi
  if gh api "repos/$GATE_REPO/contents/internal-setup/${name}-setup.sh" >/dev/null 2>&1; then
    drift "READY TO WIRE: $name — internal-setup/${name}-setup.sh exists but is not in setups=()"
    drift "  -> append ${name}-setup.sh to setups=() in all 5 scripts, bump SCRIPT_VERSION"
    mcp_drift=1
  else
    note "not ready: $name — no internal-setup/${name}-setup.sh yet"
    note "           $(echo "$desc" | cut -c1-72)"
  fi
done < "$ALL_REPOS"
[[ $skipped_noise -eq 0 ]] || note "($skipped_noise other csa-* repos have no 'MCP' in their description — not treated as servers)"
if [[ $mcp_drift -eq 1 ]]; then
  found_drift=1
else
  ok "no MCP server is waiting to be wired up"
fi

# ── summary ─────────────────────────────────────────────────────────────────────
printf '\n'
if [[ $probe_errors -gt 0 ]]; then
  err "$probe_errors probe(s) failed — results are INCOMPLETE, do not read this as 'no drift'"
  exit 2
fi
if [[ $found_drift -eq 1 ]]; then
  printf '%sdrift found%s — see docs/periodic-sweep.md for what to do with each kind\n' "$Y" "$N"
  exit 1
fi
printf '%sno drift%s — every CSA source is wired up\n' "$G" "$N"
exit 0
