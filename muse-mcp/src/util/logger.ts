// MCP transports reserve stdout for JSON-RPC; logs must go to stderr.
function emit(level: string, msg: string, extra?: unknown): void {
  const payload = extra !== undefined ? ` ${safeJson(extra)}` : "";
  process.stderr.write(`[muse ${level}] ${msg}${payload}\n`);
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export const log = {
  info: (msg: string, extra?: unknown) => emit("info", msg, extra),
  warn: (msg: string, extra?: unknown) => emit("warn", msg, extra),
  error: (msg: string, extra?: unknown) => emit("error", msg, extra),
  debug: (msg: string, extra?: unknown) => {
    if (process.env.MUSE_DEBUG) emit("debug", msg, extra);
  },
};
