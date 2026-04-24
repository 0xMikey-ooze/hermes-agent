import { describe, expect, test } from "bun:test";
import { parseJsonBlock } from "../src/llm/anthropic-client.js";
import { referenceDedupeKey } from "../src/util/hash.js";

describe("parseJsonBlock", () => {
  test("parses plain JSON", () => {
    const out = parseJsonBlock<{ ok: boolean }>('{"ok": true}');
    expect(out.ok).toBe(true);
  });

  test("strips code fences", () => {
    const out = parseJsonBlock<{ a: number }>(
      "Here is the JSON:\n```json\n{\"a\": 1}\n```",
    );
    expect(out.a).toBe(1);
  });

  test("extracts embedded object from prose", () => {
    const out = parseJsonBlock<{ x: string }>(
      'Sure, here you go: {"x": "hello"} — that\'s the answer.',
    );
    expect(out.x).toBe("hello");
  });

  test("throws on unparseable", () => {
    expect(() => parseJsonBlock("nothing here")).toThrow();
  });
});

describe("referenceDedupeKey", () => {
  test("strips utm params", () => {
    const a = referenceDedupeKey("https://ex.com/x?utm_source=foo");
    const b = referenceDedupeKey("https://ex.com/x");
    expect(a).toBe(b);
  });

  test("is case-insensitive on title", () => {
    const a = referenceDedupeKey("https://ex.com/x", "Barber Shop");
    const b = referenceDedupeKey("https://ex.com/x", "barber shop");
    expect(a).toBe(b);
  });

  test("sorts query params", () => {
    const a = referenceDedupeKey("https://ex.com/x?b=2&a=1");
    const b = referenceDedupeKey("https://ex.com/x?a=1&b=2");
    expect(a).toBe(b);
  });
});
