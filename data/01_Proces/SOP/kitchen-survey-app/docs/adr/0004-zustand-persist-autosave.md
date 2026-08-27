# 0004 — zustand + persist jako jedyna persystencja

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Spec wymaga auto-save po każdej zmianie inputa i braku backendu. Kandydaci:
LocalStorage (przez `persist`) albo IndexedDB (przez `idb-keyval`).

## Decyzja
zustand z middlewarem `persist` na LocalStorage, klucz
`kitchen-survey-draft-v1`. W store trzymamy **surowe wartości formularza**
(`z.input`), nie sparsowany model — dzięki temu draft da się zapisać w każdym
momencie, także gdy jest niepoprawny. Most RHF → store to hook `useAutosave`
podpięty pod `watch()`.

## Konsekwencje
- Jeden pomiar to kilkanaście kB tekstu; limit ~5 MB LocalStorage jest odległy.
  Gdyby doszły zdjęcia — trzeba przejść na IndexedDB (nowy ADR).
- Klucz zawiera wersję; zmiana kształtu draftu wymaga bumpa i migracji
  w `persist({ version, migrate })`.
- Nazwa store'a jest widoczna dla użytkownika w DevTools — to celowe, „Nowy
  pomiar" musi realnie czyścić dane, bo aplikacja bywa na wspólnym tablecie.
