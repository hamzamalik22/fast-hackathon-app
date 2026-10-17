import React, { useState } from 'react';
import { Image, View } from 'react-native';
import { Button, Card, Chip, Dialog, HelperText, IconButton, List, Portal, RadioButton, Text, TextInput } from 'react-native-paper';

import * as actions from '../lib/actions';
import { ApiError, assetUrl, Receipt } from '../lib/api';
import { cacheGet } from '../lib/db';
import { useOrders, useProducts } from '../lib/data';
import { useCached } from '../lib/hooks';
import { api } from '../lib/api';
import { money, useCart, useNet } from '../lib/state';
import { Empty, Screen, Stale, styles } from './common';

export function StoreScreen({ navigation }: any) {
  const products = useProducts();
  const count = useCart((s) => s.lines.reduce((n, l) => n + l.quantity, 0));
  return (
    <Screen onRefresh={products.refresh} refreshing={products.loading}>
      <View style={styles.row}>
        <Text variant="titleMedium">Club store</Text>
        <Button icon="cart" mode="contained-tonal" onPress={() => navigation.navigate('Cart')}>Cart ({count})</Button>
      </View>
      <Stale updatedAt={products.updatedAt} error={products.error} onRetry={products.refresh} />
      {products.data?.map((p) => (
        <Card key={p.product_id} style={styles.card} onPress={() => navigation.navigate('Product', { productId: p.product_id })}>
          <Card.Title title={p.name} subtitle={`${p.category} · from ${money(p.price_minor)}`}
            left={() => p.image_url ? <Image source={{ uri: assetUrl(p.image_url) }} style={{ width: 40, height: 40 }} accessibilityIgnoresInvertColors /> : null} />
        </Card>
      ))}
      {!products.data?.length && <Empty title="No products yet" />}
    </Screen>
  );
}

export function ProductScreen({ route, navigation }: any) {
  const products = useProducts();
  const p = products.data?.find((x) => x.product_id === route.params.productId);
  const [variantId, setVariantId] = useState<string | null>(null);
  const [qty, setQty] = useState(1);
  const add = useCart((s) => s.add);
  if (!p) return <Screen><Empty title="Product not found" /></Screen>;
  const v = p.variants.find((x) => x.variant_id === variantId) ?? p.variants.find((x) => x.stock > 0) ?? p.variants[0];
  return (
    <Screen>
      {p.image_url && <Image source={{ uri: assetUrl(p.image_url) }} style={{ width: 160, height: 160, alignSelf: 'center' }} accessibilityLabel={p.name} />}
      <Text variant="headlineSmall">{p.name}</Text>
      <Text>{p.description}</Text>
      <Text variant="titleLarge" style={{ marginVertical: 8 }}>{money(v.price_minor)}</Text>
      <Text variant="labelLarge">Choose an option</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {p.variants.map((x) => (
          <Chip key={x.variant_id} selected={x.variant_id === v.variant_id} disabled={x.stock <= 0} style={{ margin: 4 }}
            onPress={() => setVariantId(x.variant_id)}>{x.size} · {x.color}{x.stock <= 0 ? ' (sold out)' : ''}</Chip>
        ))}
      </View>
      <Text>{v.stock > 0 ? `${v.stock} in stock` : 'Sold out'}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <IconButton icon="minus" accessibilityLabel="Decrease quantity" onPress={() => setQty(Math.max(1, qty - 1))} />
        <Text variant="titleMedium">{qty}</Text>
        <IconButton icon="plus" accessibilityLabel="Increase quantity" onPress={() => setQty(Math.min(10, qty + 1))} />
      </View>
      <Button mode="contained" disabled={v.stock <= 0} contentStyle={{ height: 48 }}
        onPress={() => { add(p, v, qty); navigation.navigate('Cart'); }}>Add to cart</Button>
    </Screen>
  );
}

const TOKENS = [
  { value: 'tok_success', label: 'Test card – payment succeeds' },
  { value: 'tok_declined', label: 'Test card – declined' },
  { value: 'tok_capture_fail', label: 'Test card – capture fails' },
];

export function CartScreen({ navigation }: any) {
  const { lines, setQty, remove } = useCart();
  const online = useNet((s) => s.online);
  const [code, setCode] = useState('');
  const [token, setToken] = useState<actions.PaymentToken>('tok_success');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const subtotal = lines.reduce((s, l) => s + l.variant.price_minor * l.quantity, 0);
  const pay = async () => {
    setConfirm(false);
    setBusy(true);
    setError(null);
    try {
      const r = await actions.checkout(lines, code || null, token);
      navigation.replace('Receipt', { orderId: r.order_id });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Payment failed. Please try again.');
    } finally {
      setBusy(false);
    }
  };
  if (!lines.length) return <Screen><Empty title="Your cart is empty" message="Add items from the store." /><Button onPress={() => navigation.navigate('Tabs', { screen: 'Store' })}>Go to store</Button></Screen>;
  return (
    <Screen>
      {lines.map((l) => (
        <List.Item key={l.variant.variant_id} title={`${l.product.name} (${l.variant.size})`} description={`${money(l.variant.price_minor)} × ${l.quantity}`}
          right={() => (
            <View style={{ flexDirection: 'row' }}>
              <IconButton icon="minus" accessibilityLabel="Decrease" onPress={() => setQty(l.variant.variant_id, l.quantity - 1)} />
              <IconButton icon="plus" accessibilityLabel="Increase" onPress={() => setQty(l.variant.variant_id, l.quantity + 1)} />
              <IconButton icon="delete" accessibilityLabel="Remove item" onPress={() => remove(l.variant.variant_id)} />
            </View>
          )} />
      ))}
      <TextInput label="Discount code (e.g. WELCOME10)" value={code} onChangeText={setCode} autoCapitalize="characters" style={{ marginTop: 8 }} />
      <Text variant="labelLarge" style={{ marginTop: 12 }}>Payment (mock gateway)</Text>
      <RadioButton.Group value={token} onValueChange={(v) => setToken(v as actions.PaymentToken)}>
        {TOKENS.map((t) => <RadioButton.Item key={t.value} value={t.value} label={t.label} />)}
      </RadioButton.Group>
      <Text variant="titleLarge" style={{ marginVertical: 8 }}>Subtotal {money(subtotal)}</Text>
      <HelperText type="error" visible={!!error || !online}>{error ?? 'Checkout needs a connection to the server.'}</HelperText>
      <Button mode="contained" contentStyle={{ height: 52 }} loading={busy} disabled={busy || !online} onPress={() => setConfirm(true)}>Pay {money(subtotal)}</Button>
      <Portal><Dialog visible={confirm} onDismiss={() => setConfirm(false)}>
        <Dialog.Title>Confirm payment</Dialog.Title>
        <Dialog.Content><Text>Pay {money(subtotal)}{code ? ` (discount ${code.toUpperCase()} applied at checkout)` : ''}?</Text></Dialog.Content>
        <Dialog.Actions><Button onPress={() => setConfirm(false)}>Cancel</Button><Button onPress={pay}>Pay</Button></Dialog.Actions>
      </Dialog></Portal>
    </Screen>
  );
}

export function ReceiptScreen({ route }: any) {
  const { orderId } = route.params;
  const r = useCached<Receipt>(`receipt:${orderId}`, () => api.receipt(orderId));
  const [msg, setMsg] = useState<string | null>(null);
  const rec = r.data ?? cacheGet<Receipt>(`receipt:${orderId}`)?.data;
  if (!rec) return <Screen><Stale updatedAt={null} error={r.error} onRetry={r.refresh} /></Screen>;
  const p = rec.payload;
  return (
    <Screen>
      <Text variant="headlineSmall">✓ Payment successful</Text>
      <Text>Order {p.order_id}</Text>
      <Text>Paid at {new Date(p.paid_at).toLocaleString()}</Text>
      {p.items.map((i) => <Text key={i.variant_id}>{i.variant_id} × {i.quantity} · {money(i.unit_price_minor * i.quantity)}</Text>)}
      <Text>Subtotal {money(p.subtotal_minor)} · Discount {money(p.discount_minor)}</Text>
      <Text variant="titleLarge" style={{ marginVertical: 8 }}>Total {money(p.total_minor)}</Text>
      <Text variant="bodySmall" selectable>Signature {rec.signature.slice(0, 16)}…</Text>
      <Button mode="contained" icon="file-pdf-box" style={{ marginTop: 16 }} contentStyle={{ height: 48 }}
        onPress={async () => { try { await actions.openReceiptPdf(rec); setMsg('Receipt PDF saved and opened.'); } catch { setMsg('Could not open the PDF on this device.'); } }}>
        Open / download PDF receipt
      </Button>
      {msg ? <Text style={{ marginTop: 8 }}>{msg}</Text> : null}
    </Screen>
  );
}

export function OrdersScreen({ navigation }: any) {
  const orders = useOrders();
  return (
    <Screen onRefresh={orders.refresh} refreshing={orders.loading}>
      {orders.data?.map((o) => (
        <List.Item key={o.order_id} title={`${money(o.total_minor)} · ${o.status}`} description={`${o.order_id} · ${new Date(o.created_at).toLocaleString()}`}
          onPress={() => navigation.navigate('Receipt', { orderId: o.order_id })} />
      ))}
      {!orders.data?.length && <Empty title="No orders yet" message="Your purchases will appear here." />}
    </Screen>
  );
}
