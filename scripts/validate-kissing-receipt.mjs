// Validate the exact prepared bodies with the same library used by the Worker.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Validator } from '@cfworker/json-schema';
const dir = process.argv[2];
const schemas = JSON.parse(readFileSync(join(dir, 'live-schemas.json'), 'utf8'));
const bodies = JSON.parse(readFileSync(join(dir, 'validation-input.json'), 'utf8'));
for (const [name, payload] of [['RunDeclaration', bodies.run], ['ArtifactCreate', bodies.artifact], ['ReceiptCreate', bodies.receipt]]) {
  if (!schemas[name]) throw new Error(`Unknown schema ${name}`);
  const result = new Validator({ $ref: `#/components/schemas/${name}`, components: { schemas } }, '2020-12', false).validate(payload);
  if (!result.valid) { process.stdout.write(JSON.stringify({ name, errors: result.errors })); process.exit(1); }
}
process.stdout.write('Run, checker artifact and receipt bodies validate against the live schemas.\n');
