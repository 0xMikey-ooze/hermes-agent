import { briefStore } from "../store/brief-store.js";
import { tasteStore } from "../taste/taste-store.js";
import { scoreReference } from "../taste/taste.js";
import type { Brief, Reference, Scope } from "../types.js";
import { log } from "../util/logger.js";
import { fetchInspiration } from "./inspiration-fetch.js";
import { parseIntent, type IntentHints } from "./intent-parser.js";
import { extractStylesForReferences } from "./style-extraction.js";
import { synthesizeBrief } from "./brief-synthesis.js";

export interface GenerateBriefInput {
  prompt: string;
  scope?: Scope;
  hints?: IntentHints;
  numReferences?: number;
  directions?: number;
  userId?: string;
}

// Top-level end-to-end: prompt → brief. Persists to brief store.
export async function generateBrief(input: GenerateBriefInput): Promise<Brief> {
  const hints: IntentHints = { ...(input.hints ?? {}) };
  if (input.scope) hints.scope = input.scope;

  log.info("generate_brief start", {
    prompt: input.prompt,
    userId: input.userId,
    directions: input.directions,
  });

  const intent = await parseIntent(input.prompt, hints);
  log.debug("intent parsed", intent);

  const rawRefs = await fetchInspiration(intent, {
    limit: input.numReferences ?? 40,
  });
  if (rawRefs.length === 0) {
    throw new Error(
      "No references returned from any source. Check MUSE_SOURCES and source health.",
    );
  }

  const extracted = await extractStylesForReferences(rawRefs);

  // Apply taste-based re-ranking BEFORE clustering so the best references
  // anchor the clusters. Rejected refs were already filtered inside synthesis.
  const ranked = rankByTaste(extracted, input.userId);

  const brief = await synthesizeBrief({
    intent,
    references: ranked,
    directions: Math.max(1, Math.min(input.directions ?? 3, 5)),
    userId: input.userId,
    prompt: input.prompt,
  });
  briefStore.put(brief);
  log.info("generate_brief done", {
    brief_id: brief.id,
    directions: brief.directions.length,
  });
  return brief;
}

function rankByTaste(refs: Reference[], userId?: string): Reference[] {
  if (!userId) return refs;
  const profile = tasteStore.get(userId);
  if (!profile || profile.sample_count === 0) return refs;
  const scored = refs.map((r) => ({ r, s: scoreReference(profile, r) }));
  scored.sort((a, b) => b.s - a.s);
  return scored.map((x) => x.r);
}
