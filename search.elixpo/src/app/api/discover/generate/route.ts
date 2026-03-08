import { NextRequest } from 'next/server';
import { backendUrl, backendHeaders, validateXID } from '@/lib/api';
import { saveDiscoverArticles, cleanupOldArticles } from '@/lib/db';

export const runtime = 'edge';

const RETENTION_DAYS = 30;

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const categories = body.categories || ['tech', 'finance', 'sports', 'entertainment', 'arts'];

    // 1. Call Python backend to generate articles
    const backendRes = await fetch(backendUrl('/api/discover/generate'), {
      method: 'POST',
      headers: backendHeaders(),
      body: JSON.stringify({ categories }),
      cache: 'no-store',
    });

    if (!backendRes.ok) {
      const text = await backendRes.text();
      return new Response(text, { status: backendRes.status });
    }

    const result = await backendRes.json();
    const dayKey = result.dayKey;
    const categoryArticles = result.categories || {};

    // 2. Save to D1
    const totalSaved = await saveDiscoverArticles(dayKey, categories, categoryArticles);

    // 3. Cleanup old articles
    const expiredRemoved = await cleanupOldArticles(RETENTION_DAYS);

    return Response.json({
      status: 'ok',
      dayKey,
      saved: totalSaved,
      expiredRemoved,
    });
  } catch (err) {
    console.error('[API/discover/generate] Error:', err);
    return Response.json({ error: 'Failed to generate discover content' }, { status: 500 });
  }
}
