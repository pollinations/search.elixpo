import { NextRequest } from 'next/server';
import { backendUrl, backendHeaders, validateXID } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json();
    const backendRes = await fetch(backendUrl('/api/session/create'), {
      method: 'POST',
      headers: backendHeaders(),
      body: JSON.stringify(body),
    });
    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch (err) {
    console.error('[API/session] Proxy error:', err);
    return Response.json({ error: 'Internal proxy error' }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const sessionId = req.nextUrl.searchParams.get('id');
    if (!sessionId) {
      return Response.json({ error: 'Missing session id' }, { status: 400 });
    }
    const backendRes = await fetch(backendUrl(`/api/session/${sessionId}`), {
      headers: backendHeaders(),
    });
    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch (err) {
    console.error('[API/session] Proxy error:', err);
    return Response.json({ error: 'Internal proxy error' }, { status: 500 });
  }
}
