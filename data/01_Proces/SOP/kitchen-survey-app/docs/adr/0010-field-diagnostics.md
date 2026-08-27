# 0010 — `Field name=` i diagnostyki adresowane po `path`

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Każde pole w krokach 2–3 ręcznie przepisywało własny błąd:
`error={errors.obstacles?.radiatorProtrusion?.message}` plus
`invalid={!!errors.obstacles?.radiatorProtrusion}`. Dwa razy ta sama ścieżka,
przy każdym z ~40 pól. Ostrzeżenia miękkie trafiały wyłącznie na dół karty,
oderwane od pola, którego dotyczą.

## Decyzja
`Field` przyjmuje `name` (ścieżkę RHF) i sam sobie znajduje:
- błąd twardy — z `useFormState()` przez kontekst `FormProvider`,
- diagnostyki miękkie — z `DiagnosticsProvider` po dopasowaniu `path`.

Stan `invalid` schodzi do kontrolki przez `FieldStateContext`, więc `Input`
i `MmInput` ustawiają `aria-invalid` bez przekazywania propsów.

Miękkie diagnostyki renderują się **inline pod polem**, a na dole karty zostaje
skrót z samymi `critical` — te muszą być widoczne tuż przed kliknięciem „Dalej".

## Konsekwencje
- Kroki przestają importować `errors` do renderu pól; ścieżka pola występuje raz.
- Kroki muszą być owinięte w `FormProvider` — koszt jednej linii na krok.
- Ostrzeżenie pojawia się przy polu, którego dotyczy, zamiast na końcu formularza.
- `path` reguły staje się kontraktem UI: literówka w ścieżce = ostrzeżenie bez
  kotwicy. Dlatego ścieżki są typowane jako `Path<RoomGeometryInput>`.
