// Alpha League design system: exact tokens from design_handoff_alpha_league/README.md.
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { DarkTheme as NavDark } from '@react-navigation/native';
import React from 'react';
import {
  ActivityIndicator, Image, ImageSourcePropType, Modal, Pressable, Text as RNText, StyleProp, StyleSheet, TextProps,
  TextStyle, View, ViewStyle,
} from 'react-native';
import { MD3DarkTheme } from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const C = {
  bg: '#0E1014', bgSplash: '#0B0D10', card: '#16191E', card2: '#1C1F25', card3: '#22262D', divider: '#1F2329',
  border: '#23272E', border2: '#2A2E35', borderStrong: '#3A3F47',
  text: '#F3F1EA', text2: '#C9CDD3', muted: '#A3A9B2', faint: '#8E959F', dim: '#6A7079',
  lime: '#D6FF41', limeHover: '#E2FF6E', limeTint: '#1B1F16', onLime: '#0E1014',
  ok: '#43D29A', okText: '#6FE3B4', okBg: 'rgba(67,210,154,0.13)',
  warn: '#FFB648', warnText: '#FFC46E', warnBg: 'rgba(255,182,72,0.13)',
  live: '#FF5247', err: '#FF8A80', errText2: '#FFB3AA', errBg: 'rgba(255,82,71,0.13)', errSurface: '#2A1414', errBorder: '#5A2626',
  offSurface: '#231C10', offBorder: '#4A3818', offText: '#FFD9A0',
  info: '#3A63DB', infoText: '#C3D1FF', infoBg: 'rgba(58,99,219,0.16)',
  paper: '#FBFAF6', ink: '#14171B', rule: '#DDD9CF',
};
// Back-compat aliases used across screens
export const R = { chip: 7, input: 12, btn: 14, card: 18, hero: 22, sheet: 26, pill: 99 };

export const F = {
  display: 'BarlowCondensed-ExtraBold', displayBold: 'BarlowCondensed-Bold',
  regular: 'Geist-Regular', medium: 'Geist-Medium', semibold: 'Geist-SemiBold', bold: 'Geist-Bold',
  mono: 'GeistMono-Regular', monoMedium: 'GeistMono-Medium',
};
export const FONT_FILES = {
  'BarlowCondensed-ExtraBold': require('../../assets/fonts/BarlowCondensed-ExtraBold.ttf'),
  'BarlowCondensed-Bold': require('../../assets/fonts/BarlowCondensed-Bold.ttf'),
  'Geist-Regular': require('../../assets/fonts/Geist-Regular.ttf'),
  'Geist-Medium': require('../../assets/fonts/Geist-Medium.ttf'),
  'Geist-SemiBold': require('../../assets/fonts/Geist-SemiBold.ttf'),
  'Geist-Bold': require('../../assets/fonts/Geist-Bold.ttf'),
  'GeistMono-Regular': require('../../assets/fonts/GeistMono-Regular.ttf'),
  'GeistMono-Medium': require('../../assets/fonts/GeistMono-Medium.ttf'),
};
export const LOGO = require('../../assets/design/logo.jpg');

const WEIGHT_FAMILY: Record<string, string> = {
  '100': F.regular, '200': F.regular, '300': F.regular, '400': F.regular, normal: F.regular,
  '500': F.medium, '600': F.semibold, '700': F.bold, '800': F.bold, '900': F.bold, bold: F.bold,
};

/** Text with Geist by default; fontWeight picks the matching static Geist face. */
export function Text({ style, ...p }: TextProps & { style?: StyleProp<TextStyle> }) {
  const flat = (StyleSheet.flatten(style) ?? {}) as TextStyle;
  const family = flat.fontFamily ?? WEIGHT_FAMILY[String(flat.fontWeight ?? '400')] ?? F.regular;
  return <RNText {...p} style={[{ color: C.text }, style, { fontFamily: family, fontWeight: 'normal' }]} />;
}

export const paperTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors, primary: C.lime, onPrimary: C.onLime, background: C.bg, surface: C.card,
    surfaceVariant: C.card2, onSurface: C.text, onSurfaceVariant: C.muted, outline: C.border2, error: C.err,
  },
};
export const navTheme = {
  ...NavDark,
  colors: { ...NavDark.colors, primary: C.lime, background: C.bg, card: C.bg, text: C.text, border: C.border, notification: C.live },
};

type TP = TextProps & { style?: StyleProp<TextStyle> };
export const Display = ({ style, ...p }: TP) => <Text {...p} style={[s.display, style]} />;
export const Title = ({ style, ...p }: TP) => <Text {...p} style={[s.title, style]} />;
export const Body = ({ style, ...p }: TP) => <Text {...p} style={[s.body, style]} />;
export const Muted = ({ style, ...p }: TP) => <Text {...p} style={[s.muted, style]} />;
export const Caps = ({ style, ...p }: TP) => <Text {...p} style={[s.caps, style]} />;
export const Score = ({ style, ...p }: TP) => <Text {...p} style={[s.score, style]} />;
export const Mono = ({ style, ...p }: TP) => <Text {...p} style={[{ fontFamily: F.mono, fontSize: 12, color: C.muted }, style]} />;

export type IconName = keyof typeof MaterialCommunityIcons.glyphMap;
export function Icon({ name, size = 20, color = C.text }: { name: IconName; size?: number; color?: string }) {
  return <MaterialCommunityIcons name={name} size={size} color={color} />;
}

export function Card({ children, style, onPress, accessibilityLabel, selected }: {
  children: React.ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void; accessibilityLabel?: string; selected?: boolean;
}) {
  const sel = selected ? { backgroundColor: C.limeTint, borderColor: C.lime, borderWidth: 2 } : null;
  if (onPress) {
    return (
      <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={accessibilityLabel}
        style={({ pressed }) => [s.card, sel, style, pressed && { backgroundColor: C.card2 }]}>{children}</Pressable>
    );
  }
  return <View style={[s.card, sel, style]}>{children}</View>;
}

export function Row({ children, style, gap = 8 }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; gap?: number }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center', gap }, style]}>{children}</View>;
}

export function Section({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return (
    <Row style={{ justifyContent: 'space-between', marginTop: 20, marginBottom: 10 }}>
      <Caps>{title}</Caps>
      {action ? <Pressable onPress={onAction} hitSlop={14} accessibilityRole="button"><Text style={{ color: C.lime, fontWeight: '600', fontSize: 13 }}>{action}</Text></Pressable> : null}
    </Row>
  );
}

export type Tone = 'lime' | 'live' | 'ok' | 'warn' | 'err' | 'info' | 'neutral';
const TONES: Record<Tone, [string, string]> = {
  lime: ['rgba(214,255,65,0.14)', C.lime], live: [C.errBg, C.err], ok: [C.okBg, C.okText], warn: [C.warnBg, C.warnText],
  err: [C.errBg, C.err], info: [C.infoBg, C.infoText], neutral: [C.card3, C.text2],
};

export function Pill({ label, tone = 'neutral', icon, dot, onPress, style }: {
  label: string; tone?: Tone; icon?: IconName; dot?: boolean; onPress?: () => void; style?: StyleProp<ViewStyle>;
}) {
  const [bg, fg] = TONES[tone];
  const inner = (
    <View style={[s.pill, { backgroundColor: bg }, style]}>
      {dot ? <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: tone === 'ok' ? C.ok : tone === 'live' ? C.live : fg }} /> : null}
      {icon ? <Icon name={icon} size={14} color={fg} /> : null}
      <Text style={{ color: fg, fontWeight: '600', fontSize: 12 }} numberOfLines={1}>{label}</Text>
    </View>
  );
  return onPress ? <Pressable onPress={onPress} accessibilityRole="button" hitSlop={8}>{inner}</Pressable> : inner;
}

export function Chip({ label, selected, onPress, icon, disabled, strike }: {
  label: string; selected?: boolean; onPress?: () => void; icon?: IconName; disabled?: boolean; strike?: boolean;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityState={{ selected: !!selected, disabled: !!disabled }}
      style={[s.chip, selected && { backgroundColor: C.text, borderColor: C.text }, disabled && { opacity: 0.4 }]}>
      {icon ? <Icon name={icon} size={16} color={selected ? C.onLime : C.text2} /> : null}
      <Text style={{ color: selected ? C.onLime : C.text2, fontWeight: '500', fontSize: 14, textDecorationLine: strike ? 'line-through' : 'none' }}>{label}</Text>
    </Pressable>
  );
}

export function Btn({ label, onPress, kind = 'primary', icon, disabled, loading, style, small }: {
  label: string; onPress?: () => void; kind?: 'primary' | 'secondary' | 'outline' | 'danger' | 'dangerSolid' | 'light';
  icon?: IconName; disabled?: boolean; loading?: boolean; style?: StyleProp<ViewStyle>; small?: boolean;
}) {
  const map = {
    primary: [C.lime, C.onLime, C.lime], secondary: [C.card3, C.text, C.card3], outline: ['transparent', C.text, C.borderStrong],
    danger: ['transparent', C.err, C.errBorder], dangerSolid: [C.live, '#fff', C.live], light: [C.text, C.onLime, C.text],
  } as const;
  const [bg, fg, border] = map[kind];
  return (
    <Pressable onPress={onPress} disabled={disabled || loading} accessibilityRole="button" accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled, busy: !!loading }}
      style={({ pressed }) => [s.btn, small && { minHeight: 44, borderRadius: 12 }, { backgroundColor: pressed && kind === 'primary' ? C.limeHover : bg, borderColor: border, opacity: disabled ? 0.45 : 1 }, style]}>
      {loading ? <ActivityIndicator color={fg} /> : (
        <Row gap={8}>{icon ? <Icon name={icon} size={20} color={fg} /> : null}<Text style={{ color: fg, fontWeight: '600', fontSize: small ? 14 : 16 }}>{label}</Text></Row>
      )}
    </Pressable>
  );
}

export function ListRow({ icon, title, subtitle, right, onPress, danger, badge }: {
  icon?: IconName; title: string; subtitle?: string; right?: React.ReactNode; onPress?: () => void; danger?: boolean; badge?: number;
}) {
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : undefined}
      style={({ pressed }) => [s.listRow, pressed && { backgroundColor: C.card2 }]}>
      {icon ? <View style={s.iconTile}><Icon name={icon} size={20} color={danger ? C.err : C.text2} /></View> : null}
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 15, fontWeight: '500', color: danger ? C.err : C.text }} numberOfLines={2}>{title}</Text>
        {subtitle ? <Text style={{ fontSize: 12, color: C.muted, marginTop: 2 }} numberOfLines={3}>{subtitle}</Text> : null}
      </View>
      {badge ? <View style={s.badge}><Text style={{ color: C.onLime, fontWeight: '700', fontSize: 12 }}>{badge}</Text></View> : null}
      {right ?? (onPress ? <Icon name="chevron-right" size={22} color={C.dim} /> : null)}
    </Pressable>
  );
}

const BADGE_COLORS = ['#2F8F62', '#3A63DB', '#CF4436', '#7B5CF0', '#C9821E', '#00897B', '#B8860B', '#455A64'];
// Fixed club colours (like the handoff's seed data); any other club falls back to a stable hash colour.
const CLUB_COLORS: Record<string, string> = {
  'Alpha Lions': '#2F8F62', 'Alpha Falcons': '#3A63DB', 'Alpha Tigers': '#CF4436', 'Alpha Wolves': '#7B5CF0',
  'Beta Rangers': '#C9821E', 'Beta Strikers': '#00897B',
};

export function clubColor(name: string): string {
  if (CLUB_COLORS[name]) return CLUB_COLORS[name];
  // 32-bit FNV-1a: a plain h*31 overflows float precision and maps different names to the same colour.
  let h = 0x811c9dc5;
  for (let i = 0; i < name.length; i++) h = Math.imul(h ^ name.charCodeAt(i), 0x01000193);
  return BADGE_COLORS[(h >>> 0) % BADGE_COLORS.length];
}
export function initials(name: string, n = 3) {
  return name.split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, n).toUpperCase();
}

/** Image with fallback: initials on the club colour (never a broken image). */
export function TeamBadge({ name, source, size = 32 }: { name: string; source?: ImageSourcePropType; size?: number }) {
  if (source) return <Image source={source} style={{ width: size, height: size, borderRadius: size / 2 }} accessibilityIgnoresInvertColors />;
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: clubColor(name), alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: '#fff', fontFamily: F.display, fontSize: size * 0.36 }}>{initials(name)}</Text>
    </View>
  );
}

export function EmptyState({ icon = 'inbox-outline', title, message, action, onAction, dashed = true }: {
  icon?: IconName; title: string; message?: string; action?: string; onAction?: () => void; dashed?: boolean;
}) {
  return (
    <View style={[{ alignItems: 'center', padding: 24, gap: 6, borderRadius: 16 }, dashed && { borderWidth: 1, borderStyle: 'dashed', borderColor: C.borderStrong }]}>
      <Icon name={icon} size={30} color={C.faint} />
      <Text style={{ fontWeight: '600', fontSize: 15 }}>{title}</Text>
      {message ? <Muted style={{ textAlign: 'center' }}>{message}</Muted> : null}
      {action ? <Btn kind="outline" small label={action} onPress={onAction} style={{ marginTop: 8 }} /> : null}
    </View>
  );
}

/** Bottom sheet (all confirmations + secondary actions). Cancel left as outline, CTA right. */
export function Sheet({ visible, onClose, title, children, actions }: {
  visible: boolean; onClose: () => void; title?: string; children?: React.ReactNode; actions?: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <Pressable style={{ flex: 1, backgroundColor: 'rgba(5,6,8,0.66)' }} onPress={onClose} accessibilityLabel="Close" />
      <View style={[s.sheet, { paddingBottom: 16 + insets.bottom }]}>
        <View style={s.handle} />
        {title ? <Text style={{ fontSize: 19, fontWeight: '700', marginBottom: 8 }}>{title}</Text> : null}
        {children}
        {actions ? <Row gap={10} style={{ marginTop: 18 }}>{actions}</Row> : null}
      </View>
    </Modal>
  );
}

export const s = StyleSheet.create({
  display: { color: C.text, fontFamily: F.display, fontSize: 30, lineHeight: 30, textTransform: 'uppercase' },
  title: { color: C.text, fontWeight: '700', fontSize: 18 },
  body: { color: C.text, fontSize: 15, lineHeight: 21 },
  muted: { color: C.muted, fontSize: 13, lineHeight: 19 },
  caps: { color: C.faint, fontSize: 12, fontWeight: '600', letterSpacing: 1.2, textTransform: 'uppercase' },
  score: { color: C.text, fontFamily: F.display, fontSize: 28, lineHeight: 30 },
  card: { backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: R.card, padding: 16, overflow: 'hidden' },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, height: 26, borderRadius: R.pill, alignSelf: 'flex-start' },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 40, paddingHorizontal: 14, borderRadius: R.pill, borderWidth: 1, borderColor: C.border2, marginRight: 8 },
  btn: { minHeight: 54, borderRadius: R.btn, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16 },
  // marginTop -1 tucks the first row's divider under the card border, so only separators between rows show
  listRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56, paddingVertical: 10, paddingHorizontal: 14, borderTopWidth: 1, borderTopColor: C.divider, marginTop: -1 },
  iconTile: { width: 36, height: 36, borderRadius: 10, backgroundColor: C.card3, alignItems: 'center', justifyContent: 'center' },
  badge: { minWidth: 22, height: 22, borderRadius: 11, backgroundColor: C.lime, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
  sheet: { backgroundColor: C.card, borderTopLeftRadius: R.sheet, borderTopRightRadius: R.sheet, padding: 20, paddingTop: 10, borderWidth: 1, borderColor: C.border },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: C.borderStrong, alignSelf: 'center', marginBottom: 14 },
});
