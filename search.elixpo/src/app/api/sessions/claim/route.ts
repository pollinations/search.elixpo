import { NextRequest } from 'next/server';
import { validateXID } from '@/lib/api';
import { getAuthUser } from '@/lib/auth';
import { claimGuestSessions } from '@/lib/db';

export const runtime = 'edge';

/**
 * POST /api/sessions/claim
 * Called from frontend after login to adopt guest sessions into the user's account.
 * Body: { clientId: string }
 */
export async function POST(req: NextRequest) {
  try {
    const xid = req.headers.get('x-xid');
    if (!validateXID(xid)) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const user = await getAuthUser(req);
    if (!user) {
      return Response.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const body = await req.json();
    const { clientId } = body;

    if (!clientId) {
      return Response.json({ error: 'Missing clientId' }, { status: 400 });
    }

    const claimed = await claimGuestSessions(clientId, user.id);
    return Response.json({ claimed });
  } catch (err) {
    console.error('[API/sessions/claim] Error:', err);
    return Response.json({ error: 'Failed to claim sessions' }, { status: 500 });
  }
}
