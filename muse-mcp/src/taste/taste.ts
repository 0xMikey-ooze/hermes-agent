import type {
  Feedback,
  FeedbackVerdict,
  Reference,
  StyleTokens,
  TasteProfile,
} from "../types.js";
import { briefStore } from "../store/brief-store.js";
import { referenceCache } from "../store/reference-cache.js";
import { tasteStore } from "./taste-store.js";

// Verdict → weight delta. "love" is roughly 2x a "like"; "reject" is a hard
// negative signal.
const VERDICT_WEIGHT: Record<FeedbackVerdict, number> = {
  love: 2.0,
  like: 1.0,
  meh: 0.0,
  dislike: -1.0,
  reject: -2.0,
};

export interface ApplyFeedbackResult {
  profile: TasteProfile;
  affected_references: string[];
}

/**
 * Apply one feedback event to a user's taste profile.
 * - reference feedback: pull style tokens from the cached reference and
 *   bump mood/component/archetype/palette counters by the verdict weight.
 * - direction feedback: resolve the brief + direction, then apply the same
 *   bumps to every reference cited in that direction (a direction-level
 *   like generalizes to its constituent refs).
 */
export function applyFeedback(userId: string, fb: Feedback): ApplyFeedbackResult {
  const profile = tasteStore.getOrInit(userId);
  const delta = VERDICT_WEIGHT[fb.verdict];
  const affected: string[] = [];

  if (fb.kind === "reference") {
    const ref = referenceCache.getReference(fb.reference_id);
    if (ref) {
      bumpProfileFromReference(profile, ref, delta);
      affected.push(ref.id);
    } else {
      // Unknown reference — record as a free-text note so we can still learn
      // something next time we see it.
      profile.notes.push(`[${fb.verdict}] unknown ref ${fb.reference_id}${fb.note ? ` — ${fb.note}` : ""}`);
    }
    trackLikedRejected(profile, fb.reference_id, fb.verdict);
  } else {
    const brief = briefStore.get(fb.brief_id);
    if (brief) {
      const dir = brief.directions[fb.direction_index];
      if (dir) {
        for (const r of dir.references) {
          const ref = referenceCache.getReference(r.id);
          if (ref) {
            // Direction-level feedback is slightly softer than direct ref
            // feedback — scale by 0.6 so it doesn't dominate.
            bumpProfileFromReference(profile, ref, delta * 0.6);
            affected.push(ref.id);
            trackLikedRejected(profile, ref.id, fb.verdict);
          }
        }
        // Also bump on the direction-level metadata itself.
        for (const token of dir.palette) {
          bumpPaletteWeight(profile, token.role, token.hex, delta);
        }
        bumpWeight(profile.archetype_weights, dir.layout.archetype, delta);
        for (const c of dir.components) bumpWeight(profile.component_weights, c, delta);
      }
    }
  }

  if (fb.note) profile.notes.push(`[${fb.verdict}] ${fb.note}`);
  profile.sample_count += 1;
  tasteStore.save(profile);
  return { profile, affected_references: affected };
}

function trackLikedRejected(
  profile: TasteProfile,
  refId: string,
  verdict: FeedbackVerdict,
): void {
  if (verdict === "love" || verdict === "like") {
    if (!profile.liked_references.includes(refId)) profile.liked_references.push(refId);
  } else if (verdict === "reject" || verdict === "dislike") {
    if (!profile.rejected_references.includes(refId)) profile.rejected_references.push(refId);
  }
}

function bumpProfileFromReference(
  profile: TasteProfile,
  ref: Reference,
  delta: number,
): void {
  const tokens = ref.style_tokens;
  if (!tokens) return;
  for (const m of tokens.mood) bumpWeight(profile.mood_weights, m, delta);
  for (const c of tokens.components) bumpWeight(profile.component_weights, c, delta);
  for (const d of tokens.distinctive_choices)
    bumpWeight(profile.distinctive_weights, d, delta * 1.2);
  bumpWeight(profile.archetype_weights, tokens.layout.archetype, delta);
  for (const sw of tokens.palette) bumpPaletteWeight(profile, sw.role, sw.hex, delta);
}

function bumpWeight(bag: Record<string, number>, key: string, delta: number): void {
  if (!key) return;
  const k = key.trim().toLowerCase();
  if (!k) return;
  bag[k] = (bag[k] ?? 0) + delta;
}

function bumpPaletteWeight(
  profile: TasteProfile,
  role: string,
  hex: string,
  delta: number,
): void {
  if (!hex) return;
  const r = role.toLowerCase();
  const h = normalizeHex(hex);
  if (!profile.palette_role_weights[r]) profile.palette_role_weights[r] = {};
  const bucket = profile.palette_role_weights[r]!;
  bucket[h] = (bucket[h] ?? 0) + delta;
}

function normalizeHex(hex: string): string {
  const h = hex.trim().toLowerCase();
  return h.startsWith("#") ? h : `#${h}`;
}

/**
 * Score a reference against a taste profile. Returns a value in roughly
 * [-1, +1]; callers should clamp / normalize if they need [0, 1]. Rejected
 * references are hard-pinned to -1 regardless of tokens.
 */
export function scoreReference(profile: TasteProfile, ref: Reference): number {
  if (profile.rejected_references.includes(ref.id)) return -1;
  if (profile.liked_references.includes(ref.id)) return 1;
  const tokens = ref.style_tokens;
  if (!tokens) return 0;

  let total = 0;
  let terms = 0;
  total += scoreBag(profile.mood_weights, tokens.mood);
  terms += tokens.mood.length;
  total += scoreBag(profile.component_weights, tokens.components);
  terms += tokens.components.length;
  total += scoreBag(profile.distinctive_weights, tokens.distinctive_choices) * 1.2;
  terms += tokens.distinctive_choices.length;
  total += scoreBag(profile.archetype_weights, [tokens.layout.archetype]);
  terms += 1;
  total += scorePalette(profile, tokens);
  terms += tokens.palette.length;

  if (terms === 0) return 0;
  // Squash to roughly [-1, 1] via tanh-ish of the average weight.
  const avg = total / terms;
  return Math.tanh(avg / 2);
}

function scoreBag(bag: Record<string, number>, items: string[]): number {
  let sum = 0;
  for (const i of items) {
    const k = i.trim().toLowerCase();
    if (!k) continue;
    sum += bag[k] ?? 0;
  }
  return sum;
}

function scorePalette(profile: TasteProfile, tokens: StyleTokens): number {
  let sum = 0;
  for (const sw of tokens.palette) {
    const bucket = profile.palette_role_weights[sw.role.toLowerCase()];
    if (!bucket) continue;
    const h = normalizeHex(sw.hex);
    sum += bucket[h] ?? 0;
  }
  return sum;
}

// Aggregate taste score for a set of references — used to rank directions.
export function scoreReferenceSet(profile: TasteProfile, refs: Reference[]): number {
  if (refs.length === 0) return 0;
  let s = 0;
  for (const r of refs) s += scoreReference(profile, r);
  return s / refs.length;
}
