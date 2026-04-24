import * as cheerio from "cheerio";
import { config } from "../config.js";
import type { Reference } from "../types.js";
import { log } from "../util/logger.js";
import { httpText } from "../util/http.js";
import { referenceDedupeKey } from "../util/hash.js";
import type { SearchArgs, Source } from "./source.js";

const BASE = "https://dribbble.com";

/**
 * Dribbble source. Strong for category-specific shots the other galleries
 * miss (barbershop, coffee shop, taqueria, etc.). Uses Dribbble's public
 * search and tag endpoints — no API key. Respectful: UA identifies the bot,
 * each request honors the shared HTTP timeout/retry policy, and results are
 * cached for the reference TTL so popular categories are free on repeat.
 *
 * Dribbble hints at per-shot links via `<a class="shot-thumbnail-link">`;
 * we also accept any `/shots/<slug>` anchor as a fallback when markup shifts.
 */
export class DribbbleSource implements Source {
  readonly name = "dribbble" as const;
  readonly enabled: boolean;
  constructor(enabled: boolean) {
    this.enabled = enabled;
  }

  async search({ intent, limit }: SearchArgs): Promise<Reference[]> {
    if (!this.enabled) return [];

    const isLogo = intent.scope === "logo";
    const queries = isLogo
      ? buildLogoQueries(intent.keywords, intent.category, intent.mood)
      : buildQueries(intent.keywords, intent.category);

    const tagSlugs = new Set<string>();
    for (const term of [intent.category, ...intent.keywords, ...intent.mood]) {
      const slug = slugify(term);
      if (slug) tagSlugs.add(slug);
    }
    if (isLogo) {
      // Seed logo-design tag pages so even a vague prompt surfaces real marks.
      tagSlugs.add("logo");
      tagSlugs.add("logo-design");
      tagSlugs.add("logomark");
      tagSlugs.add("branding");
      tagSlugs.add("monogram");
      tagSlugs.add("wordmark");
    }

    const urls: string[] = [];
    for (const q of queries) {
      urls.push(`${BASE}/search/shots/popular?q=${encodeURIComponent(q)}`);
      urls.push(`${BASE}/search?q=${encodeURIComponent(q)}`);
    }
    for (const slug of tagSlugs) {
      urls.push(`${BASE}/tags/${slug}`);
    }

    const seen = new Set<string>();
    const refs: Reference[] = [];
    for (const url of urls) {
      if (refs.length >= limit) break;
      try {
        const html = await httpText(url);
        const parsed = parseShots(html);
        for (const r of parsed) {
          if (refs.length >= limit) break;
          if (seen.has(r.hash)) continue;
          seen.add(r.hash);
          refs.push(r);
        }
      } catch (err) {
        log.warn("dribbble url failed", { url, err: String(err) });
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

// Build search queries tuned for category-specific shots. A landing-page
// brief for "barbershop" should search ["barbershop website", "barbershop
// landing page", "barbershop"] — not just the bare keyword, which skews
// to logos/illustration on Dribbble.
function buildQueries(keywords: string[], category: string): string[] {
  const seeds = new Set<string>();
  if (category) seeds.add(category);
  for (const k of keywords) seeds.add(k);
  const queries = new Set<string>();
  for (const seed of seeds) {
    const s = seed.trim();
    if (!s) continue;
    queries.add(s);
    queries.add(`${s} website`);
    queries.add(`${s} landing page`);
  }
  return [...queries];
}

// Logo-tuned queries. Dribbble's search skews hard toward marks anyway, so
// we expand each seed with the canonical mark variants designers use as
// search tags: "logo", "logomark", "wordmark", "monogram", "brand identity".
// Mood + era modifiers ("vintage barbershop logo") surface much richer
// inspiration than the bare category alone.
function buildLogoQueries(
  keywords: string[],
  category: string,
  mood: string[],
): string[] {
  const seeds = new Set<string>();
  if (category) seeds.add(category);
  for (const k of keywords) seeds.add(k);
  const variants = ["logo", "logomark", "wordmark", "monogram", "brand identity"];
  const queries = new Set<string>();
  for (const seed of seeds) {
    const s = seed.trim();
    if (!s) continue;
    for (const v of variants) {
      queries.add(`${s} ${v}`);
    }
    // Mood-qualified variants surface stronger taste-matched results.
    for (const m of mood.slice(0, 2)) {
      const mm = m.trim();
      if (mm) queries.add(`${mm} ${s} logo`);
    }
  }
  // Fallback: if nothing seeded, at least pull generic logo inspiration.
  if (queries.size === 0) {
    queries.add("logo design");
    queries.add("logomark");
  }
  return [...queries];
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function parseShots(html: string): Reference[] {
  const $ = cheerio.load(html);
  const out: Reference[] = [];
  const expires = new Date(
    Date.now() + config.referenceCacheTtlDays * 864e5,
  ).toISOString();
  const seenHrefs = new Set<string>();

  const selectors = [
    "a.shot-thumbnail-link",
    'a[href^="/shots/"]',
    "li.shot-thumbnail a",
  ];
  for (const sel of selectors) {
    $(sel).each((_, el) => {
      const a = $(el);
      const href = a.attr("href") ?? "";
      if (!/^\/shots\/[^/]+/i.test(href)) return;
      if (seenHrefs.has(href)) return;
      seenHrefs.add(href);
      const img = a.find("img").first();
      if (img.length === 0) return;
      const src =
        img.attr("data-src") ??
        img.attr("src") ??
        img.attr("data-lazy-src") ??
        img.attr("srcset")?.split(" ")[0];
      if (!src) return;
      const alt = (img.attr("alt") ?? a.attr("title") ?? "").trim();
      const sourceUrl = absolutize(href);
      const imageUrl = absolutize(src);
      const hash = referenceDedupeKey(sourceUrl, alt);
      out.push({
        id: `dribbble:${hash}`,
        source: "dribbble",
        source_url: sourceUrl,
        image_url: imageUrl,
        thumbnail_url: imageUrl,
        title: alt || undefined,
        tags: [],
        cache_expires_at: expires,
        hash,
      });
    });
  }
  return out;
}

function absolutize(href: string): string {
  if (href.startsWith("http://") || href.startsWith("https://")) return href;
  if (href.startsWith("//")) return `https:${href}`;
  if (href.startsWith("/")) return `${BASE}${href}`;
  return `${BASE}/${href}`;
}
