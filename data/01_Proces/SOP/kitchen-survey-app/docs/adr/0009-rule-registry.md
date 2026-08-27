# 0009 — Rule registry: jeden ruleset, dwóch konsumentów

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Reguły domenowe żyły w dwóch równoległych systemach: twarde w `superRefine`
w `schema.ts`, miękkie w funkcjach `geometryWarnings` / `installationWarnings`
w `calc.ts`. Te same fakty domenowe opisane dwa razy, w dwóch stylach, bez
wspólnego identyfikatora. Przy ~20 regułach do utrzymania, przy 80 — nie.

## Decyzja
Reguła jest **danymi**, nie kodem sterującym (Specification Pattern / rejestr
tabelaryczny):

```ts
interface Rule<M> {
  code: string                  // 'GEO-003' — stabilny, cytowalny
  severity: Severity            // 'blocker' | 'critical' | 'warning' | 'info'
  path: DiagnosticPath          // do podpięcia pod pole formularza
  when?:     (m: M) => boolean  // czy reguła w ogóle dotyczy (progressive disclosure)
  requires?: (m: M) => boolean  // czy mamy dane, żeby oceniać (gating)
  check:     (m: M) => boolean  // true = OK
  message:   (m: M) => string
  suppresses?: string[]         // gasi diagnostyki następcze (kaskada)
}
```

Wynikiem przebiegu jest lista **diagnostyk** (model kompilatora: kod + severity
+ path + message), a nie boolean. `severity` jest osobną osią od blokowania:
blokuje wyłącznie `'blocker'`. `'critical'` to czerwony alert, który świadomie
przepuszcza dalej — krzywa ściana czy gniazdo za lodówką to fakt zastany
u klienta, nie błąd wypełniającego (por. ADR 0005).

Rejestr ma dwóch konsumentów:
1. **Zod** — `superRefine` wciąga wyłącznie diagnostyki `blocker` jako issues.
2. **UI** — liczy pełny zestaw na żywo z `watch()` i renderuje jako alerty.

Żeby oba czytały ten sam model, schemat rozdziela się na `…Shape` (kształt
+ wartości pochodne, zawsze się parsuje) i `…Schema` (`Shape` + polityka).
UI parsuje przez `Shape` i dostaje model domenowy nawet dla niekompletnego
formularza.

## Konsekwencje
- Dodanie reguły to dopisanie wiersza w tablicy, w jednym pliku.
- Reguły są testowalne bez formularza i bez DOM — wejście to model, wyjście to
  lista kodów. Testy tabelaryczne, z osobnym przypadkiem na gating.
- Rejestr da się wyliczyć: można go wyrenderować jako katalog „co system
  sprawdza" albo dołączyć do eksportu.
- Świadomie **nie** wprowadzamy silnika reguł (json-rules-engine, DSL, reguły
  w bazie). Przy regułach zmienianych kilka razy w roku przez tę samą osobę co
  kod, tablica obiektów w TS daje typy, autouzupełnianie i debugger; DSL nie.
