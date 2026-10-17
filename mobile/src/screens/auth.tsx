import React, { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { login } from '../lib/actions';
import { api, ApiError, serverUrl } from '../lib/api';
import { kvSet } from '../lib/db';
import { useSession } from '../lib/state';
import { checkConnection, deviceId } from '../lib/sync';
import { Btn, C, Caps, Card, Chip, F, Icon, LOGO, Muted, Row, Section, Sheet, Text } from '../ui/kit';
import { Screen, toast } from './common';

const APP_VERSION: string = require('../../app.json').expo.version;

const DEMO: [string, string][] = [
  ['viewer', 'General Viewer'], ['player', 'Player'], ['manager', 'Club Manager'],
  ['organizer', 'League Organizer'], ['admin', 'Platform Super-Admin'],
];
const PRESETS: [string, string][] = [
  ['Emulator', 'http://10.0.2.2:8080'], ['USB cable (adb reverse)', 'http://localhost:8080'], ['Laptop on Wi-Fi', 'http://192.168.1.10:8080'],
];

export function Field({ label, value, onChangeText, secure, error, ...rest }: {
  label: string; value: string; onChangeText: (t: string) => void; secure?: boolean; error?: string | null; [k: string]: any;
}) {
  const [hidden, setHidden] = useState(true);
  const [focus, setFocus] = useState(false);
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={st.label}>{label}</Text>
      <View style={[st.inputWrap, focus && { borderColor: C.lime }, error ? { borderColor: C.errBorder } : null]}>
        <TextInput value={value} onChangeText={onChangeText} placeholderTextColor={C.dim} style={st.input}
          secureTextEntry={secure && hidden} accessibilityLabel={label} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} {...rest} />
        {secure ? (
          <Pressable onPress={() => setHidden(!hidden)} hitSlop={12} accessibilityRole="button" accessibilityLabel={hidden ? 'Show password' : 'Hide password'}>
            <Icon name={hidden ? 'eye-outline' : 'eye-off-outline'} size={22} color={C.muted} />
          </Pressable>
        ) : null}
      </View>
      {error ? <Row gap={6} style={{ marginTop: 6 }}><Icon name="alert-circle" size={16} color={C.err} /><Text style={{ color: C.err, fontSize: 13 }}>{error}</Text></Row> : null}
    </View>
  );
}

export function ErrorBox({ text }: { text: string }) {
  return (
    <Row style={st.errorBox} gap={10}>
      <Icon name="alert-circle-outline" size={18} color={C.err} /><Text style={{ color: C.errText2, flex: 1, fontSize: 13 }}>{text}</Text>
    </Row>
  );
}

export function ServerSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [url, setUrl] = useState(serverUrl());
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    const target = url.trim().replace(/\/+$/, '');
    try {
      await api.health(target);
      kvSet('server_url', target);
      setResult({ ok: true, text: 'Connected. The server is reachable.' });
      void checkConnection();
      toast('Server address saved');
    } catch {
      setResult({ ok: false, text: "Can't reach that address. Check the IP and that the phone and laptop are on the same network." });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet visible={visible} onClose={onClose} title="Server address"
      actions={<><Btn kind="outline" label="Cancel" onPress={onClose} style={{ flex: 1 }} /><Btn label="Test & save" loading={busy} onPress={save} style={{ flex: 1 }} /></>}>
      <Muted style={{ marginBottom: 12 }}>The app talks to the backend running on the team laptop.</Muted>
      <Field label="Server URL" value={url} onChangeText={(t) => { setUrl(t); setResult(null); }} autoCapitalize="none" keyboardType="url" />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 8 }}>
        {PRESETS.map(([l, u]) => <Chip key={u} label={l} selected={url === u} onPress={() => { setUrl(u); setResult(null); }} />)}
      </View>
      {result ? <Row gap={8} style={{ marginTop: 12 }}><Icon name={result.ok ? 'check-circle' : 'close-circle'} color={result.ok ? C.okText : C.err} /><Text style={{ flex: 1, color: result.ok ? C.okText : C.err }}>{result.text}</Text></Row> : null}
    </Sheet>
  );
}

export function LoginScreen() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [server, setServer] = useState(false);
  const submit = async () => {
    if (!email.trim() || !password) {
      setError('Enter your email and password to sign in.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : '';
      setError(code === 'INVALID_CREDENTIALS' ? 'That email and password don’t match. Check them and try again.'
        : code === 'RATE_LIMITED' ? 'Too many attempts. Wait a few seconds and try again.'
          : e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ padding: 24, paddingTop: insets.top + 36, paddingBottom: insets.bottom + 24 }}>
      <Image source={LOGO} style={st.logo} accessibilityLabel="Alpha League logo" />
      <Text style={st.hero}>EVERY MATCH.{'\n'}EVERY CLUB.{'\n'}<Text style={[st.hero, { color: C.lime }]}>ONE LEAGUE.</Text></Text>
      <Text style={{ color: C.muted, fontSize: 15, lineHeight: 22, marginBottom: 26 }}>Sign in to Alpha League to follow fixtures, run your club and score matches live.</Text>
      <Field label="Email" value={email} onChangeText={(t) => { setEmail(t); setError(null); }} placeholder="you@club.com" autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
      <Field label="Password" value={password} onChangeText={(t) => { setPassword(t); setError(null); }} placeholder="Your password" secure onSubmitEditing={submit} />
      {error ? <ErrorBox text={error} /> : null}
      <Btn label="Sign in" onPress={submit} loading={busy} />
      <Caps style={{ marginTop: 28, marginBottom: 12 }}>Demo accounts · tap to fill</Caps>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 10 }}>
        {DEMO.map(([id, label]) => (
          <Chip key={id} label={label} selected={email === `${id}@nascon.test`}
            onPress={() => { setEmail(`${id}@nascon.test`); setPassword('Nascon@26'); setError(null); }} />
        ))}
      </View>
      <Pressable onPress={() => setServer(true)} accessibilityRole="button" accessibilityLabel="Change server address" style={{ marginTop: 34, alignSelf: 'center', minHeight: 44, justifyContent: 'center' }}>
        <Row gap={8}>
          <Icon name="dns-outline" size={16} color={C.faint} />
          <Text style={{ color: C.faint, fontSize: 13 }}>Server <Text style={{ fontFamily: F.monoMedium, color: C.text, fontSize: 13 }}>{serverUrl().replace(/^https?:\/\//, '')}</Text>  ·  </Text>
          <Text style={{ color: C.lime, fontWeight: '600', fontSize: 13 }}>Change</Text>
        </Row>
      </Pressable>
      <ServerSheet visible={server} onClose={() => setServer(false)} />
    </ScrollView>
  );
}

export function SettingsScreen() {
  const tenant = useSession((s) => s.tenant);
  const [url, setUrl] = useState(serverUrl());
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const test = async (save: boolean) => {
    setBusy(true);
    const target = url.trim().replace(/\/+$/, '');
    try {
      await api.health(target);
      if (save) { kvSet('server_url', target); void checkConnection(); toast('Server address saved'); }
      setResult({ ok: true, text: 'Connection works. The server answered.' });
    } catch {
      setResult({ ok: false, text: "Couldn't reach the server. Check the address and that the phone is on the laptop's network." });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <Section title="Server address" />
      <Field label="Server URL" value={url} onChangeText={(t: string) => { setUrl(t); setResult(null); }} autoCapitalize="none" keyboardType="url" />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 8, marginBottom: 12 }}>
        {PRESETS.map(([l, u]) => <Chip key={u} label={l} selected={url === u} onPress={() => { setUrl(u); setResult(null); }} />)}
      </View>
      <Row gap={10}>
        <Btn kind="outline" label="Test connection" onPress={() => test(false)} style={{ flex: 1 }} />
        <Btn label="Save" loading={busy} onPress={() => test(true)} style={{ flex: 1 }} />
      </Row>
      {result ? <Row gap={8} style={{ marginTop: 12 }}><Icon name={result.ok ? 'check-circle' : 'close-circle'} color={result.ok ? C.okText : C.err} /><Text style={{ flex: 1, color: result.ok ? C.okText : C.err }}>{result.text}</Text></Row> : null}
      <Section title="Security" />
      <Card>
        <Row gap={12}><Icon name="shield-lock-outline" size={24} color={C.okText} /><View style={{ flex: 1 }}>
          <Text style={{ fontWeight: '600' }}>Signed in securely</Text>
          <Muted>Your sign-in token is stored in the Android Keystore, never in plain text.</Muted></View></Row>
      </Card>
      <Section title="About" />
      <Card style={{ padding: 0 }}>
        <Row style={st.about}><Muted>App version</Muted><Text style={{ fontFamily: F.mono, fontSize: 12 }}>{APP_VERSION}</Text></Row>
        <Row style={st.about}><Muted>Tenant</Muted><Text style={{ fontSize: 13 }}>{tenant?.name ?? '—'}</Text></Row>
        <Row style={st.about}><Muted>Device id</Muted><Text style={{ fontFamily: F.mono, fontSize: 11 }} numberOfLines={1}>{deviceId().slice(0, 22)}…</Text></Row>
      </Card>
    </Screen>
  );
}

const st = StyleSheet.create({
  logo: { width: 56, height: 56, borderRadius: 14, marginBottom: 26 },
  hero: { color: C.text, fontFamily: F.display, fontSize: 44, lineHeight: 44 },
  label: { color: C.text2, fontSize: 13, fontWeight: '600', marginBottom: 8 },
  inputWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderColor: C.border2, borderWidth: 1, borderRadius: 12, paddingHorizontal: 16, minHeight: 52 },
  input: { flex: 1, color: C.text, fontSize: 15, paddingVertical: 12, fontFamily: F.regular },
  errorBox: { backgroundColor: C.errSurface, borderWidth: 1, borderColor: C.errBorder, padding: 12, borderRadius: 12, marginBottom: 14 },
  about: { justifyContent: 'space-between', paddingHorizontal: 16, minHeight: 48, borderTopWidth: 1, borderTopColor: C.divider, marginTop: -1 },
});
