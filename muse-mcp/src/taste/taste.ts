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

/**
 * Reserved user_id that represents the shared "house" taste — the aggregate
 * of every piece of feedback Muse has ever received, across users. Agents
 * can pass this to muse_get_taste to inspect global patterns, or submit
 * feedback directly to it to teach org-level taste.
 */
export const GLOBAL_TASTE_ID = "__global__";

/**
 * Cross-apply scale: one user's feedback bleeds into the global profile at
 * this fraction. Kept low so a single loud voice doesn't dominate the house
 * taste, but high enough that consistent signal across users accumulates.
 */
const GLOBAL_BLEED = 0.4;

/**
 * When we merge user + global into a single scoring profile, global counts
 * at this fraction of the user's weight. User taste wins ties; global pulls
 * when the user hasn't voted on that dimension yet.
 */
const GLOBAL_MERGE_WEIGHT = 0.6;

export interface ApplyFeedbackResult {
  profile: TasteProfile;
  affected_references: string[];
  global_updated: boolean;
}

/**
 * Apply one feedback event. Writes the per-user profile at full scale AND
 * (unless the caller is already writing global) the global profile at
 * GLOBAL_BLEED scale. liked/rejected reference ids are user-scoped only —
 * one user's reject doesn't ban a reference for everyone.
 */
export function applyFeedback(userId: string, fb: Feedback): ApplyFeedbackResult {
  const profile = tasteStore.getOrInit(userId);
  const delta = VERDICT_WEIGHT[fb.verdict];
  const affected: string[] = [];

  applyWeightsFromFeedback(profile, fb, delta, affected, /* trackIdentity */ true);
  if (fb.note) profile.notes.push(`[${fb.verdict}] ${fb.note}`);
  profile.sample_count += 1;
  tasteStore.save(profile);

  let globalUpdated = false;
  if (userId !== GLOBAL_TASTE_ID) {
    const global = tasteStore.getOrInit(GLOBAL_TASTE_ID);
    applyWeightsFromFeedback(
      global,
      fb,
      delta * GLOBAL_BLEED,
      [],
      /* trackIdentity */ false,
    );
    // Global counts each feedback event so callers can see how many total
    // samples shaped the house taste.
    global.sample_count += 1;
    tasteStore.save(global);
    globalUpdated = true;
  }

  return { profile, affected_references: affected, global_updated: globalUpdated };
}

// Core weight-mutation logic, shared between per-user and global application.
function applyWeightsFromFeedback(
  profile: TasteProfile,
  fb: Feedback,
  delta: number,
  affected: string[],
  trackIdentity: boolean,
): void {
  if (fb.kind === "reference") {
    const ref = referenceCache.getReference(fb.reference_id);
    if (ref) {
      bumpProfileFromReference(profile, ref, delta);
      affected.push(ref.id);
    } else if (trackIdentity) {
      profile.notes.push(
        `[${fb.verdict}] unknown ref ${fb.reference_id}${fb.note ? ` — ${fb.note}` : ""}`,
      );
    }
    if (trackIdentity) trackLikedRejected(profile, fb.reference_id, fb.verdict);
    return;
  }
  // Direction feedback.
  const brief = briefStore.get(fb.brief_id);
  if (!brief) return;
  const dir = brief.directions[fb.direction_index];
  if (!dir) return;
  for (const r of dir.references) {
    const ref = referenceCache.getReference(r.id);
    if (ref) {
      // Direction-level feedback is slightly softer than direct ref feedback.
      bumpProfileFromReference(profile, ref, delta * 0.6);
      affected.push(ref.id);
      if (trackIdentity) trackLikedRejected(profile, ref.id, fb.verdict);
    }
  }
  for (const token of dir.palette) {
    bumpPaletteWeight(profile, token.role, token.hex, delta);
  }
  bumpWeight(profile.archetype_weights, dir.layout.archetype, delta);
  for (const c of dir.components) bumpWeight(profile.component_weights, c, delta);
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
 * [-1, +1]. Rejected refs on this profile are hard-pinned to -1.
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

export function scoreReferenceSet(profile: TasteProfile, refs: Reference[]): number {
  if (refs.length === 0) return 0;
  let s = 0;
  for (const r of refs) s += scoreReference(profile, r);
  return s / refs.length;
}

/**
 * Return a virtual profile that blends a user's profile with the global
 * (house) profile. Used for ranking and for shaping the synthesis prompt.
 *
 * - User weight: 1.0 (personal taste wins ties)
 * - Global weight: GLOBAL_MERGE_WEIGHT (pulls when the user hasn't voted)
 *
 * liked/rejected reference ids come from the user profile only — global
 * doesn't carry per-ref identity lists.
 *
 * If no userId is supplied, the global profile is returned directly so
 * anonymous calls still benefit from the house taste.
 */
export function getCombinedProfile(userId?: string): TasteProfile | undefined {
  const global = tasteStore.get(GLOBAL_TASTE_ID);
  if (!userId || userId === GLOBAL_TASTE_ID) return global;
  const user = tasteStore.get(userId);
  if (!user && !global) return undefined;
  if (!global) return user;
  if (!user) return global;
  return mergeProfiles(user, 1.0, global, GLOBAL_MERGE_WEIGHT);
}

// Produce a synthetic merged profile. Not persisted — we build it on every
// read so it's always current vs. the underlying stores.
function mergeProfiles(
  a: TasteProfile,
  aWeight: number,
  b: TasteProfile,
  bWeight: number,
): TasteProfile {
  return {
    user_id: `${a.user_id}+${b.user_id}`,
    updated_at: a.updated_at > b.updated_at ? a.updated_at : b.updated_at,
    sample_count: a.sample_count + b.sample_count,
    mood_weights: mergeBag(a.mood_weights, aWeight, b.mood_weights, bWeight),
    component_weights: mergeBag(
      a.component_weights,
      aWeight,
      b.component_weights,
      bWeight,
    ),
    palette_role_weights: mergePaletteBag(
      a.palette_role_weights,
      aWeight,
      b.palette_role_weights,
      bWeight,
    ),
    archetype_weights: mergeBag(
      a.archetype_weights,
      aWeight,
      b.archetype_weights,
      bWeight,
    ),
    distinctive_weights: mergeBag(
      a.distinctive_weights,
      aWeight,
      b.distinctive_weights,
      bWeight,
    ),
    liked_references: [...a.liked_references],
    rejected_references: [...a.rejected_references],
    notes: a.notes,
  };
}

function mergeBag(
  a: Record<string, number>,
  aw: number,
  b: Record<string, number>,
  bw: number,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(a)) out[k] = (out[k] ?? 0) + v * aw;
  for (const [k, v] of Object.entries(b)) out[k] = (out[k] ?? 0) + v * bw;
  return out;
}

function mergePaletteBag(
  a: Record<string, Record<string, number>>,
  aw: number,
  b: Record<string, Record<string, number>>,
  bw: number,
): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  for (const [role, bucket] of Object.entries(a)) {
    out[role] = {};
    for (const [hex, v] of Object.entries(bucket)) out[role]![hex] = v * aw;
  }
  for (const [role, bucket] of Object.entries(b)) {
    if (!out[role]) out[role] = {};
    for (const [hex, v] of Object.entries(bucket)) {
      out[role]![hex] = (out[role]![hex] ?? 0) + v * bw;
    }
  }
  return out;
}
