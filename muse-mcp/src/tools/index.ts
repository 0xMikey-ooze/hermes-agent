import { z } from "zod";
import { zodToJsonSchema } from "../util/zod-to-json.js";
import {
  ExtractStyleInput,
  FetchInspirationInput,
  GenerateBriefInput,
  GetBriefInput,
  GetTasteInput,
  RecordFeedbackInput,
} from "./schemas.js";
import { generateBrief } from "../pipeline/orchestrator.js";
import { fetchInspiration } from "../pipeline/inspiration-fetch.js";
import { extractStylesForReferences } from "../pipeline/style-extraction.js";
import { parseIntent } from "../pipeline/intent-parser.js";
import { briefStore } from "../store/brief-store.js";
import { referenceCache } from "../store/reference-cache.js";
import { applyFeedback } from "../taste/taste.js";
import { tasteStore } from "../taste/taste-store.js";
import { buildSources } from "../sources/registry.js";
import { referenceDedupeKey } from "../util/hash.js";
import { config } from "../config.js";
import type { Reference, SourceName } from "../types.js";

// Shape required by @modelcontextprotocol/sdk ListTools response.
export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (args: unknown) => Promise<unknown>;
}

export const tools: ToolDefinition[] = [
  {
    name: "muse_generate_brief",
    description:
      "Generate a full design brief from a natural-language prompt. Fetches real references, extracts style tokens, clusters into directions, and ranks using the caller's taste profile if user_id is provided.",
    inputSchema: zodToJsonSchema(GenerateBriefInput),
    handler: async (args) => {
      const input = GenerateBriefInput.parse(args);
      const brief = await generateBrief({
        prompt: input.prompt,
        scope: input.scope,
        hints: input.hints,
        numReferences: input.num_references,
        directions: input.directions,
        userId: input.user_id,
      });
      return { brief };
    },
  },
  {
    name: "muse_fetch_inspiration",
    description:
      "Lower-level: pull raw references for a prompt. Parses intent and fans out across enabled sources. Returns references without style extraction.",
    inputSchema: zodToJsonSchema(FetchInspirationInput),
    handler: async (args) => {
      const input = FetchInspirationInput.parse(args);
      const intent = await parseIntent(input.prompt, { scope: input.scope });
      const allSources = buildSources();
      const filtered = input.sources
        ? allSources.filter((s) => (input.sources as SourceName[]).includes(s.name))
        : allSources;
      const refs = await fetchInspiration(intent, {
        limit: input.limit ?? 30,
        sources: filtered,
      });
      return { intent, references: refs };
    },
  },
  {
    name: "muse_get_brief",
    description:
      "Fetch a previously generated brief by id. Used for async polling or re-opening a past brief.",
    inputSchema: zodToJsonSchema(GetBriefInput),
    handler: async (args) => {
      const input = GetBriefInput.parse(args);
      const brief = briefStore.get(input.brief_id);
      if (!brief) throw new Error(`brief not found: ${input.brief_id}`);
      return { brief };
    },
  },
  {
    name: "muse_extract_style",
    description:
      "Given 1-10 image URLs, extract structured style tokens (palette, typography, layout archetype, components, distinctive choices). Powers the style-clone use case.",
    inputSchema: zodToJsonSchema(ExtractStyleInput),
    handler: async (args) => {
      const input = ExtractStyleInput.parse(args);
      const ttl = new Date(
        Date.now() + config.styleCacheTtlDays * 864e5,
      ).toISOString();
      const refs: Reference[] = input.image_urls.map((url) => {
        const hash = referenceDedupeKey(url);
        const id = `user:${hash}`;
        // Reuse cached extraction if we've seen this exact image before.
        const existing = referenceCache.getReference(id);
        if (existing) return existing;
        const ref: Reference = {
          id,
          source: "refero",
          source_url: url,
          image_url: url,
          thumbnail_url: url,
          tags: [],
          cache_expires_at: ttl,
          hash,
        };
        referenceCache.putReference(ref);
        return ref;
      });
      const withTokens = await extractStylesForReferences(refs);
      return {
        results: withTokens.map((r) => ({
          id: r.id,
          image_url: r.image_url,
          style_tokens: r.style_tokens ?? null,
        })),
      };
    },
  },
  {
    name: "muse_record_feedback",
    description:
      "Record like/dislike feedback on a reference or a direction so Muse can learn this user's taste. Verdicts: love, like, meh, dislike, reject. Reject also excludes the reference from future briefs for this user.",
    inputSchema: zodToJsonSchema(RecordFeedbackInput),
    handler: async (args) => {
      const input = RecordFeedbackInput.parse(args);
      const result = applyFeedback(input.user_id, input.feedback);
      return {
        user_id: input.user_id,
        sample_count: result.profile.sample_count,
        affected_references: result.affected_references,
      };
    },
  },
  {
    name: "muse_get_taste",
    description:
      "Inspect a user's learned taste profile: top liked moods/components/archetypes/palettes and samples count. Useful for debugging and for agents to surface the learned preferences.",
    inputSchema: zodToJsonSchema(GetTasteInput),
    handler: async (args) => {
      const input = GetTasteInput.parse(args);
      const profile = tasteStore.get(input.user_id);
      if (!profile) {
        return {
          user_id: input.user_id,
          sample_count: 0,
          top_moods: [],
          top_components: [],
          top_archetypes: [],
          top_distinctive: [],
          top_palette: {},
          avoided_moods: [],
          avoided_components: [],
        };
      }
      const n = input.top_n ?? 10;
      return {
        user_id: profile.user_id,
        updated_at: profile.updated_at,
        sample_count: profile.sample_count,
        top_moods: topN(profile.mood_weights, n),
        top_components: topN(profile.component_weights, n),
        top_archetypes: topN(profile.archetype_weights, n),
        top_distinctive: topN(profile.distinctive_weights, n),
        top_palette: topPaletteByRole(profile.palette_role_weights, n),
        avoided_moods: bottomN(profile.mood_weights, n),
        avoided_components: bottomN(profile.component_weights, n),
        liked_references: profile.liked_references,
        rejected_references: profile.rejected_references,
      };
    },
  },
];

function topN(bag: Record<string, number>, n: number): Array<{ key: string; weight: number }> {
  return Object.entries(bag)
    .filter(([, w]) => w > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([key, weight]) => ({ key, weight }));
}

function bottomN(bag: Record<string, number>, n: number): Array<{ key: string; weight: number }> {
  return Object.entries(bag)
    .filter(([, w]) => w < 0)
    .sort((a, b) => a[1] - b[1])
    .slice(0, n)
    .map(([key, weight]) => ({ key, weight }));
}

function topPaletteByRole(
  weights: Record<string, Record<string, number>>,
  n: number,
): Record<string, Array<{ hex: string; weight: number }>> {
  const out: Record<string, Array<{ hex: string; weight: number }>> = {};
  for (const [role, bucket] of Object.entries(weights)) {
    out[role] = Object.entries(bucket)
      .filter(([, w]) => w > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, n)
      .map(([hex, weight]) => ({ hex, weight }));
  }
  return out;
}

export function getTool(name: string): ToolDefinition | undefined {
  return tools.find((t) => t.name === name);
}

// Re-export z so the server can namespace errors cleanly.
export { z };
