import React, { useState } from 'react';
import { Image, Linking, Pressable, StyleSheet, TextInput, View } from 'react-native';

import * as actions from '../lib/actions';
import { ApiError, Club, RosterPlayer } from '../lib/api';
import { can, useClub, useClubs, usePending, usePlayerHistory } from '../lib/data';
import { humanize } from '../lib/hooks';
import { useNet, useSession } from '../lib/state';
import { sendNow } from '../lib/sync';
import { clubBadge, staffPhoto } from '../ui/images';
import { Btn, C, Caps, Card, Chip, clubColor, Display, EmptyState, F, Icon, initials, ListRow, Mono, Muted, Pill, Row, Score, Section, Sheet, TeamBadge, Text } from '../ui/kit';
import { Empty, Screen, Stale, toast } from './common';

const POS: Record<string, string> = { gk: 'Goalkeepers', df: 'Defenders', mf: 'Midfielders', fw: 'Forwards' };
const ROLE_ORDER = ['captain', 'vice_captain', 'starter', 'substitute'];

export function ClubsScreen({ navigation }: any) {
  const clubs = useClubs();
  return (
    <Screen onRefresh={clubs.refresh} refreshing={clubs.loading}>
      <Card style={{ padding: 0 }}>
        {clubs.data?.map((c) => (
          <Pressable key={c.club_id} style={st.clubRow} onPress={() => navigation.navigate('Club', { clubId: c.club_id })} accessibilityRole="button">
            <TeamBadge name={c.name} source={clubBadge(c.club_id)} size={36} />
            <Text style={{ flex: 1, fontWeight: '600' }}>{c.name}</Text><Icon name="chevron-right" color={C.dim} />
          </Pressable>
        ))}
      </Card>
      {!clubs.data?.length ? <Empty title="No clubs yet" icon="shield-outline" /> : null}
    </Screen>
  );
}

function Avatar({ p, size = 36 }: { p: RosterPlayer; size?: number }) {
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ fontFamily: F.display, fontSize: size * 0.42, color: C.text2 }}>{initials(p.name, 2)}</Text>
    </View>
  );
}

function grouped(roster: RosterPlayer[]) {
  const g: Record<string, RosterPlayer[]> = {};
  roster.forEach((p) => { (g[p.position] = g[p.position] || []).push(p); });
  Object.values(g).forEach((list) => list.sort((a, b) => ROLE_ORDER.indexOf(a.role ?? 'substitute') - ROLE_ORDER.indexOf(b.role ?? 'substitute')));
  return Object.entries(g).sort(([a], [b]) => Object.keys(POS).indexOf(a) - Object.keys(POS).indexOf(b));
}

export function ClubScreen({ route, navigation }: any) {
  const { clubId } = route.params;
  const club = useClub(clubId);
  const user = useSession((s) => s.user);
  const [tab, setTab] = useState<'overview' | 'squad' | 'staff' | 'history'>('overview');
  const c = club.data;
  if (!c) return <Screen><Stale error={club.error} onRetry={club.refresh} />{!club.error ? <Muted>Loading club…</Muted> : null}</Screen>;
  const color = clubColor(c.name);
  const manages = can(user?.role, 'roster') && (user?.role === 'super_admin' || user?.club_id === c.club_id);
  return (
    <Screen onRefresh={club.refresh} refreshing={club.loading}>
      <Stale error={club.error} onRetry={club.refresh} />
      <View style={[st.hero, { backgroundColor: color }]}>
        <Row gap={14}>
          <View style={st.heroBadge}><TeamBadge name={c.name} source={clubBadge(c.club_id)} size={60} /></View>
          <View style={{ flex: 1 }}><Display style={{ fontSize: 30 }}>{c.name}</Display><Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: 13 }}>{c.venue.name ?? 'Home venue'} · {c.tenant_id}</Text></View>
        </Row>
        <Row style={{ marginTop: 16 }}>
          {[[c.roster.length, 'Players'], [c.staff.length, 'Staff'], [c.stats[0] ? `${c.stats[0].won}-${c.stats[0].drawn}-${c.stats[0].lost}` : '—', `Season ${c.stats[0]?.season ?? ''}`]].map(([v, l]) => (
            <View key={String(l)} style={{ flex: 1 }}><Score>{v as any}</Score><Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: 12 }}>{l as string}</Text></View>
          ))}
        </Row>
      </View>
      {manages ? <Btn label="Manage squad" icon="account-cog-outline" onPress={() => navigation.navigate('Roster', { clubId: c.club_id })} style={{ marginTop: 14 }} /> : null}
      <Row gap={6} style={st.tabs}>
        {(['overview', 'squad', 'staff', 'history'] as const).map((t) => (
          <Pressable key={t} onPress={() => setTab(t)} style={[st.tab, tab === t && { backgroundColor: C.text }]} accessibilityRole="tab" accessibilityState={{ selected: tab === t }}>
            <Text style={{ fontSize: 13, fontWeight: '600', color: tab === t ? C.onLime : C.text2 }}>{humanize(t)}</Text>
          </Pressable>
        ))}
      </Row>
      {tab === 'overview' ? (
        <Card style={{ padding: 0 }}>
          <ListRow icon="stadium-variant" title={c.venue.name ?? 'Home venue'} subtitle="Home venue" />
          <ListRow icon="map-marker-outline" title={c.venue.lat != null ? `${c.venue.lat}, ${c.venue.lng}` : 'Not set'} subtitle="Coordinates · tap to open in Maps"
            onPress={() => c.venue.lat != null && Linking.openURL(`geo:${c.venue.lat},${c.venue.lng}?q=${c.venue.lat},${c.venue.lng}(${encodeURIComponent(c.venue.name ?? c.name)})`)} />
          {Object.entries(c.socials).map(([k, v]) => <ListRow key={k} icon={k === 'x' ? 'twitter' : k === 'instagram' ? 'instagram' : 'facebook'} title={v} subtitle={humanize(k)} />)}
        </Card>
      ) : null}
      {tab === 'squad' ? grouped(c.roster).map(([pos, list]) => (
        <View key={pos} style={{ marginBottom: 12 }}>
          <Caps style={{ marginBottom: 8 }}>{POS[pos] ?? pos.toUpperCase()} · {list.length}</Caps>
          <Card style={{ padding: 0 }}>
            {list.map((p) => (
              <Row key={p.player_id} style={st.clubRow} gap={12}>
                <Avatar p={p} />
                <View style={{ flex: 1 }}><Text style={{ fontWeight: '500' }}>{p.name}</Text><Muted style={{ fontSize: 12 }}>{p.role ? humanize(p.role) : 'Squad'}{p.registration_type === 'loan' ? ' · On loan' : ''}</Muted></View>
                {p.role === 'captain' ? <Pill label="C" tone="lime" /> : null}
              </Row>
            ))}
          </Card>
        </View>
      )) : null}
      {tab === 'staff' ? (
        <Card style={{ padding: 0 }}>
          {c.staff.map((s) => (
            <Row key={s.role} style={st.clubRow} gap={12}>
              {staffPhoto(s.role) ? <Image source={staffPhoto(s.role)!} style={{ width: 44, height: 44, borderRadius: 22 }} /> : (
                <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' }}><Text style={{ fontWeight: '700' }}>{initials(s.name, 2)}</Text></View>
              )}
              <View style={{ flex: 1 }}><Text style={{ fontWeight: '500' }}>{s.name}</Text><Muted style={{ fontSize: 12 }}>{humanize(s.role)}</Muted></View>
            </Row>
          ))}
        </Card>
      ) : null}
      {tab === 'history' ? (
        <Card style={{ padding: 0 }}>
          {c.stats.map((s) => (
            <Row key={s.season} style={st.clubRow} gap={12}>
              <Mono style={{ color: C.text, width: 44 }}>{s.season}</Mono>
              <Text style={{ flex: 1 }}>Played {s.played} · Won {s.won} · Drawn {s.drawn} · Lost {s.lost}</Text>
            </Row>
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}

export function RosterScreen({ route, navigation }: any) {
  const { clubId, intent } = route.params ?? {};
  const club = useClub(clubId);
  const pending = usePending();
  const [sheet, setSheet] = useState<RosterPlayer | null>(null);
  const [adding, setAdding] = useState(intent === 'add');
  const c = club.data;
  if (!c) return <Screen><Stale error={club.error} onRetry={club.refresh} /></Screen>;
  const gks = c.roster.filter((p) => p.position === 'gk').length;
  const pick = (p: RosterPlayer) => {
    if (intent && intent !== 'add') navigation.navigate('PlayerAction', { clubId, playerId: p.player_id, type: intent });
    else setSheet(p);
  };
  return (
    <Screen onRefresh={club.refresh} refreshing={club.loading}>
      <Row gap={10}>
        <Card style={{ flex: 1 }}><Score>{c.roster.length}<Text style={{ fontFamily: F.display, fontSize: 18, color: C.dim }}>/25</Text></Score><Muted style={{ fontSize: 12 }}>Squad size</Muted></Card>
        <Card style={{ flex: 1 }}><Score style={{ color: gks >= 1 ? C.text : C.err }}>{gks}</Score><Muted style={{ fontSize: 12 }}>Goalkeepers (min 1)</Muted></Card>
      </Row>
      {intent && intent !== 'add' ? (
        <Row style={st.hint} gap={10}><Icon name="gesture-tap" color={C.lime} /><Text style={{ flex: 1, fontSize: 13 }}>Choose a player to {intent === 'loan' ? 'loan out' : intent}.</Text></Row>
      ) : null}
      <Btn kind="outline" label="Add player" icon="account-plus-outline" onPress={() => setAdding(true)} style={{ marginTop: 12 }} />
      {grouped(c.roster).map(([pos, list]) => (
        <View key={pos} style={{ marginTop: 16 }}>
          <Caps style={{ marginBottom: 8 }}>{POS[pos] ?? pos.toUpperCase()} · {list.length}</Caps>
          <Card style={{ padding: 0 }}>
            {list.map((p) => {
              const waiting = pending.filter((x) => x.ref === `player:${p.player_id}`);
              return (
                <Pressable key={p.player_id} style={st.clubRow} onPress={() => pick(p)} accessibilityRole="button" accessibilityLabel={`${p.name}, ${p.role ?? ''}`}>
                  <Avatar p={p} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '500' }}>{p.name}</Text>
                    {waiting.length ? <Text style={{ color: C.warnText, fontSize: 12 }}>⏳ {waiting[0].label} · pending</Text>
                      : <Muted style={{ fontSize: 12 }}>{p.role ? humanize(p.role) : 'Squad'}{p.registration_type === 'loan' ? ` · On loan until ${p.loan_end_date}` : ''}</Muted>}
                  </View>
                  <Icon name="chevron-right" color={C.dim} />
                </Pressable>
              );
            })}
          </Card>
        </View>
      ))}
      <Sheet visible={!!sheet} onClose={() => setSheet(null)} title={sheet?.name}>
        {sheet?.registration_type === 'loan' ? (
          <Row style={[st.hint, { backgroundColor: C.infoBg, borderColor: C.info }]} gap={10}><Icon name="information-outline" color={C.infoText} />
            <Text style={{ color: C.infoText, flex: 1, fontSize: 13 }}>On loan until {sheet.loan_end_date}. Loaned players can’t be moved until the loan ends.</Text></Row>
        ) : null}
        <View style={{ marginHorizontal: -20 }}>
          {sheet && sheet.registration_type !== 'loan' ? <ListRow icon="swap-horizontal" title="Transfer" subtitle="Move permanently to another club" onPress={() => { const p = sheet; setSheet(null); navigation.navigate('PlayerAction', { clubId, playerId: p.player_id, type: 'transfer' }); }} /> : null}
          {sheet && sheet.registration_type !== 'loan' ? <ListRow icon="calendar-arrow-right" title="Loan out" subtitle="Lend for a set period, returns automatically" onPress={() => { const p = sheet; setSheet(null); navigation.navigate('PlayerAction', { clubId, playerId: p.player_id, type: 'loan' }); }} /> : null}
          <ListRow icon="history" title="View audit trail" subtitle="Every change, who made it and why" onPress={() => { const p = sheet!; setSheet(null); navigation.navigate('Audit', { playerId: p.player_id, name: p.name }); }} />
          {sheet && sheet.registration_type !== 'loan' ? <ListRow icon="account-remove-outline" title="Release" danger subtitle="Remove from the club" onPress={() => { const p = sheet; setSheet(null); navigation.navigate('PlayerAction', { clubId, playerId: p.player_id, type: 'release' }); }} /> : null}
        </View>
      </Sheet>
      <AddPlayerSheet visible={adding} clubId={c.club_id} onDone={(changed) => { setAdding(false); if (changed) void club.refresh(); }} />
    </Screen>
  );
}

function AddPlayerSheet({ visible, clubId, onDone }: { visible: boolean; clubId: string; onDone: (changed: boolean) => void }) {
  const [name, setName] = useState('');
  const [position, setPosition] = useState('mf');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const online = useNet((s) => s.online);
  const save = async () => {
    if (!name.trim()) { setError('Enter the player’s full name.'); return; }
    setBusy(true);
    try {
      await actions.addPlayer(clubId, name.trim(), position);
      toast(`${name.trim()} added to the squad`);
      setName(''); setError(null); onDone(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t add the player. Try again.');
    } finally { setBusy(false); }
  };
  return (
    <Sheet visible={visible} onClose={() => onDone(false)} title="Add player"
      actions={<><Btn kind="outline" label="Cancel" onPress={() => onDone(false)} style={{ flex: 1 }} /><Btn label="Add player" loading={busy} disabled={!online} onPress={save} style={{ flex: 1.3 }} /></>}>
      <Text style={st.label}>Full name</Text>
      <TextInput value={name} onChangeText={(t) => { setName(t); setError(null); }} placeholder="e.g. Ahmed Raza" placeholderTextColor={C.dim} style={st.input} accessibilityLabel="Full name" />
      <Text style={[st.label, { marginTop: 14 }]}>Position</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 8 }}>
        {Object.entries(POS).map(([k, l]) => <Chip key={k} label={l.slice(0, -1)} selected={position === k} onPress={() => setPosition(k)} />)}
      </View>
      {error ? <Row gap={6} style={{ marginTop: 10 }}><Icon name="alert-circle" size={16} color={C.err} /><Text style={{ color: C.err, fontSize: 13 }}>{error}</Text></Row> : null}
      {!online ? <Muted style={{ marginTop: 10, fontSize: 12 }}>Adding a new player needs a connection.</Muted> : null}
    </Sheet>
  );
}

const today = () => {
  const d = new Date(); // local date: the transfer window is judged on the club's calendar day
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function PlayerActionScreen({ route, navigation }: any) {
  const { clubId, playerId } = route.params;
  const club = useClub(clubId);
  const online = useNet((s) => s.online);
  const [type, setType] = useState<'transfer' | 'loan' | 'release'>(route.params.type ?? 'transfer');
  const [to, setTo] = useState<string | null>(null);
  const [eff, setEff] = useState(today());
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [rule, setRule] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const c: Club | null = club.data;
  const p = c?.roster.find((x) => x.player_id === playerId);
  if (!c || !p) return <Screen><Empty title="Player not found" message="Go back and refresh the squad." icon="account-question-outline" /></Screen>;
  const others = c.squads.filter((s) => s.squad_id !== p.squad_id);
  const destName = others.find((s) => s.squad_id === to)?.name;

  const validate = () => {
    const e: Record<string, string> = {};
    if (type !== 'release' && !to) e.to = 'Choose the club the player is moving to.';
    if (!DATE.test(eff)) e.eff = 'Use the format YYYY-MM-DD, for example 2026-10-17.';
    if (type === 'loan' && !DATE.test(end)) e.end = 'Enter when the loan ends (YYYY-MM-DD).';
    if (type === 'loan' && DATE.test(end) && end <= eff) e.end = 'The loan must end after it starts.';
    if (!reason.trim()) e.reason = 'Add a short reason. It’s saved in the audit trail.';
    setErrors(e);
    return !Object.keys(e).length;
  };
  const submit = async () => {
    setConfirm(false);
    setBusy(true);
    const row = actions.queueRosterAction({ club: c, player: p, type, toSquadId: to, effectiveDate: eff, loanEndDate: end || null, reason: reason.trim() });
    const result = await sendNow(row.action_id);
    setBusy(false);
    if (!result) { toast('Saved on this phone. It will sync when you’re back online.', 'warn'); navigation.goBack(); return; }
    if (result.status === 'rejected') { setRule(result.message); return; }
    toast(type === 'release' ? `${p.name} released` : `${p.name} ${type === 'loan' ? 'loaned' : 'transferred'} to ${destName}`);
    navigation.goBack();
  };

  return (
    <Screen>
      <Card>
        <Row gap={12}>
          <Avatar p={p} size={48} />
          <View style={{ flex: 1 }}><Text style={{ fontWeight: '700', fontSize: 17 }}>{p.name}</Text><Muted style={{ fontSize: 12 }}>{p.position.toUpperCase()} · {p.role ? humanize(p.role) : 'Squad'} · {c.name}</Muted></View>
        </Row>
      </Card>
      <Row gap={6} style={[st.tabs, { marginTop: 14 }]}>
        {(['transfer', 'loan', 'release'] as const).map((t) => (
          <Pressable key={t} onPress={() => { setType(t); setRule(null); setErrors({}); }} style={[st.tab, type === t && { backgroundColor: t === 'release' ? C.live : C.text }]} accessibilityRole="tab" accessibilityState={{ selected: type === t }}>
            <Text style={{ fontSize: 14, fontWeight: '600', color: type === t ? (t === 'release' ? '#fff' : C.onLime) : C.text2 }}>{humanize(t)}</Text>
          </Pressable>
        ))}
      </Row>
      {rule ? (
        <View style={st.rule}>
          <Row gap={8}><Icon name="block-helper" size={18} color={C.err} /><Text style={{ color: C.err, fontWeight: '700' }}>This move isn’t allowed</Text></Row>
          <Text style={{ color: C.errText2, marginTop: 6, fontSize: 13 }}>{rule}</Text>
        </View>
      ) : null}
      {type !== 'release' ? (
        <>
          <Section title={type === 'loan' ? 'Loan to' : 'Transfer to'} />
          <Card style={{ padding: 0 }}>
            {others.map((s) => {
              const sel = to === s.squad_id;
              return (
                <Pressable key={s.squad_id} onPress={() => { setTo(s.squad_id); setErrors((e) => ({ ...e, to: '' })); setRule(null); }} style={[st.clubRow, sel && { backgroundColor: C.limeTint }]} accessibilityRole="radio" accessibilityState={{ checked: sel }}>
                  <TeamBadge name={s.name} source={clubBadge(s.club_id)} size={32} />
                  <Text style={{ flex: 1, fontWeight: '500' }}>{s.name}</Text>
                  <Icon name={sel ? 'radiobox-marked' : 'radiobox-blank'} color={sel ? C.lime : C.dim} />
                </Pressable>
              );
            })}
          </Card>
          {errors.to ? <Text style={st.err}>{errors.to}</Text> : null}
        </>
      ) : null}
      <Section title="Details" />
      <Text style={st.label}>Effective date</Text>
      <TextInput value={eff} onChangeText={setEff} style={[st.input, errors.eff ? st.inputErr : null]} placeholderTextColor={C.dim} accessibilityLabel="Effective date" />
      {errors.eff ? <Text style={st.err}>{errors.eff}</Text> : null}
      {type === 'loan' ? (<>
        <Text style={[st.label, { marginTop: 14 }]}>Loan ends</Text>
        <TextInput value={end} onChangeText={setEnd} placeholder="2026-10-31" style={[st.input, errors.end ? st.inputErr : null]} placeholderTextColor={C.dim} accessibilityLabel="Loan end date" />
        {errors.end ? <Text style={st.err}>{errors.end}</Text> : null}
      </>) : null}
      <Row gap={6} style={{ marginTop: 8 }}><Icon name="calendar-range" size={15} color={C.faint} /><Muted style={{ fontSize: 12 }}>Transfer window: 1–31 Oct 2026. Releases are allowed any day.</Muted></Row>
      <Text style={[st.label, { marginTop: 14 }]}>Reason (required)</Text>
      <TextInput value={reason} onChangeText={(t) => { setReason(t); setErrors((e) => ({ ...e, reason: '' })); }} placeholder="Why is this change happening?" style={[st.input, errors.reason ? st.inputErr : null]} placeholderTextColor={C.dim} accessibilityLabel="Reason" />
      {errors.reason ? <Text style={st.err}>{errors.reason}</Text> : null}
      <Btn label={type === 'release' ? 'Release player' : type === 'loan' ? 'Loan player' : 'Transfer player'} kind={type === 'release' ? 'dangerSolid' : 'primary'} loading={busy}
        onPress={() => validate() && setConfirm(true)} style={{ marginTop: 20 }} />
      <Sheet visible={confirm} onClose={() => setConfirm(false)} title={type === 'release' ? `Release ${p.name}?` : `${type === 'loan' ? 'Loan' : 'Transfer'} ${p.name}?`}
        actions={<><Btn kind="outline" label="Cancel" onPress={() => setConfirm(false)} style={{ flex: 1 }} /><Btn kind={type === 'release' ? 'dangerSolid' : 'primary'} label={online ? 'Confirm' : 'Queue change'} onPress={submit} style={{ flex: 1.3 }} /></>}>
        <Muted>{type === 'release' ? `${p.name} will leave ${c.name} from ${eff}.` : type === 'loan' ? `${p.name} plays for ${destName} from ${eff} until ${end}, then returns automatically.` : `${p.name} moves permanently to ${destName} from ${eff} and joins as a substitute.`}</Muted>
        <Muted style={{ marginTop: 8 }}>Reason: “{reason.trim()}”. This is saved in the audit trail.</Muted>
        {!online ? <Row style={[st.hint, { backgroundColor: C.offSurface, borderColor: C.offBorder }]} gap={8}><Icon name="cloud-off-outline" color={C.offText} /><Text style={{ color: C.offText, flex: 1, fontSize: 13 }}>You’re offline. The change is queued and sent when you reconnect.</Text></Row> : null}
      </Sheet>
    </Screen>
  );
}

export function AuditScreen({ route }: any) {
  const { playerId, name } = route.params;
  const history = usePlayerHistory(playerId);
  const entries = history.data?.history ?? [];
  return (
    <Screen onRefresh={history.refresh} refreshing={history.loading}>
      <Stale error={history.error} onRetry={history.refresh} />
      <Text style={{ fontSize: 18, fontWeight: '700' }}>{name}</Text>
      <Row gap={6} style={{ marginTop: 4, marginBottom: 16 }}><Icon name="lock-outline" size={14} color={C.faint} /><Muted style={{ fontSize: 12 }}>Permanent record. Entries can’t be edited or deleted.</Muted></Row>
      {entries.map((h, i) => (
        <Row key={h.audit_id} gap={14} style={{ alignItems: 'flex-start' }}>
          <View style={{ alignItems: 'center', width: 14 }}>
            <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: C.lime, marginTop: 4 }} />
            {i < entries.length - 1 ? <View style={{ width: 2, flex: 1, minHeight: 56, backgroundColor: C.border }} /> : null}
          </View>
          <View style={{ flex: 1, paddingBottom: 18 }}>
            <Text style={{ fontWeight: '600' }}>{humanize(h.action)} · {h.from_squad_id ?? 'new'} → {h.to_squad_id ?? 'released'}</Text>
            {h.why ? <Muted style={{ marginTop: 2 }}>“{h.why}”</Muted> : null}
            <Mono style={{ marginTop: 4 }}>{h.who} · {h.effective_date} · {h.audit_id}</Mono>
          </View>
        </Row>
      ))}
      {!entries.length ? <EmptyState icon="history" title="No changes recorded yet" message="Transfers, loans and releases will appear here." /> : null}
    </Screen>
  );
}

const st = StyleSheet.create({
  clubRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, minHeight: 56, paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.divider, marginTop: -1 },
  hero: { borderRadius: 22, padding: 18 },
  heroBadge: { padding: 3, borderRadius: 36, backgroundColor: 'rgba(255,255,255,0.18)' },
  tabs: { backgroundColor: C.card, borderRadius: 14, padding: 4, marginTop: 16, marginBottom: 14, borderWidth: 1, borderColor: C.border },
  tab: { flex: 1, minHeight: 44, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  hint: { backgroundColor: C.limeTint, borderWidth: 1, borderColor: C.border2, borderRadius: 12, padding: 12, marginTop: 12 },
  label: { color: C.text2, fontWeight: '600', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: C.card, color: C.text, borderRadius: 12, borderWidth: 1, borderColor: C.border2, paddingHorizontal: 16, minHeight: 52, fontSize: 15, fontFamily: F.regular },
  inputErr: { borderColor: C.errBorder },
  err: { color: C.err, fontSize: 13, marginTop: 6 },
  rule: { backgroundColor: C.errSurface, borderWidth: 1, borderColor: C.errBorder, borderRadius: 14, padding: 14, marginBottom: 4 },
});
