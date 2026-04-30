#!/usr/bin/env node
/**
 * `agent-browser` CLI.
 *
 *   agent-browser run <script>     execute a TypeScript/JS script with `tsx`
 *   agent-browser mcp              start the MCP stdio server
 *
 * The `run` command is intentionally thin — it just hands the script off to
 * `tsx` so users get top-level await, TS, and ESM out of the box. Real agents
 * import the SDK directly.
 */
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { startMcpServer } from "./mcp/server.js";

const argv = process.argv.slice(2);
const cmd = argv[0];

async function main(): Promise<number> {
  switch (cmd) {
    case undefined:
    case "-h":
    case "--help":
    case "help":
      printHelp();
      return 0;

    case "mcp":
      await startMcpServer();
      return 0;

    case "run": {
      const scriptArg = argv[1];
      if (!scriptArg) {
        process.stderr.write("error: `agent-browser run` needs a script path\n");
        return 1;
      }
      const script = resolve(process.cwd(), scriptArg);
      return new Promise<number>((resolveExit) => {
        const child = spawn("npx", ["tsx", script, ...argv.slice(2)], {
          stdio: "inherit",
          env: process.env,
        });
        child.on("close", (code) => resolveExit(code ?? 0));
      });
    }

    default:
      process.stderr.write(`unknown command: ${cmd}\n`);
      printHelp();
      return 1;
  }
}

function printHelp(): void {
  process.stdout.write(
    [
      "agent-browser — headless EVM-aware browser runtime for agents",
      "",
      "usage:",
      "  agent-browser run <script.ts>    Run an agent script with tsx",
      "  agent-browser mcp                Start the MCP stdio server",
      "",
    ].join("\n"),
  );
}

main().then(
  (code) => process.exit(code),
  (err) => {
    process.stderr.write(`agent-browser failed: ${err?.stack ?? err}\n`);
    process.exit(1);
  },
);
