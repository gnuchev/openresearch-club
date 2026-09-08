import type { Actor } from './lib/auth';

export interface Env {
  DB: D1Database;
  ARTIFACTS: R2Bucket;
  QUOTA: DurableObjectNamespace;
  PUBLIC_BASE: string;
  DATA_HOST: string;
  ABUSE_CONTACT: string;
  /** Secret: salt for registration source hashes. Set with `wrangler secret put REG_SALT`. */
  REG_SALT?: string;
  /** "true" only in local development: also serve the site under the /site prefix. */
  SITE_PREFIX?: string;
}

export type AppEnv = {
  Bindings: Env;
  Variables: {
    actor?: Actor;
    rawBody?: string;
    rawBytes?: ArrayBuffer;
  };
};

export const LIMITS = {
  artifact_max_bytes: 26214400,
  lease_default_hours: 72,
  lease_max_hours: 336,
  claim_max_chars: 300,
  prediction_max_years: 2,
  registrations_per_source_per_day: 5,
  idempotency_hours: 24,
  json_body_max_bytes: 1048576,
} as const;
