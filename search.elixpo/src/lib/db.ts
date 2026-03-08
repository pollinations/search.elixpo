import { getRequestContext } from '@cloudflare/next-on-pages';

function cuid(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `c${ts}${rand}`;
}

function getBindings() {
  const ctx = getRequestContext();
  return {
    DB: ctx.env.DB as D1Database,
    KV: ctx.env.KV as KVNamespace,
  };
}

// ── Session ──────────────────────────────────────────────────────────────────

export async function upsertSession(
  id: string,
  clientId: string,
  title?: string | null,
  opts?: { userId?: string; incognito?: boolean }
) {
  const { DB } = getBindings();
  const now = new Date().toISOString();
  const isGuest = opts?.userId ? 0 : 1;
  const incognito = opts?.incognito ? 1 : 0;

  // Guest sessions expire in 24 hours
  const expiresAt = isGuest
    ? new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
    : null;

  const existing = await DB.prepare('SELECT id FROM Session WHERE id = ?').bind(id).first();

  if (existing) {
    const parts = ['updatedAt = ?'];
    const vals: (string | number | null)[] = [now];
    if (title !== undefined) {
      parts.push('title = ?');
      vals.push(title ?? null);
    }
    if (opts?.userId) {
      parts.push('userId = ?', 'isGuest = 0', 'expiresAt = NULL');
      vals.push(opts.userId);
    }
    vals.push(id);
    await DB.prepare(`UPDATE Session SET ${parts.join(', ')} WHERE id = ?`).bind(...vals).run();
  } else {
    await DB.prepare(
      `INSERT INTO Session (id, clientId, title, isGuest, expiresAt, incognito, createdAt, updatedAt)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(id, clientId, title ?? null, isGuest, expiresAt, incognito, now, now).run();
  }

  return { id, clientId, title };
}

export async function getSessionWithMessages(sessionId: string) {
  const { DB, KV } = getBindings();

  // Try KV cache first
  const cached = await KV.get(`session:${sessionId}`, 'json');
  if (cached) return cached as { title: string | null; messages: Array<Record<string, unknown>> };

  const session = await DB.prepare('SELECT id, title, isGuest, expiresAt FROM Session WHERE id = ?')
    .bind(sessionId).first<{ id: string; title: string | null; isGuest: number; expiresAt: string | null }>();

  if (!session) return null;

  // Check if guest session has expired
  if (session.isGuest === 1 && session.expiresAt && session.expiresAt < new Date().toISOString()) {
    return { title: session.title, messages: [], expired: true };
  }

  const { results: messages } = await DB.prepare(
    'SELECT id, role, content, sources, images FROM Message WHERE sessionId = ? ORDER BY createdAt ASC'
  ).bind(sessionId).all();

  const data = {
    title: session.title,
    messages: messages.map((m: Record<string, unknown>) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      sources: m.sources ? JSON.parse(m.sources as string) : undefined,
      images: m.images ? JSON.parse(m.images as string) : undefined,
    })),
  };

  // Cache in KV for 10 minutes (sessions are mostly read)
  await KV.put(`session:${sessionId}`, JSON.stringify(data), { expirationTtl: 600 });

  return data;
}

export async function listSessions(clientId: string, limit: number = 30, userId?: string | null) {
  const { DB, KV } = getBindings();

  // Try KV cache first
  const cacheKey = userId ? `recents:u:${userId}` : `recents:c:${clientId}`;
  const cached = await KV.get(cacheKey, 'json');
  if (cached) return cached as Array<Record<string, unknown>>;

  // For logged-in users fetch by userId; for guests fetch by clientId
  const sql = userId
    ? `SELECT s.id, s.title, s.createdAt, s.updatedAt, s.isGuest, s.expiresAt,
              (SELECT COUNT(*) FROM Message m WHERE m.sessionId = s.id) as messageCount
       FROM Session s WHERE s.userId = ? ORDER BY s.updatedAt DESC LIMIT ?`
    : `SELECT s.id, s.title, s.createdAt, s.updatedAt, s.isGuest, s.expiresAt,
              (SELECT COUNT(*) FROM Message m WHERE m.sessionId = s.id) as messageCount
       FROM Session s WHERE s.clientId = ? ORDER BY s.updatedAt DESC LIMIT ?`;

  const { results } = await DB.prepare(sql).bind(userId || clientId, limit).all();

  const now = new Date().toISOString();
  const enriched = results.map((s: Record<string, unknown>) => ({
    ...s,
    expired: s.isGuest === 1 && s.expiresAt != null && (s.expiresAt as string) < now,
  }));

  // Cache for 2 minutes
  await KV.put(cacheKey, JSON.stringify(enriched), { expirationTtl: 120 });

  return enriched;
}

// ── Message ──────────────────────────────────────────────────────────────────

export async function createMessage(
  sessionId: string,
  role: string,
  content: string,
  sources?: unknown,
  images?: unknown
) {
  const { DB, KV } = getBindings();
  const id = cuid();
  const now = new Date().toISOString();

  await DB.prepare(
    'INSERT INTO Message (id, sessionId, role, content, sources, images, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).bind(
    id, sessionId, role, content,
    sources ? JSON.stringify(sources) : null,
    images ? JSON.stringify(images) : null,
    now
  ).run();

  // Invalidate KV caches (session messages + sidebar recents)
  await KV.delete(`session:${sessionId}`);

  return { id, sessionId, role, content };
}

// ── Bookmark ─────────────────────────────────────────────────────────────────

export async function createBookmark(sessionId: string, clientId: string) {
  const { DB } = getBindings();
  const id = cuid();
  const now = new Date().toISOString();

  await DB.prepare(
    'INSERT INTO Bookmark (id, sessionId, clientId, createdAt) VALUES (?, ?, ?, ?)'
  ).bind(id, sessionId, clientId, now).run();

  return { id };
}

// ── Discover ─────────────────────────────────────────────────────────────────

export async function getDiscoverArticles(category?: string, dayKey?: string) {
  const { DB } = getBindings();
  const day = dayKey || new Date().toISOString().slice(0, 10);

  if (category) {
    const { results } = await DB.prepare(
      'SELECT * FROM DiscoverArticle WHERE category = ? AND dayKey = ? ORDER BY generatedAt DESC'
    ).bind(category, day).all();
    return results;
  }

  const { results } = await DB.prepare(
    'SELECT * FROM DiscoverArticle WHERE dayKey = ? ORDER BY generatedAt DESC'
  ).bind(day).all();
  return results;
}

export async function saveDiscoverArticles(
  dayKey: string,
  categories: string[],
  categoryArticles: Record<string, Array<{
    title: string; excerpt: string; sourceUrl?: string; sourceTitle?: string;
  }>>
) {
  const { DB } = getBindings();

  // Delete existing for these categories on this day
  for (const cat of categories) {
    await DB.prepare('DELETE FROM DiscoverArticle WHERE category = ? AND dayKey = ?')
      .bind(cat, dayKey).run();
  }

  let totalSaved = 0;
  for (const [category, articles] of Object.entries(categoryArticles)) {
    if (!Array.isArray(articles)) continue;
    for (const article of articles) {
      const id = cuid();
      await DB.prepare(
        'INSERT INTO DiscoverArticle (id, category, title, excerpt, sourceUrl, sourceTitle, dayKey) VALUES (?, ?, ?, ?, ?, ?, ?)'
      ).bind(id, category, article.title, article.excerpt, article.sourceUrl || null, article.sourceTitle || null, dayKey).run();
      totalSaved++;
    }
  }

  return totalSaved;
}

export async function cleanupOldArticles(retentionDays: number = 30) {
  const { DB } = getBindings();
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - retentionDays);
  const cutoffDay = cutoff.toISOString().slice(0, 10);

  const result = await DB.prepare('DELETE FROM DiscoverArticle WHERE dayKey < ?')
    .bind(cutoffDay).run();

  return result.meta?.changes || 0;
}

// ── User ─────────────────────────────────────────────────────────────────────

export interface UserRow {
  id: string;
  email: string;
  displayName: string | null;
  avatar: string | null;
  provider: string;
  emailVerified: number;
  bio: string | null;
  location: string | null;
  website: string | null;
  company: string | null;
  jobTitle: string | null;
  theme: string;
  language: string;
  searchRegion: string;
  safeSearch: number;
  deepSearchDefault: number;
  tier: string;
  totalSearches: number;
  totalSessions: number;
  lastLoginAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export async function upsertUser(ssoUser: {
  id: string;
  email: string;
  displayName?: string | null;
  avatar?: string | null;
  provider?: string;
  emailVerified?: boolean;
}): Promise<UserRow> {
  const { DB } = getBindings();
  const now = new Date().toISOString();

  const existing = await DB.prepare('SELECT id FROM User WHERE id = ?')
    .bind(ssoUser.id).first();

  if (existing) {
    // Update fields that may have changed on the SSO side
    await DB.prepare(
      `UPDATE User SET
        email = ?, displayName = ?, avatar = ?, provider = ?,
        emailVerified = ?, lastLoginAt = ?, updatedAt = ?
      WHERE id = ?`
    ).bind(
      ssoUser.email,
      ssoUser.displayName ?? null,
      ssoUser.avatar ?? null,
      ssoUser.provider ?? 'email',
      ssoUser.emailVerified ? 1 : 0,
      now, now,
      ssoUser.id
    ).run();
  } else {
    await DB.prepare(
      `INSERT INTO User (id, email, displayName, avatar, provider, emailVerified, lastLoginAt, createdAt, updatedAt)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      ssoUser.id,
      ssoUser.email,
      ssoUser.displayName ?? null,
      ssoUser.avatar ?? null,
      ssoUser.provider ?? 'email',
      ssoUser.emailVerified ? 1 : 0,
      now, now, now
    ).run();
  }

  return getUserById(ssoUser.id) as Promise<UserRow>;
}

export async function getUserById(userId: string): Promise<UserRow | null> {
  const { DB } = getBindings();
  return DB.prepare('SELECT * FROM User WHERE id = ?')
    .bind(userId).first<UserRow>();
}

export async function getUserByEmail(email: string): Promise<UserRow | null> {
  const { DB } = getBindings();
  return DB.prepare('SELECT * FROM User WHERE email = ?')
    .bind(email).first<UserRow>();
}

export async function updateUserProfile(userId: string, fields: {
  bio?: string | null;
  location?: string | null;
  website?: string | null;
  company?: string | null;
  jobTitle?: string | null;
  theme?: string;
  language?: string;
  searchRegion?: string;
  safeSearch?: number;
  deepSearchDefault?: number;
}): Promise<UserRow | null> {
  const { DB } = getBindings();
  const now = new Date().toISOString();

  const setClauses: string[] = ['updatedAt = ?'];
  const values: (string | number | null)[] = [now];

  const allowed: Record<string, 'string' | 'number'> = {
    bio: 'string', location: 'string', website: 'string',
    company: 'string', jobTitle: 'string', theme: 'string',
    language: 'string', searchRegion: 'string',
    safeSearch: 'number', deepSearchDefault: 'number',
  };

  for (const [key, type] of Object.entries(allowed)) {
    const val = (fields as Record<string, unknown>)[key];
    if (val !== undefined) {
      setClauses.push(`${key} = ?`);
      values.push(val as string | number | null);
    }
  }

  if (values.length <= 1) return getUserById(userId);

  values.push(userId);
  await DB.prepare(`UPDATE User SET ${setClauses.join(', ')} WHERE id = ?`)
    .bind(...values).run();

  return getUserById(userId);
}

export async function incrementUserSearchCount(userId: string) {
  const { DB } = getBindings();
  await DB.prepare('UPDATE User SET totalSearches = totalSearches + 1, updatedAt = ? WHERE id = ?')
    .bind(new Date().toISOString(), userId).run();
}

export async function listUserSessions(userId: string, limit: number = 50) {
  const { DB } = getBindings();
  const { results } = await DB.prepare(
    `SELECT s.id, s.title, s.createdAt, s.updatedAt,
            (SELECT COUNT(*) FROM Message m WHERE m.sessionId = s.id) as messageCount
     FROM Session s WHERE s.userId = ? ORDER BY s.updatedAt DESC LIMIT ?`
  ).bind(userId, limit).all();
  return results;
}

export async function deleteUserAccount(userId: string) {
  const { DB } = getBindings();
  // Cascade: bookmarks deleted, sessions unlinked (SET NULL)
  await DB.prepare('DELETE FROM User WHERE id = ?').bind(userId).run();
}

// ── Guest Cleanup & Session Claiming ────────────────────────────────────────

/**
 * Delete expired guest sessions (24h TTL).
 * Messages cascade-delete via FK constraint.
 */
export async function cleanupExpiredGuestSessions(): Promise<number> {
  const { DB } = getBindings();
  const now = new Date().toISOString();
  const result = await DB.prepare(
    'DELETE FROM Session WHERE isGuest = 1 AND expiresAt IS NOT NULL AND expiresAt < ?'
  ).bind(now).run();
  return result.meta?.changes || 0;
}

/**
 * Claim guest sessions: link a clientId's guest sessions to an authenticated user.
 * Removes the 24h expiry so they persist permanently.
 */
export async function claimGuestSessions(clientId: string, userId: string): Promise<number> {
  const { DB } = getBindings();
  const now = new Date().toISOString();
  const result = await DB.prepare(
    `UPDATE Session SET userId = ?, isGuest = 0, expiresAt = NULL, updatedAt = ?
     WHERE clientId = ? AND isGuest = 1`
  ).bind(userId, now, clientId).run();
  return result.meta?.changes || 0;
}

/**
 * Check if a session is in incognito mode.
 */
export async function isSessionIncognito(sessionId: string): Promise<boolean> {
  const { DB } = getBindings();
  const row = await DB.prepare('SELECT incognito FROM Session WHERE id = ?')
    .bind(sessionId).first<{ incognito: number }>();
  return row?.incognito === 1;
}

// ── Rate Limiting ────────────────────────────────────────────────────────────

export async function checkGuestRateLimit(ip: string, limit: number = 15): Promise<{ allowed: boolean; remaining: number }> {
  const { KV } = getBindings();
  const key = `guest:${ip}`;

  const current = parseInt(await KV.get(key) || '0', 10);

  if (current >= limit) {
    return { allowed: false, remaining: 0 };
  }

  // Increment with 24h TTL
  await KV.put(key, String(current + 1), { expirationTtl: 86400 });

  return { allowed: true, remaining: limit - current - 1 };
}
