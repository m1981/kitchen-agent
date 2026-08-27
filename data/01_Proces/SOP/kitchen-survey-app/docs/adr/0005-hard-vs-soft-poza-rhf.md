# 0005 — Soft warnings poza stanem react-hook-form

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Spec rozróżnia walidację twardą (blokuje `Dalej`) i miękką (ostrzega, ale
przepuszcza). RHF ma tylko jeden kanał — `formState.errors` — i wszystko, co
w nim wyląduje, blokuje `handleSubmit`.

## Decyzja
Twarde reguły idą przez resolver Zoda i lądują w `formState.errors`. Miękkie są
liczone poza RHF, na bieżąco z `watch()`, i renderowane jako alerty. Ostrzeżenie
miękkie nie zależy od `touched`/`dirty` — pokazuje się od razu, bo dotyczy
rzeczywistości zastanej u klienta, a nie tego, czy ktoś kliknął w pole.

## Konsekwencje
- Ostrzeżenia miękkie są świadomie „nienachalne": nie da się przez nie
  zablokować pomiaru, bo krzywa ściana to fakt, nie błąd wypełniającego.
- Wymaga dyscypliny, żeby obie ścieżki nie rozjechały się w komunikatach —
  patrz ADR 0009, który sprowadza je do jednego rejestru reguł.
