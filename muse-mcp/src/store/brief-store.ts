import type { Brief } from "../types.js";
import { KvStore } from "./kv-store.js";

// Persistent store for generated briefs. Exposes id-based retrieval so
// muse_get_brief works across server restarts.
class BriefStore {
  private readonly store = new KvStore<Brief>("briefs");

  put(brief: Brief): void {
    this.store.set(brief.id, brief);
  }

  get(id: string): Brief | undefined {
    return this.store.get(id);
  }

  list(limit = 50): Brief[] {
    return this.store
      .values()
      .sort((a, b) => b.generated_at.localeCompare(a.generated_at))
      .slice(0, limit);
  }
}

export const briefStore = new BriefStore();
