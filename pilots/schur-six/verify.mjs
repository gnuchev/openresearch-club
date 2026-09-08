// Exact second implementation: bitset intersections, not the Python pair loop.
// Node.js standard library only. Does not execute artifact content.
import fs from 'node:fs';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

export const MAX_BYTES = 1024 * 1024;
export const MAX_N = 10000;

export function parseArtifact(bytes) {
  if (bytes.length > MAX_BYTES) throw new Error('Artifact exceeds 1 MiB');
  const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  const value = JSON.parse(text);
  // JSON.parse otherwise keeps the last duplicate. Scan complete string tokens
  // at root depth so equivalent escaped keys are rejected too.
  let depth = 0;
  const keys = new Set();
  for (let i = 0; i < text.length;) {
    const ch = text[i];
    if (ch === '"') {
      const start = i++;
      while (i < text.length) {
        if (text[i] === '\\') { i += 2; continue; }
        if (text[i++] === '"') break;
      }
      if (depth === 1 && /^\s*:/.test(text.slice(i))) {
        const key = JSON.parse(text.slice(start, i));
        if (keys.has(key)) throw new Error('Duplicate JSON key: ' + key);
        keys.add(key);
      }
      continue;
    }
    if (ch === '{' || ch === '[') depth++;
    if (ch === '}' || ch === ']') depth--;
    i++;
  }
  return value;
}

export function verify(artifact) {
  if (artifact === null || Array.isArray(artifact) || typeof artifact !== 'object' || Object.keys(artifact).sort().join(',') !== 'colors,format_version,n')
    return { valid: false, error: 'Expected exactly format_version, n, colors' };
  if (!Number.isInteger(artifact.format_version) || artifact.format_version !== 1)
    return { valid: false, error: 'Unsupported format_version' };
  const { n, colors } = artifact;
  if (!Number.isInteger(n) || n < 1 || n > MAX_N)
    return { valid: false, error: 'n must be an integer from 1 to 10000' };
  if (!Array.isArray(colors) || colors.length !== n)
    return { valid: false, error: 'colors must have exactly n entries' };
  if (!colors.every(c => Number.isInteger(c) && c >= 0 && c <= 5))
    return { valid: false, error: 'Each color must be an integer from 0 to 5; booleans are invalid' };
  const masks = Array(6).fill(0n);
  const sizes = Array(6).fill(0);
  for (let i = 0; i < n; i++) {
    masks[colors[i]] |= 1n << BigInt(i + 1);
    sizes[colors[i]]++;
  }
  let shifts = 0;
  for (let x = 1; x <= n; x++) {
    const color = colors[x - 1];
    let overlap = (masks[color] << BigInt(x)) & masks[color];
    shifts++;
    if (overlap !== 0n) {
      let z = 0;
      while ((overlap & 1n) === 0n) { overlap >>= 1n; z++; }
      return { valid: false, error: 'Monochromatic sum', counterexample: [x, z - x, z], color, shifts_checked: shifts };
    }
  }
  return { valid: true, n, colors_allowed: 6, class_sizes: sizes, shifts_checked: shifts, claim: `S(6) >= ${n}` };
}

export function verifyBytes(bytes) {
  if (bytes.length > MAX_BYTES) return { valid: false, error: 'Artifact exceeds 1 MiB' };
  let result;
  try { result = verify(parseArtifact(bytes)); }
  catch (error) { result = { valid: false, error: String(error.message ?? error) }; }
  return { ...result, artifact_sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.length !== 3) { console.error('Usage: node verify.mjs artifact.json'); process.exitCode = 2; }
  else {
    let fd;
    try {
      fd = fs.openSync(process.argv[2], 'r');
      const bytes = Buffer.alloc(MAX_BYTES + 1);
      let used = 0;
      for (;;) {
        const got = fs.readSync(fd, bytes, used, bytes.length - used, null);
        used += got;
        if (!got || used === bytes.length) break;
      }
      const result = verifyBytes(bytes.subarray(0, used));
      console.log(JSON.stringify(result));
      process.exitCode = result.valid ? 0 : 1;
    } catch (error) { console.log(JSON.stringify({ valid: false, error: error.message })); process.exitCode = 2; }
    finally { if (fd !== undefined) fs.closeSync(fd); }
  }
}
