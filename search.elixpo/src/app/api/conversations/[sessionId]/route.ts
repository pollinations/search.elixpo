import { NextRequest } from 'next/server';
import { prisma } from '@/lib/prisma';
import { validateXID } from '@/lib/api';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { sessionId } = await params;

    const session = await prisma.session.findUnique({
      where: { id: sessionId },
      include: {
        messages: {
          orderBy: { createdAt: 'asc' },
        },
      },
    });

    if (!session) {
      return Response.json({ messages: [] });
    }

    const messages = session.messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      sources: m.sources || undefined,
      images: m.images || undefined,
    }));

    return Response.json({ messages, title: session.title });
  } catch (err) {
    console.error('[API/conversations] Load error:', err);
    return Response.json({ error: 'Failed to load conversation' }, { status: 500 });
  }
}
