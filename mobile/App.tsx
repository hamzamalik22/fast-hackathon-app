import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Image, Text as RNText, View } from 'react-native';
import { PaperProvider } from 'react-native-paper';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { setUnauthorizedHandler } from './src/lib/api';
import { useSession } from './src/lib/state';
import { startConnectivity } from './src/lib/sync';
import { ProfileScreen, SyncScreen } from './src/screens/account';
import { LoginScreen, SettingsScreen } from './src/screens/auth';
import { AuditScreen, ClubScreen, ClubsScreen, PlayerActionScreen, RosterScreen } from './src/screens/club';
import { AppHeader, SyncResultsDialog, ToastHost } from './src/screens/common';
import { FixturesScreen, HomeScreen, MatchScreen, ScoringScreen, StandingsScreen } from './src/screens/league';
import { CartScreen, CheckoutScreen, OrdersScreen, ProductScreen, ReceiptScreen, StoreScreen } from './src/screens/store';
import { C, F, FONT_FILES, LOGO, navTheme, paperTheme } from './src/ui/kit';

const Stack = createNativeStackNavigator();
const Tabs = createBottomTabNavigator();

const TAB_ICONS: Record<string, [keyof typeof MaterialCommunityIcons.glyphMap, keyof typeof MaterialCommunityIcons.glyphMap]> = {
  Home: ['home', 'home-outline'], Fixtures: ['scoreboard', 'scoreboard-outline'], Standings: ['podium-gold', 'podium'],
  Store: ['storefront', 'storefront-outline'], Profile: ['account', 'account-outline'],
};

function MainTabs() {
  const insets = useSafeAreaInsets();
  return (
    <Tabs.Navigator screenOptions={({ route }) => ({
      header: ({ options }) => <AppHeader title={options.title ?? route.name} brand={route.name === 'Home'} cart={route.name === 'Store'} />,
      tabBarStyle: { backgroundColor: C.bg, borderTopColor: C.border, height: 64 + insets.bottom, paddingTop: 8, paddingBottom: insets.bottom + 6 },
      tabBarActiveTintColor: C.lime,
      tabBarInactiveTintColor: C.faint,
      tabBarLabelStyle: { fontSize: 12, fontFamily: F.semibold },
      tabBarIconStyle: { width: 56, height: 30 },
      tabBarIcon: ({ focused, color }) => (
        <View style={{ width: 56, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: focused ? 'rgba(214,255,65,0.14)' : 'transparent' }}>
          <MaterialCommunityIcons name={TAB_ICONS[route.name][focused ? 0 : 1]} size={22} color={color} />
        </View>
      ),
    })}>
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Fixtures" component={FixturesScreen} />
      <Tabs.Screen name="Standings" component={StandingsScreen} />
      <Tabs.Screen name="Store" component={StoreScreen} options={{ title: 'Club store' }} />
      <Tabs.Screen name="Profile" component={ProfileScreen} />
    </Tabs.Navigator>
  );
}

const STATUS = ['Restoring session…', 'Loading saved fixtures…', 'Checking the connection…'];

function Splash({ fonts }: { fonts: boolean }) {
  const scale = useRef(new Animated.Value(0.72)).current;
  const fade = useRef(new Animated.Value(0)).current;
  const bar = useRef(new Animated.Value(0)).current;
  const [i, setI] = useState(0);
  useEffect(() => {
    Animated.parallel([
      Animated.sequence([Animated.timing(scale, { toValue: 1.04, duration: 450, useNativeDriver: true, easing: Easing.out(Easing.ease) }), Animated.timing(scale, { toValue: 1, duration: 250, useNativeDriver: true })]),
      Animated.timing(fade, { toValue: 1, duration: 500, useNativeDriver: true }),
    ]).start();
    Animated.timing(bar, { toValue: 1, duration: 1400, useNativeDriver: false, easing: Easing.inOut(Easing.ease) }).start();
    const t = setInterval(() => setI((x) => (x + 1) % STATUS.length), 600);
    return () => clearInterval(t);
  }, [bar, fade, scale]);
  return (
    <View style={{ flex: 1, backgroundColor: C.bgSplash, alignItems: 'center', justifyContent: 'center' }}>
      <View style={{ position: 'absolute', width: 260, height: 260, borderRadius: 130, backgroundColor: 'rgba(214,255,65,0.06)' }} />
      <Animated.View style={{ opacity: fade, transform: [{ scale }], alignItems: 'center' }}>
        <Image source={LOGO} style={{ width: 88, height: 88, borderRadius: 22 }} />
        <RNText style={{ color: C.text, fontFamily: fonts ? 'BarlowCondensed-ExtraBold' : undefined, fontWeight: fonts ? 'normal' : '800', fontSize: 40, letterSpacing: 3.2, marginTop: 18 }}>ALPHA LEAGUE</RNText>
        <RNText style={{ color: C.muted, fontFamily: 'Geist-Regular', fontSize: 14, marginTop: 4 }}>Every match. Every club. One league.</RNText>
      </Animated.View>
      <View style={{ position: 'absolute', bottom: 64, alignItems: 'center' }}>
        <View style={{ width: 140, height: 3, borderRadius: 2, backgroundColor: C.card3, overflow: 'hidden' }}>
          <Animated.View style={{ height: 3, backgroundColor: C.lime, width: bar.interpolate({ inputRange: [0, 1], outputRange: [0, 140] }) }} />
        </View>
        <RNText style={{ color: C.faint, fontFamily: 'Geist-Regular', fontSize: 12, marginTop: 10 }}>{STATUS[i]}</RNText>
      </View>
    </View>
  );
}

export default function App() {
  const { ready, token, restore, signOut } = useSession();
  const [fontsLoaded] = useFonts(FONT_FILES);
  const [minSplash, setMinSplash] = useState(true);

  useEffect(() => {
    setUnauthorizedHandler(() => void signOut());
    void restore();
    startConnectivity();
    const t = setTimeout(() => setMinSplash(false), 1200);
    return () => clearTimeout(t);
  }, [restore, signOut]);

  if (!ready || !fontsLoaded || minSplash) return <Splash fonts={fontsLoaded} />;

  return (
    <SafeAreaProvider>
      <PaperProvider theme={paperTheme}>
        <NavigationContainer theme={navTheme}>
          <Stack.Navigator screenOptions={{
            header: ({ navigation, route, options, back }) => (
              <AppHeader title={options.title ?? route.name} canGoBack={!!back} onBack={navigation.goBack} cart={['Product'].includes(route.name)} />
            ),
            contentStyle: { backgroundColor: C.bg },
            animation: 'slide_from_right',
          }}>
            {token ? (
              <>
                <Stack.Screen name="Tabs" component={MainTabs} options={{ headerShown: false }} />
                <Stack.Screen name="Match" component={MatchScreen} options={{ title: 'Match centre' }} />
                <Stack.Screen name="Scoring" component={ScoringScreen} options={{ title: 'Scoring entry' }} />
                <Stack.Screen name="Club" component={ClubScreen} options={{ title: 'Club' }} />
                <Stack.Screen name="Clubs" component={ClubsScreen} options={{ title: 'Clubs' }} />
                <Stack.Screen name="Roster" component={RosterScreen} options={{ title: 'Manage squad' }} />
                <Stack.Screen name="PlayerAction" component={PlayerActionScreen} options={{ title: 'Roster change' }} />
                <Stack.Screen name="Audit" component={AuditScreen} options={{ title: 'Audit history' }} />
                <Stack.Screen name="Product" component={ProductScreen} options={{ title: 'Product' }} />
                <Stack.Screen name="Cart" component={CartScreen} options={{ title: 'Your cart' }} />
                <Stack.Screen name="Checkout" component={CheckoutScreen} options={{ title: 'Checkout' }} />
                <Stack.Screen name="Receipt" component={ReceiptScreen} options={{ title: 'Receipt' }} />
                <Stack.Screen name="Orders" component={OrdersScreen} options={{ title: 'Orders & receipts' }} />
                <Stack.Screen name="Sync" component={SyncScreen} options={{ title: 'Sync status' }} />
                <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Server & settings' }} />
              </>
            ) : (
              <>
                <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
                <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Server & settings' }} />
                <Stack.Screen name="Sync" component={SyncScreen} options={{ title: 'Sync status' }} />
              </>
            )}
          </Stack.Navigator>
          <SyncResultsDialog />
          <ToastHost />
        </NavigationContainer>
        <StatusBar style="light" />
      </PaperProvider>
    </SafeAreaProvider>
  );
}
