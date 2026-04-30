import type { TransactionRequest } from "ethers";
import type { AnvilManager } from "./anvil.js";
import type { Wallet } from "./wallet.js";
import type {
  Hex,
  SessionEvent,
  SignedTypedDataInput,
  WalletRpcMethod,
} from "./types.js";

/**
 * NodeProvider is the trusted half of the EIP-1193 split.
 *
 * The page calls `window.ethereum.request({method, params})`; the page-side
 * shim forwards that to a Node binding which lands here. Every method runs
 * with PK access in Node and returns a result the page receives.
 *
 * Anything not in WalletRpcMethod is forwarded raw to Anvil.
 */
export class NodeProvider {
  private currentChainId: number;
  private permissionsGranted = false;

  constructor(
    private readonly wallet: Wallet,
    private readonly anvil: AnvilManager,
    private readonly emit: (event: SessionEvent) => void,
    private readonly sessionId: string,
  ) {
    this.currentChainId = anvil.chainId;
  }

  /** Entry point — single dispatch for every JSON-RPC request from the page. */
  async request(method: string, params: unknown[]): Promise<unknown> {
    this.emitEvent("rpc", { method, params });
    try {
      const result = await this.dispatch(method as WalletRpcMethod, params);
      return result;
    } catch (err) {
      this.emitEvent("error", { method, params, error: errToObj(err) });
      throw err;
    }
  }

  private async dispatch(method: WalletRpcMethod | string, params: unknown[]): Promise<unknown> {
    switch (method) {
      case "eth_requestAccounts": {
        this.permissionsGranted = true;
        return [this.wallet.address];
      }
      case "eth_accounts":
        return this.permissionsGranted ? [this.wallet.address] : [];

      case "eth_chainId":
        return "0x" + this.currentChainId.toString(16);

      case "net_version":
        return String(this.currentChainId);

      case "wallet_requestPermissions": {
        this.permissionsGranted = true;
        return [{ parentCapability: "eth_accounts", caveats: [] }];
      }
      case "wallet_getPermissions":
        return this.permissionsGranted
          ? [{ parentCapability: "eth_accounts", caveats: [] }]
          : [];

      case "personal_sign": {
        const [message, account] = params as [Hex, Hex];
        this.assertAccount(account);
        const sig = await this.wallet.personalSign(message);
        this.emitEvent("sign", { kind: "personal_sign", message });
        return sig;
      }

      case "eth_sign": {
        const [account, message] = params as [Hex, Hex];
        this.assertAccount(account);
        const sig = await this.wallet.ethSign(message);
        this.emitEvent("sign", { kind: "eth_sign", message });
        return sig;
      }

      case "eth_signTypedData":
      case "eth_signTypedData_v3":
      case "eth_signTypedData_v4": {
        const [account, payload] = params as [Hex, string | SignedTypedDataInput];
        this.assertAccount(account);
        const typed = typeof payload === "string"
          ? (JSON.parse(payload) as SignedTypedDataInput)
          : payload;
        const sig = await this.wallet.signTypedData(typed);
        this.emitEvent("sign", { kind: method, domain: typed.domain, primaryType: typed.primaryType });
        return sig;
      }

      case "eth_sendTransaction": {
        const [tx] = params as [PageTxRequest];
        this.assertAccount(tx.from);
        const txReq = normalizeTxRequest(tx);
        const hash = await this.wallet.sendTransaction(txReq);
        this.emitEvent("sign", { kind: "eth_sendTransaction", to: tx.to, value: tx.value, hash });
        return hash;
      }

      case "wallet_switchEthereumChain": {
        const [{ chainId }] = params as [{ chainId: Hex }];
        const target = parseInt(chainId, 16);
        if (target !== this.currentChainId) {
          // PRD 5.1 P0 — basic same-anvil switch. Multi-chain is P1.
          throw new Error(
            `wallet_switchEthereumChain to ${target} not supported; current chain is ${this.currentChainId}. ` +
              `Multi-chain mid-session switching is a P1 feature.`,
          );
        }
        return null;
      }

      case "wallet_addEthereumChain":
        // Best-effort no-op — we already control the chain via Anvil.
        return null;

      default:
        // Forward read-only or unrecognized methods to Anvil directly.
        return this.anvil.send(method, params);
    }
  }

  private assertAccount(provided: Hex | undefined): void {
    if (!provided) return;
    if (provided.toLowerCase() !== this.wallet.address.toLowerCase()) {
      throw new Error(
        `account mismatch: page asked for ${provided}, wallet is ${this.wallet.address}`,
      );
    }
  }

  private emitEvent(kind: SessionEvent["kind"], payload: unknown) {
    this.emit({ sessionId: this.sessionId, ts: Date.now(), kind, payload });
  }
}

interface PageTxRequest {
  from?: Hex;
  to?: Hex;
  value?: Hex | string;
  data?: Hex;
  gas?: Hex;
  gasPrice?: Hex;
  maxFeePerGas?: Hex;
  maxPriorityFeePerGas?: Hex;
  nonce?: Hex;
}

function normalizeTxRequest(tx: PageTxRequest): TransactionRequest {
  return {
    to: tx.to,
    value: tx.value,
    data: tx.data,
    gasLimit: tx.gas,
    gasPrice: tx.gasPrice,
    maxFeePerGas: tx.maxFeePerGas,
    maxPriorityFeePerGas: tx.maxPriorityFeePerGas,
    nonce: tx.nonce ? parseInt(tx.nonce, 16) : undefined,
  };
}

function errToObj(e: unknown): { message: string; code?: number } {
  if (e instanceof Error) {
    return { message: e.message, code: (e as { code?: number }).code };
  }
  return { message: String(e) };
}
