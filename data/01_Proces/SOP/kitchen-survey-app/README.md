# Karta Pomiarowa Kuchni — Etap 1.1 (PWA, Local-First)

Kreator inwentaryzacji zabudowy kuchennej dla stolarza. Działa w przeglądarce
na tablecie, offline, bez backendu. Odwzorowuje kartę
`01_Proces/etap-1-1-karta-pomiarowa.html` w formie interaktywnego wizarda.

## Uruchomienie

```bash
npm install
npm run dev          # tryb deweloperski
npm run build        # tsc -b + vite build (PWA: manifest + service worker)
npm run preview      # podgląd builda produkcyjnego
npm run check:schema # szybki test schematów i auto-kalkulacji (Node, bez przeglądarki)
```

## Stack

React 19 + Vite + TypeScript (strict) · Tailwind CSS v4 · react-hook-form + zod
(@hookform/resolvers) · zustand + middleware `persist` · lucide-react ·
vite-plugin-pwa.

Komponenty UI (`src/components/ui`) są napisane ręcznie w konwencji shadcn/ui —
bez CLI i bez Radixa, żeby nie ciągnąć zależności do offline'owego kiosku.

## Architektura

```
src/
  lib/schema.ts       — Zod: źródło prawdy dla wszystkich kroków
  lib/calc.ts         — auto-kalkulacje (min do CAD, słupek) + soft warnings
  lib/defaults.ts     — wartości startowe + szablon 10 przyłączy z karty
  lib/export.ts       — walidacja całości + zrzut do pliku JSON
  store/surveyStore.ts— zustand + persist (LocalStorage, klucz kitchen-survey-draft-v1)
  steps/              — 5 kroków kreatora
  components/ui/      — Input/MmInput/Select/Checkbox/SegmentedControl/Card/Alert/Button
```

### Kroki kreatora

1. **Dane klienta** — inwestor, kontakt, adres, data, budżet.
2. **Geometria** — Bounding Box, pomiar 3-punktowy, przeszkody i kolizje.
3. **AGD i przyłącza** — czerwona strefa elektryczna, wentylacja, osie X/Y dla CNC.
4. **Pakiet i logistyka** — pakiet materiałowy, transport, checklista.
5. **Podsumowanie** — widok do druku A4 (Cmd/Ctrl+P) + eksport JSON.

### Walidacja: twarda vs miękka

- **Hard (blokuje `Dalej`)** — Zod: brak nazwiska/adresu, brak wymiaru ściany A
  lub wysokości H, układ L/U bez ściany bocznej, zaznaczone okno bez wysokości
  parapetu i osi. Komunikaty renderują się pod polami.
- **Soft (żółty/czerwony alert, przepuszcza dalej)** — `lib/calc.ts`: kąt ≠ 90°,
  rozrzut pomiaru > 10 mm, sufit podwieszany, spadek posadzki > 10 mm, parapet
  poniżej blatu, płyta bliżej niż 300 mm od zlewu/ściany, odznaczone plecy HDF
  przy lodówce/piekarniku, gniazdo oznaczone jako „za AGD”.

### Auto-kalkulacje (cross-field)

Wpis `dół 2500 / środek 2510 / góra 2490` → `min = 2490` (wartość do Corpus LTR),
`spread = 20` → sugerowana blenda 50 mm. Wysokość `H min = 2618` →
`maxColumnHeight = 2588` (H − 30 mm na przekątną i blendę górną). Wyliczenia
siedzą w `.transform()` schematu, więc trafiają też do eksportu JSON.

### Persystencja

Każda zmiana inputa leci przez `useAutosave` do zustanda, a `persist` zrzuca
draft do LocalStorage. Odświeżenie strony wraca do tego samego kroku z tymi
samymi wartościami. „Nowy pomiar” czyści pamięć po potwierdzeniu.

### Eksport

`pomiar_<nazwisko>_<data>.json` — pełny, zwalidowany obiekt z wyliczonymi
wymiarami minimalnymi. Wydruk: krok 5 + Cmd/Ctrl+P (A4, `@page` + `.no-print`).

## Poza zakresem

Brak backendu, bazy, logowania i API. Brak rysowania 2D/3D — szkic robi się na
kartce, w aplikacji jest pole tekstowe. Brak wycen, umów i historii klientów:
jedna sesja pomiarowa naraz.
