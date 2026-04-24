import { config } from "../config.js";
import { callVision, parseJsonBlock } from "../llm/anthropic-client.js";
import { referenceCache } from "../store/reference-cache.js";
import type { Reference, StyleTokens } from "../types.js";
import { log } from "../util/logger.js";

const SYSTEM = `You are a senior design director extracting structured style tokens from a single design screenshot.

Return ONLY valid JSON matching this exact shape:
{
  "palette": [{"hex": "#rrggbb", "role": "bg" | "fg" | "accent" | "muted"}],
  "typography": {
    "headline": {"family": "font family or null", "weight": "e.g. 700", "style": "e.g. display-serif"},
    "body": {"family": "font family or null", "weight": "e.g. 400"},
    "pairing_vibe": "1 line — the pairing in words"
  },
  "layout": {
    "archetype": "e.g. asymmetric editorial, centered SaaS hero, broken-grid magazine",
    "density": "sparse" | "balanced" | "dense",
    "grid": "optional short grid description"
  },
  "components": ["detected UI patterns, e.g. pricing table, logo marquee, split hero"],
  "motion_hints": ["short imagined motion cues, or empty"],
  "mood": ["3-6 adjectives"],
  "distinctive_choices": ["3-5 things that make this NOT generic — be specific about the craft"]
}

Rules:
- Be concrete. "warm, editorial" beats "nice, modern".
- Pick 4-6 palette swatches max, covering real on-screen color, not assumptions.
- Do not invent components you cannot see.
- distinctive_choices must call out specific craft decisions (typography-image offset, color pairing, empty-space rhythm, etc.). This field is the anti-slop signal.`;

// Stage 3 — extract structured style tokens for a batch of references, in
// bounded parallel. Results are attached to the reference cache so repeat
// briefs skip extraction (the expensive step).
export async function extractStylesForReferences(
  refs: Reference[],
): Promise<Reference[]> {
  const concurrency = Math.max(1, config.maxExtractConcurrency);
  const queue = [...refs];
  const out: Reference[] = [];
  const workers: Promise<void>[] = [];

  const worker = async () => {
    while (queue.length > 0) {
      const ref = queue.shift();
      if (!ref) break;
      if (ref.style_tokens) {
        out.push(ref);
        continue;
      }
      try {
        const tokens = await extractOne(ref);
        referenceCache.attachStyleTokens(ref.id, tokens);
        ref.style_tokens = tokens;
        ref.extracted_at = new Date().toISOString();
        out.push(ref);
      } catch (err) {
        log.warn("extraction failed", { id: ref.id, err: String(err) });
        // Push through without tokens; synthesis can still use title/source.
        out.push(ref);
      }
    }
  };
  for (let i = 0; i < concurrency; i++) workers.push(worker());
  await Promise.all(workers);
  return out;
}

async function extractOne(ref: Reference): Promise<StyleTokens> {
  const raw = await callVision({
    model: config.extractionModel,
    system: SYSTEM,
    user: `Source: ${ref.source}\nTitle: ${ref.title ?? "(none)"}\nExtract style tokens from this screenshot.`,
    imageUrl: ref.image_url,
    maxTokens: 1200,
    temperature: 0.2,
  });
  const parsed = parseJsonBlock<Partial<StyleTokens>>(raw);
  return normalize(parsed);
}

function normalize(raw: Partial<StyleTokens>): StyleTokens {
  return {
    palette: Array.isArray(raw.palette)
      ? raw.palette
          .filter(
            (p): p is { hex: string; role: "bg" | "fg" | "accent" | "muted" } =>
              !!p &&
              typeof (p as { hex?: unknown }).hex === "string" &&
              ["bg", "fg", "accent", "muted"].includes(
                String((p as { role?: unknown }).role),
              ),
          )
          .slice(0, 8)
      : [],
    typography: {
      headline: {
        family: str(raw.typography?.headline?.family),
        weight: str(raw.typography?.headline?.weight) ?? "400",
        style: str(raw.typography?.headline?.style) ?? "sans",
      },
      body: {
        family: str(raw.typography?.body?.family),
        weight: str(raw.typography?.body?.weight) ?? "400",
      },
      pairing_vibe: str(raw.typography?.pairing_vibe) ?? "",
    },
    layout: {
      archetype: str(raw.layout?.archetype) ?? "unknown",
      density:
        raw.layout?.density === "sparse" || raw.layout?.density === "dense"
          ? raw.layout.density
          : "balanced",
      grid: str(raw.layout?.grid),
    },
    components: arr(raw.components),
    motion_hints: arr(raw.motion_hints),
    mood: arr(raw.mood),
    distinctive_choices: arr(raw.distinctive_choices),
  };
}

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v.trim() : undefined;
}

function arr(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0);
}
