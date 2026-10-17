// Connectivity monitor + offline outbox (spec 5.14 action format) + automatic sync with per-action results.
import NetInfo from '@react-native-community/netinfo';
import * as Crypto from 'expo-crypto';

import { api, ApiError } from './api';
import { kvGet, kvSet, outboxAdd, outboxAll, outboxDelete, OutboxRow, syncLogAdd } from './db';
import { friendly } from './messages';
import { useNet, useSession } from './state';

let netConnected = true;
let timer: ReturnType<typeof setInterval> | null = null;

export function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function uuid(): string {
  return Crypto.randomUUID();
}

export function deviceId(): string {
  let id = kvGet('device_id');
  if (!id) {
    id = `dev-${uuid()}`;
    kvSet('device_id', id);
  }
  return id;
}

export function refreshPending() {
  useNet.setState({ pending: outboxAll().length });
}

// Tried in order until one answers, only while no server address has been saved in Settings.
const CANDIDATE_SERVERS = ['http://localhost:8080', 'http://10.0.2.2:8080'];

async function discoverServer(): Promise<boolean> {
  for (const base of CANDIDATE_SERVERS) {
    try {
      await api.health(base);
      kvSet('server_url', base);
      return true;
    } catch {
      /* try the next candidate */
    }
  }
  return false;
}

export async function checkConnection(): Promise<boolean> {
  let ok = false;
  if (netConnected) {
    try {
      if (!kvGet('server_url')) {
        ok = await discoverServer();
      } else {
        await api.health();
        ok = true;
      }
    } catch {
      ok = false;
    }
  }
  const st = useNet.getState();
  useNet.setState({ online: ok, checked: true });
  // Reconnected, or still-queued actions from an earlier failed attempt: sync them automatically.
  if (ok && !st.syncing && (!st.online || outboxAll().length > 0)) void flush();
  return ok;
}

export function startConnectivity() {
  refreshPending();
  // A network change triggers an immediate /health probe; the probe (not NetInfo's internet check) decides
  // "online", because venue Wi-Fi may reach the laptop without reaching the internet.
  NetInfo.addEventListener((s) => {
    netConnected = !!s.isConnected;
    void checkConnection();
  });
  if (!timer) timer = setInterval(() => void checkConnection(), 8000);
  void checkConnection();
}

export function pendingFor(ref: string): OutboxRow[] {
  return outboxAll().filter((r) => r.ref === ref);
}

/** Queue an action in the exact /offline-sync format. Synced immediately when online. */
export function enqueue(type: OutboxRow['type'], payload: Record<string, unknown>, baseVersion: number, label: string, ref: string) {
  const row: OutboxRow = {
    action_id: uuid(), type, queued_at: nowIso(), base_version: baseVersion, payload: JSON.stringify(payload), label, ref,
  };
  outboxAdd(row);
  refreshPending();
  return row;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Online: send now and return this action's result. Offline (or the send fails): stays queued, result null. */
export async function sendNow(actionId: string, quiet = true) {
  if (!useNet.getState().online) return null;
  // Another sync may be running (e.g. a tap right after reconnecting): wait for it, then send ours.
  for (let i = 0; i < 50 && useNet.getState().syncing; i++) await sleep(200);
  if (outboxAll().some((r) => r.action_id === actionId)) await flush(quiet);
  return useNet.getState().lastResults?.find((r) => r.action_id === actionId) ?? null;
}

/** quiet = results are rendered inline by the caller (e.g. the roster form), so no results sheet pops up. */
export async function flush(quiet = false): Promise<void> {
  const st = useNet.getState();
  if (st.syncing || !useSession.getState().token) return;
  const rows = outboxAll();
  if (!rows.length) return;
  useNet.setState({ syncing: true });
  try {
    const res = await api.sync({
      device_id: deviceId(),
      actions: rows.map((r) => ({ action_id: r.action_id, type: r.type, queued_at: r.queued_at, base_version: r.base_version, payload: JSON.parse(r.payload) })),
    });
    const byId = new Map(rows.map((r) => [r.action_id, r]));
    const processed = nowIso();
    const items = res.results.map((x) => {
      const label = byId.get(x.action_id)?.label ?? 'Change';
      const message = x.status === 'applied' ? 'Saved on the server.'
        : x.status === 'duplicate' ? 'Already synced earlier.' : friendly(x.error_code);
      return { action_id: x.action_id, label, status: x.status, resolution: x.resolution, error_code: x.error_code, message, processed_at: processed, processed_order: x.processed_order };
    });
    outboxDelete(res.results.map((x) => x.action_id));
    syncLogAdd(items);
    useNet.setState((s) => ({ lastSync: processed, lastResults: items, resultsShown: !!quiet, dataVersion: s.dataVersion + 1 }));
  } catch (e) {
    if (e instanceof ApiError && e.code === 'NETWORK') useNet.setState({ online: false });
  } finally {
    useNet.setState({ syncing: false });
    refreshPending();
  }
}
