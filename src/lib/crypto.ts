export async function sha256hex(input: string | ArrayBuffer | Uint8Array): Promise<string> {
  const data = typeof input === 'string' ? new TextEncoder().encode(input) : input;
  const hash = await crypto.subtle.digest('SHA-256', data as BufferSource);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64.replace(/-/g, '+').replace(/_/g, '/'));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Verify an Ed25519 signature (base64) over a UTF-8 message with a base64 raw public key. */
export async function verifyEd25519(publicKeyB64: string, signatureB64: string, message: string): Promise<boolean> {
  try {
    const key = await crypto.subtle.importKey('raw', base64ToBytes(publicKeyB64), { name: 'Ed25519' }, false, ['verify']);
    return await crypto.subtle.verify('Ed25519', key, base64ToBytes(signatureB64), new TextEncoder().encode(message));
  } catch {
    return false;
  }
}
