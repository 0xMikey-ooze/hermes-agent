// Core data model for Muse. Every pipeline stage reads/writes these shapes.

export type Scope =
  | "landing_page"
  | "app_ui"
  | "component"
  | "full_site"
  | "logo";

export type Density = "sparse" | "balanced" | "dense";

export type SourceName =
  | "landbook"
  | "godly"
  | "mobbin"
  | "behance"
  | "awwwards"
  | "saaslandingpage"
  | "screenlane"
  | "lapaninja"
  | "refero"
  | "dribbble";

export interface IntentTags {
  scope: Scope;
  category: string;              // e.g. "food tour", "ai crm admin"
  audience: string;              // e.g. "travelers 30-55"
  mood: string[];                // e.g. ["warm", "editorial", "caribbean"]
  era: string;                   // e.g. "contemporary", "y2k", "analog"
  density: Density;
  keywords: string[];            // search-ready terms per source
  anti: string[];                // anti-patterns to avoid
  constraints: string[];         // e.g. ["mobile-first", "high-contrast"]
}

export interface PaletteSwatch {
  hex: string;
  role: "bg" | "fg" | "accent" | "muted";
}

export interface TypographyTokens {
  headline: { family?: string; weight: string; style: string };
  body: { family?: string; weight: string };
  pairing_vibe: string;
}

export interface LayoutTokens {
  archetype: string;
  density: Density;
  grid?: string;
}

export interface StyleTokens {
  palette: PaletteSwatch[];
  typography: TypographyTokens;
  layout: LayoutTokens;
  components: string[];
  motion_hints: string[];
  mood: string[];
  distinctive_choices: string[];
}

export interface Reference {
  id: string;
  source: SourceName;
  source_url: string;
  image_url: string;
  thumbnail_url: string;
  title?: string;
  tags: string[];
  category?: string;
  style_tokens?: StyleTokens;
  extracted_at?: string;        // ISO date
  cache_expires_at: string;     // ISO date
  hash: string;                 // content hash for dedupe
}

export interface Direction {
  name: string;
  palette: PaletteSwatch[];
  typography: TypographyTokens;
  layout: LayoutTokens;
  components: string[];
  motion: { hints: string[] };
  anti_patterns: string[];
  references: Array<{
    id: string;
    url: string;
    thumb: string;
    source: SourceName;
    why: string;
  }>;
  taste_score: number;          // 0..1 match vs caller's taste profile
}

export interface Brief {
  id: string;
  prompt: string;
  intent: IntentTags;
  directions: Direction[];
  recommended_index: number;
  generated_at: string;
  user_id?: string;             // taste owner, if any
  references_considered: number;
}

// ----- Taste learning -----

export type FeedbackVerdict = "love" | "like" | "meh" | "dislike" | "reject";

export interface ReferenceFeedback {
  kind: "reference";
  reference_id: string;
  verdict: FeedbackVerdict;
  note?: string;
}

export interface DirectionFeedback {
  kind: "direction";
  brief_id: string;
  direction_index: number;
  verdict: FeedbackVerdict;
  note?: string;
}

export type Feedback = ReferenceFeedback | DirectionFeedback;

/**
 * A TasteProfile is a running, weighted summary of what an agent/user likes.
 * Mood/component/palette vectors are simple bag-of-words frequency counts,
 * positive minus penalized; they power re-ranking in brief synthesis.
 */
export interface TasteProfile {
  user_id: string;
  updated_at: string;
  sample_count: number;
  // Weighted frequency counts. Positive = preferred, negative = avoided.
  mood_weights: Record<string, number>;
  component_weights: Record<string, number>;
  palette_role_weights: Record<string, Record<string, number>>; // role -> hex -> weight
  archetype_weights: Record<string, number>;
  distinctive_weights: Record<string, number>;
  liked_references: string[];   // reference ids
  rejected_references: string[];
  notes: string[];
}
