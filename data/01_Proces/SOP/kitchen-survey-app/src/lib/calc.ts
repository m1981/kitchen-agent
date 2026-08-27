/**
 * Auto-kalkulacje i miękkie ostrzeżenia (Soft Warnings).
 *
 * Reguły pochodzą wprost z karty pomiarowej Etap 1.1 (Bounding Box / CNC).
 * Soft warning NIGDY nie blokuje przejścia dalej — to podpowiedź dla stolarza.
 */

export type Severity = 'info' | 'warning' | 'critical'

export interface SoftWarning {
  id: string
  severity: Severity
  message: string
}

/** Luz montażowy słupka pod sufit: przekątna + blenda górna. */
export const COLUMN_CLEARANCE_MM = 30
/** Minimalna blenda maskująca przy prostej ścianie. */
export const MIN_FILLER_MM = 30
/** Blenda przy narożniku ostrym/rozwartym. */
export const CORNER_FILLER_MM = 50

export type RawNumber = string | number | null | undefined

/** Parsuje pole formularza (RHF trzyma stringi) na liczbę lub null. */
export function toNumber(value: RawNumber): number | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const normalized = value.trim().replace(',', '.')
  if (normalized === '') return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Złota zasada pomiaru 3-punktowego: do CAD wchodzi NAJMNIEJSZY wymiar.
 * Zwraca też rozrzut — im większy, tym szersza blenda maskująca.
 */
export function computeMinDimension(points: RawNumber[]): {
  min: number | null
  max: number | null
  spread: number | null
} {
  const values = points
    .map(toNumber)
    .filter((value): value is number => value !== null)
  if (values.length === 0) return { min: null, max: null, spread: null }
  const min = Math.min(...values)
  const max = Math.max(...values)
  return { min, max, spread: values.length > 1 ? max - min : null }
}

/** Maksymalna wysokość słupka = H min − 30 mm. */
export function computeMaxColumnHeight(heightMin: number | null): number | null {
  return heightMin === null ? null : heightMin - COLUMN_CLEARANCE_MM
}

/** Rekomendowana blenda maskująca na podstawie rozrzutu pomiaru. */
export function recommendedFiller(spread: number | null): number {
  if (spread === null) return MIN_FILLER_MM
  if (spread > 20) return CORNER_FILLER_MM
  return Math.max(MIN_FILLER_MM, Math.ceil((MIN_FILLER_MM + spread) / 5) * 5)
}

export function formatMm(value: number | null): string {
  return value === null ? '—' : `${value} mm`
}

/* -------------------------------------------------------------------------- */
/*  Soft warnings — geometria (krok 2)                                         */
/* -------------------------------------------------------------------------- */

export interface GeometryWarningInput {
  wallASpread: number | null
  wallBSpread: number | null
  wallCSpread: number | null
  heightMin: number | null
  heightSpread: number | null
  cornerAngle: number | null
  floorLevelDrop: number | null
  ceilingType: string
  hasWindow: boolean
  windowSillHeight: number | null
  tapWindowCollision: boolean
}

export function geometryWarnings(input: GeometryWarningInput): SoftWarning[] {
  const warnings: SoftWarning[] = []

  const angle = input.cornerAngle
  if (angle !== null && Math.abs(angle - 90) >= 1) {
    warnings.push({
      id: 'corner-angle',
      severity: 'warning',
      message:
        angle < 90
          ? `Kąt ostry (${angle}°) — zwiększ blendę narożną do min. ${CORNER_FILLER_MM} mm i sprawdź kolizję uchwytów.`
          : `Kąt rozwarty (${angle}°) — zwiększ blendę narożną do min. ${CORNER_FILLER_MM} mm.`,
    })
  }

  const spreads: Array<[string, number | null]> = [
    ['A (szerokość)', input.wallASpread],
    ['B (bok)', input.wallBSpread],
    ['C (bok)', input.wallCSpread],
  ]
  for (const [label, spread] of spreads) {
    if (spread !== null && spread > 10) {
      warnings.push({
        id: `wall-spread-${label}`,
        severity: spread > 25 ? 'critical' : 'warning',
        message: `Ściana ${label}: rozrzut ${spread} mm między punktami. Zaplanuj blendę min. ${recommendedFiller(spread)} mm.`,
      })
    }
  }

  if (input.heightSpread !== null && input.heightSpread > 15) {
    warnings.push({
      id: 'height-spread',
      severity: 'warning',
      message: `Sufit nierówny (rozrzut ${input.heightSpread} mm) — słupki licz od najmniejszej wysokości, dodaj blendę górną.`,
    })
  }

  if (input.heightMin !== null && input.heightMin < 2400) {
    warnings.push({
      id: 'low-ceiling',
      severity: 'warning',
      message: `Niski sufit (${input.heightMin} mm) — zweryfikuj wysokość słupka i okapu przed projektem w Corpusie.`,
    })
  }

  if (input.floorLevelDrop !== null && Math.abs(input.floorLevelDrop) > 10) {
    warnings.push({
      id: 'floor-drop',
      severity: 'warning',
      message: `Spadek posadzki ${input.floorLevelDrop} mm — potrzebne nóżki z większym zakresem regulacji i docinany cokół.`,
    })
  }

  if (input.ceilingType === 'podwieszany') {
    warnings.push({
      id: 'suspended-ceiling',
      severity: 'warning',
      message:
        'Sufit podwieszany (karton-gips) — nie kotwimy szafek wiszących w płycie GK. Zlokalizuj profile lub ścianę nośną.',
    })
  }

  if (input.hasWindow && input.windowSillHeight !== null) {
    if (input.windowSillHeight < 900) {
      warnings.push({
        id: 'low-sill',
        severity: 'critical',
        message: `Parapet na wysokości ${input.windowSillHeight} mm — poniżej blatu (ok. 900 mm). Konieczne obniżenie blatu lub podcięcie parapetu.`,
      })
    } else if (input.windowSillHeight < 1000) {
      warnings.push({
        id: 'tight-sill',
        severity: 'warning',
        message: `Parapet ${input.windowSillHeight} mm — mało miejsca na panel HPL i gniazda nad blatem.`,
      })
    }
  }

  if (input.tapWindowCollision) {
    warnings.push({
      id: 'tap-collision',
      severity: 'critical',
      message:
        'Kolizja baterii z oknem — dobierz baterię składaną lub przesuń zlew. Zaznacz to na szkicu.',
    })
  }

  return warnings
}

/* -------------------------------------------------------------------------- */
/*  Soft warnings — AGD i przyłącza (krok 3)                                   */
/* -------------------------------------------------------------------------- */

export interface InstallationWarningInput {
  hobVentGap: number | null
  hobDistanceToSink: number | null
  hobDistanceToSideWall: number | null
  fridgeNoHdfBack: boolean
  fridgeVentGapMin50: boolean
  ovenNoHdfBack: boolean
  hobMetalTraverses: boolean
  socketBehindApplianceIds: string[]
}

export function installationWarnings(
  input: InstallationWarningInput,
): SoftWarning[] {
  const warnings: SoftWarning[] = []

  if (input.hobDistanceToSink !== null && input.hobDistanceToSink < 300) {
    warnings.push({
      id: 'hob-sink',
      severity: 'critical',
      message: `Płyta ${input.hobDistanceToSink} mm od zlewu — norma to min. 300 mm. Przesuń moduł lub zmień układ.`,
    })
  }
  if (input.hobDistanceToSideWall !== null && input.hobDistanceToSideWall < 300) {
    warnings.push({
      id: 'hob-wall',
      severity: 'critical',
      message: `Płyta ${input.hobDistanceToSideWall} mm od ściany bocznej — norma to min. 300 mm.`,
    })
  }
  if (input.hobVentGap !== null && (input.hobVentGap < 5 || input.hobVentGap > 20)) {
    warnings.push({
      id: 'hob-vent',
      severity: 'warning',
      message: `Szczelina wentylacyjna pod indukcją ${input.hobVentGap} mm — zalecane 5–20 mm.`,
    })
  }
  if (!input.fridgeNoHdfBack) {
    warnings.push({
      id: 'fridge-hdf',
      severity: 'critical',
      message:
        'Zaznaczono plecy HDF w słupku lodówkowym — blokują komin wentylacyjny. Standard: brak pleców.',
    })
  }
  if (!input.fridgeVentGapMin50) {
    warnings.push({
      id: 'fridge-gap',
      severity: 'critical',
      message: 'Brak odstępu min. 50 mm od ściany za lodówką — komin wentylacyjny nie zadziała.',
    })
  }
  if (!input.ovenNoHdfBack) {
    warnings.push({
      id: 'oven-hdf',
      severity: 'critical',
      message: 'Plecy HDF w niszy piekarnika — brak odprowadzania ciepła. Standard: brak pleców.',
    })
  }
  if (!input.hobMetalTraverses) {
    warnings.push({
      id: 'traverses',
      severity: 'warning',
      message:
        'Brak trawersów metalowych pod blatem HPL 12 mm — wieńce płytowe nie przeniosą obciążenia płyty.',
    })
  }
  for (const id of input.socketBehindApplianceIds) {
    warnings.push({
      id: `socket-${id}`,
      severity: 'critical',
      message: `Gniazdo „${id}" oznaczone jako umieszczone za AGD — CZERWONA STREFA. Przenieś do szafki sąsiedniej.`,
    })
  }

  return warnings
}
