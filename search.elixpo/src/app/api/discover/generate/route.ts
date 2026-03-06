import { NextRequest } from 'next/server';
import { prisma } from '@/lib/prisma';
import { backendUrl, backendHeaders, validateXID } from '@/lib/api';

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
    });

    if (!backendRes.ok) {
      const text = await backendRes.text();
      return new Response(text, { status: backendRes.status });
    }

    const result = await backendRes.json();
    const dayKey = result.dayKey;
    const categoryArticles: Record<string, Array<{
      title: string;
      excerpt: string;
      sourceUrl?: string;
      sourceTitle?: string;
    }>> = result.categories || {};

    // 2. Delete existing articles for today's categories (idempotent regeneration)
    await prisma.discoverArticle.deleteMany({
      where: {
        dayKey,
        category: { in: categories },
      },
    });

    // 3. Persist generated articles
    let totalSaved = 0;
    for (const [category, articles] of Object.entries(categoryArticles)) {
      if (!Array.isArray(articles)) continue;
      for (const article of articles) {
        await prisma.discoverArticle.create({
          data: {
            category,
            title: article.title,
            excerpt: article.excerpt,
            sourceUrl: article.sourceUrl || null,
            sourceTitle: article.sourceTitle || null,
            dayKey,
          },
        });
        totalSaved++;
      }
    }

    // 4. Cleanup articles older than 30 days
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - RETENTION_DAYS);
    const cutoffDayKey = cutoffDate.toISOString().slice(0, 10);

    const deleted = await prisma.discoverArticle.deleteMany({
      where: { dayKey: { lt: cutoffDayKey } },
    });

    return Response.json({
      status: 'ok',
      dayKey,
      saved: totalSaved,
      expiredRemoved: deleted.count,
    });
  } catch (err) {
    console.error('[API/discover/generate] Error:', err);
    return Response.json({ error: 'Failed to generate discover content' }, { status: 500 });
  }
}
