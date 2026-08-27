# Architecture Decision Records

Lekkie ADR-y: kontekst → decyzja → konsekwencje. Jeden plik = jedna decyzja.
Nie edytujemy decyzji już podjętych — jeśli coś się zmienia, piszemy nowy ADR
ze statusem `Accepted` i oznaczamy stary jako `Superseded by NNNN`.

| # | Decyzja | Status |
| --- | --- | --- |
| [0001](0001-zod-jako-zrodlo-prawdy.md) | Zod jako źródło prawdy, parse-don't-validate | Accepted |
| [0002](0002-puste-pole-to-null.md) | Puste pole pomiarowe to `null`, nie `0` | Accepted |
| [0003](0003-recznie-pisane-ui.md) | Ręcznie pisane komponenty UI zamiast shadcn/ui CLI | Accepted |
| [0004](0004-zustand-persist-autosave.md) | zustand + persist jako jedyna persystencja | Accepted |
| [0005](0005-hard-vs-soft-poza-rhf.md) | Soft warnings poza stanem react-hook-form | Accepted |
| [0006](0006-ts-strict-bez-unchecked-index.md) | TS strict, bez `noUncheckedIndexedAccess` | Accepted |
| [0007](0007-podsumowanie-jako-print-view.md) | Podsumowanie jako krok kreatora, druk przez `@page` | Accepted |
| [0008](0008-normy-jako-dane.md) | Liczby z normy w jednym module `norms.ts` | Accepted |
| [0009](0009-rule-registry.md) | Rule registry: jeden ruleset, dwóch konsumentów | Accepted |
| [0010](0010-field-diagnostics.md) | `Field name=` + diagnostyki po `path` | Accepted |
