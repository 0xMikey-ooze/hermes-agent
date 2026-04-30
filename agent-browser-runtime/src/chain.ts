import { Contract, formatEther, formatUnits, parseEther, parseUnits } from "ethers";
import type { AnvilManager } from "./anvil.js";
import type { Hex } from "./types.js";

const ERC20_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function decimals() view returns (uint8)",
  "function symbol() view returns (string)",
  "function transfer(address,uint256) returns (bool)",
];

/**
 * Chain helpers. These are the read/write convenience methods exposed both
 * directly (sdk.chain.getEthBalance) and via the MCP tool surface.
 */
export class ChainHelpers {
  constructor(private readonly anvil: AnvilManager) {}

  async getEthBalance(address: Hex): Promise<{ wei: bigint; ether: string }> {
    const wei = await this.anvil.provider().getBalance(address);
    return { wei, ether: formatEther(wei) };
  }

  /** Force a balance via Anvil cheat. `etherAmount` accepts a decimal string. */
  async setEthBalance(address: Hex, etherAmount: string | number): Promise<void> {
    const wei = parseEther(String(etherAmount));
    await this.anvil.setBalance(address, wei);
  }

  async getTokenBalance(token: Hex, holder: Hex): Promise<{
    raw: bigint;
    formatted: string;
    decimals: number;
    symbol: string;
  }> {
    const c = new Contract(token, ERC20_ABI, this.anvil.provider());
    const [raw, decimals, symbol] = await Promise.all([
      c.getFunction("balanceOf").staticCall(holder) as Promise<bigint>,
      c.getFunction("decimals").staticCall() as Promise<number>,
      (c.getFunction("symbol").staticCall() as Promise<string>).catch(() => "UNKNOWN"),
    ]);
    return { raw, formatted: formatUnits(raw, decimals), decimals, symbol };
  }

  /**
   * Fund an arbitrary ERC-20 by impersonating a whale. PRD 5.2 P1.
   * Caller supplies the whale; we don't try to auto-discover one.
   */
  async fundErc20(args: {
    token: Hex;
    whale: Hex;
    recipient: Hex;
    amount: string;
  }): Promise<Hex> {
    const { token, whale, recipient, amount } = args;
    const c = new Contract(token, ERC20_ABI, this.anvil.provider());
    const decimals = (await c.getFunction("decimals").staticCall()) as number;
    const raw = parseUnits(amount, decimals);

    await this.anvil.impersonate(whale);
    // Top up the whale's gas so the transfer can be paid for.
    await this.anvil.setBalance(whale, parseEther("10"));

    const txHash = (await this.anvil.send<Hex>("eth_sendTransaction", [
      {
        from: whale,
        to: token,
        data: c.interface.encodeFunctionData("transfer", [recipient, raw]),
      },
    ]));
    await this.anvil.provider().waitForTransaction(txHash);
    await this.anvil.stopImpersonating(whale);
    return txHash;
  }
}
