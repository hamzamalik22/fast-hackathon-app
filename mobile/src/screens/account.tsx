import React, { useState } from 'react';
import { Button, Card, Dialog, List, Portal, Text } from 'react-native-paper';

import { logout } from '../lib/actions';
import { usePending, useSyncLog } from '../lib/data';
import { formatWhen, timeAgo } from '../lib/hooks';
import { roleLabel, useNet, useSession } from '../lib/state';
import { flush } from '../lib/sync';
import { Empty, Screen } from './common';

export function ProfileScreen({ navigation }: any) {
  const { user, tenant } = useSession();
  const pending = useNet((s) => s.pending);
  const [confirm, setConfirm] = useState(false);
  return (
    <Screen>
      <Text variant="headlineSmall">{user?.name}</Text>
      <Text>{user?.email}</Text>
      <Text style={{ marginBottom: 12 }}>{roleLabel(user?.role)} · {tenant?.name}</Text>
      {user?.club_id && <List.Item title="My club" left={(p) => <List.Icon {...p} icon="shield-account" />} onPress={() => navigation.navigate('Club', { clubId: user.club_id })} />}
      <List.Item title="All clubs" left={(p) => <List.Icon {...p} icon="account-group" />} onPress={() => navigation.navigate('Clubs')} />
      <List.Item title="My orders" left={(p) => <List.Icon {...p} icon="receipt" />} onPress={() => navigation.navigate('Orders')} />
      <List.Item title="Sync status" description={`${pending} pending`} left={(p) => <List.Icon {...p} icon="sync" />} onPress={() => navigation.navigate('Sync')} />
      <List.Item title="Server settings" left={(p) => <List.Icon {...p} icon="cog" />} onPress={() => navigation.navigate('Settings')} />
      <Button mode="outlined" style={{ marginTop: 16 }} onPress={() => setConfirm(true)}>Sign out</Button>
      <Portal><Dialog visible={confirm} onDismiss={() => setConfirm(false)}>
        <Dialog.Title>Sign out?</Dialog.Title>
        <Dialog.Content><Text>{pending ? `You have ${pending} change(s) not synced yet. They stay on this phone and sync after you sign in again.` : 'You can sign in again any time.'}</Text></Dialog.Content>
        <Dialog.Actions><Button onPress={() => setConfirm(false)}>Cancel</Button><Button onPress={() => { setConfirm(false); void logout(); }}>Sign out</Button></Dialog.Actions>
      </Dialog></Portal>
    </Screen>
  );
}

export function SyncScreen() {
  const { online, syncing, lastSync } = useNet();
  const pending = usePending();
  const log = useSyncLog();
  return (
    <Screen>
      <Card style={{ marginBottom: 12 }}><Card.Content>
        <Text variant="titleMedium">{syncing ? '⟳ Syncing…' : online ? '● Online' : '⊘ Offline'}</Text>
        <Text>Last sync: {timeAgo(lastSync)}</Text>
        <Button mode="contained" style={{ marginTop: 8 }} disabled={!online || syncing || !pending.length} onPress={() => void flush()}>Sync now</Button>
      </Card.Content></Card>
      <Text variant="titleMedium">Waiting to sync ({pending.length})</Text>
      {pending.map((p) => <List.Item key={p.action_id} title={p.label} description={`⏳ Pending · queued ${formatWhen(p.queued_at)}`} />)}
      {!pending.length && <Empty title="No pending changes" message="Changes you make offline will wait here." />}
      <Text variant="titleMedium" style={{ marginTop: 12 }}>Recent results</Text>
      {log.map((r) => (
        <List.Item key={r.action_id + r.processed_at} title={`${r.status === 'rejected' ? '✕ Rejected' : r.status === 'duplicate' ? '✓ Already synced' : '✓ Applied'} · ${r.label}`}
          description={r.message} descriptionNumberOfLines={3} />
      ))}
    </Screen>
  );
}
