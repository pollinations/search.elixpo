import { NextRequest } from 'next/server';
import { validateXID } from '@/lib/api';
import { cleanupExpiredGuestSessions } from '@/lib/db';

export const runtime = 'edge';

/**
 * POST /api/sessions/cleanup
 * Deletes expired guest sessions (24h TTL).
 * Can be called by a cron job or on app startup.
 */
export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const deleted = await cleanupExpiredGuestSessions();
    return Response.json({ deleted });
  } catch (err) {
    console.error('[API/sessions/cleanup] Error:', err);
    return Response.json({ error: 'Cleanup failed' }, { status: 500 });
  }
}
