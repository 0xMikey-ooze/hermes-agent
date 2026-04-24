import { z } from "zod";

// Minimal zod → JSON Schema converter. Supports the primitives Muse tools
// actually use: objects, strings, numbers, booleans, arrays, enums, unions,
// optional, and discriminated unions. Good enough to advertise via MCP
// list_tools without pulling the 80kb zod-to-json-schema dep.
export function zodToJsonSchema(schema: z.ZodTypeAny): Record<string, unknown> {
  const json = convert(schema);
  return {
    $schema: "http://json-schema.org/draft-07/schema#",
    ...json,
  };
}

function convert(schema: z.ZodTypeAny): Record<string, unknown> {
  // Unwrap optional/nullable/default layers — JSON schema handles them at the
  // parent (via required[]) rather than via the node itself.
  if (schema instanceof z.ZodOptional) return convert(schema._def.innerType);
  if (schema instanceof z.ZodNullable) {
    const inner = convert(schema._def.innerType);
    return { oneOf: [inner, { type: "null" }] };
  }
  if (schema instanceof z.ZodDefault) return convert(schema._def.innerType);
  if (schema instanceof z.ZodEffects) return convert(schema._def.schema);

  if (schema instanceof z.ZodString) {
    const out: Record<string, unknown> = { type: "string" };
    for (const check of schema._def.checks ?? []) {
      if (check.kind === "min") out.minLength = check.value;
      if (check.kind === "max") out.maxLength = check.value;
      if (check.kind === "url") out.format = "uri";
    }
    return out;
  }
  if (schema instanceof z.ZodNumber) {
    const out: Record<string, unknown> = { type: "number" };
    for (const check of schema._def.checks ?? []) {
      if (check.kind === "int") out.type = "integer";
      if (check.kind === "min") out.minimum = check.value;
      if (check.kind === "max") out.maximum = check.value;
    }
    return out;
  }
  if (schema instanceof z.ZodBoolean) return { type: "boolean" };
  if (schema instanceof z.ZodLiteral) {
    return { const: schema._def.value };
  }
  if (schema instanceof z.ZodEnum) {
    return { type: "string", enum: [...schema._def.values] };
  }
  if (schema instanceof z.ZodArray) {
    return {
      type: "array",
      items: convert(schema._def.type),
      ...(schema._def.minLength ? { minItems: schema._def.minLength.value } : {}),
      ...(schema._def.maxLength ? { maxItems: schema._def.maxLength.value } : {}),
    };
  }
  if (schema instanceof z.ZodObject) {
    const shape = schema._def.shape() as Record<string, z.ZodTypeAny>;
    const properties: Record<string, unknown> = {};
    const required: string[] = [];
    for (const [key, value] of Object.entries(shape)) {
      properties[key] = convert(value);
      if (!(value instanceof z.ZodOptional) && !(value instanceof z.ZodDefault)) {
        required.push(key);
      }
    }
    return {
      type: "object",
      properties,
      ...(required.length ? { required } : {}),
      additionalProperties: false,
    };
  }
  if (schema instanceof z.ZodUnion) {
    return { oneOf: schema._def.options.map(convert) };
  }
  if (schema instanceof z.ZodDiscriminatedUnion) {
    return {
      oneOf: Array.from(schema._def.options.values()).map((opt) => convert(opt as z.ZodTypeAny)),
    };
  }
  if (schema instanceof z.ZodRecord) {
    return {
      type: "object",
      additionalProperties: convert(schema._def.valueType),
    };
  }
  if (schema instanceof z.ZodAny || schema instanceof z.ZodUnknown) {
    return {};
  }
  // Fallback: leave empty so MCP can still advertise the tool.
  return {};
}
