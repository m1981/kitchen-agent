# 0008 — Liczby z normy w jednym module `norms.ts`

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Progi domenowe (300 mm płyta–zlew, 50 mm komin za lodówką, 30 mm luzu na
słupek, 30–50 mm blendy) były wpisane jako literały w dwóch miejscach naraz:
w warunku reguły i w treści komunikatu. Zmiana progu wymagała grepowania,
a rozjazd między warunkiem a komunikatem był kwestią czasu.

## Decyzja
Wszystkie liczby z normy i progi ostrzeżeń mieszkają w `src/lib/norms.ts` jako
`as const`, z komentarzem opisującym pochodzenie. Reguły i komunikaty czytają
tę samą stałą.

## Konsekwencje
- Zmiana progu to jedna linia; komunikat aktualizuje się sam.
- Moduł jest czytelny dla osoby nietechnicznej — można go przejrzeć ze stolarzem
  jak listę wytycznych warsztatowych.
- Progi „miękkie" (rozrzut > 10 mm, sufit < 2400 mm) leżą obok twardych norm,
  ale w osobnej sekcji — to heurystyki warsztatowe, nie normy.
