import type { IntentTags, Reference, SourceName } from "../types.js";

export interface SearchArgs {
  intent: IntentTags;
  limit: number;
}

// Every inspiration source implements this. Failures should resolve to an
// empty array with a logged warning — upstream fan-out continues.
export interface Source {
  readonly name: SourceName;
  readonly enabled: boolean;
  search(args: SearchArgs): Promise<Reference[]>;
  healthCheck?(): Promise<boolean>;
}

// Simple token-bucket style delay so we don't hammer a source.
export class RateLimiter {
  private lastAt = 0;
  constructor(private readonly minIntervalMs: number) {}
  async wait(): Promise<void> {
    const now = Date.now();
    const wait = Math.max(0, this.minIntervalMs - (now - this.lastAt));
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    this.lastAt = Date.now();
  }
}
