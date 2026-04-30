import { createAnvil, type Anvil, type CreateAnvilOptions } from "@viem/anvil";
import { JsonRpcProvider } from "ethers";
import type { Hex } from "./types.js";

/**
 * AnvilManager owns the lifecycle of a local Anvil node — spawning, funding,
 * exposing cheats, and tearing down. One AnvilManager per session.
 *
 * Wraps @viem/anvil for process management and adds:
 *  - default-funded agent wallet
 *  - ergonomic cheat methods (impersonate, time-travel, snapshot/revert)
 *  - JSON-RPC provider plumbing for the rest of the SDK
 */
export class AnvilManager {
  private anvil: Anvil | null = null;
  private rpcProvider: JsonRpcProvider | null = null;
  private _rpcUrl: string | null = null;
  private _chainId: number | null = null;

  constructor(
    private readonly options: {
      forkUrl?: string;
      forkBlockNumber?: number;
      chainId?: number;
      anvilPath?: string;
      extraArgs?: string[];
    } = {},
  ) {}

  /** Spawn the Anvil process. Idempotent. */
  async start(): Promise<{ rpcUrl: string; chainId: number }> {
    if (this.anvil) {
      return { rpcUrl: this._rpcUrl!, chainId: this._chainId! };
    }

    const opts: CreateAnvilOptions = {
      forkUrl: this.options.forkUrl,
      forkBlockNumber: this.options.forkBlockNumber
        ? BigInt(this.options.forkBlockNumber)
        : undefined,
      chainId: this.options.chainId,
      anvilBinary: this.options.anvilPath,
    };

    this.anvil = createAnvil(opts);
    await this.anvil.start();

    this._rpcUrl = `http://${this.anvil.host}:${this.anvil.port}`;
    this.rpcProvider = new JsonRpcProvider(this._rpcUrl);

    // Resolve effective chain id (fork inherits from upstream when not overridden).
    const network = await this.rpcProvider.getNetwork();
    this._chainId = Number(network.chainId);

    return { rpcUrl: this._rpcUrl, chainId: this._chainId };
  }

  async stop(): Promise<void> {
    if (this.anvil) {
      await this.anvil.stop();
      this.anvil = null;
    }
    this.rpcProvider = null;
    this._rpcUrl = null;
    this._chainId = null;
  }

  get rpcUrl(): string {
    if (!this._rpcUrl) throw new Error("Anvil not started");
    return this._rpcUrl;
  }

  get chainId(): number {
    if (this._chainId == null) throw new Error("Anvil not started");
    return this._chainId;
  }

  /** Underlying ethers provider, useful for the rest of the SDK. */
  provider(): JsonRpcProvider {
    if (!this.rpcProvider) throw new Error("Anvil not started");
    return this.rpcProvider;
  }

  // --- Cheats (PRD 5.2 P0) -------------------------------------------------

  async setBalance(address: Hex, wei: bigint): Promise<void> {
    await this.send("anvil_setBalance", [address, "0x" + wei.toString(16)]);
  }

  async impersonate(address: Hex): Promise<void> {
    await this.send("anvil_impersonateAccount", [address]);
  }

  async stopImpersonating(address: Hex): Promise<void> {
    await this.send("anvil_stopImpersonatingAccount", [address]);
  }

  /** Mine N blocks. */
  async mine(blocks = 1): Promise<void> {
    await this.send("anvil_mine", ["0x" + blocks.toString(16), "0x0"]);
  }

  /** Advance the chain clock by `seconds` and mine a block. */
  async timeTravel(seconds: number): Promise<void> {
    await this.send("evm_increaseTime", [seconds]);
    await this.send("evm_mine", []);
  }

  /** Take a snapshot. Returns an opaque snapshot id usable with `revert`. */
  async snapshot(): Promise<string> {
    return this.send<string>("evm_snapshot", []);
  }

  /** Revert to a previously-taken snapshot. */
  async revert(snapshotId: string): Promise<boolean> {
    return this.send<boolean>("evm_revert", [snapshotId]);
  }

  /** Pin behaviour of a contract — read storage at a slot. */
  async getStorageAt(address: Hex, slot: Hex): Promise<Hex> {
    return this.send<Hex>("eth_getStorageAt", [address, slot, "latest"]);
  }

  /** Raw RPC escape hatch (PRD 5.3). */
  async send<T = unknown>(method: string, params: unknown[]): Promise<T> {
    return this.provider().send(method, params) as Promise<T>;
  }
}
