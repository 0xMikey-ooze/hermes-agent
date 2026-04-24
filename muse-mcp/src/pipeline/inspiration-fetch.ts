import { config } from "../config.js";
import { buildSources } from "../sources/registry.js";
import type { Source } from "../sources/source.js";
import type { IntentTags, Reference } from "../types.js";
import { log } from "../util/logger.js";
import { referenceCache } from "../store/reference-cache.js";
import { intentCacheKey } from "./intent-parser.js";

export interface FetchOptions {
  limit: number;
  sources?: Source[];
  skipCache?: boolean;
}

// Stage 2 — fan out across sources in parallel, merge, dedupe, persist.
// Never throws on a source failure; returns whatever we can get.
export async function fetchInspiration(
  intent: IntentTags,
  opts: FetchOptions,
): Promise<Reference[]> {
  const sources = opts.sources ?? buildSources();
  if (sources.length === 0) {
    log.warn("no sources enabled");
    return [];
  }

  const perSource = Math.max(
    6,
    Math.ceil((opts.limit * 1.6) / Math.max(sources.length, 1)),
  );

  const results = await Promise.all(
    sources.map((src) => fetchFromSource(src, intent, perSource, opts.skipCache ?? false)),
  );

  // Interleave sources so the merged list is diverse even if we cap early.
  const merged = interleave(results);
  const deduped = dedupe(merged);
  const capped = deduped.slice(0, Math.min(opts.limit, config.maxReferences));
  referenceCache.putReferences(capped);
  return capped;
}

async function fetchFromSource(
  src: Source,
  intent: IntentTags,
  limit: number,
  skipCache: boolean,
): Promise<Reference[]> {
  const key = intentCacheKey(intent, src.name);
  if (!skipCache) {
    const cachedIds = referenceCache.getCachedSearch(key);
    if (cachedIds) {
      const cached = cachedIds
        .map((id) => referenceCache.getReference(id))
        .filter((r): r is Reference => r !== undefined);
      if (cached.length >= Math.min(limit, 6)) {
        log.debug("source cache hit", { source: src.name, n: cached.length });
        return cached.slice(0, limit);
      }
    }
  }
  try {
    const refs = await src.search({ intent, limit });
    referenceCache.putReferences(refs);
    referenceCache.cacheSearch(
      key,
      refs.map((r) => r.id),
      config.referenceCacheTtlDays * 864e5,
    );
    return refs;
  } catch (err) {
    log.warn("source failed", { source: src.name, err: String(err) });
    return [];
  }
}

function interleave(lists: Reference[][]): Reference[] {
  const out: Reference[] = [];
  let idx = 0;
  let added = true;
  while (added) {
    added = false;
    for (const list of lists) {
      const item = list[idx];
      if (item) {
        out.push(item);
        added = true;
      }
    }
    idx++;
  }
  return out;
}

function dedupe(refs: Reference[]): Reference[] {
  const seen = new Set<string>();
  const out: Reference[] = [];
  for (const r of refs) {
    if (seen.has(r.hash)) continue;
    seen.add(r.hash);
    out.push(r);
  }
  return out;
}
