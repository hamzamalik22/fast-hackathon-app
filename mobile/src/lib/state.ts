// Global app state: session (token in SecureStore = Android Keystore), connectivity/sync status, cart.
import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

import { setToken, Tenant, User, Variant, Product } from './api';
import { clearUserData } from './db';

type SessionState = {
  ready: boolean;
  token: string | null;
  user: User | null;
  tenant: Tenant | null;
  restore: () => Promise<void>;
  signIn: (token: string, user: User, tenant: Tenant) => Promise<void>;
  signOut: () => Promise<void>;
};

export const useSession = create<SessionState>((set) => ({
  ready: false,
  token: null,
  user: null,
  tenant: null,
  restore: async () => {
    try {
      const [token, user, tenant] = await Promise.all([
        SecureStore.getItemAsync('token'), SecureStore.getItemAsync('user'), SecureStore.getItemAsync('tenant'),
      ]);
      if (token && user) {
        setToken(token);
        set({ token, user: JSON.parse(user), tenant: tenant ? JSON.parse(tenant) : null });
      }
    } finally {
      set({ ready: true });
    }
  },
  signIn: async (token, user, tenant) => {
    await SecureStore.setItemAsync('token', token);
    await SecureStore.setItemAsync('user', JSON.stringify(user));
    await SecureStore.setItemAsync('tenant', JSON.stringify(tenant));
    setToken(token);
    set({ token, user, tenant });
  },
  signOut: async () => {
    await Promise.all(['token', 'user', 'tenant'].map((k) => SecureStore.deleteItemAsync(k)));
    setToken(null);
    clearUserData();
    set({ token: null, user: null, tenant: null });
  },
}));

export type ResultItem = { action_id: string; label: string; status: string; message: string; processed_order?: number; error_code?: string | null };

type NetState = {
  online: boolean;
  checked: boolean;
  syncing: boolean;
  pending: number;
  lastSync: string | null;
  lastResults: ResultItem[] | null;
  resultsShown: boolean;
  dataVersion: number;
};

export const useNet = create<NetState>(() => ({
  online: false, checked: false, syncing: false, pending: 0, lastSync: null, lastResults: null, resultsShown: true, dataVersion: 0,
}));

export type CartLine = { product: Product; variant: Variant; quantity: number };

type CartState = {
  lines: CartLine[];
  add: (product: Product, variant: Variant, quantity: number) => void;
  setQty: (variantId: string, quantity: number) => void;
  remove: (variantId: string) => void;
  clear: () => void;
};

export const useCart = create<CartState>((set) => ({
  lines: [],
  add: (product, variant, quantity) => set((s) => {
    const existing = s.lines.find((l) => l.variant.variant_id === variant.variant_id);
    if (existing) {
      return { lines: s.lines.map((l) => l === existing ? { ...l, quantity: Math.min(10, l.quantity + quantity) } : l) };
    }
    return { lines: [...s.lines, { product, variant, quantity }] };
  }),
  setQty: (variantId, quantity) => set((s) => ({
    lines: s.lines.map((l) => l.variant.variant_id === variantId ? { ...l, quantity: Math.max(1, Math.min(10, quantity)) } : l),
  })),
  remove: (variantId) => set((s) => ({ lines: s.lines.filter((l) => l.variant.variant_id !== variantId) })),
  clear: () => set({ lines: [] }),
}));

export function roleLabel(role?: string | null): string {
  return ({ super_admin: 'Platform Admin', league_organizer: 'League Organizer', club_manager: 'Club Manager', player: 'Player', viewer: 'Viewer' } as Record<string, string>)[role ?? ''] ?? 'Guest';
}

export function money(minor: number): string {
  return `PKR ${(minor / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
