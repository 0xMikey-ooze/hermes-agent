/**
 * Core type definitions for AgentBrowser.
 * Mirrors the data model in PRD section 6.3.
 */

export type Hex = `0x${string}`;

export interface Session {
  id: string;
  walletAddress: Hex;
  walletPrivateKey: Hex;
  chainId: number;
  rpcUrl: string;
  forkUrl?: string;
  forkBlockNumber?: number;
  createdAt: number;
  expiresAt: number;
}

export type SessionEventKind = "rpc" | "sign" | "page" | "screenshot" | "error";

export interface SessionEvent {
  sessionId: string;
  ts: number;
  kind: SessionEventKind;
  payload: unknown;
}

export interface AgentBrowserOptions {
  /** Fork RPC URL (Alchemy/Infura/etc). When omitted Anvil runs as a fresh chain. */
  forkUrl?: string;
  /** Pin the fork to a specific block. Required for deterministic test runs. */
  forkBlockNumber?: number;
  /** Override chain id reported by the provider. Defaults to the forked chain id or 31337. */
  chainId?: number;
  /** Initial native-token balance funded into the agent wallet (in ether). Default: 10000. */
  fundEther?: number;
  /** Existing private key to use. When omitted a fresh key is generated per session. */
  privateKey?: Hex;
  /** Hard TTL in milliseconds before the session is auto-torn-down. Default: 30 minutes. */
  ttlMs?: number;
  /** Run the browser headfully (visible window) — useful for debugging. */
  headed?: boolean;
  /** Override path to the anvil binary. Defaults to `anvil` on PATH. */
  anvilPath?: string;
  /** Extra anvil CLI args appended to the spawned process. */
  anvilExtraArgs?: string[];
  /** Identify the wallet as MetaMask for legacy dApp compatibility. Default: true. */
  impersonateMetamask?: boolean;
  /** Optional event sink. Receives every RPC, sign, and page event for the session. */
  onEvent?: (event: SessionEvent) => void;
}

export interface SessionInfo {
  id: string;
  address: Hex;
  chainId: number;
  rpcUrl: string;
  forkUrl?: string;
  expiresAt: number;
}

export interface SignedTypedDataInput {
  domain: Record<string, unknown>;
  types: Record<string, Array<{ name: string; type: string }>>;
  primaryType?: string;
  message: Record<string, unknown>;
}

/**
 * Subset of EIP-1193 method names AgentBrowser handles in v1.
 * Anything not listed is forwarded raw to the underlying Anvil RPC.
 */
export type WalletRpcMethod =
  | "eth_requestAccounts"
  | "eth_accounts"
  | "eth_chainId"
  | "net_version"
  | "personal_sign"
  | "eth_sign"
  | "eth_signTypedData"
  | "eth_signTypedData_v3"
  | "eth_signTypedData_v4"
  | "eth_sendTransaction"
  | "wallet_switchEthereumChain"
  | "wallet_addEthereumChain"
  | "wallet_requestPermissions"
  | "wallet_getPermissions";
