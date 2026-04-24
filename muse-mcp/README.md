# Muse MCP

An MCP server that feeds AI designer agents real-world design inspiration — so instead of generating generic AI slop, they produce grounded, category-appropriate, visually distinctive UI. Muse also learns per-user taste over time from thumbs-up/down feedback.

This is Phase 0/1 of the Muse PRD. See the PRD in the repo root for background.

## What it does

1. Takes a natural-language prompt (`"landing page for a barbershop, warm, masculine, classic"`).
2. Parses it into structured intent (category, mood, density, keywords, anti-patterns) via Haiku.
3. Fans out across real inspiration sources — **Land-book**, **Godly**, **Dribbble** — in parallel, dedupes, caches.
4. Extracts structured style tokens per reference via Sonnet vision.
5. Clusters references into 3–5 stylistic directions and synthesizes one design brief per direction.
6. Re-ranks directions by the caller's learned taste profile.
7. Persists briefs and taste profiles to disk so they survive restarts.

## Tools

| Tool | What it does |
|------|--------------|
| `muse_generate_brief` | End-to-end: prompt → full design brief with 3 directions, palettes, typography, layout archetypes, anti-patterns, and cited references. |
| `muse_fetch_inspiration` | Lower-level: just pull references for a prompt. |
| `muse_get_brief` | Fetch a previously generated brief by id. |
| `muse_extract_style` | Given 1–10 image URLs, return structured style tokens (style-clone use case). |
| `muse_record_feedback` | Thumbs-up / thumbs-down a reference or a direction. Builds the caller's taste profile. |
| `muse_get_taste` | Inspect a user's learned taste profile. |

## Scopes

| Scope | Use for | How Muse behaves |
|-------|---------|------------------|
| `landing_page` | marketing sites, one-pagers | Web sources + landing-tuned Dribbble queries |
| `full_site` | multi-page sites | Same as landing_page, more refs |
| `app_ui` | dashboards, admin, product UI | Web sources; prefer Mobbin once enabled |
| `component` | pricing, nav, hero, auth | Web sources + Refero patterns |
| `logo` | brand marks, logomarks, wordmarks, monograms | Dribbble with logo-tuned queries (`"{category} logo"`, `"{category} logomark"`, `"{category} wordmark"`, `"{category} monogram"`, `"{mood} {category} logo"`), plus `/tags/logo-design`, `/tags/branding`, `/tags/monogram`, `/tags/wordmark`. Synthesis uses a logo-specific system prompt that outputs mark archetype, shape-language cues, construction grid hints, and logo-specific anti-patterns. |

**Inspiration, not imitation.** Every synthesis prompt (web + logo) carries an explicit rule: the brief must yield ORIGINAL work that shares *language* with the cluster (weight, grid, era, mood), never *identity*. The brief cites references with a short "why" per ref — what idea it contributed — so the designer can trace lineage without copying.

## Install & run

```bash
cd muse-mcp
npm install
cp .env.example .env           # paste your ANTHROPIC_API_KEY
bun run src/index.ts           # or: npm run build && node dist/index.js
```

Muse is a stdio MCP server — register it in your MCP host (Claude Desktop, Cursor, OpenClaw, etc.):

```jsonc
// ~/.config/Claude/claude_desktop_config.json (or equivalent)
{
  "mcpServers": {
    "muse": {
      "command": "bun",
      "args": ["run", "/absolute/path/to/muse-mcp/src/index.ts"],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

## Using it in your project

Three integration paths, pick whichever fits your stack.

### 1. MCP host (Claude Desktop / Cursor / OpenClaw / any MCP-aware agent)

Register it once as above, then just ask your agent things like:

- "Use muse to generate a logo brief for a vintage barbershop in St. Kitts."
- "Use muse_fetch_inspiration to pull 20 coffee shop landing pages."
- "I loved the third reference in that brief — record it as a love for user `jesse`."

The agent discovers the 6 tools via `tools/list` and calls them directly. No code.

### 2. Node / Bun app — embed Muse via the MCP SDK

```ts
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "bun",
  args: ["run", "/abs/path/to/muse-mcp/src/index.ts"],
  env: { ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY! },
});
const client = new Client({ name: "my-app", version: "1.0" });
await client.connect(transport);

// Generate a logo brief.
const res = await client.callTool({
  name: "muse_generate_brief",
  arguments: {
    prompt: "logo for a vintage barbershop in St. Kitts",
    scope: "logo",
    directions: 3,
    num_references: 30,
    user_id: "jesse",
  },
});
const { brief } = JSON.parse(res.content[0].text);
console.log(brief.directions[brief.recommended_index]);

// Teach Muse which direction you liked.
await client.callTool({
  name: "muse_record_feedback",
  arguments: {
    user_id: "jesse",
    feedback: {
      kind: "direction",
      brief_id: brief.id,
      direction_index: brief.recommended_index,
      verdict: "love",
    },
  },
});
```

### 3. Direct import (same repo / monorepo)

If your project lives alongside `muse-mcp/` (as in hermes-agent), skip MCP entirely:

```ts
import { generateBrief } from "../muse-mcp/src/pipeline/orchestrator.js";
import { applyFeedback } from "../muse-mcp/src/taste/taste.js";

const brief = await generateBrief({
  prompt: "logo for a specialty coffee shop, analog + warm",
  scope: "logo",
  userId: "jesse",
  directions: 3,
  numReferences: 30,
});

// Later, when the human picks a reference they liked:
applyFeedback("jesse", {
  kind: "reference",
  reference_id: brief.directions[0].references[2].id,
  verdict: "love",
});
```

### Typical flow in an AI designer agent

```
1. user: "make me a landing page for a barbershop"
2. agent → muse_generate_brief({prompt, scope: "landing_page", user_id})
3. Muse returns { brief: { directions: [...], recommended_index } }
4. agent designs/generates using direction[recommended_index]
5. user reacts ("love this palette", "no, the 2nd direction felt generic")
6. agent → muse_record_feedback(...) for each reaction
7. next request: Muse now filters rejected refs + boosts liked patterns
```

Feedback is cumulative across sessions because Muse persists briefs + taste profiles to `MUSE_CACHE_DIR` (default `.muse-cache/`).

## Configuration

All config is env-driven. See `.env.example`.

| Var | Default | Purpose |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | *(required at call time)* | Used for intent, extraction, synthesis |
| `MUSE_INTENT_MODEL` | `claude-haiku-4-5-20251001` | Stage 1 |
| `MUSE_EXTRACTION_MODEL` | `claude-sonnet-4-6` | Stage 3 vision |
| `MUSE_SYNTHESIS_MODEL` | `claude-sonnet-4-6` | Stage 4 |
| `MUSE_SOURCES` | `landbook,godly,dribbble` | Comma-separated source toggles |
| `MUSE_CACHE_DIR` | `.muse-cache` | Disk location for briefs / refs / taste |
| `MUSE_HTTP_TIMEOUT_MS` | `15000` | Per-request timeout for scrapes |
| `MUSE_MAX_REFERENCES` | `60` | Cap per call |
| `MUSE_MAX_EXTRACT_CONCURRENCY` | `4` | Vision calls in parallel |

## Taste learning

Muse learns per-user taste by translating each feedback event into weighted deltas on a bag-of-words profile over mood, components, layout archetype, distinctive choices, and per-role palette colors. Scoring uses `tanh`-squashed average of these weights, so one strong like doesn't dominate forever.

```jsonc
// Teach Muse you love a reference:
{
  "tool": "muse_record_feedback",
  "arguments": {
    "user_id": "jesse",
    "feedback": {
      "kind": "reference",
      "reference_id": "dribbble:a1b2c3...",
      "verdict": "love"
    }
  }
}

// Ban a whole direction:
{
  "tool": "muse_record_feedback",
  "arguments": {
    "user_id": "jesse",
    "feedback": {
      "kind": "direction",
      "brief_id": "7f4c...",
      "direction_index": 1,
      "verdict": "reject"
    }
  }
}

// Inspect:
{ "tool": "muse_get_taste", "arguments": { "user_id": "jesse", "top_n": 8 } }
```

`reject` hard-excludes that reference from future briefs for this user; `dislike` subtracts weight but doesn't ban. `love` is ~2x a `like`.

Next time you call `muse_generate_brief` with the same `user_id`, Muse will:

1. Filter out rejected references
2. Rank remaining references by taste score *before* clustering
3. Include a "caller taste signals" block in the synthesis prompt so the LLM surfaces patterns you've preferred

## Sources

| Source | Good for | Implementation |
|--------|----------|----------------|
| **Land-book** | SaaS / product landing pages | HTTP + cheerio |
| **Godly** | Editorial / agency web | HTTP + cheerio |
| **Dribbble** | Category shots — barbershop, coffee shop, restaurant, etc. | HTTP + cheerio; respectful UA, caching, per-request timeout |

More sources (Mobbin, Behance, Awwwards) are enumerated in the source registry — each just needs a class implementing `Source.search(args)`.

## Architecture

```
prompt
  │
  ▼
┌────────────────┐
│ intent-parser  │ Haiku → IntentTags
└────────────────┘
  │
  ▼
┌────────────────────┐
│ inspiration-fetch  │ parallel sources, dedupe, cache
└────────────────────┘
  │
  ▼
┌────────────────────┐
│ style-extraction   │ Sonnet vision, bounded concurrency
└────────────────────┘
  │
  ▼  (rank by taste, if user_id)
┌────────────────────┐
│ brief-synthesis    │ cluster → synth direction per cluster
└────────────────────┘
  │
  ▼
Brief (persisted by id)
```

## Development

```bash
bun test                   # run unit tests (no API key needed)
npm run typecheck          # tsc --noEmit
npm run build              # emit dist/
npm run dev                # bun --watch
```

Tests cover: taste weight/score math, reference dedupe, intent cache keys, cluster stability, LLM JSON extraction. They don't hit the network or the API.

## Not yet implemented (deferred from PRD)

- Postgres + pgvector (currently JSON-file KV)
- Redis rate-limit buckets
- R2 image storage / local pHash
- Browserbase + Browser Use fallbacks for scraping
- Anti-plagiarism check on generated outputs
- Eval harness
- Async mode + `brief_id` polling (Muse persists briefs to id today, so adding async is a server-side change only)

These are tracked for Phase 2 per the PRD. The current codebase is end-to-end real — no stubs — for Phase 0/1 scope.
