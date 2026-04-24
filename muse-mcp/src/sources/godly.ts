import * as cheerio from "cheerio";
import { config } from "../config.js";
import type { Reference } from "../types.js";
import { log } from "../util/logger.js";
import { httpText } from "../util/http.js";
import { referenceDedupeKey } from "../util/hash.js";
import type { SearchArgs, Source } from "./source.js";

const BASE = "https://godly.website";

/**
 * Godly source: curated editorial/agency web. Tag pages live at /tag/<slug>.
 * Each card is an <a> wrapping an <img>. We parse those directly.
 */
export class GodlySource implements Source {
  readonly name = "godly" as const;
  readonly enabled: boolean;
  constructor(enabled: boolean) {
    this.enabled = enabled;
  }

  async search({ intent, limit }: SearchArgs): Promise<Reference[]> {
    if (!this.enabled) return [];
    const paths = ["/"];
    for (const term of [...intent.keywords, ...intent.mood]) {
      const slug = slugify(term);
      if (slug) paths.push(`/tag/${slug}`);
    }
    const seen = new Set<string>();
    const refs: Reference[] = [];
    for (const path of paths) {
      if (refs.length >= limit) break;
      try {
        const html = await httpText(`${BASE}${path}`);
        const parsed = parseGallery(html);
        for (const r of parsed) {
          if (refs.length >= limit) break;
          if (seen.has(r.hash)) continue;
          seen.add(r.hash);
          refs.push(r);
        }
      } catch (err) {
        log.warn("godly path failed", { path, err: String(err) });
      }
    }
    return refs;
  }

  async healthCheck(): Promise<boolean> {
    try {
      await httpText(`${BASE}/`);
      return true;
    } catch {
      return false;
    }
  }
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function parseGallery(html: string): Reference[] {
  const $ = cheerio.load(html);
  const out: Reference[] = [];
  const expires = new Date(
    Date.now() + config.referenceCacheTtlDays * 864e5,
  ).toISOString();

  // Godly cards: any anchor containing an image with a visible alt text.
  $("a").each((_, el) => {
    const a = $(el);
    const href = a.attr("href") ?? "";
    if (!href || href.startsWith("#")) return;
    const img = a.find("img").first();
    if (img.length === 0) return;
    const src =
      img.attr("data-src") ?? img.attr("src") ?? img.attr("data-lazy-src");
    if (!src) return;
    const alt = (img.attr("alt") ?? "").trim();
    // Skip nav/logo chrome — require a non-trivial alt.
    if (alt.length < 3) return;
    const sourceUrl = absolutize(href);
    const imageUrl = absolutize(src);
    const hash = referenceDedupeKey(sourceUrl, alt);
    out.push({
      id: `godly:${hash}`,
      source: "godly",
      source_url: sourceUrl,
      image_url: imageUrl,
      thumbnail_url: imageUrl,
      title: alt,
      tags: [],
      cache_expires_at: expires,
      hash,
    });
  });
  return out;
}

function absolutize(href: string): string {
  if (href.startsWith("http://") || href.startsWith("https://")) return href;
  if (href.startsWith("//")) return `https:${href}`;
  if (href.startsWith("/")) return `${BASE}${href}`;
  return `${BASE}/${href}`;
}
