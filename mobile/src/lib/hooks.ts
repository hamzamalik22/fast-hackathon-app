// Cache-first data loading (offline tolerant) + realtime match socket.
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, getToken, serverUrl } from './api';
import { cacheGet, cacheSet } from './db';
import { useNet } from './state';

export type Loaded<T> = {
  data: T | null; loading: boolean; error: ApiError | null; updatedAt: string | null; fromCache: boolean; refresh: () => Promise<void>;
};

/** Shows cached data instantly (SQLite), refreshes from the network when online, keeps the cache when offline. */
export function useCached<T>(key: string | null, fetcher: () => Promise<T>): Loaded<T> {
  const [data, setData] = useState<T | null>(() => (key ? cacheGet<T>(key)?.data ?? null : null));
  const [updatedAt, setUpdatedAt] = useState<string | null>(() => (key ? cacheGet<T>(key)?.updatedAt ?? null : null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fromCache, setFromCache] = useState(true);
  const online = useNet((s) => s.online);
  const dataVersion = useNet((s) => s.dataVersion);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  const refresh = useCallback(async () => {
    if (!key) return;
    setLoading(true);
    try {
      const fresh = await fetchRef.current();
      cacheSet(key, fresh);
      setData(fresh);
      setUpdatedAt(new Date().toISOString());
      setFromCache(false);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('NETWORK', 0));
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    if (!key) return;
    const c = cacheGet<T>(key);
    setData(c?.data ?? null);
    setUpdatedAt(c?.updatedAt ?? null);
    setFromCache(true);
  }, [key]);

  useEffect(() => {
    if (key && online) void refresh();
  }, [key, online, dataVersion, refresh]);

  return { data, loading, error, updatedAt, fromCache, refresh };
}

/** Subscribes to live updates for one channel over the backend WebSocket, reconnecting with backoff. */
export function useLiveChannel(channel: string | null, onMessage: (msg: any) => void) {
  const handler = useRef(onMessage);
  handler.current = onMessage;
  const online = useNet((s) => s.online);

  useEffect(() => {
    if (!channel || !online) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let delay = 1000;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const connect = () => {
      const url = `${serverUrl().replace(/^http/, 'ws')}/api/v1/ws?token=${encodeURIComponent(getToken() ?? '')}`;
      ws = new WebSocket(url);
      ws.onopen = () => {
        delay = 1000;
        ws?.send(JSON.stringify({ action: 'subscribe', channels: [channel] }));
      };
      ws.onmessage = (ev) => {
        try { handler.current(JSON.parse(String(ev.data))); } catch { /* ignore malformed frames */ }
      };
      ws.onclose = () => {
        if (closed) return;
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 15000);
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [channel, online]);
}

export function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatWhen(iso: string | null): string {
  if (!iso) return 'Time to be confirmed';
  const d = new Date(iso);
  return `${d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })} · ${d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
}

export function humanize(key: string): string {
  return key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}
