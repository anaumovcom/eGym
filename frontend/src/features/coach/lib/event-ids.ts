/** A ledger and its server-side seen IDs survive page reloads. A producer's
 * counter does not, so namespace it per instance (also safe across HMR).
 * This changes transport identity only, never semantic/topic dedup or billing.
 * getRandomValues works on plain-HTTP kiosks where randomUUID is unavailable. */
export function coachEventIds(producer: 'net' | 'lifecycle'): () => string {
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(12)), byte => byte.toString(16).padStart(2, '0')).join('')
  let sequence = 0
  return () => `${producer}-${nonce}-${++sequence}`
}