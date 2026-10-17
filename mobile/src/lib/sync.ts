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

export async function checkConnection(): Promise<boolean> {
  let ok = false;
  if (netConnected) {
    try {
      await api.health();
      ok = true;
    } catch {
      ok = false;
    }
  }
  const was = useNet.getState().online;
  useNet.setState({ online: ok, checked: true });
  if (ok && !was) void flush();
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
  if (useNet.getState().online) void flush();
  return row;
}

export async function flush(): Promise<void> {
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
      return { action_id: x.action_id, label, status: x.status, resolution: x.resolution, error_code: x.error_code, message, processed_at: processed };
    });
    outboxDelete(res.results.map((x) => x.action_id));
    syncLogAdd(items);
    useNet.setState((s) => ({ lastSync: processed, lastResults: items, dataVersion: s.dataVersion + 1 }));
  } catch (e) {
    if (e instanceof ApiError && e.code === 'NETWORK') useNet.setState({ online: false });
  } finally {
    useNet.setState({ syncing: false });
    refreshPending();
  }
}
