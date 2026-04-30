import {
  HDNodeWallet,
  Wallet as EthersWallet,
  type Provider,
  type TransactionRequest,
  type TypedDataDomain,
  type TypedDataField,
  getBytes,
  hashMessage,
  isHexString,
  toUtf8String,
} from "ethers";
import type { Hex, SignedTypedDataInput } from "./types.js";

/**
 * Node-side wallet. Holds the private key, performs all signing, and submits
 * transactions to the underlying RPC. The browser page never sees the PK —
 * sign requests come over `page.exposeBinding` and return finished signatures.
 *
 * Security invariant: PK is constructed in this file and only leaves via
 * sign/sendTransaction return values. It is never written to disk and never
 * exposed to the page via `addInitScript`.
 */
export class Wallet {
  private readonly signer: EthersWallet | HDNodeWallet;
  readonly address: Hex;
  readonly privateKey: Hex;

  constructor(privateKey: Hex | undefined, provider: Provider) {
    if (privateKey) {
      this.signer = new EthersWallet(privateKey, provider);
      this.privateKey = privateKey;
    } else {
      const fresh = EthersWallet.createRandom(provider);
      this.signer = fresh.connect(provider);
      this.privateKey = fresh.privateKey as Hex;
    }
    this.address = this.signer.address as Hex;
  }

  /**
   * personal_sign — message arrives hex-encoded per EIP-191. ethers handles the
   * `\x19Ethereum Signed Message:\n` prefix automatically when given bytes.
   */
  async personalSign(messageHex: Hex): Promise<Hex> {
    // Some dApps pass UTF-8 strings already; tolerate both.
    const bytes = isHexString(messageHex) ? getBytes(messageHex) : toUtf8String(messageHex);
    const sig = await this.signer.signMessage(bytes);
    return sig as Hex;
  }

  /** eth_sign — legacy raw-hash signing. Treated as personal_sign for safety. */
  async ethSign(messageHex: Hex): Promise<Hex> {
    return this.personalSign(messageHex);
  }

  /**
   * EIP-712 typed-data signing. Strips the EIP712Domain entry that some dApps
   * include in `types` since ethers v6 rejects it.
   */
  async signTypedData(input: SignedTypedDataInput): Promise<Hex> {
    const types = { ...input.types };
    delete types.EIP712Domain;
    const sig = await this.signer.signTypedData(
      input.domain as TypedDataDomain,
      types as Record<string, TypedDataField[]>,
      input.message,
    );
    return sig as Hex;
  }

  /** Submit a transaction signed by this wallet. Returns the tx hash. */
  async sendTransaction(tx: TransactionRequest): Promise<Hex> {
    const sent = await this.signer.sendTransaction(tx);
    return sent.hash as Hex;
  }

  /** Hash an arbitrary message the same way personal_sign would, for testing. */
  static personalHash(message: string | Uint8Array): Hex {
    return hashMessage(message) as Hex;
  }
}
