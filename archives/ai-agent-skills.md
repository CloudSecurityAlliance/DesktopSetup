# AI Agent Skills: Per-Project Context for AI Coding Agents

## The Problem

Tools like Claude Code, Cursor, Gemini CLI, and Codex are installed globally on your machine (that's what `macos-install.sh` handles). But the AI context they need varies per project. A Cloudflare Workers project needs different knowledge than an AWS Lambda project or a pure React app.

Installing skills globally clutters every project with irrelevant context. The AI loads skills it doesn't need, which wastes context window and can cause confused recommendations (e.g., suggesting Cloudflare patterns in an AWS project).

## The Solution: Project-Scoped Skill Installation

Agent Skills are documentation packages that AI coding agents auto-load to provide accurate, current guidance for specific platforms and tools. They follow the [Agent Skills standard](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) and work across Claude Code, Cursor, OpenCode, Codex, and others.

The approach: maintain an inventory of useful skills with match criteria, then install only the relevant ones per-project.

## How It Works

1. **Machine setup** (`macos-install.sh`): Installs the AI CLI tools themselves
2. **Project setup** (this file): AI reads the skills inventory below, inspects the current project's files and dependencies, and installs only the matching skills locally
3. Skills install into the project directory (e.g., `.agents/skills/`) — no global pollution

### Triggering a Skills Check

Reference this file from your global `~/.claude/CLAUDE.md`:

```markdown
When starting work in a new project and the user asks to set up skills, check
https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/ai-agent-skills.md
for the skills inventory. Inspect the project's files (package.json, config files, language,
frameworks) and install skills that match. Do not install skills globally.
```

Then in any project, ask the AI: "check my skills inventory and install what's relevant."

### Installation Commands

Skills can be installed via multiple methods:

```bash
# Via npx skills CLI (recommended, works across agents)
npx skills add <repo-url> --yes

# Via Claude Code plugin marketplace
/plugin marketplace add <org/repo>

# Via Cursor
# Settings > Rules > Add Rule > Remote Rule (Github) with <org/repo>
```

---

## Skills Inventory

### cloudflare/skills

| | |
|---|---|
| **Source** | https://github.com/cloudflare/skills |
| **Install** | `npx skills add https://github.com/cloudflare/skills --yes` |
| **Skills included** | 8 skills, 2 slash commands, 4 MCP doc servers |

**What it provides:**

| Expertise type | Details |
|---|---|
| Product selection (strategic) | Decision trees for choosing between 60+ Cloudflare products — "I need storage" routes you to KV vs D1 vs R2 vs Durable Objects based on your requirements |
| Implementation (deep) | Full API references and TypeScript code patterns for Workers, Agents SDK (v0.3.7+), Durable Objects, Wrangler CLI. Production-ready config and code, not tutorials |
| Guided scaffolding | Step-by-step walkthroughs for building AI agents and MCP servers on Cloudflare, with templates and troubleshooting |
| CLI reference | Comprehensive Wrangler command reference covering every binding type (KV, R2, D1, Vectorize, Queues, Containers, Workflows, Pipelines, Secrets Store) |
| Live docs access | Four remote MCP servers providing real-time access to Cloudflare documentation, bindings, build status, and observability |

**What it does NOT cover well:** Security product configuration (WAF, DDoS, bot management), networking setup (Tunnels, Spectrum), dashboard/UI workflows, cost optimization.

**Install when ANY of these are true:**
- `wrangler.jsonc`, `wrangler.json`, or `wrangler.toml` exists in the project
- `package.json` has dependencies on `wrangler`, `agents`, `@cloudflare/*`, or `cloudflare`
- `.mcp.json` references `*.mcp.cloudflare.com` endpoints
- `worker-configuration.d.ts` exists
- Project directory structure includes `workers/`, `worker/`, or `functions/` with Cloudflare-style code
- User states they are building on Cloudflare Workers, Pages, or the Cloudflare developer platform

**Skip when:**
- No Cloudflare configuration or dependencies detected
- Project targets AWS (Lambda, CDK), GCP (Cloud Functions, Cloud Run), Azure, or Vercel without Cloudflare
- Pure frontend project with no serverless/edge deployment to Cloudflare

**Individual skills breakdown:**

| Skill | What it knows | When it matters |
|---|---|---|
| `cloudflare` | Product navigator with decision trees across all 60+ products | Any Cloudflare project — helps pick the right service |
| `agents-sdk` | Agent class, state management, RPC, Workflows, MCP, React hooks | Building stateful AI agents or real-time WebSocket apps |
| `durable-objects` | SQLite, alarms, WebSockets, Hibernation API | Stateful coordination: chat, games, booking, counters |
| `wrangler` | Every CLI command and `wrangler.jsonc` config pattern | Any project that deploys to Cloudflare |
| `sandbox-sdk` | Secure code execution API | AI code interpreters, sandboxed execution environments |
| `web-perf` | Core Web Vitals (FCP, LCP, TBT, CLS) auditing | Performance optimization for any web project on Cloudflare |
| `building-ai-agent-on-cloudflare` | Agent scaffolding templates and patterns | Starting a new AI agent project from scratch |
| `building-mcp-server-on-cloudflare` | MCP server scaffolding with OAuth | Starting a new MCP server project from scratch |

---

## Adding New Skills

When you find a useful skills repo, add an entry following this pattern:

```markdown
### org/repo-name

| | |
|---|---|
| **Source** | https://github.com/org/repo |
| **Install** | `npx skills add https://github.com/org/repo --yes` |
| **Skills included** | N skills |

**What it provides:**
- (summarize the expertise types and depth)

**Install when:**
- (file patterns, dependencies, or user intent that indicate this project needs these skills)

**Skip when:**
- (conditions where installing would be irrelevant or counterproductive)
```

Key things to document for each skill repo:
- **Expertise depth**: Is it strategic/product-selection level, or deep implementation-level, or both?
- **What it does NOT cover**: Prevents false expectations
- **Concrete detection signals**: File names, dependency names, config patterns — things an AI can check programmatically
