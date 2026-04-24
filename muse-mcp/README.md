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
