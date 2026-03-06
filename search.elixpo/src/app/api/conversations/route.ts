import { NextRequest } from 'next/server';
import { prisma } from '@/lib/prisma';
import { validateXID } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json();
    const { sessionId, query, content, sources, images } = body;

    if (!sessionId || !content) {
      return Response.json({ error: 'Missing required fields' }, { status: 400 });
    }

    // Upsert session
    const session = await prisma.session.upsert({
      where: { id: sessionId },
      create: {
        id: sessionId,
        clientId: body.clientId || 'anonymous',
        title: query?.slice(0, 100) || null,
      },
      update: {
        updatedAt: new Date(),
        title: query?.slice(0, 100) || undefined,
      },
    });

    // Save user message
    if (query) {
      await prisma.message.create({
        data: {
          sessionId: session.id,
          role: 'user',
          content: query,
        },
      });
    }

    // Save assistant message
    const message = await prisma.message.create({
      data: {
        sessionId: session.id,
        role: 'assistant',
        content,
        sources: sources || undefined,
        images: images || undefined,
      },
    });

    return Response.json({ id: message.id, sessionId: session.id });
  } catch (err) {
    console.error('[API/conversations] Save error:', err);
    return Response.json({ error: 'Failed to save conversation' }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const clientId = req.nextUrl.searchParams.get('clientId') || 'anonymous';
    const limit = parseInt(req.nextUrl.searchParams.get('limit') || '20');

    const sessions = await prisma.session.findMany({
      where: { clientId },
      orderBy: { updatedAt: 'desc' },
      take: limit,
      include: {
        _count: { select: { messages: true } },
      },
    });

    return Response.json(
      sessions.map((s) => ({
        id: s.id,
        title: s.title,
        createdAt: s.createdAt.toISOString(),
        updatedAt: s.updatedAt.toISOString(),
        messageCount: s._count.messages,
      }))
    );
  } catch (err) {
    console.error('[API/conversations] List error:', err);
    return Response.json({ error: 'Failed to list conversations' }, { status: 500 });
  }
}
