# 0003 — Ręcznie pisane komponenty UI zamiast shadcn/ui CLI

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Spec narzuca „Tailwind + shadcn/ui". Oficjalna ścieżka to interaktywne CLI,
które dociąga Radix UI i generuje komponenty pod swój `components.json`.

## Decyzja
Komponenty (`Button`, `Card`, `Field`, `Input`, `MmInput`, `Select`, `Checkbox`,
`SegmentedControl`, `Alert`) piszemy ręcznie w konwencji shadcn/ui: własne pliki
w `src/components/ui`, wariantowanie przez `cn()` (clsx + tailwind-merge).

## Konsekwencje
- Zero Radixa — mniejszy bundle w kiosku offline, mniej zależności do audytu.
- Potrzebne były tylko natywne kontrolki HTML; nie ma tu dropdownów ani modali,
  które uzasadniałyby Radixa. Gdy dojdą — piszemy nowy ADR.
- Cele dotykowe wymuszone globalnie: `min-h-12` na kontrolkach, `size-6` na
  checkboxach, `font-size: 16px` (próg, poniżej którego Safari zoomuje input).
