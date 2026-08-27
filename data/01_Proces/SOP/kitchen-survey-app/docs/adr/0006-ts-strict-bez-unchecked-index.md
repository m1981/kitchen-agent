# 0006 — TS strict, bez `noUncheckedIndexedAccess`

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Spec wymaga TypeScriptu w trybie strict. Scaffold Vite nie włącza `strict`
w `tsconfig.app.json`. Osobną decyzją jest `noUncheckedIndexedAccess`, który
nie wchodzi w skład `strict`.

## Decyzja
Włączamy `strict: true`. `noUncheckedIndexedAccess` zostaje wyłączony.
Dodatkowo `paths: { "@/*": ["./src/*"] }` bez `baseUrl` (deprecated w TS 6).

## Konsekwencje
- Kod indeksujący tablice (kroki kreatora, punkty przyłączy) nie jest zaśmiecony
  asercjami `!` ani `?? fallback` przy każdym dostępie.
- Cena: literówka w indeksie nie zostanie złapana przez typy. Akceptowalna —
  indeksy pochodzą z `map()` po tablicach o znanej długości.
