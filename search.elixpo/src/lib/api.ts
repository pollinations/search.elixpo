import { getRequestContext } from '@cloudflare/next-on-pages';

function getEnv(key: string): string {
  if (process.env[key]) return process.env[key]!;
  try {
    const ctx = getRequestContext();
    return (ctx.env as unknown as Record<string, string>)[key] || '';
  } catch {}
  return '';
}

export function backendHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const internalKey = getEnv('INTERNAL_API_KEY');
  const apiKey = getEnv('API_KEY');
  if (internalKey) headers['X-Internal-Key'] = internalKey;
  if (apiKey) headers['X-API-Key'] = apiKey;
  return headers;
}

export function backendUrl(path: string): string {
  const url = getEnv('BACKEND_URL') || 'http://localhost:9002';
  return `${url}${path}`;
}

/**
 * Validate XID from request headers.
 * Returns true if valid, false otherwise.
 */
export function validateXID(requestXID: string | null): boolean {
  const xid = getEnv('XID');
  if (!xid) return true; // no XID configured = open access
  return requestXID === xid;
}
