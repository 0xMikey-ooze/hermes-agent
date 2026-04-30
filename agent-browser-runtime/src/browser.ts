import { chromium, type Browser, type BrowserContext, type Page } from "playwright";
import { v4 as uuidv4 } from "uuid";
import { AnvilManager } from "./anvil.js";
import { ChainHelpers } from "./chain.js";
import { buildInjectionScript, type InjectionConfig } from "./inject.js";
import { NodeProvider } from "./provider.js";
import type {
  AgentBrowserOptions,
  Hex,
  Session,
  SessionEvent,
  SessionInfo,
} from "./types.js";
import { Wallet } from "./wallet.js";

const DEFAULT_TTL_MS = 30 * 60 * 1000;
const DEFAULT_FUND_ETHER = 10_000;

// 1x1 transparent PNG, base64-encoded. Real branding is a P2 concern (PRD 5.1).
const PLACEHOLDER_ICON =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

/**
 * AgentBrowser — the public top-level class.
 *
 * Lifecycle:
 *   const ab = await AgentBrowser.start(opts);
 *   await ab.goto("https://app.foxify.trade");
 *   ...
 *   await ab.stop();
 *
 * One AgentBrowser ⇄ one Anvil process ⇄ one ephemeral browser context.
 * For multi-session orchestration, instantiate multiple AgentBrowsers — they
 * are designed to be independent and parallel-safe.
 */
export class AgentBrowser {
  readonly session: Session;
  readonly chain: ChainHelpers;

  private constructor(
    private readonly anvil: AnvilManager,
    private readonly wallet: Wallet,
    private readonly browser: Browser,
    private readonly context: BrowserContext,
    private readonly _page: Page,
    private readonly nodeProvider: NodeProvider,
    private readonly ttlTimer: NodeJS.Timeout,
    session: Session,
  ) {
    this.session = session;
    this.chain = new ChainHelpers(anvil);
  }

  /** Spawn anvil + chromium + injected provider. Resolves when ready to navigate. */
  static async start(options: AgentBrowserOptions = {}): Promise<AgentBrowser> {
    const sessionId = uuidv4();
    const ttlMs = options.ttlMs ?? DEFAULT_TTL_MS;
    const onEvent = options.onEvent ?? (() => {});

    const anvil = new AnvilManager({
      forkUrl: options.forkUrl,
      forkBlockNumber: options.forkBlockNumber,
      chainId: options.chainId,
      anvilPath: options.anvilPath,
      extraArgs: options.anvilExtraArgs,
    });
    const { rpcUrl, chainId } = await anvil.start();

    const wallet = new Wallet(options.privateKey, anvil.provider());

    // Fund the wallet with the configured native amount (PRD 5.2 P0).
    const fundEther = options.fundEther ?? DEFAULT_FUND_ETHER;
    if (fundEther > 0) {
      const wei = BigInt(fundEther) * 10n ** 18n;
      await anvil.setBalance(wallet.address, wei);
    }

    const browser = await chromium.launch({ headless: !options.headed });
    const context = await browser.newContext();

    const nodeProvider = new NodeProvider(wallet, anvil, onEvent, sessionId);

    // Wire the page → node bridge. Returns a structured envelope so the page
    // can distinguish `ok` vs error without throwing across the IPC boundary.
    await context.exposeBinding(
      "__agentBrowserRpc",
      async (_source, payload: { id: number; method: string; params: unknown[] }) => {
        try {
          const value = await nodeProvider.request(payload.method, payload.params ?? []);
          return { ok: true, value };
        } catch (err) {
          const e = err as { message?: string; code?: number };
          return {
            ok: false,
            error: { message: e.message ?? String(err), code: e.code },
          };
        }
      },
    );

    const config: InjectionConfig = {
      address: wallet.address,
      chainId,
      isMetaMask: options.impersonateMetamask !== false,
      rdns: "trade.peopleppl.agentbrowser",
      walletName: "AgentBrowser",
      walletIconDataUrl: PLACEHOLDER_ICON,
    };
    await context.addInitScript({ content: buildInjectionScript(config) });

    const page = await context.newPage();

    const session: Session = {
      id: sessionId,
      walletAddress: wallet.address,
      walletPrivateKey: wallet.privateKey,
      chainId,
      rpcUrl,
      forkUrl: options.forkUrl,
      forkBlockNumber: options.forkBlockNumber,
      createdAt: Date.now(),
      expiresAt: Date.now() + ttlMs,
    };

    const ttlTimer = setTimeout(() => {
      onEvent({
        sessionId,
        ts: Date.now(),
        kind: "error",
        payload: { message: "session TTL exceeded; auto-stopping" },
      });
      void instance.stop();
    }, ttlMs);
    if (typeof ttlTimer.unref === "function") ttlTimer.unref();

    const instance = new AgentBrowser(
      anvil,
      wallet,
      browser,
      context,
      page,
      nodeProvider,
      ttlTimer,
      session,
    );

    // Pipe page console output into the event stream — invaluable for debugging
    // dApp-side errors during agent runs.
    page.on("console", (msg) => {
      onEvent({
        sessionId,
        ts: Date.now(),
        kind: "page",
        payload: { kind: "console", level: msg.type(), text: msg.text() },
      });
    });
    page.on("pageerror", (err) => {
      onEvent({
        sessionId,
        ts: Date.now(),
        kind: "page",
        payload: { kind: "pageerror", message: err.message },
      });
    });

    return instance;
  }

  /** Tear down browser, anvil, and timers. Idempotent. */
  async stop(): Promise<void> {
    clearTimeout(this.ttlTimer);
    try {
      await this.context.close();
    } catch {
      /* already closed */
    }
    try {
      await this.browser.close();
    } catch {
      /* already closed */
    }
    await this.anvil.stop();
  }

  // --- Public surface (PRD 5.3 P0) -----------------------------------------

  page(): Page {
    return this._page;
  }

  info(): SessionInfo {
    return {
      id: this.session.id,
      address: this.session.walletAddress,
      chainId: this.session.chainId,
      rpcUrl: this.session.rpcUrl,
      forkUrl: this.session.forkUrl,
      expiresAt: this.session.expiresAt,
    };
  }

  get address(): Hex {
    return this.session.walletAddress;
  }

  /** Navigate. Returns the final URL after redirects. */
  async goto(url: string, opts?: { timeoutMs?: number; waitUntil?: "load" | "domcontentloaded" | "networkidle" }): Promise<string> {
    const response = await this._page.goto(url, {
      timeout: opts?.timeoutMs ?? 30_000,
      waitUntil: opts?.waitUntil ?? "load",
    });
    return response?.url() ?? this._page.url();
  }

  /** Click a selector with sensible defaults. */
  async click(selector: string, opts?: { timeoutMs?: number }): Promise<void> {
    await this._page.click(selector, { timeout: opts?.timeoutMs ?? 15_000 });
  }

  async fill(selector: string, value: string, opts?: { timeoutMs?: number }): Promise<void> {
    await this._page.fill(selector, value, { timeout: opts?.timeoutMs ?? 15_000 });
  }

  async readText(selector: string, opts?: { timeoutMs?: number }): Promise<string> {
    const handle = await this._page.waitForSelector(selector, {
      timeout: opts?.timeoutMs ?? 15_000,
    });
    return (await handle.textContent()) ?? "";
  }

  async waitFor(selector: string, opts?: { timeoutMs?: number; state?: "visible" | "attached" | "hidden" | "detached" }): Promise<void> {
    await this._page.waitForSelector(selector, {
      timeout: opts?.timeoutMs ?? 30_000,
      state: opts?.state ?? "visible",
    });
  }

  /** PRD 5.3 P1 — base64 PNG ready for vision-LLM ingestion. */
  async screenshot(opts?: { fullPage?: boolean }): Promise<string> {
    const buf = await this._page.screenshot({ fullPage: opts?.fullPage ?? false });
    return buf.toString("base64");
  }

  /**
   * PRD 5.3 P1 — accessibility tree for non-vision agents. Uses Chrome DevTools
   * Protocol directly since Playwright dropped the high-level `page.accessibility`
   * shim in 1.50+.
   */
  async getAccessibilityTree(): Promise<unknown> {
    const cdp = await this.context.newCDPSession(this._page);
    try {
      return await cdp.send("Accessibility.getFullAXTree");
    } finally {
      await cdp.detach().catch(() => {});
    }
  }

  /** PRD 5.3 P0 — direct RPC escape hatch (read or write). */
  async send<T = unknown>(method: string, params: unknown[] = []): Promise<T> {
    return this.anvil.send<T>(method, params);
  }

  // --- Anvil cheats (PRD 5.2 P0) -------------------------------------------

  async impersonate(address: Hex): Promise<void> {
    return this.anvil.impersonate(address);
  }

  async stopImpersonating(address: Hex): Promise<void> {
    return this.anvil.stopImpersonating(address);
  }

  async mine(blocks = 1): Promise<void> {
    return this.anvil.mine(blocks);
  }

  async timeTravel(seconds: number): Promise<void> {
    return this.anvil.timeTravel(seconds);
  }

  async snapshot(): Promise<string> {
    return this.anvil.snapshot();
  }

  async revert(snapshotId: string): Promise<boolean> {
    return this.anvil.revert(snapshotId);
  }
}

export type { SessionEvent };
