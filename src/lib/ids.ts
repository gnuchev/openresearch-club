const ENC = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/** ULID: 10 chars of time (ms) + 16 chars of randomness, Crockford base32, time-sortable. */
export function ulid(now: number = Date.now()): string {
  let t = now;
  let time = '';
  for (let i = 0; i < 10; i++) {
    time = ENC[t % 32] + time;
    t = Math.floor(t / 32);
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let rand = '';
  for (let i = 0; i < 16; i++) rand += ENC[bytes[i] % 32];
  return time + rand;
}

export const ULID_RE = /^[0-9A-HJKMNP-TV-Z]{26}$/;

/** ISO-8601 UTC without milliseconds, e.g. 2026-09-07T12:00:00Z */
export function nowIso(d: Date = new Date()): string {
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z');
}
export const today = (): string => nowIso().slice(0, 10);
export const currentHour = (): string => nowIso().slice(0, 13);
export function isoAfterHours(hours: number): string {
  return nowIso(new Date(Date.now() + hours * 3600_000));
}
export function secondsUntilNextUtcDay(): number {
  const d = new Date();
  const next = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1);
  return Math.max(1, Math.ceil((next - d.getTime()) / 1000));
}
