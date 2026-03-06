import { NextRequest } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET(req: NextRequest) {
  try {
    const category = req.nextUrl.searchParams.get('category');
    const day = req.nextUrl.searchParams.get('day') || new Date().toISOString().slice(0, 10);

    const where: Record<string, string> = { dayKey: day };
    if (category) {
      where.category = category;
    }

    const articles = await prisma.discoverArticle.findMany({
      where,
      orderBy: { generatedAt: 'desc' },
    });

    return Response.json(articles);
  } catch (err) {
    console.error('[API/discover] Read error:', err);
    return Response.json({ error: 'Failed to read discover articles' }, { status: 500 });
  }
}
