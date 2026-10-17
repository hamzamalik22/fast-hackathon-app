import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { Button, Card, Dialog, List, Portal, Text, TextInput } from 'react-native-paper';

import * as actions from '../lib/actions';
import { MatchDetail } from '../lib/api';
import { can, useFixtures, useLeagues, useMatch, useSelectedLeague, useStandings } from '../lib/data';
import { formatWhen, humanize } from '../lib/hooks';
import { money, roleLabel, useSession } from '../lib/state';
import { Empty, LeaguePicker, qualLabel, Screen, Stale, statusLabel, styles } from './common';

export function HomeScreen({ navigation }: any) {
  const { user, tenant } = useSession();
  const leagues = useLeagues();
  const [leagueId] = useSelectedLeague(leagues.data);
  const fixtures = useFixtures(leagueId);
  const live = (fixtures.data ?? []).filter((m) => m.status === 'in_progress');
  const next = (fixtures.data ?? []).filter((m) => m.status === 'upcoming').slice(0, 3);
  return (
    <Screen onRefresh={fixtures.refresh} refreshing={fixtures.loading}>
      <Text variant="headlineSmall">Hi, {user?.name}</Text>
      <Text style={{ marginBottom: 16 }}>{roleLabel(user?.role)} · {tenant?.name}</Text>
      {can(user?.role, 'score') && <Text variant="titleMedium">Score a live match</Text>}
      {live.map((m) => (
        <Card key={m.match_id} style={styles.card} onPress={() => navigation.navigate('Match', { matchId: m.match_id })}>
          <Card.Title title={`${m.home.name} ${m.home.score} – ${m.away.score} ${m.away.name}`} subtitle={statusLabel(m.status)} />
        </Card>
      ))}
      {user?.club_id && (
        <Button mode="contained-tonal" style={styles.card} contentStyle={{ height: 48 }} onPress={() => navigation.navigate('Club', { clubId: user.club_id })}>
          {can(user.role, 'roster') ? 'Manage my club roster' : 'My club'}
        </Button>
      )}
      <Text variant="titleMedium" style={{ marginTop: 8 }}>Next matches</Text>
      {next.length ? next.map((m) => (
        <List.Item key={m.match_id} title={`${m.home.name} v ${m.away.name}`} description={formatWhen(m.scheduled_at)}
          onPress={() => navigation.navigate('Match', { matchId: m.match_id })} />
      )) : <Empty title="No upcoming matches" />}
    </Screen>
  );
}

export function FixturesScreen({ navigation }: any) {
  const leagues = useLeagues();
  const [leagueId, setLeague] = useSelectedLeague(leagues.data);
  const fixtures = useFixtures(leagueId);
  return (
    <Screen onRefresh={fixtures.refresh} refreshing={fixtures.loading}>
      <LeaguePicker leagues={leagues.data} value={leagueId} onChange={setLeague} />
      <Stale updatedAt={fixtures.updatedAt} error={fixtures.error} onRetry={fixtures.refresh} />
      {!fixtures.data?.length ? <Empty title="No matches yet" message="Fixtures for this league will appear here." /> : null}
      {fixtures.data?.map((m) => (
        <List.Item key={m.match_id} title={`${m.home.name} ${m.status === 'upcoming' ? 'v' : `${m.home.score} – ${m.away.score}`} ${m.away.name}`}
          description={`${statusLabel(m.status)} · ${formatWhen(m.scheduled_at)}${m.venue ? ` · ${m.venue}` : ''}`}
          onPress={() => navigation.navigate('Match', { matchId: m.match_id })} />
      ))}
    </Screen>
  );
}

function eventText(ev: any, d: MatchDetail): string {
  const team = ev.payload?.team_id === d.home.team_id ? d.home_name : ev.payload?.team_id === d.away.team_id ? d.away_name : '';
  switch (ev.type) {
    case 'score': return `${humanize(ev.payload.event_type)} · ${team}`;
    case 'match_start': return 'Kick-off / match started';
    case 'match_end': return 'Full time';
    case 'discipline': return `Discipline ${ev.payload.points} · ${team}`;
    case 'tiebreak_winner': return `Tie-break won by ${team}`;
    case 'compensation': return `Correction: ${ev.payload.reason ?? 'reversed an event'}`;
    default: return humanize(ev.type);
  }
}

export function MatchScreen({ route, navigation }: any) {
  const { matchId } = route.params;
  const m = useMatch(matchId);
  const user = useSession((s) => s.user);
  const [undo, setUndo] = useState<string | null>(null);
  const [reason, setReason] = useState('Disallowed by referee');
  const d = m.data;
  if (!d) return <Screen><Stale updatedAt={null} error={m.error} onRetry={m.refresh} />{!m.error && <Text>Loading match…</Text>}</Screen>;
  const innings = d.sport.scoring_model === 'innings';
  const canScore = d.can_score || can(user?.role, 'admin');
  const status = m.pending.some((p) => p.body.type === 'match_end') ? 'completed' : m.pending.some((p) => p.body.type === 'match_start') ? 'in_progress' : d.status;
  return (
    <Screen onRefresh={m.refresh} refreshing={m.loading}>
      <Stale updatedAt={m.updatedAt} error={m.error} onRetry={m.refresh} />
      <Card style={styles.card}><Card.Content style={{ alignItems: 'center' }}>
        <Text variant="labelLarge">{statusLabel(status)} · {d.sport.name}</Text>
        <Text variant="titleMedium" style={{ marginTop: 8 }}>{d.home_name}  v  {d.away_name}</Text>
        <Text variant="displayMedium" accessibilityLabel={`Score ${d.home.score} to ${d.away.score}`}>{d.home.score} – {d.away.score}</Text>
        {innings && <Text>{d.home.wickets}/{d.home.overs} ov · {d.away.wickets}/{d.away.overs} ov</Text>}
        <Text variant="bodySmall">{formatWhen(d.scheduled_at)}{d.venue ? ` · ${d.venue}` : ''}</Text>
      </Card.Content></Card>

      {d.pinned_product && (
        <Card style={styles.card} onPress={() => navigation.navigate('Product', { productId: d.pinned_product!.product_id })}>
          <Card.Title title={`Featured: ${d.pinned_product.name}`} subtitle={`From ${money(d.pinned_product.price_minor)} · Tap to buy`} />
        </Card>
      )}

      {canScore && (
        <Card style={styles.card}><Card.Title title="Scoring" subtitle="Works offline – queued and synced automatically" />
          <Card.Content>
            {status === 'upcoming' && <Button mode="contained" onPress={() => actions.startMatch(d)}>Start match</Button>}
            {status === 'in_progress' && (
              <>
                {[d.home, d.away].map((side) => (
                  <View key={side.team_id} style={{ marginBottom: 8 }}>
                    <Text variant="labelLarge">{side.team_id === d.home.team_id ? d.home_name : d.away_name}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
                      {Object.keys(d.sport.scoring_events).map((et) => (
                        <Button key={et} mode="outlined" compact style={{ margin: 4 }} onPress={() => actions.scoreEvent(d, side.team_id, et)}>{humanize(et)}</Button>
                      ))}
                    </View>
                  </View>
                ))}
                <Button mode="contained-tonal" onPress={() => actions.endMatch(d)}>End match</Button>
              </>
            )}
          </Card.Content>
        </Card>
      )}

      <Text variant="titleMedium">Timeline</Text>
      {m.pending.map((p) => (
        <List.Item key={p.action_id} title={p.label} description="⏳ Waiting to sync" />
      ))}
      {[...d.events].reverse().map((ev) => (
        <List.Item key={ev.event_id} title={eventText(ev, d)}
          titleStyle={ev.compensated ? { textDecorationLine: 'line-through' } : undefined}
          description={ev.compensated ? 'Reversed by a correction' : `#${ev.sequence}`}
          right={() => canScore && !ev.compensated && ['score', 'discipline', 'tiebreak_winner'].includes(ev.type)
            ? <Button compact onPress={() => setUndo(ev.event_id)}>Correct</Button> : null} />
      ))}
      {!d.events.length && !m.pending.length && <Empty title="No events yet" />}

      <Portal>
        <Dialog visible={!!undo} onDismiss={() => setUndo(null)}>
          <Dialog.Title>Reverse this event?</Dialog.Title>
          <Dialog.Content>
            <Text>A correction is added to the match log; the original stays visible as reversed.</Text>
            <TextInput label="Reason" value={reason} onChangeText={setReason} style={{ marginTop: 8 }} />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setUndo(null)}>Cancel</Button>
            <Button onPress={() => { actions.compensate(d, undo!, reason); setUndo(null); }}>Reverse</Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </Screen>
  );
}

export function StandingsScreen({ navigation }: any) {
  const leagues = useLeagues();
  const [leagueId, setLeague] = useSelectedLeague(leagues.data);
  const st = useStandings(leagueId);
  const cols = ['P', 'W', 'D', 'L', 'Diff', 'Pts'];
  return (
    <Screen onRefresh={st.refresh} refreshing={st.loading}>
      <LeaguePicker leagues={leagues.data} value={leagueId} onChange={setLeague} />
      <Stale updatedAt={st.updatedAt} error={st.error} onRetry={st.refresh} />
      {st.data && <Text variant="bodySmall" style={{ marginBottom: 8 }}>Top {st.data.qualification_spots} qualify for the playoffs.</Text>}
      <ScrollView horizontal>
        <View>
          <View style={{ flexDirection: 'row', paddingVertical: 8 }}>
            <Text style={{ width: 170, fontWeight: '700' }}>#  Team</Text>
            {cols.map((c) => <Text key={c} style={{ width: 48, fontWeight: '700', textAlign: 'center' }}>{c}</Text>)}
            <Text style={{ width: 130, fontWeight: '700' }}>Status</Text>
          </View>
          {st.data?.table.map((r) => (
            <List.Item key={r.team_id} style={{ paddingHorizontal: 0 }} onPress={() => navigation.navigate('Club', { clubId: r.team_id })}
              title={() => (
                <View style={{ flexDirection: 'row' }}>
                  <Text style={{ width: 170 }} numberOfLines={1}>{r.rank}. {st.data!.team_names[r.team_id] ?? r.team_id}</Text>
                  {[r.played, r.won, r.drawn, r.lost, r.diff, r.points].map((v, i) => (
                    <Text key={i} style={{ width: 48, textAlign: 'center', fontWeight: i === 5 ? '700' : '400' }}>{v}</Text>
                  ))}
                  <Text style={{ width: 130 }}>{qualLabel(r.status)}</Text>
                </View>
              )} />
          ))}
        </View>
      </ScrollView>
      {st.data && !st.data.table.length && <Empty title="No standings yet" />}
    </Screen>
  );
}
