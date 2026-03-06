import { NextRequest } from 'next/server';
import { backendUrl, backendHeaders, validateXID } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json();
    const { query, limit = 5, images = false } = body;

    if (!query) {
      return Response.json({ error: 'Missing query' }, { status: 400 });
    }

    const backendRes = await fetch(backendUrl('/api/surf'), {
      method: 'POST',
      headers: backendHeaders(),
      body: JSON.stringify({ query, limit, images }),
    });

    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch (err) {
    console.error('[API/surf] Proxy error:', err);
    return Response.json({ error: 'Internal proxy error' }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const query = req.nextUrl.searchParams.get('query') || '';
    const limit = req.nextUrl.searchParams.get('limit') || '5';
    const images = req.nextUrl.searchParams.get('images') || 'false';

    if (!query) {
      return Response.json({ error: 'Missing query' }, { status: 400 });
    }

    const params = new URLSearchParams({ query, limit, images });
    const backendRes = await fetch(backendUrl(`/api/surf?${params}`), {
      headers: backendHeaders(),
    });

    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch (err) {
    console.error('[API/surf] Proxy error:', err);
    return Response.json({ error: 'Internal proxy error' }, { status: 500 });
  }
}
