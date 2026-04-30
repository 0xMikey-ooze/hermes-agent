import { strict as assert } from "node:assert";
import { test } from "node:test";
import { JsonRpcProvider, verifyMessage, verifyTypedData } from "ethers";
import { Wallet } from "../src/wallet.ts";

// Dummy provider — the wallet only touches it for tx submission, never for
// signing. These tests exercise pure signing paths so the URL is irrelevant.
const provider = new JsonRpcProvider("http://127.0.0.1:1");

test("Wallet generates a fresh keypair when none is supplied", () => {
  const w = new Wallet(undefined, provider);
  assert.match(w.address, /^0x[0-9a-fA-F]{40}$/);
  assert.match(w.privateKey, /^0x[0-9a-fA-F]{64}$/);
});

test("personalSign produces a recoverable signature for hex input", async () => {
  const w = new Wallet(undefined, provider);
  // "hello" as utf-8 hex
  const msgHex = "0x68656c6c6f";
  const sig = await w.personalSign(msgHex);
  // Recover with the same bytes ethers uses internally.
  const recovered = verifyMessage(Buffer.from("hello", "utf8"), sig);
  assert.equal(recovered.toLowerCase(), w.address.toLowerCase());
});

test("signTypedData strips EIP712Domain and verifies", async () => {
  const w = new Wallet(undefined, provider);
  const domain = { name: "Test", version: "1", chainId: 1, verifyingContract: "0x" + "11".repeat(20) };
  const types = {
    EIP712Domain: [{ name: "name", type: "string" }],
    Order: [
      { name: "maker", type: "address" },
      { name: "amount", type: "uint256" },
    ],
  };
  const message = { maker: w.address, amount: 1000n };
  const sig = await w.signTypedData({ domain, types, primaryType: "Order", message });
  const recovered = verifyTypedData(domain, { Order: types.Order }, message, sig);
  assert.equal(recovered.toLowerCase(), w.address.toLowerCase());
});
