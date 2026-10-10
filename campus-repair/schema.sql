PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
 created_at TEXT NOT NULL DEFAULT (datetime('now','+7 hours'))
);
CREATE TABLE IF NOT EXISTS repairs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id),
 equipment TEXT NOT NULL,
 room TEXT NOT NULL,
 description TEXT NOT NULL,
 contact TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','working','done','unrepairable')),
 created_at TEXT NOT NULL DEFAULT (datetime('now','+7 hours')),
 updated_at TEXT NOT NULL DEFAULT (datetime('now','+7 hours'))
);
CREATE TABLE IF NOT EXISTS repair_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 repair_id INTEGER NOT NULL REFERENCES repairs(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('pending','working','done','unrepairable')),
 note TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now','+7 hours'))
);
CREATE INDEX IF NOT EXISTS idx_repairs_user ON repairs(user_id);
CREATE INDEX IF NOT EXISTS idx_repairs_status ON repairs(status);
CREATE INDEX IF NOT EXISTS idx_history_repair ON repair_history(repair_id);
