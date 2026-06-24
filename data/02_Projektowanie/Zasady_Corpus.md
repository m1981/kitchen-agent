# PROJEKTOWANIE (Corpus LTR) I WSPÓŁPRACA Z CNC

## 1. ZASADY PROJEKTOWE W CORPUS LTR (Strategia Shift-Left)

- **Blendy maskujące:** Nigdy nie projektuj "na styk". Zawsze zostawiaj min. 3-5 cm po bokach i pod sufitem na blendy docinane na miejscu.
- **Pułapka "Boków Widocznych":** Jeśli bok szafki (np. słupka lodówkowego) jest widoczny z salonu, MUSI być wykonany z materiału frontowego (Swiss Krono EM), a nie z taniej płyty korpusowej (VL).
- **Shift-Left (Zleć to maszynie):** Projektuj w Corpusie wszystkie wycięcia pod gniazdka w plecach HDF, otwory wentylacyjne w wieńcach oraz otwory na rurę od okapu. Na montażu masz tylko skręcać.
- **Plecy szafek:** Projektuj plecy z HDF wpuszczane w nut (frez), aby zapewnić sztywność.
- **Trawersy:** W szafkach pod zlew i indukcję usuwaj wieńce z płyty i zastępuj je profilami metalowymi.

## 2. ZASADY ZLECEŃ NA CNC

- **Nawierty to podstawa:** Zlecaj nie tylko cięcie i okleinowanie, ale ZAWSZE nawiercanie otworów (pod konfirmaty, mimośrody, zawiasy). Składaj jak klocki IKEA.
- **Klej PUR:** Wymagaj oklejania krawędzi klejem poliuretanowym (PUR). Jest wodoodporny i termoodporny.
- **Kontrola:** Sprawdzaj pliki z Corpusa 3 razy przed wysłaniem (uwaga na usłojenie drewna w pionie/poziomie).
- **Formaty plików:** DXF (rysunki CAD), e-Rozkrój / e-Rozrys (systemy online hurtowni).

## 3. PROCES PRODUKCYJNY (Model Podwykonawstwa)

```mermaid
flowchart TD
    A([🖥️ Projekt w Corpus LTR]) --> B[Pliki produkcyjne\nwymiary, otwory, frezowania]
    A --> O[📋 Lista okuć z Corpus\nzawiasy, prowadnice, uchwyty...]

    B --> C{Wybór materiału}
    C --> C1[PET / MDF\nfronty]
    C --> C2[Wiórowa laminowana\nkorpusy]
    C --> C3[HPL Kompakt\nblaty]

    C1 & C2 & C3 --> D

    O --> Z[🛒 Zamówienie okuć\nBlum / Häfele / ATM]

    D[✂️ CENTRUM CNC]
    D --> E[Frezowanie / wiercenie CNC\notwory na zawiasy, konfirmaty]
    E --> F[Okleinowanie krawędzi ABS\nKLEJ PUR - odporność na wilgoć]

    F --> H[📦 Odbiór / dostawa\nsprawdzenie jakości]
    Z --> H

    H --> I[🏠 MONTAŻ U KLIENTA\nkorpusy → fronty → okucia → blaty → AGD]

    style A fill:#4A90D9,color:#fff
    style D fill:#E67E22,color:#fff
    style I fill:#27AE60,color:#fff
    style Z fill:#E74C3C,color:#fff
    style O fill:#E74C3C,color:#fff
```

# Projektowanie wstepne szfek i układu

Projektowanie wstepne można zrobić za pomocą konfiguratora

https://komfort.pl/netdecor
