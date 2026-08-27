# 0002 — Puste pole pomiarowe to `null`, nie `0`

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Stolarz wypełnia kartę wyrywkowo: część wymiarów mierzy od razu, część
uzupełnia po powrocie. Formularz musi odróżnić „nie zmierzono" od „zmierzono
i wyszło 0".

## Decyzja
`mmOptional` mapuje `""`, `undefined` i wartości nieparsowalne na `null`, a nie
na `0`. Reguły domenowe mają mechanizm `requires` (gating) — brak danych nie
zapala ostrzeżenia. Przecinek dziesiętny jest normalizowany do kropki, bo na
polskiej klawiaturze numerycznej tablety wstawiają przecinek.

## Konsekwencje
- Wszystkie pola wymiarowe są `number | null` — kod musi to obsłużyć jawnie.
- Świeży formularz nie krzyczy dziesiątkami fałszywych alarmów.
- W JSON-ie `null` znaczy „nie zmierzono" i to jest informacja dla działu CAD.
