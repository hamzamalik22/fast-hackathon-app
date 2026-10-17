// Global chrome from the handoff: top app bar + sync badge, offline banner, toasts, status chips, sync results sheet.
import { useNavigation } from '@react-navigation/native';
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { create } from 'zustand';

import { League } from '../lib/api';
import { db } from '../lib/db';
import { useCart, useNet } from '../lib/state';
import { sportIcon } from '../ui/images';
import { Btn, C, Chip, EmptyState, F, Icon, LOGO, Muted, Pill, Row, Sheet, Text } from '../ui/kit';

// ---------------------------------------------------------------- toasts
type ToastState = { text: string | null; kind: 'ok' | 'warn'; show: (text: string, kind?: 'ok' | 'warn') => void };
export const useToast = create<ToastState>((set) => ({
  text: null, kind: 'ok',
  show: (text, kind = 'ok') => {
    set({ text, kind });
    setTimeout(() => set((st) => (st.text === text ? { text: null } : st)), 2600);
  },
}));
export const toast = (text: string, kind: 'ok' | 'warn' = 'ok') => useToast.getState().show(text, kind);

export function ToastHost() {
  const { text, kind } = useToast();
  if (!text) return null;
  return (
    <View pointerEvents="none" style={[styles.toast, kind === 'warn' && { backgroundColor: C.warn }]} accessibilityLiveRegion="polite">
      <Icon name={kind === 'ok' ? 'check-circle-outline' : 'alert-outline'} size={20} color={kind === 'ok' ? '#2F8F62' : C.onLime} />
      <Text style={{ color: C.onLime, fontWeight: '600', flex: 1 }}>{text}</Text>
    </View>
  );
}

// ---------------------------------------------------------------- sync badge + app bar
export function SyncBar() {
  const { online, syncing, pending, checked } = useNet();
  const nav = useNavigation<any>();
  const open = () => nav.navigate('Sync');
  if (syncing) {
    return (
      <Pressable onPress={open} accessibilityRole="button" accessibilityLabel="Syncing. Open sync status" style={[styles.badge, { backgroundColor: 'rgba(214,255,65,0.12)' }]}>
        <ActivityIndicator size={12} color={C.lime} /><Text style={{ color: C.lime, fontWeight: '600', fontSize: 12 }}>Syncing</Text>
      </Pressable>
    );
  }
  if (online || !checked) {
    return (
      <Pressable onPress={open} accessibilityRole="button" accessibilityLabel={`Online${pending ? `, ${pending} pending` : ''}. Open sync status`} style={[styles.badge, { backgroundColor: C.okBg }]}>
        <Icon name="cloud-check-outline" size={15} color={C.okText} />
        <Text style={{ color: C.okText, fontWeight: '600', fontSize: 12 }} numberOfLines={1}>{pending ? `Online · ${pending}` : 'Online'}</Text>
      </Pressable>
    );
  }
  return (
    <Pressable onPress={open} accessibilityRole="button" accessibilityLabel={`Offline, ${pending} pending. Open sync status`} style={[styles.badge, { backgroundColor: C.warnBg }]}>
      <Icon name="cloud-off-outline" size={15} color={C.warnText} />
      <Text style={{ color: C.warnText, fontWeight: '600', fontSize: 12 }} numberOfLines={1}>{`Offline · ${pending}`}</Text>
    </Pressable>
  );
}

export function AppHeader({ title, canGoBack, onBack, brand, cart }: { title: string; canGoBack?: boolean; onBack?: () => void; brand?: boolean; cart?: boolean }) {
  const insets = useSafeAreaInsets();
  const nav = useNavigation<any>();
  const count = useCart((s) => s.lines.reduce((n, l) => n + l.quantity, 0));
  return (
    <View style={[styles.header, { paddingTop: insets.top + 6 }]}>
      {canGoBack ? (
        <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="Back" hitSlop={8} style={styles.back}>
          <Icon name="arrow-left" size={24} />
        </Pressable>
      ) : null}
      {brand ? (
        <Row gap={10} style={{ flex: 1 }}>
          <Image source={LOGO} style={styles.logo} accessibilityLabel="Alpha League logo" />
          <Text style={styles.brand}>ALPHA LEAGUE</Text>
        </Row>
      ) : <Text style={styles.title} numberOfLines={1}>{title}</Text>}
      {cart ? (
        <Pressable onPress={() => nav.navigate('Cart')} accessibilityRole="button" accessibilityLabel={`Cart, ${count} items`} style={styles.back}>
          <Icon name="shopping-outline" size={22} />
          {count ? <View style={styles.cartBadge}><Text style={{ color: C.onLime, fontSize: 11, fontWeight: '700' }}>{count}</Text></View> : null}
        </Pressable>
      ) : null}
      <SyncBar />
    </View>
  );
}

function hhmm(iso: string | null) {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function latestCacheTime(): string | null {
  return db.getFirstSync<{ t: string | null }>('SELECT max(updated_at) AS t FROM cache')?.t ?? null;
}

export function Screen({ children, onRefresh, refreshing, scroll = true }: {
  children: React.ReactNode; onRefresh?: () => void; refreshing?: boolean; scroll?: boolean;
}) {
  const online = useNet((s) => s.online);
  const checked = useNet((s) => s.checked);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const offline = checked && !online;
  useEffect(() => { if (offline) setSavedAt(latestCacheTime()); }, [offline]);
  return (
    <View style={{ flex: 1, backgroundColor: C.bg }}>
      {offline ? (
        <Row style={styles.banner} gap={10}>
          <Icon name="cloud-off-outline" size={18} color={C.offText} />
          <Text style={{ color: C.offText, flex: 1, fontSize: 13 }}>You’re offline. Showing data saved at {hhmm(savedAt)}.</Text>
        </Row>
      ) : null}
      {scroll ? (
        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled"
          refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={C.lime} colors={[C.onLime]} progressBackgroundColor={C.lime} /> : undefined}>
          {children}
        </ScrollView>
      ) : <View style={[styles.body, { flex: 1 }]}>{children}</View>}
    </View>
  );
}

export function Empty({ title, message, icon }: { title: string; message?: string; icon?: any }) {
  return <EmptyState title={title} message={message} icon={icon} />;
}

export function Stale({ error, onRetry }: { updatedAt?: string | null; error: any; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <Row style={styles.stale} gap={10}>
      <Icon name="alert-circle-outline" size={18} color={C.warnText} />
      <Text style={{ flex: 1, fontSize: 13, color: C.offText }}>{error.message}</Text>
      {onRetry ? <Pressable onPress={onRetry} hitSlop={12} accessibilityRole="button"><Text style={{ color: C.lime, fontWeight: '600' }}>Try again</Text></Pressable> : null}
    </Row>
  );
}

export function LeaguePicker({ leagues, value, onChange }: { leagues: League[] | null; value: string | null; onChange: (id: string) => void }) {
  const ref = useRef<ScrollView>(null);
  if (!leagues?.length) return <Empty title="No leagues yet" message="Leagues you can follow will appear here." icon="trophy-outline" />;
  return (
    <ScrollView ref={ref} horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14, flexGrow: 0 }}>
      {leagues.map((l) => (
        // Keep the selected league visible (it may be off-screen after returning to the screen).
        <View key={l.league_id} onLayout={(e) => { if (l.league_id === value) ref.current?.scrollTo({ x: Math.max(0, e.nativeEvent.layout.x - 16), animated: false }); }}>
          <Chip label={l.name} selected={l.league_id === value} onPress={() => onChange(l.league_id)} icon={sportIcon(l.scoring_model, l.sport_id)} />
        </View>
      ))}
    </ScrollView>
  );
}

export const statusLabel = (st: string) => ({ upcoming: 'Upcoming', in_progress: 'Live', completed: 'FT', postponed: 'Postponed', abandoned: 'Abandoned', cancelled: 'Cancelled' } as Record<string, string>)[st] ?? st;
export function StatusPill({ status, time }: { status: string; time?: string }) {
  if (status === 'in_progress') return <Pill label="LIVE" tone="live" dot />;
  if (status === 'completed') return <Pill label="FULL TIME" tone="neutral" />;
  if (status === 'postponed') return <Pill label="POSTPONED" tone="warn" icon="calendar-remove" />;
  if (status === 'abandoned' || status === 'cancelled') return <Pill label={status.toUpperCase()} tone="err" />;
  return <Pill label={time ?? 'UPCOMING'} tone="neutral" icon="clock-outline" />;
}

const QUAL: Record<string, [string, string, any]> = {
  clinched: ['Clinched', C.okText, 'check-circle'], eliminated: ['Eliminated', C.err, 'cancel'], still_possible: ['Still possible', C.faint, 'timer-sand-empty'],
};
export const qualLabel = (q: string) => QUAL[q]?.[0] ?? q;
export function QualTag({ status }: { status: string }) {
  const [label, color, icon] = QUAL[status] ?? [status, C.faint, 'help-circle-outline'];
  return <Row gap={4}><Icon name={icon} size={14} color={color} /><Text style={{ color, fontSize: 12, fontWeight: '500' }} numberOfLines={1}>{label}</Text></Row>;
}

/** Per-action sync results after an automatic or manual sync. */
export function SyncResultsDialog() {
  const results = useNet((s) => s.lastResults);
  const shown = useNet((s) => s.resultsShown);
  const close = () => useNet.setState({ resultsShown: true });
  return (
    <Sheet visible={!!results && !shown} onClose={close} title="Sync finished"
      actions={<Btn label="Got it" onPress={close} style={{ flex: 1 }} />}>
      <ScrollView style={{ maxHeight: 360 }}>
        {(results ?? []).map((r) => (
          <Row key={r.action_id} style={{ paddingVertical: 10, alignItems: 'flex-start' }} gap={12}>
            <Icon name={r.status === 'rejected' ? 'close-circle' : 'check-circle'} size={22} color={r.status === 'rejected' ? C.err : C.okText} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '600' }}>{r.label}</Text>
              <Muted>{r.status === 'rejected' ? `Not saved. ${r.message}` : r.status === 'duplicate' ? 'Already synced earlier.' : 'Saved on the server.'}</Muted>
            </View>
          </Row>
        ))}
      </ScrollView>
    </Sheet>
  );
}

export const styles = StyleSheet.create({
  header: { backgroundColor: C.bg, paddingHorizontal: 16, paddingBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 10 },
  back: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center', borderRadius: 24, marginLeft: -8 },
  title: { color: C.text, fontSize: 18, fontWeight: '600', flex: 1 },
  logo: { width: 32, height: 32, borderRadius: 9 },
  brand: { color: C.text, fontFamily: F.display, fontSize: 21, letterSpacing: 1.6 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 32, paddingHorizontal: 12, borderRadius: 99 },
  cartBadge: { position: 'absolute', top: 6, right: 6, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  banner: { backgroundColor: C.offSurface, borderBottomWidth: 1, borderColor: C.offBorder, paddingHorizontal: 16, paddingVertical: 10 },
  stale: { backgroundColor: C.offSurface, borderWidth: 1, borderColor: C.offBorder, borderRadius: 12, padding: 12, marginBottom: 12 },
  body: { padding: 16, paddingBottom: 48 },
  toast: { position: 'absolute', left: 16, right: 16, bottom: 100, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.text, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 14, elevation: 12 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', marginBottom: 8 },
  card: { marginBottom: 12 },
});
