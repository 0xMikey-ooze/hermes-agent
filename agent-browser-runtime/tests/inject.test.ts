import { strict as assert } from "node:assert";
import { test } from "node:test";
import { buildInjectionScript } from "../src/inject.ts";

test("buildInjectionScript inlines config and returns a self-invoking IIFE", () => {
  const script = buildInjectionScript({
    address: "0x000000000000000000000000000000000000dEaD",
    chainId: 42161,
    isMetaMask: true,
    rdns: "trade.peopleppl.agentbrowser",
    walletName: "AgentBrowser",
    walletIconDataUrl: "data:image/png;base64,AAAA",
  });
  assert.match(script, /^\(function/);
  assert.match(script, /\)\(\);$/);
  assert.match(script, /"chainId":42161/);
  assert.match(script, /isMetaMask/);
  // The page-side function must reference the config token nowhere — every
  // occurrence should have been substituted at build time.
  assert.equal(script.includes("__AGENT_BROWSER_CONFIG__"), false);
});

test("buildInjectionScript escapes config safely as JSON", () => {
  // A walletName containing a quote must not break the surrounding script.
  const script = buildInjectionScript({
    address: "0x000000000000000000000000000000000000dEaD",
    chainId: 1,
    isMetaMask: false,
    rdns: "x",
    walletName: 'evil"name',
    walletIconDataUrl: "data:image/png;base64,AAAA",
  });
  assert.match(script, /"walletName":"evil\\"name"/);
});
