// Local persistence (NFR-4): SQLite cache for fixtures/standings/profiles + persistent offline action queue.
import * as SQLite from 'expo-sqlite';

export const db = SQLite.openDatabaseSync('nascon.db');

db.execSync(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY NOT NULL, json TEXT NOT NULL, updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS outbox (
    action_id TEXT PRIMARY KEY NOT NULL, type TEXT NOT NULL, queued_at TEXT NOT NULL,
    base_version INTEGER NOT NULL, payload TEXT NOT NULL, label TEXT NOT NULL, ref TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS sync_log (
    action_id TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL, resolution TEXT NOT NULL,
    error_code TEXT, message TEXT NOT NULL, processed_at TEXT NOT NULL);
`);

export function kvGet(key: string): string | null {
  const row = db.getFirstSync<{ value: string }>('SELECT value FROM kv WHERE key = ?', [key]);
  return row ? row.value : null;
}

export function kvSet(key: string, value: string) {
  db.runSync('INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)', [key, value]);
}

export function kvDel(key: string) {
  db.runSync('DELETE FROM kv WHERE key = ?', [key]);
}

export type Cached<T> = { data: T; updatedAt: string };

export function cacheGet<T>(key: string): Cached<T> | null {
  const row = db.getFirstSync<{ json: string; updated_at: string }>('SELECT json, updated_at FROM cache WHERE key = ?', [key]);
  return row ? { data: JSON.parse(row.json) as T, updatedAt: row.updated_at } : null;
}

export function cacheSet(key: string, data: unknown) {
  db.runSync('INSERT OR REPLACE INTO cache (key, json, updated_at) VALUES (?, ?, ?)', [
    key, JSON.stringify(data), new Date().toISOString(),
  ]);
}

export type OutboxRow = {
  action_id: string; type: 'score_event' | 'roster_transfer'; queued_at: string; base_version: number;
  payload: string; label: string; ref: string;
};

export function outboxAll(): OutboxRow[] {
  return db.getAllSync<OutboxRow>('SELECT * FROM outbox ORDER BY queued_at, rowid');
}

export function outboxAdd(r: OutboxRow) {
  db.runSync('INSERT INTO outbox (action_id, type, queued_at, base_version, payload, label, ref) VALUES (?, ?, ?, ?, ?, ?, ?)',
    [r.action_id, r.type, r.queued_at, r.base_version, r.payload, r.label, r.ref]);
}

export function outboxDelete(ids: string[]) {
  db.withTransactionSync(() => ids.forEach((id) => db.runSync('DELETE FROM outbox WHERE action_id = ?', [id])));
}

export type SyncLogRow = {
  action_id: string; label: string; status: string; resolution: string; error_code: string | null;
  message: string; processed_at: string;
};

export function syncLogAdd(rows: SyncLogRow[]) {
  db.withTransactionSync(() => rows.forEach((r) => db.runSync(
    'INSERT INTO sync_log (action_id, label, status, resolution, error_code, message, processed_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
    [r.action_id, r.label, r.status, r.resolution, r.error_code, r.message, r.processed_at])));
}

export function syncLogRecent(limit = 30): SyncLogRow[] {
  return db.getAllSync<SyncLogRow>('SELECT * FROM sync_log ORDER BY rowid DESC LIMIT ?', [limit]);
}

export function clearUserData() {
  db.execSync('DELETE FROM cache; DELETE FROM sync_log;');
}
