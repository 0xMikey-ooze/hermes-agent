import { callText, parseJsonBlock } from "../llm/anthropic-client.js";
import { config } from "../config.js";
import type { IntentTags, Scope } from "../types.js";

const SCOPES: Scope[] = [
  "landing_page",
  "app_ui",
  "component",
  "full_site",
  "logo",
];

// Stage 1 — convert free-text into structured tags. Haiku-class model.
// Schema is pinned so downstream source queries are deterministic.
const SYSTEM = `You convert a natural-language design brief into structured tags.

Return ONLY valid JSON matching this exact shape, no prose:
{
  "scope": "landing_page" | "app_ui" | "component" | "full_site" | "logo",
  "category": "short category noun phrase",
  "audience": "short audience description",
  "mood": ["3-6 adjectives"],
  "era": "one word, e.g. contemporary/y2k/analog/brutalist",
  "density": "sparse" | "balanced" | "dense",
  "keywords": ["6-10 search-ready terms"],
  "anti": ["patterns the design must avoid"],
  "constraints": ["hard requirements like mobile-first, high-contrast"]
}

Rules:
- "keywords" should be terms you'd type into a design gallery's search bar.
- If the scope is "logo", keywords should include the category plus mark
  variants: e.g. ["barbershop logo", "barbershop logomark", "barbershop
  wordmark", "barbershop monogram"]. "density" should be "sparse" for logos.
- If the user gave anti-patterns or constraints in their prompt, surface them.
- Do not invent brand names.`;

export interface IntentHints {
  mood?: string;
  audience?: string;
  constraints?: string[];
  anti?: string[];
  scope?: Scope;
}

export async function parseIntent(
  prompt: string,
  hints: IntentHints = {},
): Promise<IntentTags> {
  const user = buildUserMessage(prompt, hints);
  const raw = await callText({
    model: config.intentModel,
    system: SYSTEM,
    user,
    maxTokens: 800,
    temperature: 0.2,
  });
  const parsed = parseJsonBlock<Partial<IntentTags>>(raw);
  return normalize(parsed, hints);
}

function buildUserMessage(prompt: string, hints: IntentHints): string {
  const lines = [`Prompt: ${prompt}`];
  if (hints.scope) lines.push(`Scope hint: ${hints.scope}`);
  if (hints.mood) lines.push(`Mood hint: ${hints.mood}`);
  if (hints.audience) lines.push(`Audience hint: ${hints.audience}`);
  if (hints.constraints?.length)
    lines.push(`Constraints: ${hints.constraints.join(", ")}`);
  if (hints.anti?.length) lines.push(`Avoid: ${hints.anti.join(", ")}`);
  return lines.join("\n");
}

function normalize(raw: Partial<IntentTags>, hints: IntentHints): IntentTags {
  const scope: Scope = SCOPES.includes(raw.scope as Scope)
    ? (raw.scope as Scope)
    : hints.scope ?? "landing_page";
  return {
    scope,
    category: typeof raw.category === "string" ? raw.category : "",
    audience:
      typeof raw.audience === "string"
        ? raw.audience
        : hints.audience ?? "general",
    mood: asStrArr(raw.mood, hints.mood ? [hints.mood] : []),
    era: typeof raw.era === "string" ? raw.era : "contemporary",
    density:
      raw.density === "sparse" || raw.density === "dense" ? raw.density : "balanced",
    keywords: asStrArr(raw.keywords, []),
    anti: asStrArr(raw.anti, hints.anti ?? []),
    constraints: asStrArr(raw.constraints, hints.constraints ?? []),
  };
}

function asStrArr(v: unknown, fallback: string[]): string[] {
  if (!Array.isArray(v)) return fallback;
  const cleaned = v
    .filter((x): x is string => typeof x === "string")
    .map((s) => s.trim())
    .filter(Boolean);
  return cleaned.length > 0 ? cleaned : fallback;
}

// Build a stable cache key for an intent so repeat prompts reuse fetches.
export function intentCacheKey(intent: IntentTags, source: string): string {
  const parts = [
    source,
    intent.scope,
    intent.density,
    ...[...intent.keywords].sort(),
    ...[...intent.mood].sort(),
  ];
  return parts.join("|").toLowerCase();
}
