import { randomUUID } from "node:crypto";
import { config } from "../config.js";
import { callText, parseJsonBlock } from "../llm/anthropic-client.js";
import { scoreReference, scoreReferenceSet } from "../taste/taste.js";
import { tasteStore } from "../taste/taste-store.js";
import type {
  Brief,
  Direction,
  IntentTags,
  Reference,
  TasteProfile,
} from "../types.js";
import { log } from "../util/logger.js";

const SYSTEM_WEB = `You are a senior design director synthesizing a structured design brief.

Given:
- an intent (category, audience, mood, density, constraints, anti-patterns)
- a cluster of design references with extracted style tokens
- optional taste signals from the caller (patterns they like, patterns they reject)

Produce ONE direction as JSON:
{
  "name": "short memorable direction name — 2-4 words",
  "palette": [{"hex": "#rrggbb", "role": "bg" | "fg" | "accent" | "muted"}],
  "typography": {
    "headline": {"family": "string or null", "weight": "e.g. 700", "style": "e.g. display-serif"},
    "body": {"family": "string or null", "weight": "e.g. 400"},
    "pairing_vibe": "1 line"
  },
  "layout": {"archetype": "...", "density": "sparse|balanced|dense", "grid": "..."},
  "components": ["concrete patterns this direction uses"],
  "motion": {"hints": ["short motion cues"]},
  "anti_patterns": ["slop patterns this direction explicitly rejects"],
  "reference_whys": [{"id": "<reference id>", "why": "1 sentence on what this ref contributes"}]
}

Rules:
- The direction must feel specific to the category and audience. Avoid generic SaaS voice unless the category genuinely is SaaS.
- Pull concrete values from the reference style_tokens (palettes, archetypes). Don't invent colors that aren't present across the cluster.
- Anti-patterns: be specific. "no centered hero with purple gradient", "no three-tier pricing with middle highlighted", etc.
- Respect the caller's taste signals if given — boost liked patterns, avoid rejected ones.
- INSPIRATION, NOT IMITATION. Describe a direction the designer can build ORIGINALLY. Do not reproduce any single reference's layout, copy, imagery, or trade dress. If two directions would end up too close to a single ref, differentiate them.`;

const SYSTEM_LOGO = `You are a senior brand designer synthesizing a LOGO DIRECTION from a cluster of mark references.

Given:
- an intent (brand category, audience, mood, era, constraints, anti-patterns)
- a cluster of logo references with extracted style tokens
- optional taste signals from the caller

Produce ONE direction as JSON:
{
  "name": "short memorable direction name — 2-4 words",
  "palette": [{"hex": "#rrggbb", "role": "bg" | "fg" | "accent" | "muted"}],
  "typography": {
    "headline": {"family": "string or null suggestion for the wordmark or wordmark-style", "weight": "e.g. 700", "style": "e.g. humanist-sans, slab-serif, cursive-script, geometric-sans"},
    "body": {"family": "string or null (secondary usage)", "weight": "e.g. 400"},
    "pairing_vibe": "1 line — how the headline/wordmark pairs with supporting type"
  },
  "layout": {
    "archetype": "logo archetype, e.g. circular badge + serif wordmark, abstract monogram, typographic-only wordmark, illustrative mascot, geometric emblem",
    "density": "sparse|balanced|dense",
    "grid": "optional construction grid note, e.g. 12-unit circular grid, golden-ratio square"
  },
  "components": [
    "concrete logo elements this direction uses — e.g. monogram initial, scissor iconography, leaf silhouette, badge lockup, horizontal wordmark lockup, stacked lockup"
  ],
  "motion": {"hints": ["short motion cues for an animated mark variant, or empty"]},
  "anti_patterns": ["specific slop marks to avoid — e.g. no swoosh, no gradient circle with sans-serif, no generic pin-drop"],
  "reference_whys": [{"id": "<reference id>", "why": "1 sentence on what idea this ref contributes (shape language, grid, weight, humor, etc.)"}]
}

Rules:
- Marks must feel category-appropriate AND ORIGINAL. A barbershop logo should not look like a generic food-truck badge.
- Pull concrete craft cues from the reference style_tokens — line weight, corner radius, grid, negative-space tricks, monoline vs chunky, custom lettering, wordmark character.
- Anti-patterns must be specific: name the slop shape. "no realistic barber-pole with drop shadow", "no cursive signature with heart dotting the i", etc.
- INSPIRATION, NOT IMITATION. This is the hard rule. Do NOT describe a logo that reproduces any single reference. Do not lift the exact shape, exact mascot, or exact wordmark of any ref. The brief must yield an original mark that shares LANGUAGE (weight, grid, era, mood) with the cluster, not IDENTITY.
- Respect taste signals if given — boost liked patterns, avoid rejected ones.`;

export interface SynthesisOptions {
  intent: IntentTags;
  references: Reference[];
  directions: number;
  userId?: string;
  prompt: string;
}

// Stage 4 — cluster references, synthesize one direction per cluster via LLM,
// rank by taste, package into a Brief.
export async function synthesizeBrief(opts: SynthesisOptions): Promise<Brief> {
  const profile = opts.userId ? tasteStore.getOrInit(opts.userId) : undefined;

  // Filter out references this user has explicitly rejected.
  const filtered = profile
    ? opts.references.filter((r) => !profile.rejected_references.includes(r.id))
    : opts.references;

  const clusters = clusterReferences(filtered, opts.directions);
  const directions: Direction[] = [];
  for (const cluster of clusters) {
    if (cluster.length === 0) continue;
    const dir = await synthesizeDirection(opts, cluster, profile);
    directions.push(dir);
  }

  if (directions.length === 0) {
    throw new Error(
      "Brief synthesis produced zero directions — check source output and extraction logs.",
    );
  }

  const recommendedIndex = pickRecommended(directions);

  const brief: Brief = {
    id: randomUUID(),
    prompt: opts.prompt,
    intent: opts.intent,
    directions,
    recommended_index: recommendedIndex,
    generated_at: new Date().toISOString(),
    user_id: opts.userId,
    references_considered: opts.references.length,
  };
  return brief;
}

async function synthesizeDirection(
  opts: SynthesisOptions,
  cluster: Reference[],
  profile: TasteProfile | undefined,
): Promise<Direction> {
  const tasteSection = profile ? formatTasteForPrompt(profile) : "";
  const user = [
    `Intent:\n${JSON.stringify(opts.intent, null, 2)}`,
    tasteSection ? `Caller taste signals:\n${tasteSection}` : "",
    `References in this cluster (${cluster.length}):`,
    cluster.map(formatReferenceForPrompt).join("\n\n"),
    `Prompt (original): ${opts.prompt}`,
  ]
    .filter(Boolean)
    .join("\n\n");

  const system = opts.intent.scope === "logo" ? SYSTEM_LOGO : SYSTEM_WEB;
  const raw = await callText({
    model: config.synthesisModel,
    system,
    user,
    maxTokens: 2000,
    temperature: 0.5,
  });

  const parsed = parseJsonBlock<{
    name?: string;
    palette?: Direction["palette"];
    typography?: Direction["typography"];
    layout?: Direction["layout"];
    components?: string[];
    motion?: { hints?: string[] };
    anti_patterns?: string[];
    reference_whys?: Array<{ id: string; why: string }>;
  }>(raw);

  const whysById = new Map<string, string>();
  for (const w of parsed.reference_whys ?? []) {
    if (w?.id && typeof w.why === "string") whysById.set(w.id, w.why);
  }

  const taste = profile ? scoreReferenceSet(profile, cluster) : 0;

  return {
    name: parsed.name?.trim() || "Untitled Direction",
    palette: parsed.palette ?? [],
    typography: parsed.typography ?? {
      headline: { weight: "400", style: "sans" },
      body: { weight: "400" },
      pairing_vibe: "",
    },
    layout: parsed.layout ?? {
      archetype: "unknown",
      density: opts.intent.density,
    },
    components: parsed.components ?? [],
    motion: { hints: parsed.motion?.hints ?? [] },
    anti_patterns: parsed.anti_patterns ?? [...opts.intent.anti],
    references: cluster.map((r) => ({
      id: r.id,
      url: r.source_url,
      thumb: r.thumbnail_url,
      source: r.source,
      why: whysById.get(r.id) ?? r.title ?? "",
    })),
    taste_score: normalizeTasteScore(taste),
  };
}

function normalizeTasteScore(s: number): number {
  // Map tanh'd [-1, 1] to [0, 1] for easier downstream comparison.
  return (s + 1) / 2;
}

function formatTasteForPrompt(profile: TasteProfile): string {
  const topMood = topN(profile.mood_weights, 6);
  const topComp = topN(profile.component_weights, 6);
  const topDist = topN(profile.distinctive_weights, 6);
  const topArch = topN(profile.archetype_weights, 4);
  const avoidedMood = bottomN(profile.mood_weights, 4);
  const avoidedComp = bottomN(profile.component_weights, 4);
  const lines = [
    `Sample size: ${profile.sample_count}`,
    topMood.length ? `Liked moods: ${topMood.join(", ")}` : "",
    topComp.length ? `Liked components: ${topComp.join(", ")}` : "",
    topDist.length ? `Liked distinctive choices: ${topDist.join(", ")}` : "",
    topArch.length ? `Liked layout archetypes: ${topArch.join(", ")}` : "",
    avoidedMood.length ? `Avoid moods: ${avoidedMood.join(", ")}` : "",
    avoidedComp.length ? `Avoid components: ${avoidedComp.join(", ")}` : "",
  ];
  return lines.filter(Boolean).join("\n");
}

function topN(bag: Record<string, number>, n: number): string[] {
  return Object.entries(bag)
    .filter(([, w]) => w > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([k]) => k);
}

function bottomN(bag: Record<string, number>, n: number): string[] {
  return Object.entries(bag)
    .filter(([, w]) => w < 0)
    .sort((a, b) => a[1] - b[1])
    .slice(0, n)
    .map(([k]) => k);
}

function formatReferenceForPrompt(ref: Reference): string {
  const t = ref.style_tokens;
  const mood = t?.mood?.join(", ") ?? "";
  const arche = t?.layout.archetype ?? "";
  const dist = t?.distinctive_choices?.join("; ") ?? "";
  const pal = t?.palette?.map((p) => `${p.hex}(${p.role})`).join(" ") ?? "";
  return [
    `- id: ${ref.id}`,
    `  source: ${ref.source}  url: ${ref.source_url}`,
    ref.title ? `  title: ${ref.title}` : "",
    arche ? `  archetype: ${arche}` : "",
    mood ? `  mood: ${mood}` : "",
    pal ? `  palette: ${pal}` : "",
    dist ? `  distinctive: ${dist}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

// K-clustering for references. Real clustering would vectorize style tokens;
// for Phase-0 we use a deterministic bucket by (archetype + dominant mood),
// then split the largest bucket until we hit k. Cheap and good enough to make
// the directions feel different.
export function clusterReferences(refs: Reference[], k: number): Reference[][] {
  if (refs.length === 0) return [];
  const desired = Math.max(1, Math.min(k, refs.length));
  const buckets = new Map<string, Reference[]>();
  for (const r of refs) {
    const key = bucketKey(r);
    const list = buckets.get(key) ?? [];
    list.push(r);
    buckets.set(key, list);
  }
  const clusters = Array.from(buckets.values()).sort((a, b) => b.length - a.length);
  // Collapse tiny buckets (size 1) into the nearest larger one until we have
  // at most `desired` clusters.
  while (clusters.length > desired) {
    const smallest = clusters.pop();
    if (!smallest) break;
    const target = clusters[0]!;
    target.push(...smallest);
  }
  // Split the largest cluster if we're short.
  while (clusters.length < desired) {
    const biggest = clusters.shift();
    if (!biggest || biggest.length < 2) {
      if (biggest) clusters.unshift(biggest);
      break;
    }
    const half = Math.floor(biggest.length / 2);
    clusters.push(biggest.slice(0, half));
    clusters.push(biggest.slice(half));
  }
  log.debug("clustered", { total: refs.length, clusters: clusters.map((c) => c.length) });
  return clusters;
}

function bucketKey(ref: Reference): string {
  const a = ref.style_tokens?.layout.archetype ?? "unknown";
  const m = ref.style_tokens?.mood?.[0] ?? "unspecified";
  return `${a}::${m}`.toLowerCase();
}

function pickRecommended(directions: Direction[]): number {
  let best = 0;
  let bestScore = -Infinity;
  for (let i = 0; i < directions.length; i++) {
    const d = directions[i]!;
    // Score = taste_score * weight + coverage bonus for more cited refs.
    const coverage = Math.min(1, d.references.length / 10);
    const score = d.taste_score * 0.7 + coverage * 0.3;
    if (score > bestScore) {
      bestScore = score;
      best = i;
    }
  }
  return best;
}

// Exposed for tests: score a single reference against a profile.
export { scoreReference };
