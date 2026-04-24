import type { TasteProfile } from "../types.js";
import { KvStore } from "../store/kv-store.js";

// Per-user taste profiles. user_id is whatever the calling agent supplies —
// a session id, a human's email, an agent name. We don't validate it.
class TasteStore {
  private readonly store = new KvStore<TasteProfile>("taste");

  get(userId: string): TasteProfile | undefined {
    return this.store.get(userId);
  }

  getOrInit(userId: string): TasteProfile {
    const existing = this.store.get(userId);
    if (existing) return existing;
    const fresh: TasteProfile = {
      user_id: userId,
      updated_at: new Date().toISOString(),
      sample_count: 0,
      mood_weights: {},
      component_weights: {},
      palette_role_weights: {},
      archetype_weights: {},
      distinctive_weights: {},
      liked_references: [],
      rejected_references: [],
      notes: [],
    };
    this.store.set(userId, fresh);
    return fresh;
  }

  save(profile: TasteProfile): void {
    profile.updated_at = new Date().toISOString();
    this.store.set(profile.user_id, profile);
  }

  delete(userId: string): void {
    this.store.delete(userId);
  }

  list(limit = 50): TasteProfile[] {
    return this.store
      .values()
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .slice(0, limit);
  }
}

export const tasteStore = new TasteStore();
