/**
 * Czysta matematyka pomiaru — bez reguł domenowych.
 *
 * Warstwa „derive" między parsowaniem a polityką: liczy to, co wynika
 * z pomiaru, i nic nie ocenia. Oceną zajmuje się rejestr reguł
 * (`lib/rules/`), który operuje już na wyliczonym modelu.
 */

import { NORM, THRESHOLD } from './norms.ts'

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

/** Maksymalna wysokość słupka = H min − luz na przekątną i blendę górną. */
export function computeMaxColumnHeight(heightMin: number | null): number | null {
  return heightMin === null ? null : heightMin - NORM.columnClearance
}

/** Rekomendowana blenda maskująca na podstawie rozrzutu pomiaru. */
export function recommendedFiller(spread: number | null): number {
  if (spread === null) return NORM.minFiller
  if (spread > THRESHOLD.fillerJumpToCorner) return NORM.cornerFiller
  return Math.max(NORM.minFiller, Math.ceil((NORM.minFiller + spread) / 5) * 5)
}

export function formatMm(value: number | null): string {
  return value === null ? '—' : `${value} mm`
}
