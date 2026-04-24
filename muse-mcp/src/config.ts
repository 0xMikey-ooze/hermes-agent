import { resolve } from "node:path";

// Central config. Reads env once at import time. Missing ANTHROPIC_API_KEY is
// NOT fatal at startup — tools that need it error at call time so the MCP
// server still answers initialize/list_tools without a key present.
function env(name: string, fallback?: string): string | undefined {
  const v = process.env[name];
  if (v === undefined || v === "") return fallback;
  return v;
}

function intEnv(name: string, fallback: number): number {
  const v = process.env[name];
  if (!v) return fallback;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export const config = {
  anthropicApiKey: env("ANTHROPIC_API_KEY"),
  intentModel: env("MUSE_INTENT_MODEL", "claude-haiku-4-5-20251001")!,
  extractionModel: env("MUSE_EXTRACTION_MODEL", "claude-sonnet-4-6")!,
  synthesisModel: env("MUSE_SYNTHESIS_MODEL", "claude-sonnet-4-6")!,
  cacheDir: resolve(env("MUSE_CACHE_DIR", ".muse-cache")!),
  enabledSources: (env("MUSE_SOURCES", "landbook,godly,dribbble")!)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
  httpTimeoutMs: intEnv("MUSE_HTTP_TIMEOUT_MS", 15000),
  maxReferences: intEnv("MUSE_MAX_REFERENCES", 60),
  maxExtractConcurrency: intEnv("MUSE_MAX_EXTRACT_CONCURRENCY", 4),
  userAgent:
    "Muse-MCP/0.1 (+https://github.com/0xmikey-ooze/hermes-agent; respectful-bot)",
  referenceCacheTtlDays: 14,
  styleCacheTtlDays: 90,
} as const;

export type MuseConfig = typeof config;
