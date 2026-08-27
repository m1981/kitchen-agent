# 0007 — Podsumowanie jako krok kreatora, druk przez `@page`

**Status:** Accepted · **Data:** 2026-08-27

## Kontekst
Spec wymaga widoku do druku (Ctrl+P → PDF) i eksportu JSON. Alternatywą było
generowanie PDF-a w kodzie (jsPDF, pdfmake).

## Decyzja
Ostatni krok kreatora renderuje kartę A4 zwykłym HTML-em. Druk obsługuje
przeglądarka: `@page { size: A4 portrait }`, klasa `.no-print` na elementach
sterujących i `.print-avoid-break` na sekcjach. Żadnej biblioteki PDF.

## Konsekwencje
- Zero kilobajtów bundle'a na generowanie PDF; wygląd wydruku = wygląd ekranu.
- Podsumowanie renderuje się z `z.output` całości, więc gdy brakuje danych,
  krok pokazuje listę braków zamiast pustej karty.
- Nagłówki/stopki drukarki są poza naszą kontrolą — akceptowalne dla dokumentu
  roboczego z miejscem na podpisy.
