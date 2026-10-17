// Design imagery bundled with the app (works offline). Mapped onto backend ids.
import { ImageSourcePropType } from 'react-native';

const IMG = {
  homeKit: require('../../assets/design/home-kit.jpg'),
  awayKit: require('../../assets/design/away-kit.jpg'),
  scarf: require('../../assets/design/scarf.jpg'),
  cap: require('../../assets/design/cap.jpg'),
  jacket: require('../../assets/design/jacket.jpg'),
  badgeA: require('../../assets/design/badge-mfc.jpg'),
  badgeB: require('../../assets/design/badge-ind.jpg'),
  coach: require('../../assets/design/staff-coach.jpg'),
  manager: require('../../assets/design/staff-manager.jpg'),
  player: require('../../assets/design/player-hamza.jpg'),
  bgFootball: require('../../assets/design/bg-football.jpg'),
  bgBasketball: require('../../assets/design/bg-basketball.jpg'),
  bgCricket: require('../../assets/design/bg-cricket.jpg'),
  bgEsports: require('../../assets/design/bg-esports.jpg'),
};

const PRODUCTS: Record<string, ImageSourcePropType> = {
  'prod-jersey-001': IMG.homeKit, 'prod-scarf-001': IMG.scarf, 'prod-cap-001': IMG.cap,
  'prod-wallpaper-001': IMG.bgFootball, 'prod-beta-shirt-001': IMG.awayKit,
};
const CLUBS: Record<string, ImageSourcePropType> = { 'club-alpha-1': IMG.badgeA, 'club-alpha-2': IMG.badgeB };
const SPORTS_BG: Record<string, ImageSourcePropType> = {
  event: IMG.bgFootball, innings: IMG.bgCricket, round: IMG.bgEsports, basketball: IMG.bgBasketball,
};

export const productImage = (id: string): ImageSourcePropType => PRODUCTS[id] ?? IMG.jacket;
export const clubBadge = (id?: string | null): ImageSourcePropType | undefined => (id ? CLUBS[id] : undefined);
export const staffPhoto = (role: string): ImageSourcePropType | undefined =>
  role === 'coach' ? IMG.coach : role === 'manager' ? IMG.manager : undefined;
export const playerPhoto = IMG.player;
export const promoKit = IMG.homeKit;

/** Sport background: by sport id when we have art for it, else by scoring model. */
export function sportBackground(sportId: string, model: string): ImageSourcePropType {
  return SPORTS_BG[sportId] ?? SPORTS_BG[model] ?? IMG.bgFootball;
}

export function sportIcon(model: string, sportId?: string): 'soccer' | 'cricket' | 'gamepad-variant' | 'basketball' {
  if (sportId === 'basketball') return 'basketball';
  return model === 'innings' ? 'cricket' : model === 'round' ? 'gamepad-variant' : 'soccer';
}
