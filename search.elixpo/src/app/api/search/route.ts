import { NextRequest } from 'next/server';
import { backendUrl, backendHeaders, validateXID } from '@/lib/api';
import { checkGuestRateLimit, incrementUserSearchCount } from '@/lib/db';
import { getAuthUser } from '@/lib/auth';

export const runtime = 'edge';

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Check if user is authenticated — skip rate limit for logged-in users
    const user = await getAuthUser(req);
    let remaining = -1; // -1 = unlimited (authenticated)

    if (!user) {
      // Guest rate limiting by IP
      const ip = req.headers.get('cf-connecting-ip') || req.headers.get('x-forwarded-for') || 'unknown';
      const rateCheck = await checkGuestRateLimit(ip);
      if (!rateCheck.allowed) {
        return Response.json(
          { error: 'Guest request limit reached. Sign in for unlimited access.' },
          { status: 429, headers: { 'X-RateLimit-Remaining': '0' } }
        );
      }
      remaining = rateCheck.remaining;
    }

    const body = await req.json();
    const { query, session_id, stream = true, deep_search = false, image, images } = body;

    const hasImages = image || (Array.isArray(images) && images.length > 0);
    if (!session_id || (!query && !hasImages)) {
      return Response.json({ error: 'Missing session_id, and query or image' }, { status: 400 });
    }

    // Track search count for authenticated users (fire-and-forget)
    if (user) {
      incrementUserSearchCount(user.id).catch(() => {});
    }

    const backendPayload: Record<string, unknown> = { query: query || '', session_id, stream, deep_search };
    if (image) backendPayload.image = image;
    if (Array.isArray(images) && images.length > 0) backendPayload.images = images.slice(0, 3);

    const backendRes = await fetch(backendUrl('/api/search'), {
      method: 'POST',
      headers: backendHeaders(),
      body: JSON.stringify(backendPayload),
      cache: 'no-store',
    });

    if (!backendRes.ok) {
      const text = await backendRes.text();
      return new Response(text, { status: backendRes.status });
    }

    const rateLimitHeader = remaining >= 0 ? String(remaining) : 'unlimited';

    // For streaming, pass through the SSE stream
    if (stream && backendRes.body) {
      return new Response(backendRes.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
          'X-RateLimit-Remaining': rateLimitHeader,
        },
      });
    }

    // Non-streaming: return JSON
    const data = await backendRes.json();
    return Response.json(data, {
      headers: { 'X-RateLimit-Remaining': rateLimitHeader },
    });
  } catch (err) {
    console.error('[API/search] Proxy error:', err);
    return Response.json({ error: 'Internal proxy error' }, { status: 500 });
  }
}
