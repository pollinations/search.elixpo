-- User profiles synced from Elixpo Accounts SSO
-- Stores local profile data + preferences for lixSearch

CREATE TABLE IF NOT EXISTS User (
  id              TEXT PRIMARY KEY,          -- same as Elixpo Accounts user ID
  email           TEXT NOT NULL UNIQUE,
  displayName     TEXT,
  avatar          TEXT,                      -- URL from SSO provider
  provider        TEXT DEFAULT 'email',      -- email, google, github, etc.
  emailVerified   INTEGER DEFAULT 0,         -- boolean

  -- Profile fields (user-editable on lixSearch)
  bio             TEXT,
  location        TEXT,
  website         TEXT,
  company         TEXT,
  jobTitle        TEXT,

  -- Preferences
  theme           TEXT DEFAULT 'system',     -- system, light, dark
  language        TEXT DEFAULT 'en',
  searchRegion    TEXT DEFAULT 'auto',       -- auto, us, eu, in, etc.
  safeSearch      INTEGER DEFAULT 1,         -- 0=off, 1=moderate, 2=strict
  deepSearchDefault INTEGER DEFAULT 0,      -- auto-enable deep search

  -- Usage & limits
  tier            TEXT DEFAULT 'free',       -- free, pro, enterprise
  totalSearches   INTEGER DEFAULT 0,
  totalSessions   INTEGER DEFAULT 0,

  -- Timestamps
  lastLoginAt     TEXT,
  createdAt       TEXT NOT NULL DEFAULT (datetime('now')),
  updatedAt       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_user_email ON User(email);
CREATE INDEX IF NOT EXISTS idx_user_tier ON User(tier);

-- Link sessions to authenticated users (nullable — guests have no userId)
-- Session table already exists from 0001_init; add userId column
ALTER TABLE Session ADD COLUMN userId TEXT REFERENCES User(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_session_userId ON Session(userId);

-- Link bookmarks to authenticated users
ALTER TABLE Bookmark ADD COLUMN userId TEXT REFERENCES User(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_bookmark_userId ON Bookmark(userId);
