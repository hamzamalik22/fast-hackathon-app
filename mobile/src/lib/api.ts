// HTTP client for the backend (/api/v1). Server address is configurable in Settings.
import { kvGet } from './db';
import { friendly } from './messages';

export const DEFAULT_SERVER = 'http://10.0.2.2:8080';

export class ApiError extends Error {
  constructor(public code: string, public status: number, public details: any = {}) {
    super(friendly(code));
  }
}

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) { token = t; }
export function getToken() { return token; }
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }
export function serverUrl(): string { return (kvGet('server_url') || DEFAULT_SERVER).replace(/\/+$/, ''); }
export function assetUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  return path.startsWith('http') ? path : serverUrl() + path;
}

export async function request<T = any>(method: string, path: string, body?: unknown, timeoutMs = 10000, base?: string): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch((base ?? serverUrl()) + path, {
      method,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
  } catch {
    throw new ApiError('NETWORK', 0);
  } finally {
    clearTimeout(timer);
  }
  const text = await res.text();
  let json: any = null;
  try { json = text ? JSON.parse(text) : null; } catch { json = null; }
  if (!res.ok) {
    const err = json?.error ?? {};
    if (res.status === 401 && token && path !== '/api/v1/auth/login') onUnauthorized?.();
    throw new ApiError(err.code ?? (res.status >= 500 ? 'SERVER' : 'HTTP'), res.status, err.details ?? {});
  }
  return json as T;
}

// ---------------------------------------------------------------- types
export type Role = 'super_admin' | 'league_organizer' | 'club_manager' | 'player' | 'viewer';
export type User = { user_id: string; email: string; name: string; role: Role; tenant_id: string | null; league_ids: string[]; club_id: string | null; player_id: string | null };
export type Tenant = { tenant_id: string; name: string; logo_url: string | null; primary_color: string | null; accent_color: string | null };
export type League = { league_id: string; name: string; season: string; sport_id: string; sport_name: string; scoring_model: string; tenant_id: string };
export type Side = { team_id: string; name: string; score: number; wickets?: number | null; overs?: string | null };
export type MatchSummary = { match_id: string; round: number | null; scheduled_at: string | null; venue: string | null; status: string; version: number; sport_id?: string; scoring_model?: string; home: Side; away: Side };

/** Cricket shows runs/wickets; other sports show the plain score. */
export function scoreText(s: { score: number; wickets?: number | null }): string {
  return s.wickets != null ? `${s.score}/${s.wickets}` : String(s.score);
}
export type StandingRow = { rank: number; team_id: string; played: number; won: number; drawn: number; lost: number; scored: number; conceded: number; diff: number; points: number; fair_play: number; status: 'clinched' | 'eliminated' | 'still_possible'; resolved_by: string | null };
export type Standings = { league_id: string; sport_id: string; qualification_spots: number; table: StandingRow[]; team_names: Record<string, string> };
export type MatchEvent = { sequence: number; event_id: string; type: string; payload: any; compensated: boolean; compensated_by: string | null };
export type ScoreSide = { team_id: string; score: number; wickets: number | null; balls: number | null; overs: string | null; fair_play: number };
export type Variant = { variant_id: string; size: string; color: string; price_minor: number; stock: number };
export type Product = { product_id: string; name: string; category: string; description: string; image_url: string | null; club_id: string | null; price_minor: number; variants: Variant[] };
export type MatchDetail = {
  match_id: string; sport_id: string; league_id: string | null; status: string; outcome: string; winner_team_id: string | null;
  home: ScoreSide; away: ScoreSide; version: number; events: MatchEvent[]; scheduled_at: string | null; venue: string | null;
  home_name: string; away_name: string; can_score: boolean; pinned_product: Product | null;
  sport: { sport_id: string; name: string; scoring_model: string; scoring_events: Record<string, any>; draw_allowed: boolean };
};
export type RosterPlayer = { player_id: string; name: string; position: string; role: string | null; squad_id: string; parent_squad_id: string | null; registration_type: string; loan_end_date: string | null; audit_count: number };
export type Club = {
  club_id: string; name: string; tenant_id: string; logo_url: string | null; colors: { primary: string | null; accent: string | null };
  venue: { name: string | null; lat: number | null; lng: number | null }; socials: Record<string, string>;
  staff: { name: string; role: string }[]; stats: { season: string; played: number; won: number; drawn: number; lost: number }[];
  roster_league_id: string | null; squads: { squad_id: string; name: string; club_id: string }[]; roster: RosterPlayer[];
};
export type AuditEntry = { audit_id: string; action: string; from_squad_id: string | null; to_squad_id: string | null; effective_date: string; state: string; who: string; when: string; why: string | null };
export type Receipt = { payload: { order_id: string; customer_id: string; items: { variant_id: string; quantity: number; unit_price_minor: number }[]; subtotal_minor: number; discount_minor: number; total_minor: number; currency: string; paid_at: string }; signature: string; pdf_base64: string };
export type CheckoutResult = { order_id: string; status: string; total_minor: number; subtotal_minor: number; discount_minor: number; receipt: Receipt; payment?: { authorization_id: string; capture_id: string; state: string } };
export type SyncResult = { action_id: string; status: 'applied' | 'rejected' | 'duplicate'; resolution: string; error_code: string | null; processed_order: number; server_version: number; signature: string | null };

// ---------------------------------------------------------------- endpoints
export const api = {
  health: (base?: string) => request<{ status: string }>('GET', '/health', undefined, 3000, base),
  login: (email: string, password: string) => request<{ token: string; user: User; tenant: Tenant }>('POST', '/api/v1/auth/login', { email, password }),
  me: () => request<{ user: User; tenant: Tenant }>('GET', '/api/v1/me'),
  leagues: () => request<{ leagues: League[] }>('GET', '/api/v1/leagues'),
  fixtures: (leagueId: string) => request<{ matches: MatchSummary[] }>('GET', `/api/v1/leagues/${leagueId}/fixtures`),
  standings: (leagueId: string) => request<Standings>('GET', `/api/v1/leagues/${leagueId}/standings`),
  match: (matchId: string) => request<MatchDetail>('GET', `/api/v1/matches/${matchId}`),
  clubs: () => request<{ clubs: { club_id: string; name: string; logo_url: string | null }[] }>('GET', '/api/v1/clubs'),
  club: (clubId: string) => request<Club>('GET', `/api/v1/clubs/${clubId}`),
  addPlayer: (clubId: string, body: { name: string; position: string; role: string }) => request<{ player: RosterPlayer }>('POST', `/api/v1/clubs/${clubId}/players`, body),
  history: (playerId: string) => request<{ history: AuditEntry[]; current_squad_id: string | null }>('GET', `/api/v1/players/${playerId}/history`),
  products: () => request<{ products: Product[] }>('GET', '/api/v1/store/products'),
  checkout: (body: unknown) => request<CheckoutResult>('POST', '/api/v1/store/checkout', body, 15000),
  orders: () => request<{ orders: { order_id: string; status: string; total_minor: number; created_at: string }[] }>('GET', '/api/v1/orders'),
  receipt: (orderId: string) => request<Receipt>('GET', `/api/v1/orders/${orderId}/receipt`),
  sync: (body: unknown) => request<{ results: SyncResult[]; summary: Record<string, number> }>('POST', '/api/v1/sync', body, 20000),
  createSport: (body: unknown) => request<{ sport_id: string; status: string }>('POST', '/api/v1/admin/sports', body),
};
