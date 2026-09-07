import { Validator } from '@cfworker/json-schema';
import schemas from '../generated/schemas.json';
import { badRequest, type FieldError } from './errors';

// The OpenAPI component schemas are the single source of truth. Each named schema is validated
// through a root document that carries all components so `#/components/schemas/...` references
// resolve exactly as they do for the reviewers' probes.
const cache = new Map<string, Validator>();

function validatorFor(name: string): Validator {
  let v = cache.get(name);
  if (!v) {
    if (!(name in (schemas as Record<string, unknown>))) throw new Error(`unknown schema ${name}`);
    const root = { $ref: `#/components/schemas/${name}`, components: { schemas } } as unknown as Parameters<typeof Validator.prototype.validate>[0];
    v = new Validator(root as any, '2020-12', false);
    cache.set(name, v);
  }
  return v;
}

export function validationErrors(name: string, payload: unknown): FieldError[] {
  const result = validatorFor(name).validate(payload);
  if (result.valid) return [];
  const seen = new Set<string>();
  const out: FieldError[] = [];
  for (const e of result.errors) {
    const field = e.instanceLocation.replace(/^#\/?/, '').replace(/\//g, '.') || undefined;
    const key = `${field}|${e.error}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ field, message: e.error });
  }
  return out.slice(0, 25);
}

export function assertValid<T>(name: string, payload: unknown): T {
  const errors = validationErrors(name, payload);
  if (errors.length) throw badRequest(`Body does not match ${name}`, errors);
  return payload as T;
}
