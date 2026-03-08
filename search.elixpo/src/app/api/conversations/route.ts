import { NextRequest } from 'next/server';
import { validateXID } from '@/lib/api';
import { upsertSession, createMessage, listSessions } from '@/lib/db';
import { getAuthUser } from '@/lib/auth';

export const runtime = 'edge';

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json();
    const { sessionId, query, content, sources, images, incognito } = body;

    if (!sessionId || !content) {
      return Response.json({ error: 'Missing required fields' }, { status: 400 });
    }

    // Check if user is authenticated
    const user = await getAuthUser(req);

    // Upsert session with guest/incognito metadata
    const session = await upsertSession(
      sessionId,
      body.clientId || 'anonymous',
      query?.slice(0, 100) || null,
      { userId: user?.id, incognito: !!incognito }
    );

    // In incognito mode, save only session metadata — skip message content
    if (incognito) {
      return Response.json({ id: null, sessionId: session.id, incognito: true });
    }

    // Save user message
    if (query) {
      await createMessage(session.id, 'user', query);
    }

    // Save assistant message
    const message = await createMessage(session.id, 'assistant', content, sources, images);

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
    const limit = parseInt(req.nextUrl.searchParams.get('limit') || '30');

    // If user is logged in, list their sessions; otherwise list by clientId
    const user = await getAuthUser(req);
    const sessions = await listSessions(clientId, limit, user?.id);
    return Response.json(sessions);
  } catch (err) {
    console.error('[API/conversations] List error:', err);
    return Response.json({ error: 'Failed to list conversations' }, { status: 500 });
  }
}
