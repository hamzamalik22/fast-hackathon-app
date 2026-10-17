import React, { useState } from 'react';
import { View } from 'react-native';
import { Button, Chip, HelperText, Text, TextInput } from 'react-native-paper';

import { login } from '../lib/actions';
import { api, ApiError, DEFAULT_SERVER, serverUrl } from '../lib/api';
import { kvSet } from '../lib/db';
import { checkConnection, deviceId } from '../lib/sync';
import { Screen } from './common';

const DEMO = ['admin', 'organizer', 'manager', 'player', 'viewer'];

export function LoginScreen({ navigation }: any) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <Text variant="headlineSmall" style={{ marginBottom: 16 }}>Sign in</Text>
      <TextInput label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
      <TextInput label="Password" value={password} onChangeText={setPassword} secureTextEntry style={{ marginTop: 12 }} onSubmitEditing={submit} />
      <HelperText type="error" visible={!!error}>{error}</HelperText>
      <Button mode="contained" onPress={submit} loading={busy} disabled={busy || !email || !password} contentStyle={{ height: 48 }}>Sign in</Button>
      <Text variant="labelLarge" style={{ marginTop: 24 }}>Demo accounts (password Nascon@26)</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginTop: 8 }}>
        {DEMO.map((d) => (
          <Chip key={d} style={{ margin: 4 }} onPress={() => { setEmail(`${d}@nascon.test`); setPassword('Nascon@26'); }}>{d}</Chip>
        ))}
      </View>
      <Button style={{ marginTop: 24 }} icon="cog" onPress={() => navigation.navigate('Settings')}>Server settings</Button>
    </Screen>
  );
}

export function SettingsScreen() {
  const [url, setUrl] = useState(serverUrl());
  const [result, setResult] = useState<string | null>(null);
  const test = async (target: string) => {
    setResult('Testing…');
    try {
      await api.health(target.replace(/\/+$/, ''));
      setResult('✓ Connected to the server.');
    } catch {
      setResult("✕ Can't reach the server at that address.");
    }
  };
  const save = async () => {
    kvSet('server_url', url.trim().replace(/\/+$/, ''));
    await test(url.trim());
    void checkConnection();
  };
  return (
    <Screen>
      <Text variant="titleMedium">Server address</Text>
      <Text variant="bodySmall" style={{ marginBottom: 8 }}>Emulator: {DEFAULT_SERVER} · Phone: http://&lt;laptop IP&gt;:8080</Text>
      <TextInput label="Server URL" value={url} onChangeText={setUrl} autoCapitalize="none" keyboardType="url" />
      <View style={{ flexDirection: 'row', marginTop: 12 }}>
        <Button mode="contained" onPress={save} style={{ marginRight: 8 }}>Save</Button>
        <Button mode="outlined" onPress={() => test(url)}>Test connection</Button>
      </View>
      {result ? <Text style={{ marginTop: 12 }}>{result}</Text> : null}
      <Text variant="bodySmall" style={{ marginTop: 24 }}>Device id: {deviceId()}</Text>
    </Screen>
  );
}
