#!/usr/bin/env node
/**
 * AgentBrowser MCP server (stdio transport).
 *
 * Exposes the SDK as a set of MCP tools for Claude / OpenClaw / Hermes agents.
 * Sessions are keyed by id; each tool that takes a sessionId looks up the
 * AgentBrowser instance from an in-process map. PRD 5.4 P0.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from "@modelcontextprotocol/sdk/types.js";
import { AgentBrowser } from "../browser.js";
import type { AgentBrowserOptions, Hex } from "../types.js";

const sessions = new Map<string, AgentBrowser>();

function tool(name: string, description: string, inputSchema: Tool["inputSchema"]): Tool {
  return { name, description, inputSchema };
}

const TOOLS: Tool[] = [
  tool("session.start", "Spawn a new AgentBrowser session (Anvil + browser + wallet). Returns the session id and wallet address.", {
    type: "object",
    properties: {
      forkUrl: { type: "string", description: "Fork RPC URL (Alchemy, Infura, etc). Omit for a fresh chain." },
      forkBlockNumber: { type: "number", description: "Block to pin the fork at." },
      chainId: { type: "number" },
      fundEther: { type: "number", description: "Native balance to fund into the agent wallet (default 10000)." },
      ttlMs: { type: "number" },
      headed: { type: "boolean" },
      privateKey: { type: "string", description: "Use this PK instead of a fresh ephemeral one. Hex 0x-prefixed." },
    },
  }),
  tool("session.stop", "Tear down a session.", {
    type: "object",
    required: ["sessionId"],
    properties: { sessionId: { type: "string" } },
  }),
  tool("session.info", "Inspect a session.", {
    type: "object",
    required: ["sessionId"],
    properties: { sessionId: { type: "string" } },
  }),
  tool("page.goto", "Navigate to a URL.", {
    type: "object",
    required: ["sessionId", "url"],
    properties: {
      sessionId: { type: "string" },
      url: { type: "string" },
      timeoutMs: { type: "number" },
    },
  }),
  tool("page.click", "Click a selector.", {
    type: "object",
    required: ["sessionId", "selector"],
    properties: {
      sessionId: { type: "string" },
      selector: { type: "string" },
      timeoutMs: { type: "number" },
    },
  }),
  tool("page.fill", "Type text into a form field.", {
    type: "object",
    required: ["sessionId", "selector", "value"],
    properties: {
      sessionId: { type: "string" },
      selector: { type: "string" },
      value: { type: "string" },
      timeoutMs: { type: "number" },
    },
  }),
  tool("page.readText", "Get text content of a selector.", {
    type: "object",
    required: ["sessionId", "selector"],
    properties: {
      sessionId: { type: "string" },
      selector: { type: "string" },
      timeoutMs: { type: "number" },
    },
  }),
  tool("page.waitFor", "Wait for a selector to reach a state.", {
    type: "object",
    required: ["sessionId", "selector"],
    properties: {
      sessionId: { type: "string" },
      selector: { type: "string" },
      state: { type: "string", enum: ["visible", "hidden", "attached", "detached"] },
      timeoutMs: { type: "number" },
    },
  }),
  tool("page.screenshot", "Take a screenshot. Returns base64 PNG.", {
    type: "object",
    required: ["sessionId"],
    properties: {
      sessionId: { type: "string" },
      fullPage: { type: "boolean" },
    },
  }),
  tool("page.accessibility", "Get the accessibility tree for the current page.", {
    type: "object",
    required: ["sessionId"],
    properties: { sessionId: { type: "string" } },
  }),
  tool("chain.getEthBalance", "Get native balance of an address.", {
    type: "object",
    required: ["sessionId", "address"],
    properties: {
      sessionId: { type: "string" },
      address: { type: "string" },
    },
  }),
  tool("chain.setEthBalance", "Force a native balance via Anvil cheat.", {
    type: "object",
    required: ["sessionId", "address", "amount"],
    properties: {
      sessionId: { type: "string" },
      address: { type: "string" },
      amount: { type: "string", description: "Amount in ether, e.g. \"100\"." },
    },
  }),
  tool("chain.getTokenBalance", "Get ERC-20 balance.", {
    type: "object",
    required: ["sessionId", "token", "holder"],
    properties: {
      sessionId: { type: "string" },
      token: { type: "string" },
      holder: { type: "string" },
    },
  }),
  tool("chain.fundErc20", "Fund the agent wallet with an ERC-20 by impersonating a whale.", {
    type: "object",
    required: ["sessionId", "token", "whale", "recipient", "amount"],
    properties: {
      sessionId: { type: "string" },
      token: { type: "string" },
      whale: { type: "string" },
      recipient: { type: "string" },
      amount: { type: "string" },
    },
  }),
  tool("chain.timeTravel", "Advance the chain clock by N seconds and mine a block.", {
    type: "object",
    required: ["sessionId", "seconds"],
    properties: {
      sessionId: { type: "string" },
      seconds: { type: "number" },
    },
  }),
  tool("chain.mine", "Mine N blocks.", {
    type: "object",
    required: ["sessionId"],
    properties: {
      sessionId: { type: "string" },
      blocks: { type: "number" },
    },
  }),
  tool("chain.snapshot", "Take an EVM snapshot. Returns the snapshot id.", {
    type: "object",
    required: ["sessionId"],
    properties: { sessionId: { type: "string" } },
  }),
  tool("chain.revert", "Revert to a snapshot.", {
    type: "object",
    required: ["sessionId", "snapshotId"],
    properties: {
      sessionId: { type: "string" },
      snapshotId: { type: "string" },
    },
  }),
  tool("rpc.send", "Direct RPC escape hatch.", {
    type: "object",
    required: ["sessionId", "method"],
    properties: {
      sessionId: { type: "string" },
      method: { type: "string" },
      params: { type: "array" },
    },
  }),
];

function getSession(args: Record<string, unknown>): AgentBrowser {
  const id = args.sessionId as string;
  if (!id) throw new Error("sessionId is required");
  const sess = sessions.get(id);
  if (!sess) throw new Error(`unknown session: ${id}`);
  return sess;
}

function ok(value: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(value, replacer, 2) }],
  };
}

// JSON.stringify can't serialize bigints out of the box.
function replacer(_key: string, value: unknown): unknown {
  return typeof value === "bigint" ? value.toString() : value;
}

async function dispatch(name: string, args: Record<string, unknown>): Promise<unknown> {
  switch (name) {
    case "session.start": {
      const opts = args as AgentBrowserOptions;
      const ab = await AgentBrowser.start(opts);
      sessions.set(ab.session.id, ab);
      return ab.info();
    }
    case "session.stop": {
      const sess = getSession(args);
      await sess.stop();
      sessions.delete(sess.session.id);
      return { stopped: true };
    }
    case "session.info":
      return getSession(args).info();

    case "page.goto":
      return { url: await getSession(args).goto(args.url as string, { timeoutMs: args.timeoutMs as number }) };
    case "page.click":
      await getSession(args).click(args.selector as string, { timeoutMs: args.timeoutMs as number });
      return { clicked: true };
    case "page.fill":
      await getSession(args).fill(args.selector as string, args.value as string, { timeoutMs: args.timeoutMs as number });
      return { filled: true };
    case "page.readText":
      return { text: await getSession(args).readText(args.selector as string, { timeoutMs: args.timeoutMs as number }) };
    case "page.waitFor":
      await getSession(args).waitFor(args.selector as string, {
        state: args.state as "visible" | "hidden" | "attached" | "detached" | undefined,
        timeoutMs: args.timeoutMs as number,
      });
      return { ready: true };
    case "page.screenshot":
      return { base64: await getSession(args).screenshot({ fullPage: args.fullPage as boolean }) };
    case "page.accessibility":
      return { tree: await getSession(args).getAccessibilityTree() };

    case "chain.getEthBalance":
      return getSession(args).chain.getEthBalance(args.address as Hex);
    case "chain.setEthBalance":
      await getSession(args).chain.setEthBalance(args.address as Hex, args.amount as string);
      return { funded: true };
    case "chain.getTokenBalance":
      return getSession(args).chain.getTokenBalance(args.token as Hex, args.holder as Hex);
    case "chain.fundErc20":
      return { txHash: await getSession(args).chain.fundErc20({
        token: args.token as Hex,
        whale: args.whale as Hex,
        recipient: args.recipient as Hex,
        amount: args.amount as string,
      }) };
    case "chain.timeTravel":
      await getSession(args).timeTravel(args.seconds as number);
      return { advanced: true };
    case "chain.mine":
      await getSession(args).mine((args.blocks as number) ?? 1);
      return { mined: true };
    case "chain.snapshot":
      return { id: await getSession(args).snapshot() };
    case "chain.revert":
      return { reverted: await getSession(args).revert(args.snapshotId as string) };

    case "rpc.send":
      return getSession(args).send(args.method as string, (args.params as unknown[]) ?? []);

    default:
      throw new Error(`unknown tool: ${name}`);
  }
}

export async function startMcpServer(): Promise<void> {
  const server = new Server(
    { name: "agent-browser", version: "0.1.0-alpha.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args = {} } = request.params;
    try {
      const result = await dispatch(name, args as Record<string, unknown>);
      return ok(result);
    } catch (err) {
      const e = err as Error;
      return {
        isError: true,
        content: [{ type: "text" as const, text: e.message }],
      };
    }
  });

  // Best-effort cleanup on shutdown so anvil children don't linger.
  const cleanup = async () => {
    for (const sess of sessions.values()) {
      try { await sess.stop(); } catch { /* ignore */ }
    }
    process.exit(0);
  };
  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

// Auto-start when invoked directly (e.g. `agent-browser-mcp`).
if (import.meta.url === `file://${process.argv[1]}`) {
  startMcpServer().catch((err) => {
    process.stderr.write(`agent-browser-mcp failed: ${err?.stack ?? err}\n`);
    process.exit(1);
  });
}
