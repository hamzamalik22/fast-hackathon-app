import React, { useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { logout } from '../lib/actions';
import { can, usePending } from '../lib/data';
import { cacheTimes, syncLogClear, syncLogRecent } from '../lib/db';
import { formatWhen, timeAgo } from '../lib/hooks';
import { roleLabel, useNet, useSession } from '../lib/state';
import { flush } from '../lib/sync';
import { Btn, C, Card, Icon, initials, ListRow, Mono, Muted, Pill, Row, Section, Sheet, Text } from '../ui/kit';
import { Screen } from './common';

export function ProfileScreen({ navigation }: any) {
  const { user, tenant } = useSession();
  const pending = useNet((s) => s.pending);
  const [confirm, setConfirm] = useState(false);
  return (
    <Screen>
      <Card>
        <Row gap={14}>
          <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ fontWeight: '700', fontSize: 18 }}>{initials(user?.name ?? '?', 2)}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '700', fontSize: 18 }}>{user?.name}</Text>
            <Mono style={{ fontSize: 12 }}>{user?.email}</Mono>
            <Pill label={roleLabel(user?.role)} tone="lime" style={{ marginTop: 6 }} />
          </View>
        </Row>
      </Card>
      <Card style={{ padding: 0, marginTop: 14 }}>
        {can(user?.role, 'roster') && user?.club_id ? <ListRow icon="account-cog-outline" title="Manage squad" onPress={() => navigation.navigate('Roster', { clubId: user.club_id })} /> : null}
        {can(user?.role, 'score') ? <ListRow icon="pencil-box-outline" title="Scoring entry" subtitle="Open a live match to score it" onPress={() => navigation.navigate('Fixtures')} /> : null}
        {user?.role === 'player' && user.player_id ? <ListRow icon="history" title="My registration history" onPress={() => navigation.navigate('Audit', { playerId: user.player_id, name: user.name })} /> : null}
        {user?.club_id ? <ListRow icon="shield-outline" title={user.role === 'club_manager' ? 'My club' : 'Favourite club'} onPress={() => navigation.navigate('Club', { clubId: user.club_id })} /> : <ListRow icon="shield-outline" title="Clubs" onPress={() => navigation.navigate('Clubs')} />}
        <ListRow icon="receipt" title="Orders & receipts" onPress={() => navigation.navigate('Orders')} />
        <ListRow icon="sync" title="Sync & offline" badge={pending || undefined} onPress={() => navigation.navigate('Sync')} />
        <ListRow icon="dns-outline" title="Server & settings" onPress={() => navigation.navigate('Settings')} />
      </Card>
      <Btn kind="danger" label="Sign out" icon="logout" onPress={() => setConfirm(true)} style={{ marginTop: 16 }} />
      <Muted style={{ textAlign: 'center', marginTop: 12, fontSize: 12 }}>{tenant?.name}</Muted>
      <Sheet visible={confirm} onClose={() => setConfirm(false)} title="Sign out?"
        actions={<><Btn kind="outline" label="Cancel" onPress={() => setConfirm(false)} style={{ flex: 1 }} /><Btn kind="dangerSolid" label="Sign out" onPress={() => { setConfirm(false); void logout(); }} style={{ flex: 1.3 }} /></>}>
        <Muted>{pending ? `${pending} change${pending > 1 ? 's' : ''} haven’t synced yet. They stay on this phone and sync after you sign in again.` : 'You can sign in again at any time.'}</Muted>
      </Sheet>
    </Screen>
  );
}

const CACHE_LABEL: [string, string, any][] = [['fixtures:', 'Fixtures', 'scoreboard-outline'], ['standings:', 'Standings', 'podium'], ['club:', 'Club profiles', 'shield-outline']];

export function SyncScreen() {
  const { online, syncing, lastSync, lastResults } = useNet();
  const pending = usePending();
  const [cleared, setCleared] = useState(0);
  const results = lastResults ?? syncLogRecent(10).map((r) => ({ ...r, processed_order: undefined }));
  return (
    <Screen>
      <Card>
        <Row gap={12}>
          {syncing ? <ActivityIndicator color={C.lime} /> : <Icon name={online ? 'cloud-check-outline' : 'cloud-off-outline'} size={30} color={online ? C.okText : C.warnText} />}
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '700', fontSize: 17 }}>{syncing ? 'Syncing your changes…' : online ? (pending.length ? 'Ready to sync' : 'Everything is synced') : 'You’re offline'}</Text>
            <Muted style={{ fontSize: 13 }}>{syncing ? 'Sending queued actions to the server.' : online ? `Last sync ${timeAgo(lastSync)}.` : 'Changes are saved on this phone and sync automatically when you reconnect.'}</Muted>
          </View>
        </Row>
        <Btn label="Sync now" icon="sync" disabled={!online || syncing || !pending.length} onPress={() => void flush()} style={{ marginTop: 14 }} />
      </Card>

      <Section title={`Waiting to sync · ${pending.length}`} />
      <Card style={{ padding: 0 }}>
        {pending.map((p) => (
          <Row key={p.action_id} style={{ paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.divider }} gap={12}>
            <View style={{ width: 36, height: 36, borderRadius: 10, borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.warn, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="timer-sand" size={18} color={C.warnText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '500' }}>{p.label}</Text>
              <Muted style={{ fontSize: 12 }}>{p.type === 'score_event' ? 'Score event' : 'Roster change'} · saved {formatWhen(p.queued_at)} · base v{p.base_version}</Muted>
            </View>
            <Pill label="Pending" tone="warn" />
          </Row>
        ))}
        {!pending.length ? <Row style={{ padding: 16 }} gap={10}><Icon name="check-all" color={C.okText} /><Text style={{ color: C.okText, fontWeight: '600' }}>All caught up</Text></Row> : null}
      </Card>

      <Section title="Last sync results" action={results.length ? 'Clear' : undefined} onAction={() => { syncLogClear(); useNet.setState({ lastResults: [] }); setCleared(cleared + 1); }} />
      <Card style={{ padding: 0 }}>
        {results.map((r) => (
          <Row key={r.action_id} style={{ paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.divider, alignItems: 'flex-start' }} gap={12}>
            <Icon name={r.status === 'rejected' ? 'close-circle' : 'check-circle'} size={22} color={r.status === 'rejected' ? C.err : C.okText} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '500' }}>{r.label}</Text>
              <Muted style={{ fontSize: 12 }}>{r.status === 'rejected' ? `Rejected: ${r.message}` : r.status === 'duplicate' ? 'Already synced earlier' : 'Applied on the server'}</Muted>
            </View>
            {r.processed_order ? <Mono>#{r.processed_order}</Mono> : null}
          </Row>
        ))}
        {!results.length ? <View style={{ padding: 16 }}><Muted>No sync results yet.</Muted></View> : null}
      </Card>

      <Section title="Saved for offline use" />
      <Card style={{ padding: 0 }}>
        {CACHE_LABEL.map(([prefix, label, icon]) => {
          const times = cacheTimes(prefix);
          return <ListRow key={prefix} icon={icon} title={label} subtitle={times.length ? `${times.length} saved · updated ${timeAgo(times[0].updated_at)}` : 'Not saved yet. Open it once while online.'} />;
        })}
      </Card>
    </Screen>
  );
}
