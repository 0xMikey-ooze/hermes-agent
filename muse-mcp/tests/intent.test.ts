import { describe, expect, test } from "bun:test";
import { intentCacheKey } from "../src/pipeline/intent-parser.js";
import type { IntentTags } from "../src/types.js";

const baseIntent: IntentTags = {
  scope: "landing_page",
  category: "barbershop",
  audience: "men 18-45",
  mood: ["warm", "masculine"],
  era: "contemporary",
  density: "balanced",
  keywords: ["barbershop", "haircut", "classic"],
  anti: ["generic saas"],
  constraints: ["mobile-first"],
};

describe("intent cache key", () => {
  test("is stable regardless of keyword ordering", () => {
    const a = intentCacheKey(baseIntent, "dribbble");
    const reordered = { ...baseIntent, keywords: ["classic", "haircut", "barbershop"] };
    const b = intentCacheKey(reordered, "dribbble");
    expect(a).toBe(b);
  });

  test("differs by source", () => {
    const a = intentCacheKey(baseIntent, "dribbble");
    const b = intentCacheKey(baseIntent, "godly");
    expect(a).not.toBe(b);
  });

  test("differs by scope", () => {
    const a = intentCacheKey(baseIntent, "dribbble");
    const b = intentCacheKey({ ...baseIntent, scope: "app_ui" }, "dribbble");
    expect(a).not.toBe(b);
  });
});
