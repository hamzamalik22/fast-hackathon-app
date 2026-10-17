// Data hooks for screens: cache-first (SQLite), auto-refresh online, live match updates, pending-queue overlays.
import { useEffect, useMemo, useState } from 'react';

import { api, League, MatchDetail, Product } from './api';
import { kvGet, kvSet, outboxAll, OutboxRow, syncLogRecent } from './db';
import { useCached, useLiveChannel } from './hooks';
import { useNet, useSession } from './state';

export const useLeagues = () => useCached<League[]>('leagues', () => api.leagues().then((r) => r.leagues));
export const useFixtures = (leagueId: string | null) =>
  useCached(leagueId ? `fixtures:${leagueId}` : null, () => api.fixtures(leagueId!).then((r) => r.matches));
export const useStandings = (leagueId: string | null) =>
  useCached(leagueId ? `standings:${leagueId}` : null, () => api.standings(leagueId!));
export const useClub = (clubId: string | null) => useCached(clubId ? `club:${clubId}` : null, () => api.club(clubId!));
export const useClubs = () => useCached('clubs', () => api.clubs().then((r) => r.clubs));
export const useProducts = () => useCached<Product[]>('products', () => api.products().then((r) => r.products));
export const useOrders = () => useCached('orders', () => api.orders().then((r) => r.orders));
export const usePlayerHistory = (playerId: string | null) =>
  useCached(playerId ? `history:${playerId}` : null, () => api.history(playerId!));

/** Actions still waiting in the offline queue for one entity (match:<id> / player:<id>), re-read on every change. */
export function usePending(ref?: string): (OutboxRow & { body: any })[] {
  const pending = useNet((s) => s.pending);
  const syncing = useNet((s) => s.syncing);
  return useMemo(() => outboxAll().filter((r) => !ref || r.ref === ref).map((r) => ({ ...r, body: JSON.parse(r.payload) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ref, pending, syncing]);
}

export function useSyncLog() {
  const dataVersion = useNet((s) => s.dataVersion);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => syncLogRecent(), [dataVersion]);
}

/** Match detail + live WebSocket refresh + the organizer's queued (not yet synced) events. */
export function useMatch(matchId: string) {
  const q = useCached<MatchDetail>(`match:${matchId}`, () => api.match(matchId));
  useLiveChannel(`match:${matchId}`, (msg) => {
    if (['match_event', 'match_status', 'product_pinned'].includes(msg?.type)) void q.refresh();
  });
  const pending = usePending(`match:${matchId}`);
  return { ...q, pending };
}

/** Selected league (persisted). Defaults to the organizer's own league, else the first visible league. */
export function useSelectedLeague(leagues: League[] | null): [string | null, (id: string) => void] {
  const user = useSession((s) => s.user);
  const [id, setId] = useState<string | null>(() => kvGet('selected_league'));
  useEffect(() => {
    if (!leagues?.length) return;
    if (!id || !leagues.some((l) => l.league_id === id)) {
      const own = leagues.find((l) => user?.league_ids?.includes(l.league_id));
      setId((own ?? leagues[0]).league_id);
    }
  }, [leagues, id, user]);
  return [id, (next: string) => { kvSet('selected_league', next); setId(next); }];
}

export function can(role: string | undefined, what: 'score' | 'roster' | 'admin'): boolean {
  if (what === 'score') return role === 'league_organizer' || role === 'super_admin';
  if (what === 'roster') return role === 'club_manager' || role === 'super_admin';
  return role === 'super_admin';
}
