import { config } from "../config.js";
import { log } from "./logger.js";

// Thin fetch wrapper: timeout, UA, retry on transient errors.
export interface FetchOptions {
  method?: "GET" | "POST";
  headers?: Record<string, string>;
  body?: string;
  timeoutMs?: number;
  retries?: number;
}

export async function httpText(url: string, opts: FetchOptions = {}): Promise<string> {
  const res = await httpRaw(url, opts);
  return await res.text();
}

export async function httpJson<T>(url: string, opts: FetchOptions = {}): Promise<T> {
  const res = await httpRaw(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts.headers ?? {}) },
  });
  return (await res.json()) as T;
}

async function httpRaw(url: string, opts: FetchOptions): Promise<Response> {
  const retries = opts.retries ?? 2;
  const timeoutMs = opts.timeoutMs ?? config.httpTimeoutMs;
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        method: opts.method ?? "GET",
        headers: {
          "User-Agent": config.userAgent,
          ...(opts.headers ?? {}),
        },
        body: opts.body,
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (res.status >= 500 || res.status === 429) {
        throw new Error(`HTTP ${res.status} on ${url}`);
      }
      if (!res.ok) {
        // 4xx: don't retry. Probably a real client error (bad URL, auth).
        throw new Error(`HTTP ${res.status} on ${url}`);
      }
      return res;
    } catch (err) {
      clearTimeout(timer);
      lastErr = err;
      if (attempt < retries) {
        const backoff = 300 * Math.pow(2, attempt);
        log.debug("http retry", { url, attempt, backoff, err: String(err) });
        await new Promise((r) => setTimeout(r, backoff));
      }
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}
