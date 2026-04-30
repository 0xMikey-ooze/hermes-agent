/**
 * Phase 1 reference flow (PRD section 11.1).
 *
 * Validates Foxify's connect → deposit → open → close → withdraw sequence
 * against an Arbitrum fork. Run with:
 *
 *   ARB_RPC=https://arb-mainnet.g.alchemy.com/v2/<key> \
 *   npx tsx examples/foxify-flow.ts
 *
 * The sequence matches PRD 11.1 exactly. Selectors are placeholders — Foxify
 * frontend partners need to wire the real test ids. The point of this file is
 * to demonstrate the SDK shape and serve as a CI harness skeleton.
 */
import { AgentBrowser } from "../src/index.js";

async function main(): Promise<void> {
  const forkUrl = process.env.ARB_RPC;
  if (!forkUrl) {
    throw new Error("ARB_RPC env var required (Alchemy/Infura/QuickNode)");
  }

  const ab = await AgentBrowser.start({
    forkUrl,
    chainId: 42161,
    fundEther: 10,
    onEvent: (e) => process.stderr.write(`[${e.kind}] ${JSON.stringify(e.payload)}\n`),
  });

  const t0 = Date.now();
  try {
    // 1. CONNECT
    await ab.goto("https://app.foxify.trade");
    await ab.click('button:has-text("Connect Wallet")');
    await ab.click('button:has-text("MetaMask")'); // EIP-6963 entry
    await ab.waitFor(`text=${ab.address.slice(0, 6)}`); // address chip visible

    // 2. DEPOSIT COLLATERAL
    await ab.click('button:has-text("Deposit")');
    await ab.fill('input[name="amount"]', "1000");
    await ab.click('button:has-text("Approve")'); // signs EIP-2612 permit
    await ab.click('button:has-text("Deposit")');
    await ab.waitFor('text=Deposit confirmed');

    // 3. OPEN LONG
    await ab.click('[data-testid="pair-eth-usdc"]');
    await ab.fill('input[name="leverage"]', "5");
    await ab.fill('input[name="size"]', "500");
    await ab.click('button:has-text("Long")');
    await ab.waitFor('text=Position opened');

    // 4. CLOSE
    await ab.click('[data-testid="position-card"]');
    await ab.click('button:has-text("Close")');
    await ab.waitFor('text=Position closed');

    // 5. WITHDRAW
    await ab.click('button:has-text("Withdraw")');
    await ab.click('button:has-text("Max")');
    await ab.click('button:has-text("Confirm")');
    await ab.waitFor('text=Withdrawal confirmed');

    const elapsedSec = ((Date.now() - t0) / 1000).toFixed(1);
    process.stdout.write(`✓ flow completed in ${elapsedSec}s (PRD budget: 60s)\n`);
  } finally {
    await ab.stop();
  }
}

main().catch((err) => {
  process.stderr.write(`flow failed: ${err?.stack ?? err}\n`);
  process.exit(1);
});
