import { NextRequest } from 'next/server';
import { buildAuthorizationUrl, generateState } from '@/lib/auth';

export const runtime = 'edge';

/**
 * GET /api/auth/login
 * Redirects the user to the Elixpo Accounts SSO login page.
 * Stores CSRF state in a short-lived cookie.
 */
export async function GET(req: NextRequest) {
  const state = generateState();
  const returnTo = req.nextUrl.searchParams.get('returnTo') || '/';

  const authUrl = buildAuthorizationUrl(state, req);

  const headers = new Headers({
    Location: authUrl,
  });

  // Store state + returnTo in a short-lived cookie for CSRF validation on callback
  headers.append(
    'Set-Cookie',
    `elixpo_oauth_state=${state}:${encodeURIComponent(returnTo)}; Max-Age=600; HttpOnly; Secure; SameSite=Lax; Path=/`
  );

  return new Response(null, { status: 302, headers });
}
