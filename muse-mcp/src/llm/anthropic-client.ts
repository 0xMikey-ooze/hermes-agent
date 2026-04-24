import Anthropic from "@anthropic-ai/sdk";
import { config } from "../config.js";
import { log } from "../util/logger.js";

// Shared Anthropic client. Instantiated lazily so the MCP server can boot
// without a key (tools error at call time instead).
let client: Anthropic | null = null;

export class MissingApiKeyError extends Error {
  constructor() {
    super(
      "ANTHROPIC_API_KEY is not set. Muse needs it for intent parsing, style extraction, and brief synthesis.",
    );
    this.name = "MissingApiKeyError";
  }
}

function getClient(): Anthropic {
  if (!config.anthropicApiKey) throw new MissingApiKeyError();
  if (!client) client = new Anthropic({ apiKey: config.anthropicApiKey });
  return client;
}

export interface TextCallOptions {
  model: string;
  system: string;
  user: string;
  maxTokens?: number;
  temperature?: number;
}

// Plain text call with a system prompt. Used for intent parsing + synthesis
// where we want JSON back.
export async function callText(opts: TextCallOptions): Promise<string> {
  const c = getClient();
  const resp = await c.messages.create({
    model: opts.model,
    max_tokens: opts.maxTokens ?? 2048,
    temperature: opts.temperature ?? 0.4,
    system: opts.system,
    messages: [{ role: "user", content: opts.user }],
  });
  return extractText(resp);
}

export interface VisionCallOptions {
  model: string;
  system: string;
  user: string;
  imageUrl: string;
  maxTokens?: number;
  temperature?: number;
}

// Vision call for style extraction. Uses URL-based image refs so we don't
// have to download/base64-encode during the spike.
export async function callVision(opts: VisionCallOptions): Promise<string> {
  const c = getClient();
  const resp = await c.messages.create({
    model: opts.model,
    max_tokens: opts.maxTokens ?? 2048,
    temperature: opts.temperature ?? 0.2,
    system: opts.system,
    messages: [
      {
        role: "user",
        content: [
          { type: "image", source: { type: "url", url: opts.imageUrl } },
          { type: "text", text: opts.user },
        ],
      },
    ],
  });
  return extractText(resp);
}

function extractText(resp: Anthropic.Messages.Message): string {
  const parts: string[] = [];
  for (const block of resp.content) {
    if (block.type === "text") parts.push(block.text);
  }
  return parts.join("\n").trim();
}

// Extract a JSON object from an LLM response. Models sometimes wrap JSON in
// ```json``` fences or prose; we pull the first balanced {...} or [...] block.
export function parseJsonBlock<T>(raw: string): T {
  const cleaned = stripFences(raw).trim();
  // Try straight parse first.
  try {
    return JSON.parse(cleaned) as T;
  } catch {
    // Fall through to bracket scan.
  }
  const extracted = extractFirstJsonBlock(cleaned);
  if (extracted) {
    return JSON.parse(extracted) as T;
  }
  log.warn("Failed to parse JSON from LLM response", { preview: cleaned.slice(0, 200) });
  throw new Error("LLM response did not contain parseable JSON.");
}

function stripFences(s: string): string {
  const fence = s.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
  return fence?.[1] ?? s;
}

function extractFirstJsonBlock(s: string): string | null {
  const starts = ["{", "["];
  let startIdx = -1;
  let opener = "";
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]!;
    if (starts.includes(ch)) {
      startIdx = i;
      opener = ch;
      break;
    }
  }
  if (startIdx === -1) return null;
  const closer = opener === "{" ? "}" : "]";
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = startIdx; i < s.length; i++) {
    const ch = s[i]!;
    if (escape) {
      escape = false;
      continue;
    }
    if (ch === "\\") {
      escape = true;
      continue;
    }
    if (ch === '"') {
      inString = !inString;
      continue;
    }
    if (inString) continue;
    if (ch === opener) depth++;
    else if (ch === closer) {
      depth--;
      if (depth === 0) return s.slice(startIdx, i + 1);
    }
  }
  return null;
}
