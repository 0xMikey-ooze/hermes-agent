import { createHash } from "node:crypto";

// Deterministic ids and dedupe keys. We use sha1 (short + fast); collision
// risk is irrelevant for our URL/content space.
export function sha1(input: string): string {
  return createHash("sha1").update(input).digest("hex");
}

export function shortId(input: string, len = 12): string {
  return sha1(input).slice(0, len);
}

// Perceptual hash substitute: normalize URL + trimmed title so two scrapes
// of the same shot dedupe even if query params differ. Real pHash is a
// later upgrade once images are fetched locally.
export function referenceDedupeKey(sourceUrl: string, title?: string): string {
  const u = stripQueryNoise(sourceUrl);
  const t = (title ?? "").trim().toLowerCase();
  return shortId(`${u}|${t}`);
}

function stripQueryNoise(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    // Drop tracking/cachebuster params so the same ref from different
    // referrers collapses to one cache key.
    const drop = [
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_term",
      "utm_content",
      "ref",
      "source",
    ];
    for (const k of drop) parsed.searchParams.delete(k);
    parsed.searchParams.sort();
    return parsed.toString();
  } catch {
    return url;
  }
}
