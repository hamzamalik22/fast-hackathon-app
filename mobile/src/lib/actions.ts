// Everything a screen can *do*. UI components call these; none of them talk to fetch/SQLite directly.
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

import { toast } from '../screens/common';
import { api, Club, MatchDetail, Receipt, RosterPlayer } from './api';
import { cacheSet, OutboxRow } from './db';
import { humanize } from './hooks';
import { CartLine, useCart, useSession } from './state';
import { enqueue, pendingFor, sendNow, uuid } from './sync';

// ---------------------------------------------------------------- session
export async function login(email: string, password: string) {
  const r = await api.login(email.trim(), password);
  await useSession.getState().signIn(r.token, r.user, r.tenant);
  void prewarmCache();
}

export async function logout() {
  await useSession.getState().signOut();
  useCart.getState().clear();
}

/** Caches leagues, fixtures, standings and the user's club right after login so they open offline. */
export async function prewarmCache() {
  try {
    const { leagues } = await api.leagues();
    cacheSet('leagues', leagues);
    await Promise.all(leagues.slice(0, 4).flatMap((l) => [
      api.fixtures(l.league_id).then((r) => cacheSet(`fixtures:${l.league_id}`, r.matches)),
      api.standings(l.league_id).then((r) => cacheSet(`standings:${l.league_id}`, r)),
    ]));
    const clubId = useSession.getState().user?.club_id;
    if (clubId) cacheSet(`club:${clubId}`, await api.club(clubId));
    cacheSet('products', (await api.products()).products);
  } catch {
    /* best effort: screens fetch on open anyway */
  }
}

// ---------------------------------------------------------------- scoring (league organizer) -> offline queue
export const matchRef = (matchId: string) => `match:${matchId}`;

function matchBaseVersion(match: MatchDetail): number {
  return match.version + pendingFor(matchRef(match.match_id)).length;
}

function teamName(match: MatchDetail, teamId: string) {
  return teamId === match.home.team_id ? match.home_name : match.away_name;
}

/** Sends a queued action right away when online and reports the outcome as a toast. */
export async function deliver(row: OutboxRow, done: string) {
  const r = await sendNow(row.action_id);
  if (!r) toast('Saved on this phone. It will sync when you’re back online.', 'warn');
  else if (r.status === 'rejected') toast(r.message, 'warn');
  else toast(done);
  return r;
}

function queueMatchEvent(match: MatchDetail, type: string, payload: Record<string, unknown>, label: string) {
  const row = enqueue('score_event', { event_id: `app-${uuid()}`, match_id: match.match_id, type, payload },
    matchBaseVersion(match), label, matchRef(match.match_id));
  void deliver(row, `${label} · saved`);
  return row;
}

export const scoreEvent = (match: MatchDetail, teamId: string, eventType: string) =>
  queueMatchEvent(match, 'score', { team_id: teamId, event_type: eventType }, `${humanize(eventType)} · ${teamName(match, teamId)}`);

export const startMatch = (match: MatchDetail) => queueMatchEvent(match, 'match_start', {}, `Start match · ${match.home_name} v ${match.away_name}`);

export const endMatch = (match: MatchDetail) => queueMatchEvent(match, 'match_end', {}, `End match · ${match.home_name} v ${match.away_name}`);

export const tiebreakWinner = (match: MatchDetail, teamId: string) =>
  queueMatchEvent(match, 'tiebreak_winner', { team_id: teamId }, `Tie-break winner · ${teamName(match, teamId)}`);

export const disciplinePoints = (match: MatchDetail, teamId: string, points: number) =>
  queueMatchEvent(match, 'discipline', { team_id: teamId, points }, `Discipline ${points} · ${teamName(match, teamId)}`);

/** Correction = compensating event (the original stays in the log, marked reversed). */
export const compensate = (match: MatchDetail, eventId: string, reason: string) =>
  queueMatchEvent(match, 'compensation', { compensates: eventId, reason }, `Correction · ${reason}`);

// ---------------------------------------------------------------- roster (club manager) -> offline queue
export const playerRef = (playerId: string) => `player:${playerId}`;

export type RosterActionInput = {
  club: Club; player: RosterPlayer; type: 'transfer' | 'loan' | 'release';
  toSquadId?: string | null; effectiveDate: string; loanEndDate?: string | null; reason: string;
};

export function queueRosterAction(i: RosterActionInput) {
  const user = useSession.getState().user;
  const payload = {
    request_id: `app-${uuid()}`, league_id: i.club.roster_league_id, player_id: i.player.player_id, type: i.type,
    from_squad_id: i.player.squad_id, to_squad_id: i.type === 'release' ? null : i.toSquadId ?? null,
    effective_date: i.effectiveDate, loan_end_date: i.type === 'loan' ? i.loanEndDate ?? null : null,
    reason: i.reason || humanize(i.type), requested_by: user?.user_id ?? null,
  };
  const base = i.player.audit_count + pendingFor(playerRef(i.player.player_id)).length;
  const dest = i.club.squads.find((s) => s.squad_id === i.toSquadId)?.name ?? i.toSquadId ?? '';
  const label = i.type === 'release' ? `Release · ${i.player.name}` : `${humanize(i.type)} · ${i.player.name} → ${dest}`;
  return enqueue('roster_transfer', payload, base, label, playerRef(i.player.player_id));
}

/** Registering a brand-new player needs a connection (not part of the offline action format). */
export const addPlayer = (clubId: string, name: string, position: string, role = 'substitute') =>
  api.addPlayer(clubId, { name, position, role });

// ---------------------------------------------------------------- store
export type PaymentToken = 'tok_success' | 'tok_declined' | 'tok_capture_fail';

export async function checkout(lines: CartLine[], discountCode: string | null, token: PaymentToken = 'tok_success') {
  const result = await api.checkout({
    order_id: `ord-${uuid()}`,
    items: lines.map((l) => ({ variant_id: l.variant.variant_id, quantity: l.quantity })),
    discount_code: discountCode?.trim() ? discountCode.trim().toUpperCase() : null,
    payment: { token },
  });
  cacheSet(`receipt:${result.order_id}`, result.receipt);
  cacheSet(`order:${result.order_id}`, result);
  useCart.getState().clear();
  return result;
}

/** Writes the server-generated PDF to the cache dir and opens the system share/open sheet. */
export async function openReceiptPdf(receipt: Receipt): Promise<string> {
  const uri = `${FileSystem.cacheDirectory}receipt-${receipt.payload.order_id}.pdf`;
  await FileSystem.writeAsStringAsync(uri, receipt.pdf_base64, { encoding: FileSystem.EncodingType.Base64 });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: `Receipt ${receipt.payload.order_id}`, UTI: 'com.adobe.pdf' });
  }
  return uri;
}
