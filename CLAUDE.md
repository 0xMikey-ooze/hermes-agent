# CLAUDE.md — Swarm Agent Rules

## Context Management (MANDATORY)


### Subagent Delegation Rules
- Reading 3+ files → spawn a subagent, get back a summary
- Exploring an unfamiliar directory → spawn a subagent to map it
- Researching how a library/API works → spawn a subagent
- Running tests or builds → spawn a subagent, read the result
- Any task that takes >10 tool calls to understand → delegate it

### Main Session Stays Clean
- Never read entire files into main context unless you are actively editing them
- Use `grep`, `head`, `tail` instead of full file reads when exploring
- Get summaries back from subagents — not raw file contents
- After a subagent completes, keep only its final answer — discard the exploration

### Output Protocol
- Write decisions to `output/shared-context.md` (other teams read this)
- Write your completion summary to `output/team-N-done.md`
- Do NOT explain your thinking in the main session — just act

## Swarm Rules

- You are ONE team in a multi-team swarm. Stay in your lane.
- Only modify files assigned to your team in `output/file-ownership.json`
- Never touch `main` branch — push to your assigned branch only
- Write key architectural decisions to `output/team-N-summary.json` so downstream teams can read them

## Git Rules

- `git add -A && git commit -m "feat(team-N): ..."` after each logical chunk
- Push frequently — don't wait until the end
- Branch: see your task file for the assigned branch name

## Quality Rules

- No `any` types in TypeScript
- No hardcoded secrets — env vars only
- Every new function needs a comment explaining what it does
- If you fix a bug, add a comment explaining what was wrong

---
<!-- Project-specific content appended below by planner -->

## ⚠️ SWARM DISCIPLINE — NON-NEGOTIABLE (read before touching any code)

You do not have creative latitude. You execute the PRD exactly.

**Before writing any code:**
1. Grep the PRD for: `FORK THIS`, `DO NOT reimplement`, `MANDATORY FIRST STEP`, `npm install`
2. If an existing npm package is listed → INSTALL IT. Do not reimplement it.
3. If a repo is listed to fork → clone it, read its exports, IMPORT from it directly.

```bash
# WRONG: writing your own registry.ts that mimics @tambo-ai/react
# RIGHT: npm install @tambo-ai/react && import { TamboComponent } from '@tambo-ai/react'
```

**Verify before every commit:**
- `npm run build` or `tsc --noEmit` must pass BEFORE committing
- `feat: complete X` means X exists, compiles, and works
- No stubs. No placeholders. If blocked → note in `output/blockers.md` and move on.

---

When building UI, components, landing pages, dashboards, or any frontend work:
- Use the `refero` MCP tool to search for real design references and UI patterns
- Call it before building any major component: `mcp__refero__search` with your component name
- Use it for: hero sections, pricing tables, dashboards, auth forms, nav patterns, cards
- Refero shows real production designs — match the quality level you see there
- Do NOT default to generic layouts. Check Refero first, then design above that bar.

## Gemini API Skills
When writing code that uses the Gemini API (@google/genai, @google/generative-ai, or Vertex AI):
- Load skill: `gemini-api-dev` for standard Gemini API best practices
- Load skill: `gemini-interactions-api` for chat, streaming, function calling, structured output
- Load skill: `gemini-live-api-dev` for real-time audio/video/WebSocket streaming
- Load skill: `vertex-ai-api-dev` for Google Cloud Vertex AI deployments
Skills are at: ~/.openclaw/workspace/skills/<skill-name>/SKILL.md

## Anti-TODO Rules (enforced by PostToolUse hooks)

The following markers in code are considered incomplete work and will trigger warnings:
- `TODO`, `FIXME`, `HACK`, `XXX`
- `PLACEHOLDER`, `implement later`, `stub`

If you must leave a TODO, document WHY in output/blockers.md with:
- What needs to be done
- Why it couldn't be done now
- What team/person should handle it

Do NOT commit code with placeholder implementations. Write real code or skip the feature.

## Scope Guard Rules (enforced by PreToolUse hooks)

Each team can only write to files in their ownership boundaries:

| Team | Allowed Paths |
|------|--------------|
| backend | src/api, src/middleware, src/models, prisma, lib, utils, db, server, routes, controllers, services |
| frontend | src/components, src/pages, src/app, src/hooks, src/styles, src/ui, public, styles, components, pages, app |
| qa | tests, __tests__, spec, cypress, playwright, e2e |

**All teams** can always write to: .swarm/, output/, PLAN.md, *.md files, config files

If you need to change a file outside your scope:
1. Do NOT attempt to write it
2. Document the needed change in `/workspace/.swarm/cross-team-requests.md`
3. Include: file path, what change is needed, why

## Structured Plan (plan.json)

If `.swarm/plan.json` exists, read it for:
- Your team's specific tasks
- File ownership boundaries
- Interface contracts with other teams
- QA checks to run

This supplements (does not replace) your PLAN.md task file.
