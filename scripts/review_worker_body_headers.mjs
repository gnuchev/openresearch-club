// Isolate the application's missing-upload-length response from Wrangler's HTTP proxy.
// Usage: node scripts/review_worker_body_headers.mjs <bundled-worker.mjs> <output.json>
// DB and quota bindings are mocked; this is not a workerd or authentication acceptance test.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [bundle, output] = process.argv.slice(2);
if (!bundle || !output) throw new Error('Pass the local bundle and output paths.');
const { default: app } = await import(pathToFileURL(path.resolve(bundle)).href);
const actor = { id: 'fixture-actor', handle: 'fixture', tier: 'new', status: 'active', kind: 'agent', credential_id: 'fixture-credential' };
const reads = [];
const env = {
  DB: {
    prepare(sql) {
      return { bind() { return this; }, async first() {
        if (sql.includes('FROM credentials')) { reads.push('authentication-mock'); return actor; }
        if (sql.includes('quota_policies')) { reads.push('quota-policy-mock'); return { tier: 'new', requests_per_hour: 600 }; }
        throw new Error('Unexpected DB query: ' + sql);
      } };
    },
    async batch() { return []; },
  },
  QUOTA: { idFromName() { return 'fixture'; }, get() { return { async fetch() { return Response.json({ ok: true, count: 1 }); } }; } },
};
const request = new Request('http://fixture.invalid/v1/artifacts/fixture/content', {
  method: 'PUT',
  headers: { Authorization: 'Bearer ' + crypto.randomUUID(), 'Idempotency-Key': crypto.randomUUID(), 'Content-Type': 'application/octet-stream' },
  body: new ReadableStream({ start(c) { c.enqueue(new Uint8Array([1])); c.close(); } }),
  duplex: 'half',
});
const response = await app.fetch(request, env, { waitUntil() {} });
const result = { scope: 'Node adapter with mocked DB/quota bindings; not workerd HTTP', content_length_present: request.headers.has('Content-Length'), status: response.status, body: await response.json(), mocked_reads: reads, passed: response.status === 411 };
fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
if (!result.passed) process.exitCode = 1;
