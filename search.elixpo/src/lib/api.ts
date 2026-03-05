const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:9002';
const INTERNAL_KEY = process.env.INTERNAL_API_KEY || '';
const XID = process.env.XID || '';

export function backendHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Internal-Key': INTERNAL_KEY,
  };
}

export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path}`;
}

/**
 * Validate XID from request headers.
 * Returns true if valid, false otherwise.
 */
export function validateXID(requestXID: string | null): boolean {
  if (!XID) return true; // no XID configured = open access
  return requestXID === XID;
}
