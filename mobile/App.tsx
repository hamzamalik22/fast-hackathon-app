import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useMemo } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { MD3LightTheme, PaperProvider } from 'react-native-paper';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { setUnauthorizedHandler } from './src/lib/api';
import { useSession } from './src/lib/state';
import { startConnectivity } from './src/lib/sync';
import { ProfileScreen, SyncScreen } from './src/screens/account';
import { LoginScreen, SettingsScreen } from './src/screens/auth';
import { ClubScreen, ClubsScreen, PlayerActionScreen } from './src/screens/club';
import { SyncResultsDialog } from './src/screens/common';
import { FixturesScreen, HomeScreen, MatchScreen, StandingsScreen } from './src/screens/league';
import { CartScreen, OrdersScreen, ProductScreen, ReceiptScreen, StoreScreen } from './src/screens/store';

const Stack = createNativeStackNavigator();
const Tabs = createBottomTabNavigator();

const TAB_ICONS: Record<string, keyof typeof MaterialCommunityIcons.glyphMap> = {
  Home: 'home', Fixtures: 'calendar-month', Standings: 'trophy', Store: 'shopping', Profile: 'account-circle',
};

function MainTabs() {
  return (
    <Tabs.Navigator screenOptions={({ route }) => ({
      tabBarIcon: ({ color, size }) => <MaterialCommunityIcons name={TAB_ICONS[route.name]} color={color} size={size} />,
      tabBarLabelStyle: { fontSize: 12 },
    })}>
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Fixtures" component={FixturesScreen} />
      <Tabs.Screen name="Standings" component={StandingsScreen} />
      <Tabs.Screen name="Store" component={StoreScreen} />
      <Tabs.Screen name="Profile" component={ProfileScreen} />
    </Tabs.Navigator>
  );
}

export default function App() {
  const { ready, token, tenant, restore, signOut } = useSession();

  useEffect(() => {
    setUnauthorizedHandler(() => void signOut());
    void restore();
    startConnectivity();
  }, [restore, signOut]);

  const theme = useMemo(() => ({
    ...MD3LightTheme,
    colors: { ...MD3LightTheme.colors, primary: tenant?.primary_color ?? '#0B5FFF' },
  }), [tenant]);

  if (!ready) {
    return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><ActivityIndicator size="large" /></View>;
  }

  return (
    <SafeAreaProvider>
      <PaperProvider theme={theme}>
        <NavigationContainer>
          <Stack.Navigator>
            {token ? (
              <>
                <Stack.Screen name="Tabs" component={MainTabs} options={{ headerShown: false }} />
                <Stack.Screen name="Match" component={MatchScreen} options={{ title: 'Match' }} />
                <Stack.Screen name="Club" component={ClubScreen} options={{ title: 'Club profile' }} />
                <Stack.Screen name="Clubs" component={ClubsScreen} options={{ title: 'Clubs' }} />
                <Stack.Screen name="PlayerAction" component={PlayerActionScreen} options={{ title: 'Roster action' }} />
                <Stack.Screen name="Product" component={ProductScreen} options={{ title: 'Product' }} />
                <Stack.Screen name="Cart" component={CartScreen} options={{ title: 'Cart & checkout' }} />
                <Stack.Screen name="Receipt" component={ReceiptScreen} options={{ title: 'Receipt' }} />
                <Stack.Screen name="Orders" component={OrdersScreen} options={{ title: 'My orders' }} />
                <Stack.Screen name="Sync" component={SyncScreen} options={{ title: 'Sync status' }} />
                <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
              </>
            ) : (
              <>
                <Stack.Screen name="Login" component={LoginScreen} options={{ title: 'NaSCon League' }} />
                <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
                <Stack.Screen name="Sync" component={SyncScreen} options={{ title: 'Sync status' }} />
              </>
            )}
          </Stack.Navigator>
          <SyncResultsDialog />
        </NavigationContainer>
        <StatusBar style="dark" />
      </PaperProvider>
    </SafeAreaProvider>
  );
}
