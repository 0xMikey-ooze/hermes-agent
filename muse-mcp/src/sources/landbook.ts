import * as cheerio from "cheerio";
import { config } from "../config.js";
import type { Reference } from "../types.js";
import { log } from "../util/logger.js";
import { httpText } from "../util/http.js";
import { referenceDedupeKey } from "../util/hash.js";
import type { SearchArgs, Source } from "./source.js";

const BASE = "https://land-book.com";

/**
 * Land-book source: curated SaaS/product landing pages. The site exposes
 * category and tag pages as plain HTML — we parse `<a href="/gallery/...">`
 * entries and pull their thumbnail + title. Fragile by design; circuit-broken
 * upstream so a selector break degrades quietly.
 */
export class LandbookSource implements Source {
  readonly name = "landbook" as const;
  readonly enabled: boolean;
  constructor(enabled: boolean) {
    this.enabled = enabled;
  }

  async search({ intent, limit }: SearchArgs): Promise<Reference[]> {
    if (!this.enabled) return [];
    const paths = candidatePaths(intent.keywords, intent.mood);
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
        log.warn("landbook path failed", { path, err: String(err) });
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

function candidatePaths(keywords: string[], mood: string[]): string[] {
  const slugged = new Set<string>();
  for (const term of [...keywords, ...mood]) {
    const slug = slugify(term);
    if (slug) slugged.add(slug);
  }
  const paths: string[] = ["/", "/websites"];
  for (const slug of slugged) {
    paths.push(`/websites/style/${slug}`);
    paths.push(`/websites/industry/${slug}`);
  }
  return paths;
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

  // Land-book exposes website cards as anchors to /websites/<slug>.
  $('a[href^="/websites/"]').each((_, el) => {
    const a = $(el);
    const href = a.attr("href") ?? "";
    if (!/^\/websites\/[a-z0-9-]+$/i.test(href)) return;
    const img = a.find("img").first();
    const src =
      img.attr("data-src") ?? img.attr("src") ?? img.attr("data-lazy-src");
    if (!src) return;
    const title = (img.attr("alt") ?? a.attr("title") ?? "").trim();
    const sourceUrl = absolutize(href);
    const imageUrl = absolutize(src);
    const hash = referenceDedupeKey(sourceUrl, title);
    out.push({
      id: `landbook:${hash}`,
      source: "landbook",
      source_url: sourceUrl,
      image_url: imageUrl,
      thumbnail_url: imageUrl,
      title: title || undefined,
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
