import { describe, expect, test, beforeEach } from "bun:test";
import { applyFeedback, scoreReference } from "../src/taste/taste.js";
import { tasteStore } from "../src/taste/taste-store.js";
import { referenceCache } from "../src/store/reference-cache.js";
import type { Reference } from "../src/types.js";

function makeRef(id: string, archetype: string, mood: string[], comp: string[]): Reference {
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
      palette: [
        { hex: "#111111", role: "bg" },
        { hex: "#ffffff", role: "fg" },
        { hex: "#ff8844", role: "accent" },
      ],
      typography: {
        headline: { weight: "700", style: "display-serif" },
        body: { weight: "400" },
        pairing_vibe: "editorial",
      },
      layout: { archetype, density: "balanced" },
      components: comp,
      motion_hints: [],
      mood,
      distinctive_choices: ["handset-type", "asymmetric spacing"],
    },
  };
  referenceCache.putReference(ref);
  return ref;
}

describe("taste", () => {
  beforeEach(() => {
    tasteStore.delete("unit-user");
  });

  test("liked reference boosts score on similar refs", () => {
    const liked = makeRef("r1", "asymmetric editorial", ["warm", "analog"], ["split hero"]);
    const similar = makeRef("r2", "asymmetric editorial", ["warm"], ["split hero"]);
    const different = makeRef("r3", "centered saas hero", ["clinical"], ["logo marquee"]);

    applyFeedback("unit-user", {
      kind: "reference",
      reference_id: liked.id,
      verdict: "love",
    });
    const profile = tasteStore.getOrInit("unit-user");

    const sSim = scoreReference(profile, similar);
    const sDiff = scoreReference(profile, different);
    expect(sSim).toBeGreaterThan(sDiff);
    expect(sSim).toBeGreaterThan(0);
  });

  test("rejected reference is hard-pinned to -1", () => {
    const rejected = makeRef("r4", "centered saas hero", ["bland"], ["three-tier pricing"]);
    applyFeedback("unit-user", {
      kind: "reference",
      reference_id: rejected.id,
      verdict: "reject",
    });
    const profile = tasteStore.getOrInit("unit-user");
    expect(scoreReference(profile, rejected)).toBe(-1);
    expect(profile.rejected_references).toContain(rejected.id);
  });

  test("dislike accumulates as negative weight", () => {
    const disliked = makeRef("r5", "grid magazine", ["moody"], ["pull quote"]);
    applyFeedback("unit-user", {
      kind: "reference",
      reference_id: disliked.id,
      verdict: "dislike",
    });
    applyFeedback("unit-user", {
      kind: "reference",
      reference_id: disliked.id,
      verdict: "dislike",
    });
    const profile = tasteStore.getOrInit("unit-user");
    expect(profile.mood_weights["moody"]).toBeLessThan(0);
    expect(profile.sample_count).toBe(2);
  });
});
