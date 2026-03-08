-- D1 schema for elixpo-search
-- Matches the previous Prisma/PostgreSQL schema, adapted for SQLite/D1

CREATE TABLE IF NOT EXISTS Session (
  id         TEXT PRIMARY KEY,
  clientId   TEXT NOT NULL,
  title      TEXT,
  createdAt  TEXT NOT NULL DEFAULT (datetime('now')),
  updatedAt  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_clientId ON Session(clientId);

CREATE TABLE IF NOT EXISTS Message (
  id         TEXT PRIMARY KEY,
  sessionId  TEXT NOT NULL,
  role       TEXT NOT NULL,
  content    TEXT NOT NULL,
  sources    TEXT,  -- JSON string
  images     TEXT,  -- JSON string
  createdAt  TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (sessionId) REFERENCES Session(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_message_sessionId ON Message(sessionId);

CREATE TABLE IF NOT EXISTS Bookmark (
  id         TEXT PRIMARY KEY,
  sessionId  TEXT NOT NULL,
  clientId   TEXT NOT NULL,
  createdAt  TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (sessionId) REFERENCES Session(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bookmark_clientId ON Bookmark(clientId);

CREATE TABLE IF NOT EXISTS DiscoverArticle (
  id          TEXT PRIMARY KEY,
  category    TEXT NOT NULL,
  title       TEXT NOT NULL,
  excerpt     TEXT NOT NULL,
  sourceUrl   TEXT,
  sourceTitle TEXT,
  imageUrl    TEXT,
  generatedAt TEXT NOT NULL DEFAULT (datetime('now')),
  dayKey      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discover_category_day ON DiscoverArticle(category, dayKey);
CREATE INDEX IF NOT EXISTS idx_discover_day ON DiscoverArticle(dayKey);
