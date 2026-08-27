export const STYLE_PACKAGE_DETAILS = {
  scandi: {
    name: 'Pakiet 1 — Scandi / Japandi',
    lines: [
      'Fronty dół: Swiss Krono K101 EM (biel) / U119 EM (beż)',
      'Fronty góra: Swiss Krono D20270 CX (dąb Eden)',
      'Blat: Egger Kompakt HPL 12 mm (jasny kamień / biel)',
    ],
  },
  wloski: {
    name: 'Pakiet 2 — Ciepły włoski',
    lines: [
      'Fronty: Swiss Krono U3189 EM (trufla)',
      'Korpusy: Swiss Krono U3189 VL',
      'Blat: Egger Kompakt HPL 12 mm (ciemny marmur)',
    ],
  },
  loft: {
    name: 'Pakiet 3 — Nowoczesny loft',
    lines: [
      'Fronty: Swiss Krono U164 EM (antracyt)',
      'Korpusy: Swiss Krono U164 VL',
      'Blat: Egger Kompakt HPL 12 mm (czarny monolit)',
    ],
  },
} as const

export type StylePackageKey = keyof typeof STYLE_PACKAGE_DETAILS
