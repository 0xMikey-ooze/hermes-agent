/**
 * Page-side injection script.
 *
 * Runs at document_start in every frame. It installs `window.ethereum`,
 * announces the wallet via EIP-6963, and bridges every JSON-RPC call to a
 * Node binding (`__agentBrowserRpc`) which Playwright wires up via
 * `page.exposeBinding`.
 *
 * The script is built from a single source-of-truth function that gets
 * stringified — that way it survives Playwright's `addInitScript` (which
 * passes a string to the page).
 */

export interface InjectionConfig {
  address: string;
  chainId: number;
  isMetaMask: boolean;
  rdns: string;
  walletName: string;
  walletIconDataUrl: string;
}

/**
 * The function that actually runs in the page. Kept self-contained so it can
 * be `.toString()`-ed without bundler help.
 *
 * NOTE: Anything captured from the closure must be inlined as JSON literals
 * in `buildInjectionScript` below — the page has no access to Node scope.
 */
declare const __AGENT_BROWSER_CONFIG__: InjectionConfig;

function pageScript(): void {
  const config = __AGENT_BROWSER_CONFIG__;

  type PendingHandler = {
    resolve: (value: unknown) => void;
    reject: (reason: unknown) => void;
  };

  const pending = new Map<number, PendingHandler>();
  let nextId = 1;

  const rpc: (payload: { id: number; method: string; params: unknown[] }) => Promise<unknown> =
    (window as unknown as { __agentBrowserRpc: (payload: unknown) => Promise<unknown> })
      .__agentBrowserRpc;

  if (typeof rpc !== "function") {
    // Binding hasn't landed yet — leave a marker so Node can detect/log it.
    (window as unknown as Record<string, unknown>).__agentBrowserError =
      "binding-missing";
    return;
  }

  type Listener = (...args: unknown[]) => void;
  const listeners = new Map<string, Set<Listener>>();

  function emit(event: string, ...args: unknown[]): void {
    const set = listeners.get(event);
    if (!set) return;
    for (const listener of set) {
      try {
        listener(...args);
      } catch {
        /* swallow listener errors per EIP-1193 guidance */
      }
    }
  }

  async function request(args: { method: string; params?: unknown[] }): Promise<unknown> {
    const id = nextId++;
    const params = args.params ?? [];
    const promise = new Promise<unknown>((resolve, reject) => {
      pending.set(id, { resolve, reject });
    });

    rpc({ id, method: args.method, params })
      .then((result) => {
        const handler = pending.get(id);
        if (!handler) return;
        pending.delete(id);
        const r = result as { ok: boolean; value?: unknown; error?: { message: string; code?: number } };
        if (r && r.ok) {
          handler.resolve(r.value);
        } else {
          const errPayload = (r && r.error) || { message: "unknown error" };
          const err = new Error(errPayload.message) as Error & { code?: number };
          if (errPayload.code != null) err.code = errPayload.code;
          handler.reject(err);
        }
      })
      .catch((err) => {
        const handler = pending.get(id);
        if (!handler) return;
        pending.delete(id);
        handler.reject(err);
      });

    // Side-effects mirroring real wallets — emit chain/account changes after
    // the call resolves so dApps that listen update their UI.
    promise.then((value) => {
      if (args.method === "wallet_switchEthereumChain") {
        emit("chainChanged", "0x" + config.chainId.toString(16));
      } else if (
        args.method === "eth_requestAccounts" ||
        args.method === "wallet_requestPermissions"
      ) {
        emit("accountsChanged", value);
        emit("connect", { chainId: "0x" + config.chainId.toString(16) });
      }
    }).catch(() => {});

    return promise;
  }

  interface InjectedProvider {
    isMetaMask: boolean;
    isAgentBrowser: boolean;
    chainId: string;
    networkVersion: string;
    selectedAddress: string;
    request(args: { method: string; params?: unknown[] }): Promise<unknown>;
    send(methodOrPayload: unknown, paramsOrCallback?: unknown): unknown;
    sendAsync(
      payload: { id?: number; method: string; params?: unknown[] },
      cb: (err: unknown, result: unknown) => void,
    ): void;
    on(event: string, listener: Listener): InjectedProvider;
    removeListener(event: string, listener: Listener): InjectedProvider;
    enable(): Promise<unknown>;
  }

  const provider: InjectedProvider = {
    isMetaMask: config.isMetaMask,
    isAgentBrowser: true,
    chainId: "0x" + config.chainId.toString(16),
    networkVersion: String(config.chainId),
    selectedAddress: config.address,

    request,

    // Legacy synchronous send() compatibility — return cached values where
    // possible, throw otherwise. Modern dApps don't hit this path.
    send(methodOrPayload: unknown, paramsOrCallback?: unknown): unknown {
      if (typeof methodOrPayload === "string") {
        return request({ method: methodOrPayload, params: (paramsOrCallback as unknown[]) ?? [] });
      }
      const payload = methodOrPayload as { id?: number; method: string; params?: unknown[] };
      const cb = paramsOrCallback as ((err: unknown, result: unknown) => void) | undefined;
      request({ method: payload.method, params: payload.params })
        .then((result) => cb && cb(null, { id: payload.id, jsonrpc: "2.0", result }))
        .catch((err) => cb && cb(err, null));
      return undefined;
    },

    sendAsync(payload, cb): void {
      request({ method: payload.method, params: payload.params })
        .then((result) => cb(null, { id: payload.id, jsonrpc: "2.0", result }))
        .catch((err) => cb(err, null));
    },

    on(event, listener) {
      let set = listeners.get(event);
      if (!set) {
        set = new Set();
        listeners.set(event, set);
      }
      set.add(listener);
      return provider;
    },

    removeListener(event, listener) {
      listeners.get(event)?.delete(listener);
      return provider;
    },

    enable() {
      return request({ method: "eth_requestAccounts" });
    },
  };

  Object.defineProperty(window, "ethereum", {
    value: provider,
    writable: false,
    configurable: false,
  });

  // EIP-6963 announcement — required by RainbowKit / wagmi / Web3Modal.
  const info = {
    uuid: cryptoRandomUuid(),
    name: config.walletName,
    icon: config.walletIconDataUrl,
    rdns: config.rdns,
  };
  const announce = () => {
    window.dispatchEvent(
      new CustomEvent("eip6963:announceProvider", {
        detail: Object.freeze({ info, provider }),
      }),
    );
  };

  window.addEventListener("eip6963:requestProvider", announce);
  announce();

  function cryptoRandomUuid(): string {
    const c = (window.crypto as Crypto | undefined);
    if (c && typeof c.randomUUID === "function") return c.randomUUID();
    // Fallback — sufficient for EIP-6963 uniqueness within a session.
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
      const r = (Math.random() * 16) | 0;
      const v = ch === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
}

/**
 * Generate the page-side script as a single string by stringifying
 * `pageScript` and inlining the config as a JSON literal where the
 * `__AGENT_BROWSER_CONFIG__` token is referenced.
 */
export function buildInjectionScript(config: InjectionConfig): string {
  const body = pageScript.toString();
  const literal = JSON.stringify(config);
  // Replace the declared identifier with the literal config.
  const inlined = body.replace(/__AGENT_BROWSER_CONFIG__/g, literal);
  return `(${inlined})();`;
}
