# AgentBrowser

Headless, EVM-aware browser runtime for autonomous agents. Combines Playwright + Anvil + an injected EIP-1193/6963 provider so a Claude/Hermes/OpenClaw agent can drive crypto dApps end-to-end — connecting, signing, sending transactions — without MetaMask popups, extension state, or human-in-the-loop confirmation.

> **Status:** Phase 1 alpha (PRD §8). P0 surface complete, dependencies declared, tests pass under `node --test`. `npm install` and a local `anvil` binary required to actually run sessions.

## Why this exists

Synpress is slow and flaky. Direct RPC bypass loses front-end fidelity. Browserbase / Computer Use are wallet-agnostic. AgentBrowser is the canonical primitive that:

- spawns a fresh wallet + fresh forked chain + fresh browser context in a single call
- announces over EIP-6963 so RainbowKit / wagmi / ConnectKit / Web3Modal pick it up automatically
- handles every signing method server-side — the page never sees the private key
- exposes Anvil cheats (impersonate, time-travel, snapshot/revert) as first-class agent tools
- ships an MCP stdio server so any agent framework can drive it as a tool

## Install

```bash
npm install @peopleppl/agent-browser
npx playwright install chromium
# anvil binary required on PATH (https://book.getfoundry.sh/anvil/)
```

## SDK quickstart

```ts
import { AgentBrowser } from "@peopleppl/agent-browser";

const ab = await AgentBrowser.start({
  forkUrl: process.env.ARB_RPC,
  chainId: 42161,
  fundEther: 10,
});

await ab.goto("https://app.foxify.trade");
await ab.click('button:has-text("Connect Wallet")');
await ab.click('button:has-text("MetaMask")'); // EIP-6963 picks AgentBrowser

const balance = await ab.chain.getEthBalance(ab.address);
console.log(balance.ether);

await ab.stop();
```

## MCP server

```bash
npx agent-browser mcp
```

Wire it into Claude Code or OpenClaw via stdio. Tool surface:

- `session.start`, `session.stop`, `session.info`
- `page.goto`, `page.click`, `page.fill`, `page.readText`, `page.waitFor`, `page.screenshot`, `page.accessibility`
- `chain.getEthBalance`, `chain.setEthBalance`, `chain.getTokenBalance`, `chain.fundErc20`
- `chain.timeTravel`, `chain.mine`, `chain.snapshot`, `chain.revert`
- `rpc.send` (escape hatch)

## Architecture

```
Agent runtime ──► AgentBrowser SDK ──► Playwright Chromium ──► dApp DOM
                       │                       ▲
                       │              window.ethereum (EIP-1193 + 6963)
                       │                       │   forwards every request
                       ▼                       │   via page.exposeBinding
                  Wallet (PK) ◄────────────────┘
                       │
                       ▼
                  Anvil (local or fork)
```

The page-side script (`src/inject.ts`) installs `window.ethereum` and dispatches every `request()` over a single Playwright binding. The Node-side `NodeProvider` (`src/provider.ts`) holds the only PK reference and signs everything in-process. PRD §6.4 security model.

## Mapping to the PRD

| PRD section                        | Implementation                                                  |
|------------------------------------|-----------------------------------------------------------------|
| 5.1 Browser & wallet (P0)          | `src/browser.ts`, `src/inject.ts`, `src/provider.ts`            |
| 5.2 Chain management (P0)          | `src/anvil.ts`, `src/chain.ts`                                  |
| 5.3 Agent API (P0)                 | `AgentBrowser.{goto,click,fill,readText,screenshot,waitFor}`    |
| 5.3 Vision / a11y (P1)             | `AgentBrowser.{screenshot,getAccessibilityTree}`                |
| 5.4 MCP server (P0, stdio)         | `src/mcp/server.ts`                                             |
| 5.5 Sandbox / isolation (P0)       | Per-instance ephemeral wallet/context/anvil; TTL auto-teardown  |
| 11.1 Foxify reference flow         | `examples/foxify-flow.ts`                                       |

## Tests

```bash
npm test     # node --test, no browser required
npm run typecheck
```

Unit tests exercise the wallet, provider, and injection-script builder in isolation. Integration tests against a real Anvil + Chromium are the next milestone (Phase 1 exit criteria, PRD §8).

## Roadmap (PRD §8)

- **Phase 1 (alpha)** — current. P0 surface against Foxify on Arbitrum fork.
- **Phase 2 (MCP + multi-tenant)** — per-session Daytona sandboxes, RPC traces, hourly Sentinel runs.
- **Phase 3 (Hermes)** — HTTP/SSE transport, ERC-20 funding helpers, recording/replay.
- **Phase 4 (external beta)** — public npm + docs site + 3 design partners.
