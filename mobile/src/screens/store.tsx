import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Modal, Pressable, ScrollView, StyleSheet, TextInput, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import * as actions from '../lib/actions';
import { api, ApiError, CheckoutResult, Receipt } from '../lib/api';
import { cacheGet } from '../lib/db';
import { useOrders, useProducts } from '../lib/data';
import { useCached } from '../lib/hooks';
import { money, useCart, useNet } from '../lib/state';
import { productImage, promoKit } from '../ui/images';
import { Btn, C, Caps, Card, Chip, Display, EmptyState, F, Icon, Mono, Muted, Pill, Row, Score, Section, Sheet, Text } from '../ui/kit';
import { Empty, Screen, Stale, toast } from './common';

const CATS = [['all', 'All'], ['apparel', 'Apparel'], ['accessories', 'Accessories'], ['digital', 'Digital']] as const;

export function StoreScreen({ navigation }: any) {
  const products = useProducts();
  const [cat, setCat] = useState<string>('all');
  const { width } = useWindowDimensions();
  const cols = width >= 600 ? 3 : 2;
  const tileW = Math.floor((width - 32 - 12 * (cols - 1)) / cols);
  const list = (products.data ?? []).filter((p) => cat === 'all' || p.category === cat);
  return (
    <Screen onRefresh={products.refresh} refreshing={products.loading}>
      <Stale error={products.error} onRetry={products.refresh} />
      <Pressable style={st.banner} onPress={() => navigation.navigate('Product', { productId: 'prod-jersey-001' })} accessibilityRole="button" accessibilityLabel="New season. The 2026 kits have landed">
        <View style={{ flex: 1, padding: 18 }}>
          <Caps style={{ color: '#CFF5DD' }}>New season</Caps>
          <Display style={{ fontSize: 30, lineHeight: 30, marginTop: 8 }}>The 2026 kits{'\n'}have landed</Display>
          <Row gap={6} style={{ marginTop: 12 }}><Text style={{ fontWeight: '600', fontSize: 13 }}>Shop the home kit</Text><Icon name="arrow-right" size={16} /></Row>
        </View>
        <Image source={promoKit} style={st.bannerImg} />
      </Pressable>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginVertical: 14, flexGrow: 0 }}>
        {CATS.map(([k, l]) => <Chip key={k} label={l} selected={cat === k} onPress={() => setCat(k)} />)}
      </ScrollView>
      <View style={st.grid}>
        {list.map((p) => {
          const stock = p.variants.reduce((n, v) => n + v.stock, 0);
          const tag = stock === 0 ? null : stock === 1 ? 'Last one' : stock <= 10 ? 'Low stock' : null;
          return (
            <Pressable key={p.product_id} style={[st.tile, { width: tileW }]} onPress={() => navigation.navigate('Product', { productId: p.product_id })}
              accessibilityRole="button" accessibilityLabel={`${p.name}, ${money(p.price_minor)}${stock === 0 ? ', sold out' : tag ? `, ${tag}` : ''}`}>
              <View>
                <Image source={productImage(p.product_id)} style={{ width: tileW, height: tileW, backgroundColor: C.card2 }} />
                {tag ? <Pill label={tag} tone="warn" style={st.tag} /> : null}
                {stock === 0 ? <View style={st.soldOut}><Text style={{ fontWeight: '700' }}>Sold out</Text></View> : null}
              </View>
              <View style={{ padding: 12 }}>
                <Text style={{ fontWeight: '600', fontSize: 14 }} numberOfLines={2}>{p.name}</Text>
                <Text style={{ color: C.text2, marginTop: 4, fontSize: 13 }}>{money(p.price_minor)}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>
      {!list.length ? <EmptyState title="Nothing here yet" message="Try another category." icon="shopping-outline" /> : null}
    </Screen>
  );
}

export function ProductScreen({ route, navigation }: any) {
  const products = useProducts();
  const p = products.data?.find((x) => x.product_id === route.params.productId);
  const [variantId, setVariantId] = useState<string | null>(null);
  const [qty, setQty] = useState(1);
  const add = useCart((s) => s.add);
  const { width } = useWindowDimensions();
  if (!p) return <Screen><Empty title="This item isn’t available" message="Go back to the store and pull to refresh." icon="shopping-outline" /></Screen>;
  const ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];
  const variants = [...p.variants].sort((a, b) => (ORDER.indexOf(a.size) + 1 || 99) - (ORDER.indexOf(b.size) + 1 || 99));
  const v = variants.find((x) => x.variant_id === variantId) ?? variants.find((x) => x.stock > 0) ?? variants[0];
  const max = Math.max(1, Math.min(10, v.stock));
  return (
    <Screen>
      <Image source={productImage(p.product_id)} style={{ width: width - 32, height: (width - 32) * 0.75, borderRadius: 20, backgroundColor: C.card }} accessibilityLabel={p.name} />
      <Caps style={{ marginTop: 16 }}>{p.category}</Caps>
      <Text style={{ fontSize: 20, fontWeight: '700', marginTop: 6 }}>{p.name}</Text>
      <Score style={{ color: C.lime, marginTop: 8 }}>{money(v.price_minor)}</Score>
      <Muted style={{ marginTop: 6 }}>{p.description}</Muted>
      <Section title="Size" />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: 10 }}>
        {variants.map((x) => (
          <Chip key={x.variant_id} label={x.size} selected={x.variant_id === v.variant_id} disabled={x.stock <= 0} strike={x.stock <= 0}
            onPress={() => { setVariantId(x.variant_id); setQty(1); }} />
        ))}
      </View>
      <Row gap={6} style={{ marginTop: 12 }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: v.stock > 10 ? C.ok : v.stock > 0 ? C.warn : C.live }} />
        <Muted>{v.stock > 0 ? `${v.stock} left in this size · ${v.color}` : 'Sold out in this size'}</Muted>
      </Row>
      <Section title="Quantity" />
      <Row gap={16}>
        <Pressable style={st.qty} onPress={() => setQty(Math.max(1, qty - 1))} accessibilityRole="button" accessibilityLabel="Decrease quantity"><Icon name="minus" /></Pressable>
        <Score accessibilityLabel={`Quantity ${qty}`}>{qty}</Score>
        <Pressable style={st.qty} onPress={() => setQty(Math.min(max, qty + 1))} accessibilityRole="button" accessibilityLabel="Increase quantity"><Icon name="plus" /></Pressable>
      </Row>
      <Row gap={10} style={{ marginTop: 22 }}>
        <Btn kind="outline" label="Add to cart" disabled={v.stock <= 0} style={{ flex: 1 }}
          onPress={() => { add(p, v, qty); toast(`${p.name} (${v.size}) added to your cart`); }} />
        <Btn label="Buy now" disabled={v.stock <= 0} style={{ flex: 1 }} onPress={() => { add(p, v, qty); navigation.navigate('Cart'); }} />
      </Row>
    </Screen>
  );
}

const CARDS: { value: actions.PaymentToken; label: string; hint: string }[] = [
  { value: 'tok_success', label: 'Test card · payment succeeds', hint: '4242 •••• •••• 4242' },
  { value: 'tok_declined', label: 'Test card · bank declines', hint: '4000 •••• •••• 0002' },
  { value: 'tok_capture_fail', label: 'Test card · approved, then fails', hint: '4000 •••• •••• 0341' },
];
const VALID_CODES: Record<string, number> = { WELCOME10: 10 };

export function CartScreen({ navigation }: any) {
  const { lines, setQty, remove } = useCart();
  const [code, setCode] = useState('');
  const [applied, setApplied] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const subtotal = lines.reduce((s, l) => s + l.variant.price_minor * l.quantity, 0);
  const discount = applied ? Math.floor((subtotal * VALID_CODES[applied]) / 100) : 0;
  if (!lines.length) {
    return <Screen><EmptyState title="Your cart is empty" message="Kits, scarves and caps from your club are in the store." icon="cart-outline"
      action="Browse the store" onAction={() => navigation.navigate('Tabs', { screen: 'Store' })} /></Screen>;
  }
  return (
    <Screen>
      {lines.map((l) => (
        <Card key={l.variant.variant_id} style={{ marginBottom: 10, padding: 12 }}>
          <Row gap={12}>
            <Image source={productImage(l.product.product_id)} style={st.lineImg} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '600' }} numberOfLines={1}>{l.product.name}</Text>
              <Muted style={{ fontSize: 12 }}>Size {l.variant.size} · {money(l.variant.price_minor)}</Muted>
              <Row gap={10} style={{ marginTop: 8 }}>
                <Pressable style={st.qtySm} onPress={() => setQty(l.variant.variant_id, l.quantity - 1)} accessibilityLabel="Decrease quantity"><Icon name="minus" size={18} /></Pressable>
                <Text style={{ fontWeight: '700', minWidth: 16, textAlign: 'center' }}>{l.quantity}</Text>
                <Pressable style={st.qtySm} onPress={() => setQty(l.variant.variant_id, Math.min(l.variant.stock, l.quantity + 1))} accessibilityLabel="Increase quantity"><Icon name="plus" size={18} /></Pressable>
              </Row>
            </View>
            <Pressable onPress={() => remove(l.variant.variant_id)} hitSlop={8} accessibilityRole="button" accessibilityLabel={`Remove ${l.product.name}`} style={st.qtySm}>
              <Icon name="trash-can-outline" size={20} color={C.err} />
            </Pressable>
          </Row>
        </Card>
      ))}
      <Section title="Discount code" />
      {applied ? (
        <Row style={st.applied} gap={10}>
          <Icon name="ticket-percent-outline" color={C.okText} />
          <Text style={{ flex: 1, color: C.okText, fontWeight: '600' }}>{applied} applied · {VALID_CODES[applied]}% off</Text>
          <Pressable onPress={() => setApplied(null)} hitSlop={12} accessibilityRole="button" accessibilityLabel="Remove discount code"><Icon name="close" color={C.okText} /></Pressable>
        </Row>
      ) : (
        <Row gap={10}>
          <TextInput value={code} onChangeText={(t) => { setCode(t); setCodeError(null); }} placeholder="Enter a code" placeholderTextColor={C.dim}
            autoCapitalize="characters" style={[st.input, { flex: 1 }, codeError ? { borderColor: C.errBorder } : null]} accessibilityLabel="Discount code" />
          <Btn kind="secondary" small label="Apply" onPress={() => {
            const c = code.trim().toUpperCase();
            if (VALID_CODES[c]) { setApplied(c); setCode(''); } else setCodeError('That code isn’t valid. Check the spelling and try again.');
          }} style={{ paddingHorizontal: 18, minHeight: 52 }} />
        </Row>
      )}
      {codeError ? <Row gap={6} style={{ marginTop: 6 }}><Icon name="alert-circle" size={16} color={C.err} /><Text style={{ color: C.err, fontSize: 13 }}>{codeError}</Text></Row> : null}
      <Card style={{ marginTop: 16 }}>
        <Row style={st.sum}><Muted>Subtotal</Muted><Text>{money(subtotal)}</Text></Row>
        <Row style={st.sum}><Muted>Discount</Muted><Text style={{ color: discount ? C.okText : C.text }}>{discount ? `− ${money(discount)}` : money(0)}</Text></Row>
        <Row style={st.sum}><Muted>Delivery</Muted><Text>Free</Text></Row>
        <View style={{ height: 1, backgroundColor: C.divider, marginVertical: 8 }} />
        <Row style={st.sum}><Text style={{ fontWeight: '700' }}>Total</Text><Score style={{ fontSize: 24 }}>{money(subtotal - discount)}</Score></Row>
      </Card>
      <Btn label="Checkout" icon="lock-outline" onPress={() => navigation.navigate('Checkout', { code: applied })} style={{ marginTop: 16 }} />
    </Screen>
  );
}

type Step = 'idle' | 'running' | 'done' | 'fail';
const STEPS = ['Creating order', 'Authorising', 'Capturing', 'Confirming'];

export function CheckoutScreen({ route, navigation }: any) {
  const code: string | null = route.params?.code ?? null;
  const { lines } = useCart();
  const online = useNet((s) => s.online);
  const insets = useSafeAreaInsets();
  const [method, setMethod] = useState<'delivery' | 'pickup'>('delivery');
  const [card, setCard] = useState<actions.PaymentToken>('tok_success');
  const [overlay, setOverlay] = useState(false);
  const [steps, setSteps] = useState<Step[]>(['idle', 'idle', 'idle', 'idle']);
  const [failure, setFailure] = useState<string | null>(null);
  const [paying, setPaying] = useState(0);
  const subtotal = lines.reduce((s, l) => s + l.variant.price_minor * l.quantity, 0);
  const discount = code ? Math.floor((subtotal * (VALID_CODES[code] ?? 0)) / 100) : 0;
  const total = subtotal - discount;
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const pay = async () => {
    setFailure(null);
    setPaying(total);
    setOverlay(true);
    const mark = (i: number, s: Step) => setSteps((prev) => prev.map((x, j) => (j === i ? s : x)));
    setSteps(['running', 'idle', 'idle', 'idle']);
    const call = actions.checkout(lines, code, card);
    await wait(500); mark(0, 'done'); mark(1, 'running');
    try {
      const r = await call;
      await wait(400); mark(1, 'done'); mark(2, 'running');
      await wait(400); mark(2, 'done'); mark(3, 'running');
      await wait(350); mark(3, 'done');
      await wait(300);
      setOverlay(false);
      // Store → Receipt: Back from the receipt returns to the store, not to an empty cart.
      navigation.popToTop();
      navigation.navigate('Receipt', { orderId: r.order_id });
    } catch (e) {
      const err = e as ApiError;
      if (err.code === 'PAYMENT_CAPTURE_FAILED') {
        mark(1, 'done'); mark(2, 'fail');
        setFailure('The bank approved the payment, but we couldn’t complete it. The hold on your card has been released and you haven’t been charged.');
      } else if (err.code === 'PAYMENT_DECLINED') {
        mark(1, 'fail');
        setFailure('Your card was declined by the bank. No money was taken.');
      } else {
        mark(1, 'fail');
        setFailure(err.message ?? 'Something went wrong. No money was taken.');
      }
    }
  };

  return (
    <Screen>
      <Section title="How do you want it?" />
      <Row gap={10}>
        {([['delivery', 'truck-delivery-outline', 'Delivery', '2–3 days · Free'], ['pickup', 'storefront-outline', 'Pickup', 'Club shop · Free']] as const).map(([k, ic, l, sub]) => (
          <Card key={k} selected={method === k} onPress={() => setMethod(k)} style={{ flex: 1, padding: 14 }} accessibilityLabel={`${l}, ${sub}`}>
            <Icon name={ic} size={22} color={method === k ? C.lime : C.text2} />
            <Text style={{ fontWeight: '600', marginTop: 8 }}>{l}</Text><Muted style={{ fontSize: 12 }}>{sub}</Muted>
          </Card>
        ))}
      </Row>
      <Section title="Pay with a test card" />
      {CARDS.map((c) => (
        <Card key={c.value} selected={card === c.value} onPress={() => setCard(c.value)} style={{ marginBottom: 8, padding: 14 }} accessibilityLabel={c.label}>
          <Row gap={12}>
            <Icon name={card === c.value ? 'radiobox-marked' : 'radiobox-blank'} color={card === c.value ? C.lime : C.dim} />
            <View style={{ flex: 1 }}><Text style={{ fontWeight: '600' }}>{c.label}</Text><Mono>{c.hint}</Mono></View>
            <Icon name="credit-card-outline" color={C.faint} />
          </Row>
        </Card>
      ))}
      <Card style={{ marginTop: 8 }}>
        <Row style={st.sum}><Muted>Items</Muted><Text>{money(subtotal)}</Text></Row>
        {discount ? <Row style={st.sum}><Muted>Discount ({code})</Muted><Text style={{ color: C.okText }}>− {money(discount)}</Text></Row> : null}
        <Row style={st.sum}><Muted>{method === 'delivery' ? 'Delivery' : 'Pickup'}</Muted><Text>Free</Text></Row>
        <View style={{ height: 1, backgroundColor: C.divider, marginVertical: 8 }} />
        <Row style={st.sum}><Text style={{ fontWeight: '700' }}>Total</Text><Score style={{ fontSize: 24 }}>{money(total)}</Score></Row>
      </Card>
      {!online ? (
        <Row style={st.offline} gap={10}><Icon name="cloud-off-outline" color={C.offText} /><Text style={{ color: C.offText, flex: 1, fontSize: 13 }}>Payments need a connection. Reconnect to pay. Your cart is saved.</Text></Row>
      ) : null}
      <Btn label={`Pay ${money(total)}`} icon="lock-outline" disabled={!online || !lines.length} onPress={pay} style={{ marginTop: 16 }} />
      <Muted style={{ textAlign: 'center', marginTop: 8, fontSize: 12 }}>Mock payment gateway. No real money moves.</Muted>

      <Modal visible={overlay} animationType="fade" onRequestClose={() => failure && setOverlay(false)} statusBarTranslucent>
        <View style={[st.overlay, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }]}>
          <Text style={{ fontSize: 20, fontWeight: '700' }}>{failure ? 'Payment didn’t go through' : 'Processing your payment'}</Text>
          <Muted style={{ marginTop: 6, marginBottom: 24 }}>{failure ? 'Nothing was charged.' : `Paying ${money(paying)}. Please keep the app open.`}</Muted>
          {STEPS.map((label, i) => (
            <Row key={label} style={st.step} gap={14}>
              <View style={[st.stepIcon, steps[i] === 'done' && { backgroundColor: C.lime }, steps[i] === 'fail' && { backgroundColor: C.live }]}>
                {steps[i] === 'running' ? <ActivityIndicator color={C.lime} size="small" /> : steps[i] === 'done' ? <Icon name="check" size={18} color={C.onLime} />
                  : steps[i] === 'fail' ? <Icon name="close" size={18} color="#fff" /> : <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.dim }} />}
              </View>
              <Text style={{ fontSize: 16, fontWeight: steps[i] === 'idle' ? '400' : '600', color: steps[i] === 'idle' ? C.faint : C.text }}>{label}</Text>
            </Row>
          ))}
          {failure ? (
            <>
              <Row style={[st.offline, { backgroundColor: C.errSurface, borderColor: C.errBorder, marginTop: 24 }]} gap={10}>
                <Icon name="alert-circle-outline" color={C.err} /><Text style={{ color: C.errText2, flex: 1 }}>{failure}</Text>
              </Row>
              <View style={{ flex: 1 }} />
              <Row gap={10}>
                <Btn kind="outline" label="Back to cart" onPress={() => { setOverlay(false); navigation.goBack(); }} style={{ flex: 1 }} />
                <Btn label="Try again" onPress={() => setOverlay(false)} style={{ flex: 1 }} />
              </Row>
            </>
          ) : null}
        </View>
      </Modal>
    </Screen>
  );
}

export function ReceiptScreen({ route, navigation }: any) {
  const { orderId } = route.params;
  const r = useCached<Receipt>(`receipt:${orderId}`, () => api.receipt(orderId));
  const order = cacheGet<CheckoutResult>(`order:${orderId}`)?.data;
  const [paper, setPaper] = useState(false);
  const products = useProducts();
  const rec = r.data ?? cacheGet<Receipt>(`receipt:${orderId}`)?.data;
  const itemName = (vid: string) => {
    for (const pr of products.data ?? []) {
      const va = pr.variants.find((x) => x.variant_id === vid);
      if (va) return `${pr.name} · ${va.size}`;
    }
    return vid;
  };
  if (!rec) return <Screen><Stale error={r.error} onRetry={r.refresh} /></Screen>;
  const p = rec.payload;
  return (
    <Screen>
      <View style={{ alignItems: 'center', marginVertical: 14 }}>
        <View style={st.okCircle}><Icon name="check" size={34} color={C.onLime} /></View>
        <Display style={{ marginTop: 14, fontSize: 30 }}>Payment complete</Display>
        <Muted style={{ marginTop: 4 }}>Thanks! Your order is confirmed.</Muted>
        <Mono style={{ marginTop: 6 }}>{p.order_id}</Mono>
      </View>
      <Card>
        {p.items.map((i) => (
          <Row key={i.variant_id} style={st.sum}><Text style={{ flex: 1 }} numberOfLines={2}>{itemName(i.variant_id)} × {i.quantity}</Text><Text>{money(i.unit_price_minor * i.quantity)}</Text></Row>
        ))}
        <View style={{ height: 1, backgroundColor: C.divider, marginVertical: 8 }} />
        <Row style={st.sum}><Muted>Subtotal</Muted><Text>{money(p.subtotal_minor)}</Text></Row>
        <Row style={st.sum}><Muted>Discount</Muted><Text>− {money(p.discount_minor)}</Text></Row>
        <Row style={st.sum}><Text style={{ fontWeight: '700' }}>Total paid</Text><Score style={{ fontSize: 24, color: C.lime }}>{money(p.total_minor)}</Score></Row>
      </Card>
      <Card style={{ marginTop: 12, padding: 0 }}>
        <Row style={st.meta}><Muted>Paid at</Muted><Mono style={{ color: C.text }}>{new Date(p.paid_at).toLocaleString()}</Mono></Row>
        {order?.payment ? <Row style={st.meta}><Muted>Authorisation</Muted><Mono style={{ color: C.text }}>{order.payment.authorization_id}</Mono></Row> : null}
        {order?.payment ? <Row style={st.meta}><Muted>Capture</Muted><Mono style={{ color: C.text }}>{order.payment.capture_id}</Mono></Row> : null}
        <Row style={st.meta}><Muted>Signature</Muted><Mono style={{ color: C.text }}>{rec.signature.slice(0, 16)}…</Mono></Row>
      </Card>
      <Btn label="View receipt" icon="file-document-outline" onPress={() => setPaper(true)} style={{ marginTop: 16 }} />
      <Btn kind="outline" label="Back to the store" onPress={() => navigation.navigate('Tabs', { screen: 'Store' })} style={{ marginTop: 10 }} />
      <Sheet visible={paper} onClose={() => setPaper(false)}
        actions={<><Btn kind="outline" label="Close" onPress={() => setPaper(false)} style={{ flex: 1 }} /><Btn label="Download PDF" icon="download" style={{ flex: 1.3 }}
          onPress={async () => { try { await actions.openReceiptPdf(rec); } catch { toast('Couldn’t open the PDF on this phone', 'warn'); } }} /></>}>
        <View style={st.paper}>
          <Text style={{ color: C.ink, fontFamily: F.display, fontSize: 24 }}>ALPHA LEAGUE · RECEIPT</Text>
          <Text style={{ color: '#5A5F66', fontFamily: F.mono, fontSize: 11, marginTop: 2 }}>{p.order_id}</Text>
          <View style={{ height: 1, backgroundColor: C.rule, marginVertical: 10 }} />
          {p.items.map((i) => (
            <Row key={i.variant_id} style={{ justifyContent: 'space-between', marginBottom: 4 }}>
              <Text style={{ color: C.ink, fontSize: 13, flex: 1 }} numberOfLines={2}>{itemName(i.variant_id)} × {i.quantity}</Text>
              <Text style={{ color: C.ink, fontFamily: F.mono, fontSize: 12 }}>{money(i.unit_price_minor * i.quantity)}</Text>
            </Row>
          ))}
          <View style={{ height: 1, backgroundColor: C.rule, marginVertical: 10 }} />
          <Row style={{ justifyContent: 'space-between' }}><Text style={{ color: C.ink, fontWeight: '700' }}>Total</Text><Text style={{ color: C.ink, fontFamily: F.monoMedium }}>{money(p.total_minor)}</Text></Row>
          <Text style={{ color: '#5A5F66', fontFamily: F.mono, fontSize: 10, marginTop: 10 }}>HMAC {rec.signature}</Text>
        </View>
      </Sheet>
    </Screen>
  );
}

export function OrdersScreen({ navigation }: any) {
  const orders = useOrders();
  return (
    <Screen onRefresh={orders.refresh} refreshing={orders.loading}>
      <Stale error={orders.error} onRetry={orders.refresh} />
      {orders.data?.map((o) => (
        <Card key={o.order_id} style={{ marginBottom: 10 }} onPress={() => navigation.navigate('Receipt', { orderId: o.order_id })}>
          <Row style={{ justifyContent: 'space-between' }}>
            <View style={{ flex: 1 }}><Text style={{ fontWeight: '700' }}>{money(o.total_minor)}</Text><Mono numberOfLines={1}>{o.order_id}</Mono><Muted style={{ fontSize: 12 }}>{new Date(o.created_at).toLocaleString()}</Muted></View>
            <Pill label={o.status === 'paid' ? 'Paid' : o.status} tone="ok" icon="check" />
          </Row>
        </Card>
      ))}
      {!orders.data?.length ? <EmptyState title="No orders yet" message="Your purchases and receipts appear here." icon="receipt" /> : null}
    </Screen>
  );
}

const st = StyleSheet.create({
  banner: { flexDirection: 'row', alignItems: 'stretch', backgroundColor: '#2F8F62', borderRadius: 22, overflow: 'hidden', minHeight: 150 },
  bannerImg: { width: 130, height: '100%', minHeight: 150 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile: { backgroundColor: C.card, borderRadius: 18, borderWidth: 1, borderColor: C.border, overflow: 'hidden' },
  tag: { position: 'absolute', top: 8, left: 8 },
  soldOut: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(14,16,20,0.66)', alignItems: 'center', justifyContent: 'center' },
  qty: { width: 48, height: 48, borderRadius: 24, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' },
  qtySm: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' },
  lineImg: { width: 72, height: 72, borderRadius: 12 },
  input: { backgroundColor: C.card, color: C.text, borderRadius: 12, borderWidth: 1, borderColor: C.border2, paddingHorizontal: 16, minHeight: 52, fontSize: 15, fontFamily: F.regular },
  applied: { backgroundColor: C.okBg, borderRadius: 12, paddingHorizontal: 14, minHeight: 52 },
  sum: { justifyContent: 'space-between', paddingVertical: 4 },
  meta: { justifyContent: 'space-between', paddingHorizontal: 16, minHeight: 44, borderTopWidth: 1, borderTopColor: C.divider, marginTop: -1 },
  offline: { backgroundColor: C.offSurface, borderWidth: 1, borderColor: C.offBorder, borderRadius: 12, padding: 12, marginTop: 14 },
  overlay: { flex: 1, backgroundColor: C.bg, paddingHorizontal: 24 },
  step: { minHeight: 56 },
  stepIcon: { width: 32, height: 32, borderRadius: 16, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' },
  okCircle: { width: 64, height: 64, borderRadius: 32, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center' },
  paper: { backgroundColor: C.paper, borderRadius: 14, padding: 18, elevation: 8 },
});
