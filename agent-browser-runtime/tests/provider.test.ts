import { strict as assert } from "node:assert";
import { test } from "node:test";
import { JsonRpcProvider, verifyMessage } from "ethers";
import { NodeProvider } from "../src/provider.ts";
import { Wallet } from "../src/wallet.ts";
import type { AnvilManager } from "../src/anvil.ts";
import type { SessionEvent } from "../src/types.ts";

// Stand-in AnvilManager — we don't spawn a real anvil for this unit test.
function makeFakeAnvil(chainId: number) {
  const calls: Array<{ method: string; params: unknown[] }> = [];
  const fake = {
    chainId,
    rpcUrl: "http://fake",
    provider() {
      throw new Error("not used");
    },
    async setBalance() {},
    async impersonate() {},
    async stopImpersonating() {},
    async mine() {},
    async timeTravel() {},
    async snapshot() {
      return "0x1";
    },
    async revert() {
      return true;
    },
    async getStorageAt() {
      return "0x" + "0".repeat(64);
    },
    async send(method: string, params: unknown[]) {
      calls.push({ method, params });
      if (method === "eth_blockNumber") return "0x10";
      return null;
    },
  } as unknown as AnvilManager;
  return { fake, calls };
}

test("eth_requestAccounts returns the wallet address and grants permissions", async () => {
  const { fake } = makeFakeAnvil(31337);
  const w = new Wallet(undefined, new JsonRpcProvider("http://127.0.0.1:1"));
  const events: SessionEvent[] = [];
  const p = new NodeProvider(w, fake, (e) => events.push(e), "session-1");

  const before = await p.request("eth_accounts", []);
  assert.deepEqual(before, []);

  const after = await p.request("eth_requestAccounts", []);
  assert.deepEqual(after, [w.address]);

  const post = await p.request("eth_accounts", []);
  assert.deepEqual(post, [w.address]);

  const rpcEvents = events.filter((e) => e.kind === "rpc");
  assert.equal(rpcEvents.length, 3);
});

test("eth_chainId returns hex chain id from anvil", async () => {
  const { fake } = makeFakeAnvil(42161);
  const w = new Wallet(undefined, new JsonRpcProvider("http://127.0.0.1:1"));
  const p = new NodeProvider(w, fake, () => {}, "s");
  const cid = await p.request("eth_chainId", []);
  assert.equal(cid, "0xa4b1");
});

test("personal_sign delegates to the wallet and is verifiable", async () => {
  const { fake } = makeFakeAnvil(1);
  const w = new Wallet(undefined, new JsonRpcProvider("http://127.0.0.1:1"));
  const p = new NodeProvider(w, fake, () => {}, "s");
  const msgHex = "0x68656c6c6f"; // "hello"
  const sig = (await p.request("personal_sign", [msgHex, w.address])) as string;
  const recovered = verifyMessage(Buffer.from("hello", "utf8"), sig);
  assert.equal(recovered.toLowerCase(), w.address.toLowerCase());
});

test("account-mismatched signing requests are rejected", async () => {
  const { fake } = makeFakeAnvil(1);
  const w = new Wallet(undefined, new JsonRpcProvider("http://127.0.0.1:1"));
  const p = new NodeProvider(w, fake, () => {}, "s");
  await assert.rejects(
    () => p.request("personal_sign", ["0x68656c6c6f", "0x" + "11".repeat(20)]),
    /account mismatch/,
  );
});

test("unknown methods are forwarded to anvil verbatim", async () => {
  const { fake, calls } = makeFakeAnvil(1);
  const w = new Wallet(undefined, new JsonRpcProvider("http://127.0.0.1:1"));
  const p = new NodeProvider(w, fake, () => {}, "s");
  const result = await p.request("eth_blockNumber", []);
  assert.equal(result, "0x10");
  assert.equal(calls.at(-1)?.method, "eth_blockNumber");
});

test("wallet_switchEthereumChain to a different chain throws (P0 limitation)", async () => {
  const { fake } = makeFakeAnvil(31337);
  const w = new Wallet(undefined, new JsonRpcProvider("http://127.0.0.1:1"));
  const p = new NodeProvider(w, fake, () => {}, "s");
  await assert.rejects(
    () => p.request("wallet_switchEthereumChain", [{ chainId: "0xa4b1" }]),
    /not supported/,
  );
});
