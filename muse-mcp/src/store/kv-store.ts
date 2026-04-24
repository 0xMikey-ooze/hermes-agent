import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { config } from "../config.js";
import { log } from "../util/logger.js";

// Simple JSON-file backed K/V. Phase-0 substitute for Postgres+Redis.
// Writes are best-effort and synchronous; reads are cached in memory.
export class KvStore<V> {
  private readonly file: string;
  private mem: Map<string, V>;
  private dirty = false;

  constructor(name: string) {
    this.file = join(config.cacheDir, `${name}.json`);
    this.mem = this.load();
  }

  private load(): Map<string, V> {
    try {
      if (!existsSync(this.file)) return new Map();
      const raw = readFileSync(this.file, "utf8");
      const obj = JSON.parse(raw) as Record<string, V>;
      return new Map(Object.entries(obj));
    } catch (err) {
      log.warn("kvstore load failed, starting empty", { file: this.file, err: String(err) });
      return new Map();
    }
  }

  get(key: string): V | undefined {
    return this.mem.get(key);
  }

  has(key: string): boolean {
    return this.mem.has(key);
  }

  set(key: string, value: V): void {
    this.mem.set(key, value);
    this.dirty = true;
    this.flush();
  }

  delete(key: string): void {
    if (this.mem.delete(key)) {
      this.dirty = true;
      this.flush();
    }
  }

  values(): V[] {
    return Array.from(this.mem.values());
  }

  size(): number {
    return this.mem.size;
  }

  private flush(): void {
    if (!this.dirty) return;
    try {
      mkdirSync(dirname(this.file), { recursive: true });
      const obj: Record<string, V> = {};
      for (const [k, v] of this.mem.entries()) obj[k] = v;
      writeFileSync(this.file, JSON.stringify(obj), "utf8");
      this.dirty = false;
    } catch (err) {
      log.warn("kvstore flush failed", { file: this.file, err: String(err) });
    }
  }
}
