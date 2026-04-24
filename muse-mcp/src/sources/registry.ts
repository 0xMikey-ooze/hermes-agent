import { config } from "../config.js";
import type { SourceName } from "../types.js";
import { DribbbleSource } from "./dribbble.js";
import { GodlySource } from "./godly.js";
import { LandbookSource } from "./landbook.js";
import type { Source } from "./source.js";

// Build the active source list from config. Additional sources plug in by
// adding an entry here and toggling via MUSE_SOURCES.
export function buildSources(): Source[] {
  const enabled = new Set(config.enabledSources);
  const sources: Source[] = [
    new LandbookSource(enabled.has("landbook")),
    new GodlySource(enabled.has("godly")),
    new DribbbleSource(enabled.has("dribbble")),
  ];
  return sources.filter((s) => s.enabled);
}

export function knownSourceNames(): SourceName[] {
  return ["landbook", "godly", "dribbble", "mobbin", "behance", "awwwards"];
}
