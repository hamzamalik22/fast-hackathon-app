import React, { useState } from 'react';
import { Linking, View } from 'react-native';
import { Button, Card, Dialog, HelperText, List, Portal, SegmentedButtons, Text, TextInput } from 'react-native-paper';

import * as actions from '../lib/actions';
import { ApiError } from '../lib/api';
import { can, useClub, useClubs, usePending, usePlayerHistory } from '../lib/data';
import { humanize } from '../lib/hooks';
import { useSession } from '../lib/state';
import { Empty, Screen, Stale, styles } from './common';

export function ClubsScreen({ navigation }: any) {
  const clubs = useClubs();
  return (
    <Screen onRefresh={clubs.refresh} refreshing={clubs.loading}>
      {clubs.data?.map((c) => <List.Item key={c.club_id} title={c.name} onPress={() => navigation.navigate('Club', { clubId: c.club_id })} />)}
      {!clubs.data?.length && <Empty title="No clubs yet" />}
    </Screen>
  );
}

export function ClubScreen({ route, navigation }: any) {
  const { clubId } = route.params;
  const club = useClub(clubId);
  const user = useSession((s) => s.user);
  const pending = usePending();
  const [adding, setAdding] = useState(false);
  const c = club.data;
  if (!c) return <Screen><Stale updatedAt={null} error={club.error} onRetry={club.refresh} />{!club.error && <Text>Loading club…</Text>}</Screen>;
  const manages = can(user?.role, 'roster') && (user?.role === 'super_admin' || user?.club_id === c.club_id);
  return (
    <Screen onRefresh={club.refresh} refreshing={club.loading}>
      <Stale updatedAt={club.updatedAt} error={club.error} onRetry={club.refresh} />
      <Text variant="headlineSmall">{c.name}</Text>
      <List.Item title={c.venue.name ?? 'Home venue'} description={c.venue.lat != null ? `${c.venue.lat}, ${c.venue.lng} · Open in Maps` : undefined}
        left={(p) => <List.Icon {...p} icon="map-marker" />}
        onPress={() => c.venue.lat != null && Linking.openURL(`geo:${c.venue.lat},${c.venue.lng}?q=${c.venue.lat},${c.venue.lng}(${encodeURIComponent(c.venue.name ?? c.name)})`)} />
      <Text>{Object.entries(c.socials).map(([k, v]) => `${k}: ${v}`).join('  ·  ')}</Text>
      <Text variant="titleMedium" style={{ marginTop: 12 }}>Staff</Text>
      {c.staff.map((s) => <List.Item key={s.role} title={s.name} description={humanize(s.role)} />)}
      <Text variant="titleMedium">Season record</Text>
      {c.stats.map((s) => <Text key={s.season}>{s.season}: P{s.played} W{s.won} D{s.drawn} L{s.lost}</Text>)}
      <View style={[styles.row, { marginTop: 12 }]}>
        <Text variant="titleMedium">Roster ({c.roster.length})</Text>
        {manages && <Button icon="account-plus" onPress={() => setAdding(true)}>Add player</Button>}
      </View>
      {c.roster.map((p) => {
        const waiting = pending.filter((x) => x.ref === `player:${p.player_id}`);
        return (
          <List.Item key={p.player_id} title={`${p.name} · ${p.position.toUpperCase()}`}
            description={[p.role ? humanize(p.role) : null, p.registration_type === 'loan' ? `On loan until ${p.loan_end_date}` : null,
              waiting.length ? `⏳ ${waiting[0].label} – waiting to sync` : null].filter(Boolean).join(' · ')}
            onPress={manages ? () => navigation.navigate('PlayerAction', { clubId: c.club_id, playerId: p.player_id }) : undefined}
            right={manages ? (pr) => <List.Icon {...pr} icon="chevron-right" /> : undefined} />
        );
      })}
      {!c.roster.length && <Empty title="No players yet" />}
      <AddPlayerDialog visible={adding} clubId={c.club_id} onDone={() => { setAdding(false); void club.refresh(); }} />
    </Screen>
  );
}

function AddPlayerDialog({ visible, clubId, onDone }: { visible: boolean; clubId: string; onDone: () => void }) {
  const [name, setName] = useState('');
  const [position, setPosition] = useState('mf');
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      await actions.addPlayer(clubId, name, position);
      setName('');
      setError(null);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not add the player.');
    }
  };
  return (
    <Portal><Dialog visible={visible} onDismiss={onDone}>
      <Dialog.Title>Add player</Dialog.Title>
      <Dialog.Content>
        <TextInput label="Full name" value={name} onChangeText={setName} />
        <TextInput label="Position (gk, df, mf, fw)" value={position} onChangeText={setPosition} autoCapitalize="none" style={{ marginTop: 8 }} />
        <HelperText type="error" visible={!!error}>{error}</HelperText>
      </Dialog.Content>
      <Dialog.Actions><Button onPress={onDone}>Cancel</Button><Button disabled={!name.trim()} onPress={save}>Add</Button></Dialog.Actions>
    </Dialog></Portal>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

export function PlayerActionScreen({ route, navigation }: any) {
  const { clubId, playerId } = route.params;
  const club = useClub(clubId);
  const history = usePlayerHistory(playerId);
  const [type, setType] = useState<'transfer' | 'loan' | 'release'>('transfer');
  const [to, setTo] = useState<string | null>(null);
  const [eff, setEff] = useState(today());
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const [confirm, setConfirm] = useState(false);
  const c = club.data;
  const p = c?.roster.find((x) => x.player_id === playerId);
  if (!c || !p) return <Screen><Empty title="Player not found" message="Go back and refresh the club roster." /></Screen>;
  const others = c.squads.filter((s) => s.squad_id !== p.squad_id);
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(eff) && (type === 'release' || !!to) && (type !== 'loan' || /^\d{4}-\d{2}-\d{2}$/.test(end));
  return (
    <Screen>
      <Text variant="headlineSmall">{p.name}</Text>
      <Text style={{ marginBottom: 12 }}>{p.position.toUpperCase()} · {p.role ? humanize(p.role) : 'No role'}</Text>
      <SegmentedButtons value={type} onValueChange={(v) => setType(v as any)}
        buttons={[{ value: 'transfer', label: 'Transfer' }, { value: 'loan', label: 'Loan' }, { value: 'release', label: 'Release' }]} />
      {type !== 'release' && (
        <>
          <Text variant="labelLarge" style={{ marginTop: 12 }}>Destination squad</Text>
          {others.map((s) => (
            <List.Item key={s.squad_id} title={s.name} onPress={() => setTo(s.squad_id)}
              left={(pr) => <List.Icon {...pr} icon={to === s.squad_id ? 'radiobox-marked' : 'radiobox-blank'} />} />
          ))}
        </>
      )}
      <TextInput label="Effective date (YYYY-MM-DD)" value={eff} onChangeText={setEff} style={{ marginTop: 8 }} />
      {type === 'loan' && <TextInput label="Loan end date (YYYY-MM-DD)" value={end} onChangeText={setEnd} style={{ marginTop: 8 }} />}
      <TextInput label="Reason" value={reason} onChangeText={setReason} style={{ marginTop: 8 }} />
      <Button mode="contained" disabled={!valid} style={{ marginTop: 16 }} contentStyle={{ height: 48 }} onPress={() => setConfirm(true)}>
        {humanize(type)} player
      </Button>
      <Text variant="bodySmall" style={{ marginTop: 4 }}>Works offline: the change is queued and synced automatically.</Text>

      <Card style={{ marginTop: 24 }}><Card.Title title="History (audit trail)" />
        <Card.Content>
          {history.data?.history.map((h) => (
            <Text key={h.audit_id} style={{ marginBottom: 4 }}>{h.effective_date} · {humanize(h.action)} {h.from_squad_id ?? ''} → {h.to_squad_id ?? '—'} · by {h.who}</Text>
          ))}
          {!history.data?.history.length && <Text>No changes recorded yet.</Text>}
        </Card.Content>
      </Card>

      <Portal><Dialog visible={confirm} onDismiss={() => setConfirm(false)}>
        <Dialog.Title>Confirm {type}</Dialog.Title>
        <Dialog.Content><Text>{type === 'release' ? `Release ${p.name} from the club?` : `${humanize(type)} ${p.name} to ${others.find((s) => s.squad_id === to)?.name}?`}</Text></Dialog.Content>
        <Dialog.Actions>
          <Button onPress={() => setConfirm(false)}>Cancel</Button>
          <Button onPress={() => {
            actions.queueRosterAction({ club: c, player: p, type, toSquadId: to, effectiveDate: eff, loanEndDate: end || null, reason });
            setConfirm(false);
            navigation.goBack();
          }}>Confirm</Button>
        </Dialog.Actions>
      </Dialog></Portal>
    </Screen>
  );
}
