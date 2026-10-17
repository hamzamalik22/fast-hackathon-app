import React, { useMemo, useState } from 'react';
import { Image, ImageBackground, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import * as actions from '../lib/actions';
import { api, ApiError, MatchDetail, MatchSummary, scoreText } from '../lib/api';
import { can, useClub, useFixtures, useLeagues, useMatch, useProducts, useSelectedLeague, useStandings, useSyncLog } from '../lib/data';
import { formatWhen, humanize } from '../lib/hooks';
import { money, roleLabel, useNet, useSession } from '../lib/state';
import { clubBadge, playerPhoto, productImage, sportBackground, sportIcon } from '../ui/images';
import { Btn, C, Caps, Card, Chip, clubColor, Display, EmptyState, F, Icon, IconName, ListRow, Mono, Muted, Pill, Row, Score, Section, Sheet, TeamBadge, Text } from '../ui/kit';
import { Empty, LeaguePicker, QualTag, Screen, Stale, StatusPill, toast } from './common';

const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'; };
const timeOf = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : 'TBC');

export function MatchCard({ m, leagueName, sport, onPress }: { m: MatchSummary; leagueName?: string; sport?: string; onPress: () => void }) {
  const started = m.status !== 'upcoming';
  return (
    <Card style={{ marginBottom: 12 }} onPress={onPress} accessibilityLabel={`${m.home.name} versus ${m.away.name}, ${m.status}`}>
      <Row style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <Row gap={6} style={{ flex: 1 }}><Icon name={(sport as IconName) ?? 'soccer'} size={16} color={C.faint} /><Muted numberOfLines={1} style={{ fontSize: 12 }}>{leagueName ?? `Round ${m.round ?? '-'}`}</Muted></Row>
        <StatusPill status={m.status} time={timeOf(m.scheduled_at)} />
      </Row>
      {[m.home, m.away].map((side) => (
        <Row key={side.team_id} style={{ marginBottom: 8 }} gap={12}>
          <TeamBadge name={side.name} source={clubBadge(side.team_id)} size={28} />
          <Text style={{ flex: 1, fontWeight: '600', fontSize: 15 }} numberOfLines={1}>{side.name}</Text>
          {started && side.overs ? <Mono style={{ fontSize: 11 }}>{side.overs} ov</Mono> : null}
          {started ? <Score style={{ fontSize: 24 }}>{scoreText(side)}</Score> : null}
        </Row>
      ))}
      <Row gap={6} style={{ marginTop: 2 }}>
        <Icon name="map-marker-outline" size={15} color={C.faint} />
        <Muted style={{ fontSize: 12 }} numberOfLines={1}>{m.venue ?? 'Venue to be confirmed'}{started ? '' : ` · ${formatWhen(m.scheduled_at)}`}</Muted>
      </Row>
    </Card>
  );
}

function LiveHero({ m, sportId, model, onOpen }: { m: MatchSummary; sportId: string; model: string; onOpen: () => void }) {
  return (
    <ImageBackground source={sportBackground(sportId, model)} style={st.hero} imageStyle={{ borderRadius: 22, opacity: 0.38 }}>
      <View style={st.heroIn}>
        <Row style={{ justifyContent: 'space-between' }}>
          <Row gap={6}><Icon name={sportIcon(model, sportId)} size={16} color={C.text2} /><Text style={{ color: C.text2, fontSize: 13 }}>{humanize(sportId)}</Text></Row>
          <StatusPill status={m.status} />
        </Row>
        <Row style={{ justifyContent: 'space-between', marginTop: 16 }} gap={6}>
          <View style={st.heroTeam}><TeamBadge name={m.home.name} source={clubBadge(m.home.team_id)} size={52} /><Text style={st.heroName} numberOfLines={2}>{m.home.name}</Text></View>
          <Text style={[st.heroScore, m.home.wickets != null && st.heroScoreSm]}>{scoreText(m.home)}<Text style={[st.heroScore, m.home.wickets != null && st.heroScoreSm, { color: C.dim }]}>:</Text>{scoreText(m.away)}</Text>
          <View style={st.heroTeam}><TeamBadge name={m.away.name} source={clubBadge(m.away.team_id)} size={52} /><Text style={st.heroName} numberOfLines={2}>{m.away.name}</Text></View>
        </Row>
        <Btn label="Open match centre" kind="light" onPress={onOpen} style={{ marginTop: 16 }} small />
      </View>
    </ImageBackground>
  );
}

const SPORT_TEMPLATE = `{
  "sport_id": "kabaddi",
  "name": "Kabaddi",
  "scoring_model": "event",
  "periods": { "count": 2, "duration_minutes": 20 },
  "scoring_events": { "raid_point": { "points": 1 }, "all_out": { "points": 2 } },
  "draw_allowed": false,
  "overtime": { "policy": "golden_score", "duration_minutes": 5 },
  "roster": { "min_squad_size": 7, "max_squad_size": 12, "required_positions": { "raider": 2 } }
}`;

function AddSportSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [json, setJson] = useState(SPORT_TEMPLATE);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const create = async () => {
    let body: unknown;
    try { body = JSON.parse(json); } catch { setError('That isn’t valid JSON. Check commas, quotes and brackets.'); return; }
    setBusy(true);
    try {
      const r = await api.createSport(body);
      toast(`Sport “${r.sport_id}” created. It’s ready for leagues and scoring.`);
      setError(null);
      onClose();
    } catch (e) {
      const err = e as ApiError;
      setError(err.code === 'VALIDATION_ERROR' ? `Fix these fields: ${(err.details?.fields ?? []).join(', ')}` : err.message);
    } finally { setBusy(false); }
  };
  return (
    <Sheet visible={visible} onClose={onClose} title="Add a sport from JSON"
      actions={<><Btn kind="outline" label="Cancel" onPress={onClose} style={{ flex: 1 }} /><Btn label="Validate & create" loading={busy} onPress={create} style={{ flex: 1.4 }} /></>}>
      <Muted style={{ marginBottom: 10 }}>Sports are data. No code change or restart is needed.</Muted>
      <TextInput value={json} onChangeText={(t) => { setJson(t); setError(null); }} multiline style={st.json} autoCapitalize="none" autoCorrect={false} accessibilityLabel="Sport JSON" />
      {error ? <Row gap={6} style={{ marginTop: 8 }}><Icon name="alert-circle" size={16} color={C.err} /><Text style={{ color: C.err, flex: 1, fontSize: 13 }}>{error}</Text></Row> : null}
    </Sheet>
  );
}

export function HomeScreen({ navigation }: any) {
  const { user, tenant } = useSession();
  const role = user?.role;
  const leagues = useLeagues();
  const [leagueId] = useSelectedLeague(leagues.data);
  const league = leagues.data?.find((l) => l.league_id === leagueId);
  const fixtures = useFixtures(leagueId);
  const standings = useStandings(leagueId);
  const products = useProducts();
  const club = useClub(user?.club_id ?? null);
  const log = useSyncLog();
  const [addSport, setAddSport] = useState(false);
  const all = fixtures.data ?? [];
  const live = all.filter((m) => m.status === 'in_progress');
  const today = new Date().toDateString();
  const later = all.filter((m) => m.status === 'upcoming' && m.scheduled_at && new Date(m.scheduled_at).toDateString() === today);
  const attention = all.filter((m) => ['postponed', 'abandoned'].includes(m.status));
  const next = all.filter((m) => m.status === 'upcoming').slice(0, 3);
  const promo = products.data?.find((p) => p.product_id === 'prod-jersey-001') ?? products.data?.[0];
  const open = (id: string) => navigation.navigate('Match', { matchId: id });
  const myRow = standings.data?.table.find((r) => r.team_id === user?.club_id);
  const sportId = league?.sport_id ?? 'football';
  const model = league?.scoring_model ?? 'event';

  return (
    <Screen onRefresh={() => { void fixtures.refresh(); void standings.refresh(); }} refreshing={fixtures.loading}>
      <Muted>{greeting()}, {user?.name?.split(' ')[0]}</Muted>
      <Row gap={6} style={{ marginBottom: 16, marginTop: 2 }}>
        <Icon name="badge-account-horizontal-outline" size={16} color={C.lime} /><Text style={{ color: C.lime, fontWeight: '600', fontSize: 13 }}>{roleLabel(role)}</Text>
      </Row>
      <Stale error={fixtures.error} onRetry={fixtures.refresh} />

      {role === 'player' && club.data ? (
        <Card>
          <Row gap={14}>
            <Image source={playerPhoto} style={{ width: 64, height: 64, borderRadius: 16 }} accessibilityLabel={user?.name} />
            <View style={{ flex: 1 }}>
              <Display style={{ fontSize: 26 }}>{user?.name}</Display>
              <Muted>{(club.data.roster.find((p) => p.player_id === user?.player_id)?.position ?? 'fw').toUpperCase()} · {club.data.name}</Muted>
            </View>
          </Row>
          <Row style={{ marginTop: 14 }}>
            {[[club.data.stats[0]?.played ?? 0, 'Played'], [club.data.stats[0]?.won ?? 0, 'Won'], [club.data.stats[0]?.drawn ?? 0, 'Drawn'], [club.data.stats[0]?.lost ?? 0, 'Lost']].map(([v, l]) => (
              <View key={String(l)} style={{ flex: 1 }}><Score>{v as number}</Score><Muted style={{ fontSize: 12 }}>{l as string}</Muted></View>
            ))}
          </Row>
          <Btn kind="outline" small label="My registration history" icon="history" onPress={() => navigation.navigate('Audit', { playerId: user?.player_id, name: user?.name })} style={{ marginTop: 14 }} />
        </Card>
      ) : null}

      {role === 'club_manager' && club.data ? (
        <>
          <Card onPress={() => navigation.navigate('Club', { clubId: club.data!.club_id })} style={{ backgroundColor: '#142A20', borderColor: '#2F8F62' }}>
            <Row gap={12}>
              <TeamBadge name={club.data.name} source={clubBadge(club.data.club_id)} size={48} />
              <View style={{ flex: 1 }}><Display style={{ fontSize: 24 }}>{club.data.name}</Display><Muted style={{ fontSize: 12 }}>Your club · {club.data.club_id}</Muted></View>
              <Icon name="chevron-right" color={C.text2} />
            </Row>
            <Row style={{ marginTop: 14 }}>
              <View style={{ flex: 1 }}><Score>{myRow ? `${myRow.rank}${['th', 'st', 'nd', 'rd'][myRow.rank] ?? 'th'}` : '—'}</Score><Muted style={{ fontSize: 12 }}>{myRow ? `${myRow.points} pts` : 'No table yet'}</Muted></View>
              <View style={{ flex: 1 }}><Score>{club.data.roster.length}<Text style={[st.scoreSmall, { color: C.dim }]}>/25</Text></Score><Muted style={{ fontSize: 12 }}>Squad size</Muted></View>
              <View style={{ flex: 1 }}><Score style={{ color: C.lime }}>Open</Score><Muted style={{ fontSize: 12 }}>Window · to 31 Oct</Muted></View>
            </Row>
          </Card>
          <Section title="Roster actions" />
          <Row gap={8}>
            {([['account-plus-outline', 'Add player', 'add'], ['swap-horizontal', 'Transfer', 'transfer'], ['calendar-arrow-right', 'Loan out', 'loan'], ['account-remove-outline', 'Release', 'release']] as const).map(([ic, l, intent]) => (
              <Pressable key={l} style={st.action} onPress={() => navigation.navigate('Roster', { clubId: club.data!.club_id, intent })} accessibilityRole="button" accessibilityLabel={l}>
                <View style={st.actionIcon}><Icon name={ic} size={22} color={C.lime} /></View>
                <Text style={{ fontSize: 12, fontWeight: '600', textAlign: 'center' }}>{l}</Text>
              </Pressable>
            ))}
          </Row>
          <Section title="Recent roster changes" action="Squad" onAction={() => navigation.navigate('Roster', { clubId: club.data!.club_id })} />
          <Card style={{ padding: 0 }}>
            {log.filter((r) => /Transfer|Loan|Release/.test(r.label)).slice(0, 4).map((r) => (
              <ListRow key={r.action_id + r.processed_at} title={r.label} subtitle={`${new Date(r.processed_at).toLocaleString()} · ${r.status === 'rejected' ? `Not saved: ${r.message}` : 'Saved'}`} />
            ))}
            {!log.some((r) => /Transfer|Loan|Release/.test(r.label)) ? <View style={{ padding: 14 }}><Muted>No roster changes yet. Use the actions above.</Muted></View> : null}
          </Card>
        </>
      ) : null}

      {role === 'super_admin' ? (
        <>
          <Section title="Tenants" />
          <Card style={{ padding: 0 }}>
            <ListRow icon="domain" title="Alpha Sports" subtitle="tenant-alpha · 2 leagues · 4 clubs" />
            <ListRow icon="domain" title="Beta Athletics" subtitle="tenant-beta · 1 league · 2 clubs" />
          </Card>
          <Section title="Sports" />
          <Card style={{ padding: 0 }}>
            {[['soccer', 'Football', 'Event model · goals'], ['basketball', 'Basketball', 'Event model · 1/2/3 points'], ['cricket', 'Cricket', 'Innings model · runs, wickets, overs'], ['gamepad-variant', 'Esports', 'Round model · best of 3']].map(([ic, n, d]) => (
              <ListRow key={n} icon={ic as IconName} title={n} subtitle={d} />
            ))}
          </Card>
          <Btn kind="outline" label="Add a sport from JSON" icon="code-json" onPress={() => setAddSport(true)} style={{ marginTop: 12 }} />
          <AddSportSheet visible={addSport} onClose={() => setAddSport(false)} />
        </>
      ) : null}

      {(role === 'league_organizer' || role === 'super_admin') && league ? (
        <>
          {role === 'super_admin' ? <Section title="League" /> : null}
          <Card onPress={() => navigation.navigate('Standings')}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Row gap={6}><Icon name={sportIcon(model, sportId)} size={16} color={C.faint} /><Mono>{league.league_id}</Mono></Row>
              <Muted style={{ fontSize: 12 }}>{all.filter((m) => m.status === 'completed').length} of {all.length} played</Muted>
            </Row>
            <Display style={{ marginVertical: 12, fontSize: 28 }}>{league.name}</Display>
            <View style={{ height: 1, backgroundColor: C.divider, marginBottom: 12 }} />
            <Row>
              {[[live.length, 'Live now', C.err], [later.length, 'Later today', C.text], [attention.length, 'Needs attention', C.warnText]].map(([n, l, c]) => (
                <View key={String(l)} style={{ flex: 1 }}><Score style={{ color: c as string }}>{n as number}</Score><Muted style={{ fontSize: 12 }}>{l as string}</Muted></View>
              ))}
            </Row>
          </Card>
          {live[0] ? (
            <>
              <Section title="Score this match" />
              <Card>
                <Row style={{ justifyContent: 'space-between' }}>
                  <View style={{ flex: 1 }}>
                    <Row gap={6}><View style={st.liveDot} /><Text style={{ color: C.err, fontWeight: '700', fontSize: 12 }}>LIVE</Text></Row>
                    <Text style={{ fontWeight: '600', marginTop: 6 }} numberOfLines={2}>{live[0].home.name} v {live[0].away.name}</Text>
                  </View>
                  <Score style={{ fontSize: 44, lineHeight: 46 }}>{live[0].home.score}–{live[0].away.score}</Score>
                </Row>
                <Btn label="Open scoring entry" icon="pencil-box-outline" onPress={() => navigation.navigate('Scoring', { matchId: live[0].match_id })} style={{ marginTop: 14 }} />
              </Card>
            </>
          ) : null}
          {attention.length ? <Section title="Needs attention" /> : null}
          {attention.map((m) => (
            <Card key={m.match_id} style={{ backgroundColor: C.offSurface, borderColor: C.offBorder, marginBottom: 10 }} onPress={() => open(m.match_id)}>
              <Row gap={12} style={{ alignItems: 'flex-start' }}><Icon name="calendar-remove" color={C.warnText} /><View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '600' }}>{m.home.name} v {m.away.name} {m.status}</Text>
                <Muted>Pick a new slot. Later fixtures will be checked again.</Muted></View></Row>
            </Card>
          ))}
        </>
      ) : null}

      {(role === 'viewer' || role === 'player') && live[0] ? (
        <><Section title="Live now" /><LiveHero m={live[0]} sportId={sportId} model={model} onOpen={() => open(live[0].match_id)} /></>
      ) : null}

      {role !== 'club_manager' ? (
        <>
          <Section title={role === 'viewer' || role === 'player' ? 'Later today' : live.length ? 'Live now' : 'Coming up'} action="Fixtures" onAction={() => navigation.navigate('Fixtures')} />
          {(role === 'viewer' || role === 'player') ? (
            <Card style={{ padding: 0 }}>
              {(later.length ? later : next).map((m) => (
                <Pressable key={m.match_id} onPress={() => open(m.match_id)} style={st.laterRow} accessibilityRole="button">
                  <ImageBackground source={sportBackground(sportId, model)} style={st.thumb} imageStyle={{ borderRadius: 10 }}><Icon name={sportIcon(model, sportId)} size={18} /></ImageBackground>
                  <View style={{ flex: 1 }}><Text style={{ fontWeight: '600' }} numberOfLines={1}>{m.home.name} v {m.away.name}</Text><Muted style={{ fontSize: 12 }}>{league?.name}</Muted></View>
                  <Mono style={{ color: C.text }}>{timeOf(m.scheduled_at)}</Mono>
                </Pressable>
              ))}
              {!later.length && !next.length ? <View style={{ padding: 14 }}><Muted>No more matches today.</Muted></View> : null}
            </Card>
          ) : (live.length ? live : next).map((m) => <MatchCard key={m.match_id} m={m} leagueName={league?.name} sport={sportIcon(model, sportId)} onPress={() => open(m.match_id)} />)}
        </>
      ) : null}

      {standings.data?.table.length ? (
        <>
          <Section title="Standings" action="Full table" onAction={() => navigation.navigate('Standings')} />
          <Card style={{ padding: 0 }}>
            {standings.data.table.slice(0, 4).map((r) => (
              <Pressable key={r.team_id} style={st.snapRow} onPress={() => navigation.navigate('Club', { clubId: r.team_id })} accessibilityRole="button">
                <Mono style={{ width: 18, color: C.text }}>{r.rank}</Mono>
                <TeamBadge name={standings.data!.team_names[r.team_id] ?? r.team_id} source={clubBadge(r.team_id)} size={22} />
                <Text style={{ flex: 1, fontWeight: '500' }} numberOfLines={1}>{standings.data!.team_names[r.team_id] ?? r.team_id}</Text>
                {r.status === 'clinched' ? <QualTag status="clinched" /> : null}
                <Score style={{ fontSize: 20, width: 30, textAlign: 'right' }}>{r.points}</Score>
              </Pressable>
            ))}
          </Card>
        </>
      ) : null}

      {promo ? (
        <Pressable onPress={() => navigation.navigate('Product', { productId: promo.product_id })} style={st.promo} accessibilityRole="button" accessibilityLabel={`${promo.name}, ${money(promo.price_minor)}`}>
          <View style={{ flex: 1, padding: 16 }}>
            <Caps style={{ color: '#CFF5DD' }}>Club store</Caps>
            <Display style={{ fontSize: 24, marginVertical: 6 }}>{promo.name}</Display>
            <Text style={{ fontWeight: '700' }}>{money(promo.price_minor)}</Text>
          </View>
          <Image source={productImage(promo.product_id)} style={st.promoImg} />
        </Pressable>
      ) : null}
      {!league && !leagues.loading ? <Empty title="No leagues yet" message="When your organisation adds a league it shows up here." icon="trophy-outline" /> : null}
      <Muted style={{ textAlign: 'center', marginTop: 18, fontSize: 12 }}>{tenant?.name}</Muted>
    </Screen>
  );
}

function dayKey(d: Date) { return d.toISOString().slice(0, 10); }

export function FixturesScreen({ navigation }: any) {
  const leagues = useLeagues();
  const [leagueId, setLeague] = useSelectedLeague(leagues.data);
  const fixtures = useFixtures(leagueId);
  const league = leagues.data?.find((l) => l.league_id === leagueId);
  const days = useMemo(() => {
    const base = new Date();
    return Array.from({ length: 7 }, (_, i) => { const d = new Date(base); d.setDate(base.getDate() + i - 2); return d; });
  }, []);
  const [day, setDay] = useState<string | 'all'>('all');
  const rows = (fixtures.data ?? []).filter((m) => day === 'all' || (m.scheduled_at && dayKey(new Date(m.scheduled_at)) === day));
  const todayKey = dayKey(new Date());
  return (
    <Screen onRefresh={fixtures.refresh} refreshing={fixtures.loading}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12, flexGrow: 0 }}>
        <Pressable onPress={() => setDay('all')} style={[st.day, day === 'all' && st.daySel]} accessibilityRole="button" accessibilityState={{ selected: day === 'all' }}>
          <Text style={[st.dayTop, day === 'all' && { color: C.onLime }]}>ALL</Text><Text style={[st.dayNum, day === 'all' && { color: C.onLime }]}>•</Text>
        </Pressable>
        {days.map((d) => {
          const k = dayKey(d);
          const sel = day === k;
          return (
            <Pressable key={k} onPress={() => setDay(k)} style={[st.day, sel && st.daySel]} accessibilityRole="button" accessibilityLabel={d.toDateString()} accessibilityState={{ selected: sel }}>
              <Text style={[st.dayTop, sel && { color: C.onLime }]}>{k === todayKey ? 'TODAY' : d.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase()}</Text>
              <Text style={[st.dayNum, sel && { color: C.onLime }]}>{d.getDate()}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <LeaguePicker leagues={leagues.data} value={leagueId} onChange={setLeague} />
      <Stale error={fixtures.error} onRetry={fixtures.refresh} />
      {rows.map((m) => <MatchCard key={m.match_id} m={m} leagueName={league?.name} sport={sportIcon(league?.scoring_model ?? 'event', league?.sport_id)} onPress={() => navigation.navigate('Match', { matchId: m.match_id })} />)}
      {!rows.length ? <EmptyState icon="calendar-blank-outline" title="No matches on this day" message="Pick another day or league." /> : null}
    </Screen>
  );
}

function eventInfo(ev: any, d: MatchDetail): { icon: IconName; title: string; sub: string } {
  const team = ev.payload?.team_id === d.home.team_id ? d.home_name : ev.payload?.team_id === d.away.team_id ? d.away_name : '';
  switch (ev.type) {
    case 'score': return { icon: sportIcon(d.sport.scoring_model, d.sport_id), title: `${humanize(ev.payload.event_type)} · ${team}`, sub: `Event v${ev.sequence}` };
    case 'match_start': return { icon: 'whistle-outline', title: 'Kick-off', sub: 'Match started' };
    case 'match_end': return { icon: 'flag-checkered', title: 'Full time', sub: 'Match completed' };
    case 'discipline': return { icon: 'cards-outline', title: `Discipline ${ev.payload.points} · ${team}`, sub: 'Fair-play points' };
    case 'tiebreak_winner': return { icon: 'trophy-outline', title: `Tie-break won by ${team}`, sub: 'Shootout or overtime' };
    case 'compensation': return { icon: 'undo-variant', title: 'Correction', sub: `Correction to event · ${ev.payload.reason ?? 'reversed'}` };
    default: return { icon: 'information-outline', title: humanize(ev.type), sub: '' };
  }
}

export function MatchScreen({ route, navigation }: any) {
  const { matchId } = route.params;
  const m = useMatch(matchId);
  const user = useSession((s) => s.user);
  const d = m.data;
  if (!d) return <Screen><Stale error={m.error} onRetry={m.refresh} />{!m.error ? <Muted>Loading match…</Muted> : null}</Screen>;
  const innings = d.sport.scoring_model === 'innings';
  const canScore = d.can_score || can(user?.role, 'admin');
  const byId = new Map(d.events.map((e) => [e.event_id, e]));
  return (
    <Screen onRefresh={m.refresh} refreshing={m.loading}>
      <Stale error={m.error} onRetry={m.refresh} />
      <ImageBackground source={sportBackground(d.sport_id, d.sport.scoring_model)} style={st.hero} imageStyle={{ borderRadius: 22, opacity: 0.4 }}>
        <View style={st.heroIn}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Row gap={6}><Icon name={sportIcon(d.sport.scoring_model, d.sport_id)} size={16} color={C.text2} /><Text style={{ color: C.text2, fontSize: 13 }}>{d.sport.name}</Text></Row>
            <StatusPill status={d.status} time={timeOf(d.scheduled_at)} />
          </Row>
          <Row style={{ justifyContent: 'space-between', marginTop: 18 }} gap={6}>
            <View style={st.heroTeam}><TeamBadge name={d.home_name} source={clubBadge(d.home.team_id)} size={56} /><Text style={st.heroName} numberOfLines={2}>{d.home_name}</Text></View>
            <Text style={[st.heroScore, innings && st.heroScoreSm]} accessibilityLabel={`Score ${scoreText(d.home)} to ${scoreText(d.away)}`}>{scoreText(d.home)}<Text style={[st.heroScore, innings && st.heroScoreSm, { color: C.dim }]}>:</Text>{scoreText(d.away)}</Text>
            <View style={st.heroTeam}><TeamBadge name={d.away_name} source={clubBadge(d.away.team_id)} size={56} /><Text style={st.heroName} numberOfLines={2}>{d.away_name}</Text></View>
          </Row>
          {innings ? <Text style={{ color: C.text2, textAlign: 'center', marginTop: 6, fontFamily: F.mono, fontSize: 12 }}>{d.home.overs} ov   ·   {d.away.overs} ov</Text> : null}
          <Text style={{ color: C.text2, textAlign: 'center', marginTop: 8, fontSize: 13 }}>{d.status === 'in_progress' ? 'In play' : d.status === 'completed' ? 'Full time' : formatWhen(d.scheduled_at)}</Text>
          {canScore && d.status !== 'completed' ? (
            <Btn label={d.status === 'upcoming' ? 'Open scoring entry' : 'Enter score event'} icon="pencil-box-outline" onPress={() => navigation.navigate('Scoring', { matchId })} style={{ marginTop: 16 }} />
          ) : null}
        </View>
      </ImageBackground>

      {d.pinned_product ? (
        <Card style={{ marginTop: 14 }} onPress={() => navigation.navigate('Product', { productId: d.pinned_product!.product_id })}>
          <Row gap={14}>
            <Image source={productImage(d.pinned_product.product_id)} style={st.pinImg} accessibilityLabel={d.pinned_product.name} />
            <View style={{ flex: 1 }}>
              <Row gap={4}><Icon name="pin-outline" size={14} color={C.warnText} /><Caps style={{ color: C.warnText, fontSize: 11 }}>Pinned by the club</Caps></Row>
              <Text style={{ fontWeight: '600', marginTop: 4 }} numberOfLines={2}>{d.pinned_product.name}</Text>
              <Text style={{ marginTop: 2 }}>{money(d.pinned_product.price_minor)}</Text>
            </View>
            <View style={st.buy}><Text style={{ color: C.onLime, fontWeight: '700' }}>Buy</Text></View>
          </Row>
        </Card>
      ) : null}

      <Section title="Timeline" action={`Event log v${d.version}`} />
      <Card style={{ padding: 0 }}>
        {m.pending.map((p) => (
          <Row key={p.action_id} style={st.tl} gap={12}>
            <View style={[st.tlIcon, { borderStyle: 'dashed', borderWidth: 1, borderColor: C.warn, backgroundColor: 'transparent' }]}><Icon name="timer-sand" size={16} color={C.warnText} /></View>
            <View style={{ flex: 1 }}><Text style={{ fontWeight: '500' }}>{p.label}</Text><Text style={{ color: C.warnText, fontSize: 12 }}>Waiting to sync</Text></View>
          </Row>
        ))}
        {[...d.events].reverse().map((ev) => {
          const info = eventInfo(ev, d);
          const target = ev.type === 'compensation' ? byId.get(ev.payload?.compensates) : null;
          return (
            <Row key={ev.event_id} style={st.tl} gap={12}>
              <Mono style={{ width: 26, color: C.faint }}>v{ev.sequence}</Mono>
              <View style={[st.tlIcon, ev.type === 'score' && !ev.compensated && { backgroundColor: C.lime }, ev.type === 'compensation' && { backgroundColor: C.warnBg }]}>
                <Icon name={info.icon} size={17} color={ev.type === 'score' && !ev.compensated ? C.onLime : ev.type === 'compensation' ? C.warnText : C.text2} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[{ fontWeight: '600' }, ev.compensated && { textDecorationLine: 'line-through', color: C.faint }]}>{info.title}</Text>
                {ev.compensated ? <Pill label="Reversed" tone="warn" icon="undo-variant" style={{ marginTop: 4 }} /> : (
                  <Muted style={{ fontSize: 12 }}>{target ? `Correction to event v${target.sequence} · ${ev.payload.reason ?? ''}` : info.sub}</Muted>
                )}
              </View>
            </Row>
          );
        })}
        {!d.events.length && !m.pending.length ? <View style={{ padding: 16 }}><Muted>No events yet. They appear here as the match is scored.</Muted></View> : null}
      </Card>

      <Section title="Match info" />
      <Card style={{ padding: 0 }}>
        <ListRow icon="map-marker-outline" title={d.venue ?? 'Venue to be confirmed'} subtitle="Venue" />
        <ListRow icon="calendar-clock" title={formatWhen(d.scheduled_at)} subtitle="Kick-off" />
        <ListRow icon="database-outline" title={`${d.match_id} · v${d.version}`} subtitle="Score is rebuilt from the event log" />
      </Card>
    </Screen>
  );
}

const REVERSE_REASONS = ['Offside', 'Foul in the build-up', 'Wrong team', 'Entered by mistake'];

export function ScoringScreen({ route }: any) {
  const { matchId } = route.params;
  const m = useMatch(matchId);
  const online = useNet((s) => s.online);
  const [team, setTeam] = useState<string | null>(null);
  const [event, setEvent] = useState<string | null>(null);
  const [reverse, setReverse] = useState<string | null>(null);
  const [reason, setReason] = useState(REVERSE_REASONS[0]);
  const [endSheet, setEndSheet] = useState(false);
  const d = m.data;
  if (!d) return <Screen><Stale error={m.error} onRetry={m.refresh} /></Screen>;
  const status = m.pending.some((p) => p.body.type === 'match_end') ? 'completed' : m.pending.some((p) => p.body.type === 'match_start') ? 'in_progress' : d.status;
  const t = team ?? d.home.team_id;
  const ev = event ?? Object.keys(d.sport.scoring_events)[0];
  const teamName = t === d.home.team_id ? d.home_name : d.away_name;
  const recent = [...d.events].reverse().filter((e) => ['score', 'discipline', 'tiebreak_winner'].includes(e.type)).slice(0, 6);
  const pendingScore = (id: string) => m.pending.filter((p) => p.body.type === 'score' && p.body.payload?.team_id === id).length;
  return (
    <Screen onRefresh={m.refresh} refreshing={m.loading}>
      <Card>
        <Row style={{ justifyContent: 'space-between' }}><StatusPill status={status} /><Mono>{d.match_id} · v{d.version + m.pending.length}</Mono></Row>
        <Row style={{ justifyContent: 'space-between', marginTop: 14 }} gap={6}>
          <Text style={{ flex: 1, fontWeight: '600' }} numberOfLines={2}>{d.home_name}</Text>
          <Score style={{ fontSize: d.sport.scoring_model === 'innings' ? 34 : 48, lineHeight: 50 }}>{scoreText(d.home)}–{scoreText(d.away)}</Score>
          <Text style={{ flex: 1, fontWeight: '600', textAlign: 'right' }} numberOfLines={2}>{d.away_name}</Text>
        </Row>
        <Muted style={{ fontSize: 12, marginTop: 8 }}>The score is rebuilt from the event log. Corrections are added, never deleted.</Muted>
      </Card>

      {status === 'upcoming' ? <Btn label={online ? 'Start match' : 'Queue start match'} icon="whistle-outline" onPress={() => actions.startMatch(d)} style={{ marginTop: 14 }} /> : null}
      {status === 'in_progress' ? (
        <>
          <Section title="Team" />
          <Row gap={8}>
            {[d.home, d.away].map((side) => {
              const sel = side.team_id === t;
              return (
                <Pressable key={side.team_id} onPress={() => setTeam(side.team_id)} style={[st.seg, sel && { backgroundColor: C.limeTint, borderColor: C.lime, borderWidth: 2 }]} accessibilityRole="radio" accessibilityState={{ checked: sel }}>
                  <TeamBadge name={side.team_id === d.home.team_id ? d.home_name : d.away_name} source={clubBadge(side.team_id)} size={24} />
                  <Text style={{ fontWeight: '600', flexShrink: 1 }} numberOfLines={1}>{side.team_id === d.home.team_id ? d.home_name : d.away_name}</Text>
                </Pressable>
              );
            })}
          </Row>
          <Section title="Event" />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(d.sport.scoring_events).map(([key, rule]: [string, any]) => {
              const sel = key === ev;
              return (
                <Pressable key={key} onPress={() => setEvent(key)} style={[st.tile, sel && { backgroundColor: C.limeTint, borderColor: C.lime, borderWidth: 2 }]} accessibilityRole="radio" accessibilityState={{ checked: sel }}>
                  <Icon name={sportIcon(d.sport.scoring_model, d.sport_id)} size={20} color={sel ? C.lime : C.text2} />
                  <Text style={{ fontSize: 12, fontWeight: '600', textAlign: 'center' }} numberOfLines={2}>{humanize(key)}</Text>
                  <Mono style={{ fontSize: 10 }}>{rule.points != null ? `+${rule.points}` : rule.runs != null ? `${rule.runs} run${rule.runs === 1 ? '' : 's'}` : `+${rule.rounds}`}</Mono>
                </Pressable>
              );
            })}
          </View>
          <Btn label={`${online ? 'Append' : 'Queue'} ${humanize(ev).toLowerCase()} · ${teamName}`} icon={online ? 'plus' : 'tray-arrow-down'} onPress={() => actions.scoreEvent(d, t, ev)} style={{ marginTop: 16 }} />
          {!online ? <Muted style={{ marginTop: 6, fontSize: 12 }}>You’re offline. Events are saved on this phone and sent when you reconnect.</Muted> : null}
          <Btn kind="outline" label="End match" icon="flag-checkered" onPress={() => setEndSheet(true)} style={{ marginTop: 10 }} />
        </>
      ) : null}

      <Section title="Recent events" />
      <Card style={{ padding: 0 }}>
        {m.pending.map((p) => <ListRow key={p.action_id} icon="timer-sand" title={p.label} subtitle="Pending · waiting to sync" />)}
        {recent.map((e) => {
          const info = eventInfo(e, d);
          return (
            <ListRow key={e.event_id} icon={info.icon} title={info.title} subtitle={e.compensated ? 'Reversed by a correction' : `Event v${e.sequence}`}
              right={e.compensated ? <Pill label="Reversed" tone="warn" /> : <Btn kind="outline" small label="Reverse" onPress={() => setReverse(e.event_id)} style={{ minHeight: 40, paddingHorizontal: 12 }} />} />
          );
        })}
        {!recent.length && !m.pending.length ? <View style={{ padding: 14 }}><Muted>No scoring events yet.</Muted></View> : null}
      </Card>

      <Sheet visible={!!reverse} onClose={() => setReverse(null)} title="Reverse this event?"
        actions={<><Btn kind="outline" label="Cancel" onPress={() => setReverse(null)} style={{ flex: 1 }} /><Btn kind="dangerSolid" label="Reverse event" onPress={() => { actions.compensate(d, reverse!, reason); setReverse(null); }} style={{ flex: 1.3 }} /></>}>
        <Muted style={{ marginBottom: 12 }}>We add a correction to the event log. The original stays visible, struck through. Nothing is deleted.</Muted>
        <Caps style={{ marginBottom: 8 }}>Reason</Caps>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 8 }}>
          {REVERSE_REASONS.map((r) => <Chip key={r} label={r} selected={reason === r} onPress={() => setReason(r)} />)}
        </View>
      </Sheet>
      <Sheet visible={endSheet} onClose={() => setEndSheet(false)} title="End this match?"
        actions={<><Btn kind="outline" label="Cancel" onPress={() => setEndSheet(false)} style={{ flex: 1 }} /><Btn label={online ? 'End match' : 'Queue end match'} onPress={() => { actions.endMatch(d); setEndSheet(false); }} style={{ flex: 1.3 }} /></>}>
        <Muted>The final score is {d.home.score}–{d.away.score}. The standings update straight away.</Muted>
      </Sheet>
    </Screen>
  );
}

export function StandingsScreen({ navigation }: any) {
  const leagues = useLeagues();
  const [leagueId, setLeague] = useSelectedLeague(leagues.data);
  const s2 = useStandings(leagueId);
  const league = leagues.data?.find((l) => l.league_id === leagueId);
  const spots = s2.data?.qualification_spots ?? 0;
  const diffLabel = league?.scoring_model === 'innings' ? 'NRR' : league?.scoring_model === 'round' ? 'MD' : 'GD';
  const draws = league?.scoring_model !== 'round';
  return (
    <Screen onRefresh={s2.refresh} refreshing={s2.loading}>
      <LeaguePicker leagues={leagues.data} value={leagueId} onChange={setLeague} />
      <Stale error={s2.error} onRetry={s2.refresh} />
      {league ? <Display style={{ fontSize: 30 }}>{league.name}</Display> : null}
      {league ? <Muted style={{ marginTop: 6, marginBottom: 14 }}>{league.sport_name} · Top {spots} qualify for the playoffs</Muted> : null}
      <Card style={{ padding: 0 }}>
        <Row style={[st.tr, { borderTopWidth: 0 }]} gap={0}>
          <Text style={[st.th, { width: 22 }]}>#</Text><Text style={[st.th, { flex: 1, marginLeft: 12 }]}>CLUB</Text>
          {['P', 'W', ...(draws ? ['D'] : []), 'L', diffLabel].map((h) => <Text key={h} style={[st.th, st.num]}>{h}</Text>)}
          <Text style={[st.th, st.num, { color: C.text }]}>PTS</Text>
        </Row>
        {s2.data?.table.map((r) => {
          const name = s2.data!.team_names[r.team_id] ?? r.team_id;
          return (
            <Pressable key={r.team_id} onPress={() => navigation.navigate('Club', { clubId: r.team_id })} accessibilityRole="button"
              accessibilityLabel={`${name}, position ${r.rank}, ${r.points} points, ${r.status.replace('_', ' ')}`}
              style={({ pressed }) => [st.tr, { flexDirection: 'column', alignItems: 'stretch' }, r.rank <= spots && { backgroundColor: '#171C12' }, pressed && { backgroundColor: C.card2 }]}>
              <Row gap={0}>
                <Mono style={{ width: 22, color: C.text, fontSize: 12 }}>{r.rank}</Mono>
                <View style={[st.bar, { backgroundColor: clubColor(name) }]} />
                <Text style={{ flex: 1, fontWeight: '500', fontSize: 14 }} numberOfLines={1}>{name}</Text>
                {[r.played, r.won, ...(draws ? [r.drawn] : []), r.lost].map((v, i) => <Mono key={i} style={[st.num, { color: C.text2, fontSize: 11 }]}>{v}</Mono>)}
                <Mono style={[st.num, { color: C.text2, fontSize: 11 }]}>{r.diff > 0 ? `+${r.diff}` : r.diff}</Mono>
                <Score style={[st.num, { fontSize: 18, lineHeight: 20 }]}>{r.points}</Score>
              </Row>
              <Row style={{ justifyContent: 'flex-end', marginTop: 4 }}><QualTag status={r.status} /></Row>
            </Pressable>
          );
        })}
        {s2.data && !s2.data.table.length ? <View style={{ padding: 16 }}><Muted>The table fills in as results come in.</Muted></View> : null}
      </Card>
      <View style={{ marginTop: 14, gap: 8 }}>
        <Row gap={8}><QualTag status="clinched" /><Muted style={{ fontSize: 12 }}>has a playoff place</Muted></Row>
        <Row gap={8}><QualTag status="eliminated" /><Muted style={{ fontSize: 12 }}>can no longer qualify</Muted></Row>
        <Row gap={8}><QualTag status="still_possible" /><Muted style={{ fontSize: 12 }}>can still qualify</Muted></Row>
      </View>
    </Screen>
  );
}

const st = StyleSheet.create({
  hero: { borderRadius: 22, overflow: 'hidden', backgroundColor: '#0B0D10', borderWidth: 1, borderColor: C.border },
  heroIn: { padding: 16, backgroundColor: 'rgba(14,16,20,0.45)' },
  heroTeam: { alignItems: 'center', flex: 1, gap: 8 },
  heroName: { color: C.text, fontWeight: '600', textAlign: 'center', fontSize: 14 },
  heroScore: { color: C.text, fontFamily: F.display, fontSize: 56, lineHeight: 58 },
  heroScoreSm: { fontSize: 34, lineHeight: 40 },
  scoreSmall: { fontFamily: F.display, fontSize: 20 },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.live },
  action: { flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 16, alignItems: 'center', paddingVertical: 12, gap: 8, minHeight: 84 },
  actionIcon: { width: 40, height: 40, borderRadius: 12, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' },
  laterRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderTopWidth: 1, borderTopColor: C.divider, minHeight: 60 },
  thumb: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center', borderRadius: 10, overflow: 'hidden', backgroundColor: C.card3 },
  snapRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, minHeight: 48, borderTopWidth: 1, borderTopColor: C.divider },
  promo: { marginTop: 20, flexDirection: 'row', alignItems: 'center', backgroundColor: '#2F8F62', borderRadius: 20, overflow: 'hidden' },
  promoImg: { width: 120, height: 120 },
  json: { backgroundColor: C.bg, color: C.text, fontFamily: F.mono, fontSize: 12, borderRadius: 12, borderWidth: 1, borderColor: C.border2, padding: 12, minHeight: 200, maxHeight: 280, textAlignVertical: 'top' },
  day: { width: 56, height: 64, borderRadius: 16, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  daySel: { backgroundColor: C.text, borderColor: C.text },
  dayTop: { fontSize: 10, fontWeight: '600', color: C.faint },
  dayNum: { fontFamily: F.display, fontSize: 22, color: C.text },
  pinImg: { width: 64, height: 64, borderRadius: 12 },
  buy: { backgroundColor: C.lime, borderRadius: 12, paddingHorizontal: 18, minHeight: 44, justifyContent: 'center' },
  tl: { paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.divider },
  tlIcon: { width: 32, height: 32, borderRadius: 16, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' },
  seg: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: C.border2, backgroundColor: C.card, paddingHorizontal: 12 },
  tile: { width: '31.5%', height: 84, borderRadius: 14, borderWidth: 1, borderColor: C.border2, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', gap: 4, padding: 6 },
  tr: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.divider },
  th: { color: C.faint, fontSize: 11, fontWeight: '600', letterSpacing: 0.6 },
  num: { width: 28, textAlign: 'center' },
  bar: { width: 4, height: 18, borderRadius: 2, marginRight: 8, marginLeft: 6 },
});
