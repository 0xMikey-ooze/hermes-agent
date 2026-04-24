import type { Reference, StyleTokens } from "../types.js";
import { KvStore } from "./kv-store.js";

// Two-layer cache:
//  - references keyed by Reference.id (full record, including extracted tokens)
//  - source-search results keyed by sourceName|slug(intent) so repeat queries
//    skip network hops.
export class ReferenceCache {
  private readonly refs = new KvStore<Reference>("references");
  private readonly searches = new KvStore<{ refIds: string[]; expires_at: string }>(
    "searches",
  );

  getReference(id: string): Reference | undefined {
    const r = this.refs.get(id);
    if (!r) return undefined;
    if (new Date(r.cache_expires_at).getTime() < Date.now()) return undefined;
    return r;
  }

  putReference(ref: Reference): void {
    const prev = this.refs.get(ref.id);
    // Preserve extracted tokens if we already have them — extraction is expensive.
    if (prev?.style_tokens && !ref.style_tokens) {
      ref.style_tokens = prev.style_tokens;
      ref.extracted_at = prev.extracted_at;
    }
    this.refs.set(ref.id, ref);
  }

  putReferences(refs: Reference[]): void {
    for (const r of refs) this.putReference(r);
  }

  attachStyleTokens(refId: string, tokens: StyleTokens): void {
    const r = this.refs.get(refId);
    if (!r) return;
    r.style_tokens = tokens;
    r.extracted_at = new Date().toISOString();
    this.refs.set(refId, r);
  }

  cacheSearch(key: string, refIds: string[], ttlMs: number): void {
    this.searches.set(key, {
      refIds,
      expires_at: new Date(Date.now() + ttlMs).toISOString(),
    });
  }

  getCachedSearch(key: string): string[] | undefined {
    const entry = this.searches.get(key);
    if (!entry) return undefined;
    if (new Date(entry.expires_at).getTime() < Date.now()) return undefined;
    return entry.refIds;
  }
}

export const referenceCache = new ReferenceCache();
