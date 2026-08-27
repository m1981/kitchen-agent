import type { Path } from 'react-hook-form'
import { recommendedFiller } from '../calc.ts'
import type { Rule } from '../diagnostics.ts'
import { NORM, THRESHOLD } from '../norms.ts'
import type { RoomGeometryInput, RoomGeometryModel } from '../schema.ts'

/** Ścieżki są typowane kształtem formularza — literówka nie skompiluje się. */
type GeoPath = Path<RoomGeometryInput>
type GeoRule = Rule<RoomGeometryModel, GeoPath>

const WALLS = [
  { key: 'wallA', label: 'A (szerokość)', path: 'wallA.bottom' },
  { key: 'wallB', label: 'B (bok)', path: 'wallB.bottom' },
  { key: 'wallC', label: 'C (bok)', path: 'wallC.bottom' },
] as const

/** Rozrzut pomiaru 3-punktowego — jedna reguła na ścianę, ten sam warunek. */
const spreadRules: GeoRule[] = WALLS.map(({ key, label, path }, index) => ({
  code: `GEO-01${index + 1}`,
  severity: 'warning',
  path: path as GeoPath,
  requires: (m) => m[key].spread !== null,
  check: (m) => m[key].spread! <= THRESHOLD.wallSpreadWarning,
  message: (m) =>
    `Ściana ${label}: rozrzut ${m[key].spread} mm między punktami. Zaplanuj blendę min. ${recommendedFiller(m[key].spread)} mm.`,
}))

export const GEOMETRY_RULES: readonly GeoRule[] = [
  /* ---- blokery: bez tych danych nie ma czego wprowadzić do CAD ---- */
  {
    code: 'GEO-001',
    severity: 'blocker',
    path: 'wallA.bottom',
    check: (m) => m.wallA.min !== null,
    message: () => 'Podaj przynajmniej jeden wymiar ściany A (dół / środek / góra)',
    // Bez wymiaru ściany A nie ma sensu ostrzegać o jej rozrzucie.
    suppresses: ['GEO-011'],
  },
  {
    code: 'GEO-002',
    severity: 'blocker',
    path: 'wallB.bottom',
    when: (m) => m.layout === 'L' || m.layout === 'U',
    check: (m) => m.wallB.min !== null,
    message: () => 'Układ L/U wymaga pomiaru ściany bocznej B',
    suppresses: ['GEO-012'],
  },
  {
    code: 'GEO-003',
    severity: 'blocker',
    path: 'wallC.bottom',
    when: (m) => m.layout === 'U',
    check: (m) => m.wallC.min !== null,
    message: () => 'Układ U wymaga pomiaru ściany bocznej C',
    suppresses: ['GEO-013'],
  },
  {
    code: 'GEO-004',
    severity: 'blocker',
    path: 'height.bottom',
    check: (m) => m.height.min !== null,
    message: () => 'Podaj przynajmniej jedną wysokość pomieszczenia (lewa / środek / prawa)',
    suppresses: ['GEO-014', 'GEO-015'],
  },
  {
    code: 'GEO-005',
    severity: 'blocker',
    path: 'windowSillHeight',
    when: (m) => m.hasWindow,
    check: (m) => m.windowSillHeight !== null,
    message: () => 'Podaj wysokość do parapetu',
    suppresses: ['GEO-018', 'GEO-019'],
  },
  {
    code: 'GEO-006',
    severity: 'blocker',
    path: 'windowAxisFromLeft',
    when: (m) => m.hasWindow,
    check: (m) => m.windowAxisFromLeft !== null,
    message: () => 'Podaj oś okna od lewej ściany',
  },
  {
    code: 'GEO-007',
    severity: 'blocker',
    path: 'bulkheadHeight',
    when: (m) => m.hasBulkhead,
    check: (m) => m.bulkheadHeight !== null,
    message: () => 'Podaj wysokość podciągu / uskoku',
  },
  {
    code: 'GEO-008',
    severity: 'blocker',
    path: 'obstacles.radiatorProtrusion',
    when: (m) => m.obstacles.radiator,
    check: (m) => m.obstacles.radiatorProtrusion !== null,
    message: () => 'Podaj o ile grzejnik odstaje od ściany',
  },
  {
    code: 'GEO-009',
    severity: 'blocker',
    path: 'obstacles.wallNicheDepth',
    when: (m) => m.obstacles.wallNiche,
    check: (m) => m.obstacles.wallNicheDepth !== null,
    message: () => 'Podaj głębokość wnęki',
  },

  /* ---- ostrzeżenia miękkie: przepuszczają, ale zmieniają projekt ---- */
  {
    code: 'GEO-010',
    severity: 'warning',
    path: 'cornerAngle',
    requires: (m) => m.cornerAngle !== null,
    check: (m) => Math.abs(m.cornerAngle! - 90) < THRESHOLD.cornerAngleTolerance,
    message: (m) =>
      m.cornerAngle! < 90
        ? `Kąt ostry (${m.cornerAngle}°) — zwiększ blendę narożną do min. ${NORM.cornerFiller} mm i sprawdź kolizję uchwytów.`
        : `Kąt rozwarty (${m.cornerAngle}°) — zwiększ blendę narożną do min. ${NORM.cornerFiller} mm.`,
  },
  ...spreadRules,
  {
    code: 'GEO-014',
    severity: 'warning',
    path: 'height.bottom',
    requires: (m) => m.height.spread !== null,
    check: (m) => m.height.spread! <= THRESHOLD.heightSpreadWarning,
    message: (m) =>
      `Sufit nierówny (rozrzut ${m.height.spread} mm) — słupki licz od najmniejszej wysokości, dodaj blendę górną.`,
  },
  {
    code: 'GEO-015',
    severity: 'warning',
    path: 'height.bottom',
    requires: (m) => m.height.min !== null,
    check: (m) => m.height.min! >= THRESHOLD.lowCeiling,
    message: (m) =>
      `Niski sufit (${m.height.min} mm) — zweryfikuj wysokość słupka i okapu przed projektem w Corpusie.`,
  },
  {
    code: 'GEO-016',
    severity: 'warning',
    path: 'floorLevelDrop',
    requires: (m) => m.floorLevelDrop !== null,
    check: (m) => Math.abs(m.floorLevelDrop!) <= THRESHOLD.floorDropWarning,
    message: (m) =>
      `Spadek posadzki ${m.floorLevelDrop} mm — potrzebne nóżki z większym zakresem regulacji i docinany cokół.`,
  },
  {
    code: 'GEO-017',
    severity: 'warning',
    path: 'ceilingType',
    check: (m) => m.ceilingType !== 'podwieszany',
    message: () =>
      'Sufit podwieszany (karton-gips) — nie kotwimy szafek wiszących w płycie GK. Zlokalizuj profile lub ścianę nośną.',
  },
  {
    code: 'GEO-018',
    severity: 'critical',
    path: 'windowSillHeight',
    when: (m) => m.hasWindow,
    requires: (m) => m.windowSillHeight !== null,
    check: (m) => m.windowSillHeight! >= THRESHOLD.worktopHeight,
    message: (m) =>
      `Parapet na wysokości ${m.windowSillHeight} mm — poniżej blatu (${THRESHOLD.worktopHeight} mm). Konieczne obniżenie blatu lub podcięcie parapetu.`,
    // Skoro parapet jest poniżej blatu, ostrzeżenie „mało miejsca" jest zbędne.
    suppresses: ['GEO-019'],
  },
  {
    code: 'GEO-019',
    severity: 'warning',
    path: 'windowSillHeight',
    when: (m) => m.hasWindow,
    requires: (m) => m.windowSillHeight !== null,
    check: (m) => m.windowSillHeight! >= THRESHOLD.tightSillHeight,
    message: (m) =>
      `Parapet ${m.windowSillHeight} mm — mało miejsca na panel HPL i gniazda nad blatem.`,
  },
  {
    code: 'GEO-020',
    severity: 'critical',
    path: 'obstacles.tapWindowCollision',
    check: (m) => !m.obstacles.tapWindowCollision,
    message: () =>
      'Kolizja baterii z oknem — dobierz baterię składaną lub przesuń zlew. Zaznacz to na szkicu.',
  },
]
