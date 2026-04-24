import { describe, expect, test, beforeEach } from "bun:test";
import {
  applyFeedback,
  GLOBAL_TASTE_ID,
  getCombinedProfile,
  scoreReference,
} from "../src/taste/taste.js";
import { tasteStore } from "../src/taste/taste-store.js";
import { referenceCache } from "../src/store/reference-cache.js";
import type { Reference } from "../src/types.js";

function makeRef(id: string, archetype: string, mood: string[]): Reference {
  const ref: Reference = {
    id,
    source: "godly",
    source_url: `https://example.test/${id}`,
    image_url: `https://example.test/${id}.png`,
    thumbnail_url: `https://example.test/${id}.png`,
    tags: [],
    cache_expires_at: new Date(Date.now() + 86400000).toISOString(),
    hash: id,
    style_tokens: {
      palette: [{ hex: "#222", role: "bg" }, { hex: "#ffa", role: "accent" }],
      typography: {
        headline: { weight: "700", style: "display-serif" },
        body: { weight: "400" },
        pairing_vibe: "editorial",
      },
      layout: { archetype, density: "balanced" },
      components: ["split hero"],
      motion_hints: [],
      mood,
      distinctive_choices: ["asymmetric spacing"],
    },
  };
  referenceCache.putReference(ref);
  return ref;
}

describe("global taste learning", () => {
  beforeEach(() => {
    tasteStore.delete("alice");
    tasteStore.delete("bob");
    tasteStore.delete("carol");
    tasteStore.delete(GLOBAL_TASTE_ID);
  });

  test("per-user feedback also writes to global at reduced scale", () => {
    const ref = makeRef("gref-1", "asymmetric editorial", ["warm"]);
    const res = applyFeedback("alice", {
      kind: "reference",
      reference_id: ref.id,
      verdict: "love",
    });
    expect(res.global_updated).toBe(true);

    const alice = tasteStore.get("alice")!;
    const global = tasteStore.get(GLOBAL_TASTE_ID)!;
    expect(alice.mood_weights["warm"]).toBeGreaterThan(0);
    expect(global.mood_weights["warm"]).toBeGreaterThan(0);
    // Global scale is < user scale.
    expect(global.mood_weights["warm"]).toBeLessThan(alice.mood_weights["warm"]!);
  });

  test("global accumulates across users", () => {
    const ref = makeRef("gref-2", "asymmetric editorial", ["editorial"]);
    applyFeedback("alice", { kind: "reference", reference_id: ref.id, verdict: "love" });
    applyFeedback("bob", { kind: "reference", reference_id: ref.id, verdict: "love" });
    applyFeedback("carol", { kind: "reference", reference_id: ref.id, verdict: "like" });

    const global = tasteStore.get(GLOBAL_TASTE_ID)!;
    expect(global.mood_weights["editorial"]).toBeGreaterThan(0);
    // 3 users' scaled contributions should sum meaningfully.
    expect(global.sample_count).toBe(3);
  });

  test("combined profile blends user + global", () => {
    // Alice teaches global that "warm" is liked.
    const seed = makeRef("gref-3", "asymmetric editorial", ["warm"]);
    applyFeedback("alice", { kind: "reference", reference_id: seed.id, verdict: "love" });

    // Bob is a brand-new user with no personal feedback.
    const similar = makeRef("probe-1", "asymmetric editorial", ["warm"]);
    const bobCombined = getCombinedProfile("bob");
    expect(bobCombined).toBeDefined();

    // Bob should still benefit from the house taste — "warm" is positive.
    const score = scoreReference(bobCombined!, similar);
    expect(score).toBeGreaterThan(0);
  });

  test("anonymous (no user_id) calls use global profile alone", () => {
    const seed = makeRef("gref-4", "broken grid", ["moody"]);
    applyFeedback("alice", { kind: "reference", reference_id: seed.id, verdict: "love" });
    const anon = getCombinedProfile(undefined);
    expect(anon).toBeDefined();
    expect(anon!.user_id).toBe(GLOBAL_TASTE_ID);
    expect(anon!.mood_weights["moody"]).toBeGreaterThan(0);
  });

  test("one user's reject does NOT ban a reference globally", () => {
    const ref = makeRef("gref-5", "centered saas hero", ["bland"]);
    applyFeedback("alice", {
      kind: "reference",
      reference_id: ref.id,
      verdict: "reject",
    });
    const global = tasteStore.get(GLOBAL_TASTE_ID)!;
    expect(global.rejected_references).not.toContain(ref.id);
    // Alice's profile does carry the reject.
    const alice = tasteStore.get("alice")!;
    expect(alice.rejected_references).toContain(ref.id);
  });

  test("direct writes to __global__ apply at full scale", () => {
    const ref = makeRef("gref-6", "editorial", ["handset"]);
    applyFeedback(GLOBAL_TASTE_ID, {
      kind: "reference",
      reference_id: ref.id,
      verdict: "love",
    });
    const global = tasteStore.get(GLOBAL_TASTE_ID)!;
    // Direct global write gets the full "love" delta (2.0 on distinctive_weights, etc.).
    expect(global.mood_weights["handset"]).toBeCloseTo(2.0, 5);
    expect(global.sample_count).toBe(1);
  });
});
