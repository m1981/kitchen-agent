/**
 * Model diagnostyk — reguła domenowa jest DANYMI, nie kodem sterującym.
 *
 * Zamiast „formularz jest poprawny / niepoprawny" jedno przejście produkuje
 * listę diagnostyk z kodem i severity, jak w kompilatorze. Rejestr reguł ma
 * dwóch konsumentów: Zod (bierze same `blocker`y) i UI (bierze wszystko).
 *
 * Patrz: docs/adr/0009-rule-registry.md
 */

/**
 * `blocker` to jedyna severity, która blokuje przejście dalej. `critical` jest
 * czerwony i ważny, ale świadomie przepuszcza — krzywa ściana czy gniazdo za
 * lodówką to fakt zastany u klienta, a nie błąd wypełniającego.
 */
export type Severity = 'blocker' | 'critical' | 'warning' | 'info'

const SEVERITY_ORDER: Record<Severity, number> = {
  blocker: 0,
  critical: 1,
  warning: 2,
  info: 3,
}

export interface Diagnostic<P extends string = string> {
  /** Stabilny kod, np. 'GEO-003' — cytowalny w dokumentacji i rozmowie. */
  code: string
  severity: Severity
  /** Ścieżka pola w formularzu (notacja kropkowa), do zakotwiczenia w UI. */
  path: P
  message: string
}

export interface Rule<M, P extends string = string> {
  code: string
  severity: Severity
  path: P
  /** Czy reguła w ogóle dotyczy tego pomiaru (progressive disclosure). */
  when?: (model: M) => boolean
  /** Czy mamy dane, żeby oceniać. Brak pomiaru ≠ zły pomiar. */
  requires?: (model: M) => boolean
  /** `true` = wszystko w porządku. */
  check: (model: M) => boolean
  message: (model: M) => string
  /** Kody diagnostyk następczych, które ta reguła gasi (kaskada). */
  suppresses?: string[]
}

/**
 * Uruchamia rejestr i zwraca diagnostyki posortowane wg wagi.
 *
 * Kolejność ma znaczenie: najpierw odsiewamy reguły, które nie dotyczą (`when`)
 * lub nie mają danych (`requires`), potem gasimy diagnostyki następcze
 * (`suppresses`) — żeby jeden brakujący wymiar nie zapalił ośmiu komunikatów.
 */
export function runRules<M, P extends string>(
  model: M,
  rules: ReadonlyArray<Rule<M, P>>,
): Diagnostic<P>[] {
  const fired = rules.filter(
    (rule) =>
      (rule.when?.(model) ?? true) &&
      (rule.requires?.(model) ?? true) &&
      !rule.check(model),
  )
  const muted = new Set(fired.flatMap((rule) => rule.suppresses ?? []))

  return fired
    .filter((rule) => !muted.has(rule.code))
    .map((rule) => ({
      code: rule.code,
      severity: rule.severity,
      path: rule.path,
      message: rule.message(model),
    }))
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
}

export const isBlocking = (diagnostic: Diagnostic): boolean =>
  diagnostic.severity === 'blocker'

/** 'obstacles.radiatorProtrusion' → ['obstacles', 'radiatorProtrusion'] */
export function toPathSegments(path: string): (string | number)[] {
  return path
    .split('.')
    .map((segment) => (/^\d+$/.test(segment) ? Number(segment) : segment))
}
