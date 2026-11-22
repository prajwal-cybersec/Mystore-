/**
 * Single Category -> Try-On Type Mapping File
 * /src/tryon/categoryMap.js
 * 
 * Used by backend backfill scripts and frontend Try-On router.
 * All calibration defaults and tracking methods are mapped here in one central location.
 */

export const TRYON_TYPES = {
  SHIRT: 'shirt',
  TSHIRT: 'tshirt',
  SAREE: 'saree',
  HEADPHONES: 'headphones',
  LIPSTICK: 'lipstick',
  BLUSH: 'blush',
  GLASSES: 'glasses',
  EARRINGS: 'earrings',
  NOSE_PIN: 'nose_pin',
  WATCH: 'watch'
};

export const CATEGORY_MAP = [
  // 1. T-Shirts & Polos
  {
    category: 'Fashion',
    subcategories: ['Women\'s T-shirts', 'T-shirts', 'Polo T-shirts', 'Topwear'],
    keywords: ['t-shirt', 'tshirt', 'tee', 'top'],
    tryon_type: TRYON_TYPES.TSHIRT,
    tryon_supported: true,
    default_config: {
      scale: 1.0,
      scaleX: 1.4, // Width multiplier ~ shoulder distance x 1.4
      scaleY: 1.2, // Height multiplier ~ shoulder-to-hip x 1.2
      offsetX: 0.0,
      offsetY: -0.05,
      offsetZ: 0.0,
      rotation: 0.0,
      flip: false,
      fadeAngleDeg: 60.0
    }
  },

  // 2. Shirts & Kurtas
  {
    category: 'Fashion',
    subcategories: ['Casual Shirts', 'Shirts', 'Formal Shirts', 'Men\'s Shirts', 'Men\'s Kurtas', 'Kurtas', 'Ethnic Wear'],
    keywords: ['shirt', 'kurta', 'kurti', 'tunic'],
    tryon_type: TRYON_TYPES.SHIRT,
    tryon_supported: true,
    default_config: {
      scale: 1.0,
      scaleX: 1.45,
      scaleY: 1.35,
      offsetX: 0.0,
      offsetY: -0.04,
      offsetZ: 0.0,
      rotation: 0.0,
      flip: false,
      fadeAngleDeg: 60.0
    }
  },

  // 2b. Sarees
  {
    category: 'Fashion',
    subcategories: ['Sarees', 'Banarasi Sarees', 'Pure Cotton Sarees', 'Jacquard Sarees', 'Ethnic Wear'],
    keywords: ['saree', 'sari', 'jacquard saree', 'banarasi', 'sambalpuri'],
    tryon_type: TRYON_TYPES.SAREE,
    tryon_supported: true,
    default_config: {
      scale: 1.0,
      scaleX: 1.5,
      scaleY: 1.45,
      offsetX: 0.0,
      offsetY: -0.02,
      offsetZ: 0.0,
      rotation: 0.0,
      flip: false,
      fadeAngleDeg: 60.0
    }
  },

  // 3. Audio & Headphones / Earbuds
  {
    category: 'Electronics',
    subcategories: ['Headphones', 'Bluetooth Headsets', 'Earphones', 'Audio'],
    keywords: ['headphone', 'headset', 'earphone', 'rockerz'],
    tryon_type: TRYON_TYPES.HEADPHONES,
    tryon_supported: true,
    default_config: {
      scale: 1.05,
      offsetX: 0.0,
      offsetY: 0.02,
      offsetZ: 0.0,
      rotation: 0.0,
      flip: false,
      color: '#1a1a1a'
    }
  },

  // 4. Lipstick & Lip gloss
  {
    category: 'Beauty',
    subcategories: ['Lip Color', 'Lipstick', 'Liquid Lip Color', 'Lip Care'],
    keywords: ['lip color', 'lipstick', 'matte lip', 'lip gloss'],
    tryon_type: TRYON_TYPES.LIPSTICK,
    tryon_supported: true,
    default_config: {
      opacity: 0.65,
      blendMode: 'multiply',
      gloss: 0.35,
      defaultColor: '#b74152'
    }
  },

  // 5. Blush & Cheek Tint
  {
    category: 'Beauty',
    subcategories: ['Blush', 'Powder Blush', 'Cheek Tint', 'Face Makeup'],
    keywords: ['blush', 'rouge', 'cheek'],
    tryon_type: TRYON_TYPES.BLUSH,
    tryon_supported: true,
    default_config: {
      opacity: 0.45,
      radiusMultiplier: 1.1,
      blendMode: 'source-over',
      defaultColor: '#e07a8b'
    }
  },

  // 6. Eyewear (Glasses / Sunglasses)
  {
    category: 'Accessories',
    subcategories: ['Sunglasses', 'Spectacles', 'Eyeglasses', 'Goggles'],
    keywords: ['sunglass', 'spectacle', 'glass', 'goggle', 'eyewear'],
    tryon_type: TRYON_TYPES.GLASSES,
    tryon_supported: true,
    default_config: {
      scale: 1.0,
      offsetX: 0.0,
      offsetY: 0.0,
      offsetZ: 0.0,
      rotation: 0.0
    }
  },

  // 7. Earrings
  {
    category: 'Jewellery',
    subcategories: ['Earrings', 'Studs', 'Jhumkas', 'Drops'],
    keywords: ['earring', 'stud', 'jhumka'],
    tryon_type: TRYON_TYPES.EARRINGS,
    tryon_supported: true,
    default_config: {
      scale: 1.0,
      offsetX: 0.0,
      offsetY: 0.02,
      cutoffAngleDeg: 35.0
    }
  },

  // 8. Watches & Bracelets
  {
    category: 'Accessories',
    subcategories: ['Watches', 'Smart Watches', 'Wrist Watches', 'Bracelets'],
    keywords: ['watch', 'smartwatch', 'wrist', 'bracelet'],
    tryon_type: TRYON_TYPES.WATCH,
    tryon_supported: true,
    default_config: {
      scale: 1.0,
      offsetX: 0.0,
      offsetY: 0.0,
      offsetZ: 0.0
    }
  }
];

/**
 * Resolves a product's tryon mapping from its category, subcategory and name.
 * Returns { tryon_supported: boolean, tryon_type: string | null, default_config: object | null }
 */
export function resolveTryonMapping(product) {
  const cat = (product.category || '').trim();
  const name = (product.name || '').toLowerCase();
  
  let subcat = '';
  if (product.attrs) {
    if (typeof product.attrs === 'string') {
      try {
        const parsed = JSON.parse(product.attrs);
        subcat = parsed.subcategory || (parsed.breadcrumbs ? parsed.breadcrumbs[parsed.breadcrumbs.length - 2] : '');
      } catch (e) {}
    } else {
      subcat = product.attrs.subcategory || (product.attrs.breadcrumbs ? product.attrs.breadcrumbs[product.attrs.breadcrumbs.length - 2] : '');
    }
  }
  const subcatLower = (subcat || '').toLowerCase();

  for (const entry of CATEGORY_MAP) {
    const catMatches = !entry.category || entry.category.toLowerCase() === cat.toLowerCase();
    const subcatMatches = entry.subcategories.some(sc => sc.toLowerCase() === subcatLower || subcatLower.includes(sc.toLowerCase()));
    const keywordMatches = entry.keywords.some(kw => name.includes(kw));

    if (catMatches && (subcatMatches || keywordMatches)) {
      return {
        tryon_supported: entry.tryon_supported,
        tryon_type: entry.tryon_type,
        default_config: { ...entry.default_config }
      };
    }
  }

  return {
    tryon_supported: false,
    tryon_type: null,
    default_config: null
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { TRYON_TYPES, CATEGORY_MAP, resolveTryonMapping };
}
