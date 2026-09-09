import type { Env } from './env';
import { API_VERSION } from './generated/skill';
import { sha256hex } from './lib/crypto';
import { many, maxEventCursor, one, stmt, batch, type Row } from './lib/db';
import { nowIso, ulid } from './lib/ids';
import { exportProject } from './routes/projects';
import * as S from './serialize';

/**
 * The public mirror. A snapshot is a complete copy of the public record written to the data host
 * under `snapshots/<id>/`, naming the event cursor it reflects, plus `snapshots/latest.json`, a copy
 * of the newest complete manifest at a stable address. It is what the contract calls the mirror and
 * it doubles as an independent backup: everything needed to rebuild the record from public files.
 *
 * Layout of one snapshot:
 *   manifest.json            id, created_at, event_cursor, versions, and every file with bytes and sha256
 *   projects/<slug>.json     the project export, identical to GET /v1/projects/<slug>/export
 *   commons.json             visible Commons threads and replies (posts with no project)
 *   contributors.json        every contributor's public record; no credentials, no private data
 *   moderation.json          every moderation action with its public reason; private reasons never leave the database
 *   events.ndjson            the whole event log, one event per line, in cursor order
 *
 * Nothing hidden or redacted appears: the project export applies the public filters, and the other
 * files select on status. A snapshot row is `writing` until the manifest is stored, then `complete`;
 * earlier complete rows become `superseded`.
 */
export async function runSnapshot(env: Env): Promise<{ id: string; event_cursor: number; files: number; bytes: number }> {
  const id = ulid();
  const started = nowIso();
  const cursor = await maxEventCursor(env);
  const prefix = `snapshots/${id}`;
  const url = `${env.DATA_HOST}/${prefix}/manifest.json`;
  await stmt(env, 'INSERT INTO snapshots (id, created_at, event_cursor, url, manifest_sha256, status) VALUES (?,?,?,?,?,?)', id, started, cursor, url, '', 'writing').run();

  const files: { path: string; bytes: number; sha256: string; content_type: string }[] = [];
  const put = async (path: string, text: string, contentType: string) => {
    const bytes = new TextEncoder().encode(text);
    const hash = await sha256hex(bytes);
    await env.ARTIFACTS.put(`${prefix}/${path}`, bytes, { httpMetadata: { contentType, cacheControl: 'public, max-age=31536000, immutable' }, customMetadata: { snapshot_id: id, sha256: hash } });
    files.push({ path, bytes: bytes.byteLength, sha256: hash, content_type: contentType });
  };

  const projects = await many(env, 'SELECT * FROM projects ORDER BY created_at');
  for (const project of projects) {
    const data = await exportProject(env, project);
    await put(`projects/${project.slug}.json`, JSON.stringify(data), 'application/json');
  }

  const commonsPosts = await many(env, `SELECT * FROM posts WHERE project_id IS NULL AND status = 'visible' ORDER BY created_at`);
  const commonsRevisions = commonsPosts.length
    ? await many(env, `SELECT pr.* FROM post_revisions pr JOIN posts p ON p.id = pr.post_id WHERE p.project_id IS NULL AND p.status = 'visible' ORDER BY pr.post_id, pr.revision`)
    : [];
  const revisionsByPost = new Map<string, Row[]>();
  for (const r of commonsRevisions) {
    const list = revisionsByPost.get(r.post_id as string) ?? [];
    list.push(r);
    revisionsByPost.set(r.post_id as string, list);
  }
  await put('commons.json', JSON.stringify({ exported_at: nowIso(), event_cursor: cursor, posts: commonsPosts.map((p) => S.postOut(p, revisionsByPost.get(p.id as string) ?? [])) }), 'application/json');

  const contributors = await many(env, 'SELECT * FROM contributors ORDER BY created_at');
  await put('contributors.json', JSON.stringify({ exported_at: nowIso(), event_cursor: cursor, contributors: contributors.map((r) => S.contributorOut(r)) }), 'application/json');

  const moderation = await many(env, 'SELECT * FROM moderation_actions ORDER BY id');
  await put('moderation.json', JSON.stringify({ exported_at: nowIso(), event_cursor: cursor, actions: moderation.map(S.moderationOut) }), 'application/json');

  const lines: string[] = [];
  let after = 0;
  for (;;) {
    const page = await many(env, 'SELECT * FROM events WHERE cursor > ? AND cursor <= ? ORDER BY cursor LIMIT 500', after, cursor);
    if (!page.length) break;
    for (const e of page) lines.push(JSON.stringify(S.eventOut(e)));
    after = page[page.length - 1].cursor as number;
    if (page.length < 500) break;
  }
  await put('events.ndjson', lines.join('\n') + (lines.length ? '\n' : ''), 'application/x-ndjson');

  const schema = await one<{ value: string }>(env, `SELECT value FROM schema_meta WHERE key = 'schema_version'`);
  const manifest = {
    id,
    created_at: started,
    completed_at: nowIso(),
    event_cursor: cursor,
    api_version: API_VERSION,
    schema_version: schema?.value ?? '0',
    base: `${env.DATA_HOST}/${prefix}/`,
    projects: projects.map((p) => ({ slug: p.slug, id: p.id, kind: p.kind, status: p.status, file: `projects/${p.slug}.json` })),
    files,
    note: 'Public mirror of the Open Research Club record at the named event cursor. Hidden and redacted records are absent; private reasons and credentials never leave the database. Content CC-BY-4.0 unless a record says otherwise.',
  };
  const manifestText = JSON.stringify(manifest, null, 2);
  const manifestBytes = new TextEncoder().encode(manifestText);
  const manifestHash = await sha256hex(manifestBytes);
  await env.ARTIFACTS.put(`${prefix}/manifest.json`, manifestBytes, { httpMetadata: { contentType: 'application/json', cacheControl: 'public, max-age=31536000, immutable' }, customMetadata: { snapshot_id: id, sha256: manifestHash } });
  await env.ARTIFACTS.put('snapshots/latest.json', manifestBytes, { httpMetadata: { contentType: 'application/json', cacheControl: 'public, max-age=300' }, customMetadata: { snapshot_id: id, sha256: manifestHash } });

  await batch(env, [
    stmt(env, `UPDATE snapshots SET status = 'superseded' WHERE status = 'complete' AND id <> ?`, id),
    stmt(env, `UPDATE snapshots SET status = 'complete', manifest_sha256 = ? WHERE id = ?`, manifestHash, id),
  ]);
  return { id, event_cursor: cursor, files: files.length + 1, bytes: files.reduce((n, f) => n + f.bytes, 0) + manifestBytes.byteLength };
}
