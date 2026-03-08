import { getRequestContext } from '@cloudflare/next-on-pages';
import { NextRequest } from 'next/server';

// ── SSO Config ───────────────────────────────────────────────────────────────

const ACCOUNTS_BASE = 'https://accounts.elixpo.com';

function getEnv(key: string): string {
  // process.env takes priority (set via .env locally, or runtime env in production)
  if (process.env[key]) return process.env[key]!;
  try {
    const ctx = getRequestContext();
    return (ctx.env as unknown as Record<string, string>)[key] || '';
  } catch {}
  return '';
}

function getSSO() {
  return {
    clientId: getEnv('SSO_CLIENT_ID'),
    clientSecret: getEnv('SSO_CLIENT_SECRET'),
  };
}

function getRedirectUri(req: NextRequest): string {
  const origin = req.nextUrl.origin;
  return `${origin}/api/auth/callback`;
}

// ── OAuth URL Builder ────────────────────────────────────────────────────────

export function buildAuthorizationUrl(state: string, req: NextRequest): string {
  const { clientId } = getSSO();
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: clientId,
    redirect_uri: getRedirectUri(req),
    state,
    scope: 'openid profile email',
  });
  return `${ACCOUNTS_BASE}/oauth/authorize?${params}`;
}

// ── Token Exchange ───────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  scope: string;
}

export async function exchangeCodeForTokens(code: string, req: NextRequest): Promise<TokenResponse> {
  const { clientId, clientSecret } = getSSO();

  const res = await fetch(`${ACCOUNTS_BASE}/api/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      code,
      client_id: clientId,
      client_secret: clientSecret,
      redirect_uri: getRedirectUri(req),
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'token_exchange_failed' }));
    throw new Error((err as Record<string, string>).error_description || (err as Record<string, string>).error || 'Token exchange failed');
  }

  return res.json() as Promise<TokenResponse>;
}

export async function refreshAccessToken(refreshToken: string): Promise<TokenResponse> {
  const { clientId } = getSSO();

  const res = await fetch(`${ACCOUNTS_BASE}/api/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: clientId,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'refresh_failed' }));
    throw new Error((err as Record<string, string>).error_description || (err as Record<string, string>).error || 'Token refresh failed');
  }

  return res.json() as Promise<TokenResponse>;
}

// ── User Info ────────────────────────────────────────────────────────────────

export interface SSOUser {
  id: string;
  userId: string;
  email: string;
  displayName: string | null;
  isAdmin: boolean;
  provider: string;
  avatar: string | null;
  emailVerified: boolean;
  expiresAt: string;
}

export async function fetchUserFromSSO(accessToken: string): Promise<SSOUser> {
  const res = await fetch(`${ACCOUNTS_BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!res.ok) {
    throw new Error('Failed to fetch user from SSO');
  }

  return res.json() as Promise<SSOUser>;
}

// ── Cookie Helpers ───────────────────────────────────────────────────────────

const COOKIE_OPTIONS = {
  httpOnly: true,
  secure: true,
  sameSite: 'lax' as const,
  path: '/',
};

export function setAuthCookies(headers: Headers, tokens: TokenResponse) {
  // Access token — short-lived (matches SSO expiry, typically 15min)
  headers.append(
    'Set-Cookie',
    `elixpo_access_token=${tokens.access_token}; Max-Age=${tokens.expires_in}; HttpOnly; Secure; SameSite=Lax; Path=/`
  );

  // Refresh token — long-lived (7 days)
  headers.append(
    'Set-Cookie',
    `elixpo_refresh_token=${tokens.refresh_token}; Max-Age=${7 * 86400}; HttpOnly; Secure; SameSite=Lax; Path=/`
  );
}

export function clearAuthCookies(headers: Headers) {
  headers.append(
    'Set-Cookie',
    'elixpo_access_token=; Max-Age=0; HttpOnly; Secure; SameSite=Lax; Path=/'
  );
  headers.append(
    'Set-Cookie',
    'elixpo_refresh_token=; Max-Age=0; HttpOnly; Secure; SameSite=Lax; Path=/'
  );
}

// ── Request Auth Extraction ──────────────────────────────────────────────────

export function getAccessToken(req: NextRequest): string | null {
  return req.cookies.get('elixpo_access_token')?.value || null;
}

export function getRefreshToken(req: NextRequest): string | null {
  return req.cookies.get('elixpo_refresh_token')?.value || null;
}

/**
 * Get the authenticated user from request cookies.
 * Returns null if not authenticated or token expired.
 * Does NOT auto-refresh — caller should redirect to /api/auth/refresh if null.
 */
export async function getAuthUser(req: NextRequest): Promise<SSOUser | null> {
  const token = getAccessToken(req);
  if (!token) return null;

  try {
    return await fetchUserFromSSO(token);
  } catch {
    return null;
  }
}

// ── State Generation (CSRF) ─────────────────────────────────────────────────

export function generateState(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}
