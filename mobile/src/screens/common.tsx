// Minimal shared UI (placeholder until the designed UI is dropped in): sync bar, screen wrapper, league picker, chips.
import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { Button, Chip, Dialog, List, Portal, Text } from 'react-native-paper';

import { League } from '../lib/api';
import { timeAgo } from '../lib/hooks';
import { useNet } from '../lib/state';

export function SyncBar() {
  const { online, syncing, pending, checked } = useNet();
  const nav = useNavigation<any>();
  const label = syncing ? 'Syncing…' : online ? 'Online' : checked ? 'Offline – changes are saved on this phone' : 'Checking connection…';
  const icon = syncing ? '⟳' : online ? '●' : '⊘';
  const bg = syncing ? '#E8F0FE' : online ? '#E6F4EA' : '#FDECEA';
  const fg = syncing ? '#0B57D0' : online ? '#1B5E20' : '#8C1D18';
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={`Connection: ${label}. ${pending} pending changes. Open sync status.`}
      onPress={() => nav.navigate('Sync')} style={[styles.bar, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontWeight: '600' }}>{icon} {label}</Text>
      {pending > 0 && <Text style={{ color: fg }}>{pending} pending ›</Text>}
    </Pressable>
  );
}

export function Screen({ children, onRefresh, refreshing, scroll = true }: {
  children: React.ReactNode; onRefresh?: () => void; refreshing?: boolean; scroll?: boolean;
}) {
  return (
    <View style={{ flex: 1, backgroundColor: '#fff' }}>
      <SyncBar />
      {scroll ? (
        <ScrollView contentContainerStyle={styles.body}
          refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} /> : undefined}>
          {children}
        </ScrollView>
      ) : <View style={[styles.body, { flex: 1 }]}>{children}</View>}
    </View>
  );
}

export function Empty({ title, message }: { title: string; message?: string }) {
  return (
    <View style={{ padding: 24, alignItems: 'center' }}>
      <Text variant="titleMedium">{title}</Text>
      {message ? <Text style={{ textAlign: 'center', marginTop: 4 }}>{message}</Text> : null}
    </View>
  );
}

export function Stale({ updatedAt, error, onRetry }: { updatedAt: string | null; error: any; onRetry?: () => void }) {
  if (!error && !updatedAt) return null;
  return (
    <View style={styles.row}>
      <Text variant="bodySmall">{error ? `${error.message} ` : ''}Last updated {timeAgo(updatedAt)}</Text>
      {error && onRetry ? <Button compact onPress={onRetry}>Try again</Button> : null}
    </View>
  );
}

export function LeaguePicker({ leagues, value, onChange }: { leagues: League[] | null; value: string | null; onChange: (id: string) => void }) {
  if (!leagues?.length) return <Empty title="No leagues yet" message="Leagues you can see will appear here." />;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
      {leagues.map((l) => (
        <Chip key={l.league_id} selected={l.league_id === value} onPress={() => onChange(l.league_id)} style={{ marginRight: 8 }}
          accessibilityLabel={`League ${l.name}`}>{l.name}</Chip>
      ))}
    </ScrollView>
  );
}

const STATUS: Record<string, string> = {
  upcoming: '🗓 Upcoming', in_progress: '● Live', completed: '✓ Full time', postponed: '⏸ Postponed',
  abandoned: '✕ Abandoned', cancelled: '✕ Cancelled',
};
export const statusLabel = (s: string) => STATUS[s] ?? s;

const QUAL: Record<string, string> = { clinched: '✓ Clinched', eliminated: '✕ Eliminated', still_possible: '… In contention' };
export const qualLabel = (s: string) => QUAL[s] ?? s;

/** Global dialog with per-action sync results (applied / rejected + plain-language reason). */
export function SyncResultsDialog() {
  const results = useNet((s) => s.lastResults);
  return (
    <Portal>
      <Dialog visible={!!results} onDismiss={() => useNet.setState({ lastResults: null })}>
        <Dialog.Title>Sync finished</Dialog.Title>
        <Dialog.ScrollArea style={{ maxHeight: 360 }}>
          <ScrollView>
            {(results ?? []).map((r) => (
              <List.Item key={r.action_id} title={r.label} description={r.message} descriptionNumberOfLines={3}
                left={() => <Text style={{ alignSelf: 'center', fontSize: 18 }}>{r.status === 'rejected' ? '✕' : '✓'}</Text>} />
            ))}
          </ScrollView>
        </Dialog.ScrollArea>
        <Dialog.Actions><Button onPress={() => useNet.setState({ lastResults: null })}>OK</Button></Dialog.Actions>
      </Dialog>
    </Portal>
  );
}

export const styles = StyleSheet.create({
  bar: { minHeight: 40, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  body: { padding: 16, paddingBottom: 48 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', marginBottom: 8 },
  card: { marginBottom: 12 },
});
