#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { getTool, tools } from "./tools/index.js";
import { log } from "./util/logger.js";

// Entry point. stdio transport so any MCP-capable host can spawn us.
async function main(): Promise<void> {
  const server = new Server(
    { name: "muse", version: "0.1.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: tools.map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const tool = getTool(req.params.name);
    if (!tool) {
      return {
        isError: true,
        content: [{ type: "text", text: `unknown tool: ${req.params.name}` }],
      };
    }
    try {
      const result = await tool.handler(req.params.arguments ?? {});
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } catch (err) {
      const message =
        err instanceof z.ZodError
          ? `invalid arguments: ${formatZod(err)}`
          : err instanceof Error
            ? err.message
            : String(err);
      log.warn("tool error", { tool: req.params.name, err: message });
      return {
        isError: true,
        content: [{ type: "text", text: message }],
      };
    }
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
  log.info("muse mcp server ready", { tools: tools.map((t) => t.name) });
}

function formatZod(err: z.ZodError): string {
  return err.issues
    .map((i) => `${i.path.join(".") || "<root>"}: ${i.message}`)
    .join("; ");
}

main().catch((err) => {
  log.error("fatal", { err: err instanceof Error ? err.stack : String(err) });
  process.exit(1);
});
