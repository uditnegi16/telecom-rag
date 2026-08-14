/**
 * Generate a unique id without requiring a secure context.
 *
 * WHY NOT crypto.randomUUID (ERROR_LOG E-032)
 * -------------------------------------------
 * `crypto.randomUUID` is exposed only in SECURE CONTEXTS - HTTPS, or
 * localhost. On a plain-HTTP deployment (an EC2 box addressed by IP) it is
 * simply absent, and calling it throws:
 *
 *     TypeError: crypto.randomUUID is not a function
 *
 * That threw inside the send handler, so React never applied the state
 * update and the composer stayed locked with no visible error. Development
 * never caught it because localhost IS a secure context.
 *
 * `crypto.getRandomValues` carries no such restriction and is used where
 * available; Math.random is the last resort. These ids need only be unique
 * within one page session - they are React keys, not security tokens - so
 * the weaker fallback is acceptable.
 */
export function uid(): string {
  const g = globalThis.crypto as Crypto | undefined;

  if (g && typeof g.randomUUID === "function") {
    return g.randomUUID();
  }

  if (g && typeof g.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    g.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;   // RFC 4122 version
    bytes[8] = (bytes[8] & 0x3f) | 0x80;   // RFC 4122 variant
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
