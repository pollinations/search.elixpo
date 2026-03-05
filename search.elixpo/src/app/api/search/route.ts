import { NextRequest } from 'next/server';
import { backendUrl, backendHeaders, validateXID } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json();
    const { query, session_id, stream = true, deep_search = false } = body;

    if (!query || !session_id) {
      return Response.json({ error: 'Missing query or session_id' }, { status: 400 });
    }

    const backendRes = await fetch(backendUrl('/api/search'), {
      method: 'POST',
      headers: backendHeaders(),
      body: JSON.stringify({ query, session_id, stream, deep_search }),
    });

    if (!backendRes.ok) {
      const text = await backendRes.text();
      return new Response(text, { status: backendRes.status });
    }

    // For streaming, pass through the SSE stream
    if (stream && backendRes.body) {
      return new Response(backendRes.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
      });
    }

    // Non-streaming: return JSON
    const data = await backendRes.json();
    return Response.json(data);
  } catch (err) {
    console.error('[API/search] Proxy error:', err);
    return Response.json({ error: 'Internal proxy error' }, { status: 500 });
  }
}
