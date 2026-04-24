import { describe, expect, test } from "bun:test";
import { clusterReferences } from "../src/pipeline/brief-synthesis.js";
import type { Reference } from "../src/types.js";

function ref(id: string, archetype: string, mood: string): Reference {
  return {
    id,
    source: "godly",
    source_url: `https://example.test/${id}`,
    image_url: `https://example.test/${id}.png`,
    thumbnail_url: `https://example.test/${id}.png`,
    tags: [],
    cache_expires_at: new Date(Date.now() + 86400000).toISOString(),
    hash: id,
    style_tokens: {
      palette: [],
      typography: {
        headline: { weight: "400", style: "sans" },
        body: { weight: "400" },
        pairing_vibe: "",
      },
      layout: { archetype, density: "balanced" },
      components: [],
      motion_hints: [],
      mood: [mood],
      distinctive_choices: [],
    },
  };
}

describe("clusterReferences", () => {
  test("groups refs by archetype+mood bucket", () => {
    const refs = [
      ref("a1", "centered saas hero", "clinical"),
      ref("a2", "centered saas hero", "clinical"),
      ref("b1", "asymmetric editorial", "warm"),
      ref("b2", "asymmetric editorial", "warm"),
      ref("c1", "broken grid", "analog"),
    ];
    const clusters = clusterReferences(refs, 3);
    expect(clusters.length).toBe(3);
    const total = clusters.reduce((s, c) => s + c.length, 0);
    expect(total).toBe(refs.length);
  });

  test("handles k larger than distinct buckets by splitting", () => {
    const refs = [
      ref("a1", "centered saas hero", "clinical"),
      ref("a2", "centered saas hero", "clinical"),
      ref("a3", "centered saas hero", "clinical"),
      ref("a4", "centered saas hero", "clinical"),
    ];
    const clusters = clusterReferences(refs, 2);
    expect(clusters.length).toBe(2);
  });

  test("returns empty on empty input", () => {
    expect(clusterReferences([], 3)).toEqual([]);
  });
});
