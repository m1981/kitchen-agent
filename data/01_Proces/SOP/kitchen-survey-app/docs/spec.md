# Spec — Kitchen Survey App (Karta Pomiarowa, Etap 1.1)

> Zakres uzgodniony na starcie projektu. Dokument referencyjny dla przyszłych
> sesji: zanim dołożysz funkcję, sprawdź, czy nie jest świadomie poza zakresem.
> Decyzje wykonawcze i ich uzasadnienia: `docs/adr/`.

## Cel główny

Działająca w przeglądarce, responsywna aplikacja **PWA** w architekturze
**Local-First**. Pełni rolę **kreatora (Wizard Pattern)**, który przeprowadza
stolarza przez proces pomiaru, waliduje dane w czasie rzeczywistym i na końcu
generuje ustrukturyzowany plik JSON oraz widok podsumowania do druku/PDF.

Źródło merytoryczne: `../etap-1-1-karta-pomiarowa.html` (karta A4 do wypełniania
na tablecie u klienta) oraz `../etap-1-1-karta-pomiarowa.md`.

## IN-SCOPE

### 1. Architektura i UI/UX
- **Mobile/Tablet First** — interfejs pod dotyk (duże przyciski, czytelne
  inputy), oparty na frameworku CSS (Tailwind + komponenty w konwencji shadcn/ui).
- **Wizard Pattern** — formularz podzielony na logiczne kroki (Dane, Geometria,
  Instalacje, Pakiet, Podsumowanie). Użytkownik widzi jeden krok naraz.
- **Progressive Disclosure** — pola pojawiają się dynamicznie. Przykład: sekcja
  „Wymiary okna" renderuje się TYLKO gdy `hasWindow === true`.

### 2. Zarządzanie stanem i walidacja
- **Schema-Driven Validation** — Zod jako ścisłe typowanie danych.
- **Auto-kalkulacje (cross-field)** — wpis `bottom: 2500, middle: 2510,
  top: 2490` wylicza i zapisuje w stanie `min_dimension: 2490`.
- **Soft & Hard Warnings**
  - *Hard (blokujące)* — brak szerokości ściany blokuje przejście dalej.
  - *Soft (ostrzegawcze)* — kąt `85°` wyświetla żółty alert („Kąt ostry!"),
    ale pozwala iść dalej.

### 3. Persystencja (Offline-First)
- **Auto-Save do LocalStorage/IndexedDB** — po każdej zmianie inputa stan jest
  zapisywany lokalnie. Odświeżenie strony lub zamknięcie przeglądarki wraca do
  ostatniego draftu.
- **Reset Session** — przycisk czyszczący pamięć lokalną.

### 4. Output
- **JSON Export** — przycisk „Pobierz dane" zrzucający stan do
  `pomiar_<nazwisko>.json`.
- **Print View** — ostatni krok kreatora generuje czysty, sformatowany widok
  HTML do wydruku przez systemowe `Ctrl+P` / `Cmd+P`.

## OUT-OF-SCOPE

### 1. Backend i chmura
- Brak bazy danych (SQL/NoSQL) — bez PostgreSQL, MongoDB, Firebase.
- Brak autentykacji — bez logowania, rejestracji, JWT, OAuth.
- Brak API — bez endpointów REST i GraphQL.

### 2. Funkcje graficzne i CAD
- Brak renderowania 2D/3D — aplikacja zbiera **tylko liczby i wartości
  logiczne**. Bez Canvasa, Fabric.js, Three.js.
- Brak narzędzia do szkicowania — zostaje `textarea` na notatki. Szkic stolarz
  robi na kartce lub telefonem, poza aplikacją.

### 3. Funkcje biznesowe (ERP/CRM)
- Brak wycen i cenników.
- Brak generowania umów — to osobny proces.
- Brak historii klientów i listy „Moje Pomiary". Jedna sesja pomiarowa naraz.

## Tech stack (narzucony)

| Obszar | Wybór |
| --- | --- |
| Framework | React + Vite + TypeScript (strict) |
| Styling | Tailwind CSS + komponenty w konwencji `shadcn/ui` |
| Formularze | `react-hook-form` + `zod` + `@hookform/resolvers` |
| Stan | `zustand` + middleware `persist` |
| Ikony | `lucide-react` |

Stack jest celowo wąski — nie dobieramy egzotycznych bibliotek bez ADR-a.
