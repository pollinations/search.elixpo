import { NextRequest } from 'next/server';
import { exchangeCodeForTokens, fetchUserFromSSO, setAuthCookies } from '@/lib/auth';
import { upsertUser } from '@/lib/db';

export const runtime = 'edge';

/**
 * GET /api/auth/callback
 * OAuth callback — exchanges code for tokens, syncs user to D1, sets cookies.
 */
export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code');
  const state = req.nextUrl.searchParams.get('state');
  const error = req.nextUrl.searchParams.get('error');

  // Handle denial
  if (error) {
    const desc = req.nextUrl.searchParams.get('error_description') || 'Access denied';
    return Response.redirect(new URL(`/?auth_error=${encodeURIComponent(desc)}`, req.url));
  }

  if (!code || !state) {
    return Response.redirect(new URL('/?auth_error=missing_code', req.url));
  }

  // Validate CSRF state
  const stateCookie = req.cookies.get('elixpo_oauth_state')?.value || '';
  const [expectedState, returnToEncoded] = stateCookie.split(':');
  const returnTo = returnToEncoded ? decodeURIComponent(returnToEncoded) : '/';

  if (state !== expectedState) {
    return Response.redirect(new URL('/?auth_error=state_mismatch', req.url));
  }

  try {
    // 1. Exchange code for tokens
    const tokens = await exchangeCodeForTokens(code, req);

    // 2. Fetch user profile from SSO
    const ssoUser = await fetchUserFromSSO(tokens.access_token);

    // 3. Upsert user in local D1 (sync profile from SSO)
    await upsertUser({
      id: ssoUser.id,
      email: ssoUser.email,
      displayName: ssoUser.displayName,
      avatar: ssoUser.avatar,
      provider: ssoUser.provider,
      emailVerified: ssoUser.emailVerified,
    });

    // 4. Set auth cookies and redirect
    const headers = new Headers({ Location: returnTo });
    setAuthCookies(headers, tokens);

    // Clear the state cookie
    headers.append(
      'Set-Cookie',
      'elixpo_oauth_state=; Max-Age=0; HttpOnly; Secure; SameSite=Lax; Path=/'
    );

    return new Response(null, { status: 302, headers });
  } catch (err) {
    console.error('[Auth/callback] Error:', err);
    return Response.redirect(
      new URL(`/?auth_error=${encodeURIComponent((err as Error).message)}`, req.url)
    );
  }
}
