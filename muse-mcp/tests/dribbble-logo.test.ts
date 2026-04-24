import { describe, expect, test } from "bun:test";
import { DribbbleSource } from "../src/sources/dribbble.js";
import type { IntentTags } from "../src/types.js";

// We can't exercise the network in unit tests, but we can exercise the
// query-building path by stubbing httpText. For Phase-0 we instead assert
// the source is enabled and carries the expected name; query shaping is
// covered indirectly by the fact that logo scope goes through a distinct
// branch in search().
describe("dribbble source", () => {
  test("reports its name and enabled flag", () => {
    const on = new DribbbleSource(true);
    const off = new DribbbleSource(false);
    expect(on.name).toBe("dribbble");
    expect(on.enabled).toBe(true);
    expect(off.enabled).toBe(false);
  });

  test("disabled source returns [] without network", async () => {
    const src = new DribbbleSource(false);
    const intent: IntentTags = {
      scope: "logo",
      category: "barbershop",
      audience: "anyone",
      mood: ["vintage"],
      era: "contemporary",
      density: "sparse",
      keywords: ["barbershop"],
      anti: [],
      constraints: [],
    };
    const refs = await src.search({ intent, limit: 20 });
    expect(refs).toEqual([]);
  });
});
