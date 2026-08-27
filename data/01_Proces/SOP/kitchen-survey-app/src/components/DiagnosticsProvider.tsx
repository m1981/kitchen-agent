import { createContext, useContext, useMemo, type ReactNode } from 'react'
import type { Diagnostic } from '@/lib/diagnostics'

/**
 * Diagnostyki bieżącego kroku, adresowane po `path`. Pola nie dostają ich
 * propsami — `Field` sam odpytuje kontekst swoją ścieżką.
 *
 * Patrz: docs/adr/0010-field-diagnostics.md
 */
const EMPTY: Diagnostic[] = []
const DiagnosticsContext = createContext<Diagnostic[]>(EMPTY)

export function DiagnosticsProvider({
  diagnostics,
  children,
}: {
  diagnostics: Diagnostic[]
  children: ReactNode
}) {
  return (
    <DiagnosticsContext.Provider value={diagnostics}>
      {children}
    </DiagnosticsContext.Provider>
  )
}

export function useDiagnostics(): Diagnostic[] {
  return useContext(DiagnosticsContext)
}

/**
 * Diagnostyki zakotwiczone w konkretnym polu. Blokery są pomijane — te idą
 * przez resolver Zoda i renderują się jako błąd pola, żeby nie dublować
 * komunikatu i nie krzyczeć, zanim użytkownik dotknie pola.
 */
export function useFieldDiagnostics(path?: string): Diagnostic[] {
  const all = useDiagnostics()
  return useMemo(
    () =>
      path
        ? all.filter((d) => d.path === path && d.severity !== 'blocker')
        : EMPTY,
    [all, path],
  )
}
