-- All JSON blobs are TEXT (ASCII-escaped JSON) so payloads round-trip byte-exactly for signatures/idempotency.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value BIGINT NOT NULL);

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL, logo_url TEXT, primary_color TEXT, accent_color TEXT);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL,
  tenant_id TEXT, name TEXT NOT NULL, league_ids TEXT NOT NULL DEFAULT '[]', club_id TEXT, player_id TEXT);

-- FR-5.1 policy matrix stored as data: scope in any|own_league|own_club|own_club_player|self|same_tenant
CREATE TABLE IF NOT EXISTS rbac_policies (
  action TEXT NOT NULL, role TEXT NOT NULL, scope TEXT NOT NULL, PRIMARY KEY (action, role));

CREATE TABLE IF NOT EXISTS sports (
  sport_id TEXT PRIMARY KEY, name TEXT NOT NULL, scoring_model TEXT NOT NULL, config TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS leagues (
  league_id TEXT PRIMARY KEY, tenant_id TEXT, sport_id TEXT NOT NULL, name TEXT, season TEXT,
  format TEXT NOT NULL DEFAULT 'league', config TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS matches (
  match_id TEXT PRIMARY KEY, league_id TEXT, sport_id TEXT NOT NULL,
  home_team_id TEXT NOT NULL, away_team_id TEXT NOT NULL, created_by_init BOOLEAN NOT NULL DEFAULT FALSE,
  scheduled_at TIMESTAMPTZ, venue_id TEXT, round INT, admin_status TEXT, pinned_product_id TEXT,
  created_seq BIGSERIAL);
CREATE INDEX IF NOT EXISTS matches_league_idx ON matches (league_id);

-- Append-only event log (never UPDATEd or DELETEd except by /reset)
CREATE TABLE IF NOT EXISTS match_events (
  event_id TEXT PRIMARY KEY, match_id TEXT NOT NULL, sequence INT NOT NULL, type TEXT NOT NULL,
  payload TEXT NOT NULL, signature TEXT NOT NULL, compensates TEXT, request_canonical TEXT NOT NULL,
  response TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (match_id, sequence));

CREATE TABLE IF NOT EXISTS clubs (
  club_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, logo_url TEXT, venue_name TEXT,
  lat DOUBLE PRECISION, lng DOUBLE PRECISION, socials TEXT NOT NULL DEFAULT '{}',
  staff TEXT NOT NULL DEFAULT '[]', stats TEXT NOT NULL DEFAULT '[]');

CREATE TABLE IF NOT EXISTS venues (
  venue_id TEXT PRIMARY KEY, tenant_id TEXT, name TEXT NOT NULL,
  open_hour INT NOT NULL DEFAULT 8, close_hour INT NOT NULL DEFAULT 23);

CREATE TABLE IF NOT EXISTS roster_leagues (
  league_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sport_id TEXT NOT NULL,
  window_open DATE, window_close DATE, max_squad_size INT NOT NULL, required_positions TEXT NOT NULL DEFAULT '{}');

CREATE TABLE IF NOT EXISTS squads (
  league_id TEXT NOT NULL, squad_id TEXT NOT NULL, club_id TEXT, tenant_id TEXT NOT NULL, name TEXT,
  PRIMARY KEY (league_id, squad_id));

CREATE TABLE IF NOT EXISTS roster_players (
  player_id TEXT PRIMARY KEY, league_id TEXT NOT NULL, name TEXT, position TEXT, squad_id TEXT, role TEXT,
  parent_squad_id TEXT, registration_type TEXT, start_date DATE, loan_end_date DATE, initial_squad_id TEXT);

CREATE TABLE IF NOT EXISTS roster_live_matches (
  league_id TEXT NOT NULL, match_id TEXT NOT NULL, home_squad_id TEXT, away_squad_id TEXT);

-- Append-only roster audit trail
CREATE TABLE IF NOT EXISTS roster_audit (
  seq BIGSERIAL PRIMARY KEY, audit_id TEXT UNIQUE NOT NULL, player_id TEXT NOT NULL, league_id TEXT NOT NULL,
  action TEXT NOT NULL, effective_date DATE NOT NULL, entry TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS roster_audit_player_idx ON roster_audit (player_id);

CREATE TABLE IF NOT EXISTS roster_requests (
  request_id TEXT PRIMARY KEY, request_canonical TEXT NOT NULL, response TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS products (
  product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, club_id TEXT, name TEXT NOT NULL,
  category TEXT NOT NULL, description TEXT, image_url TEXT);

CREATE TABLE IF NOT EXISTS variants (
  variant_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, size TEXT, color TEXT, price_minor BIGINT NOT NULL,
  stock INT NOT NULL CHECK (stock >= 0), reserved INT NOT NULL DEFAULT 0 CHECK (reserved >= 0));

CREATE TABLE IF NOT EXISTS price_schedules (
  variant_id TEXT NOT NULL, price_minor BIGINT NOT NULL, effective_from TIMESTAMPTZ NOT NULL);

CREATE TABLE IF NOT EXISTS discount_codes (code TEXT PRIMARY KEY, percent INT NOT NULL);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, status TEXT NOT NULL, request_canonical TEXT NOT NULL,
  response TEXT, total_minor BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS order_events (
  id BIGSERIAL PRIMARY KEY, order_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS payments (
  id BIGSERIAL PRIMARY KEY, order_id TEXT NOT NULL, authorization_id TEXT, capture_id TEXT, state TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sync_actions (
  device_id TEXT NOT NULL, action_id TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY (device_id, action_id));

CREATE TABLE IF NOT EXISTS domain_event_log (
  id BIGSERIAL PRIMARY KEY, type TEXT NOT NULL, payload TEXT NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT now());
