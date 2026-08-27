# 0001 — Zod jako źródło prawdy, parse-don't-validate

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Ten sam pomiar musi trafić do trzech miejsc: formularza (stringi z inputów),
widoku do druku i pliku JSON dla CAD/CNC. Trzymanie osobnych typów dla każdego
z nich gwarantuje rozjazd.

## Decyzja
Zod jest jedynym źródłem prawdy o kształcie danych. Schemat nie tylko waliduje,
ale **parsuje**: `z.input` to surowy formularz (stringi), `z.output` to model
domenowy (liczby, wartości wyliczone). Wartości pochodne — `min`, `spread`,
`maxColumnHeight` — powstają w `.transform()`, więc trafiają do eksportu
automatycznie, bez ręcznego przepisywania.

## Konsekwencje
- Eksport JSON to dosłownie `z.output` — nie ma osobnego serializatora.
- `useForm<Input>` i `handleSubmit` operują na różnych typach; w krokach 2–4
  ignorujemy dane z `handleSubmit` i czytamy stan ze store'a.
- Każde nowe pole wymaga decyzji: surowe czy pochodne. To dobry przymus.
