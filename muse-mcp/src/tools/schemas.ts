import { z } from "zod";

// Tool input schemas. Zod is used both to validate inputs at runtime and to
// surface JSON Schema to MCP clients.
export const GenerateBriefInput = z.object({
  prompt: z.string().min(3, "prompt must be at least 3 characters"),
  scope: z
    .enum(["landing_page", "app_ui", "component", "full_site"])
    .optional(),
  hints: z
    .object({
      mood: z.string().optional(),
      audience: z.string().optional(),
      constraints: z.array(z.string()).optional(),
      anti: z.array(z.string()).optional(),
      scope: z
        .enum(["landing_page", "app_ui", "component", "full_site"])
        .optional(),
    })
    .optional(),
  num_references: z.number().int().min(4).max(120).optional(),
  directions: z.number().int().min(1).max(5).optional(),
  user_id: z.string().optional(),
});

export const FetchInspirationInput = z.object({
  prompt: z.string().min(3),
  scope: z
    .enum(["landing_page", "app_ui", "component", "full_site"])
    .optional(),
  limit: z.number().int().min(1).max(120).optional(),
  sources: z
    .array(
      z.enum([
        "landbook",
        "godly",
        "dribbble",
        "mobbin",
        "behance",
        "awwwards",
      ]),
    )
    .optional(),
});

export const GetBriefInput = z.object({
  brief_id: z.string().min(1),
});

export const ExtractStyleInput = z.object({
  image_urls: z.array(z.string().url()).min(1).max(10),
});

export const RecordFeedbackInput = z.object({
  user_id: z.string().min(1),
  feedback: z.discriminatedUnion("kind", [
    z.object({
      kind: z.literal("reference"),
      reference_id: z.string().min(1),
      verdict: z.enum(["love", "like", "meh", "dislike", "reject"]),
      note: z.string().optional(),
    }),
    z.object({
      kind: z.literal("direction"),
      brief_id: z.string().min(1),
      direction_index: z.number().int().min(0),
      verdict: z.enum(["love", "like", "meh", "dislike", "reject"]),
      note: z.string().optional(),
    }),
  ]),
});

export const GetTasteInput = z.object({
  user_id: z.string().min(1),
  top_n: z.number().int().min(1).max(50).optional(),
});
