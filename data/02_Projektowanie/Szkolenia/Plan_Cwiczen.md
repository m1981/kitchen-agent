### ETAP 1: Fundamenty – Materiałoznawstwo i Okucia

## Makra

### Dodawanie zmiennych i równania

https://youtu.be/P0mBZGfTSQg?list=PLnvYGeIBTN4flHgPWNfijSAISTkB51Ej9&t=778

Nie zaprojektujesz szafki, jeśli nie wiesz, z czego i jak jest zrobiona.

1.  **Płyty i obrzeża:** Standardy grubości (18 mm korpusy, czasem 16 mm; fronty 18-19 mm). Rodzaje obrzeży (ABS 0.8 mm, 1 mm, 2 mm) i jak wpływają na wymiar końcowy formatki.
2.  **Plecy (HDF 3 mm):** Nabijane (błąd w kuchniach premium) vs. wpuszczane w nut (frezowany rowek). Jak głęboko wpuścić nut, żeby szafka trzymała kąt prosty i żeby zmieściła się zawieszka do szyny montażowej.
3.  **Okucia bazowe:** Zawiasy (nakładane, bliźniacze, wpuszczane, kątowe) – jak wyliczyć odległość puszki i szczeliny. Systemy szuflad (np. Blum, GTV) – jak czytać ich katalogi techniczne i wyliczać dno/tył.
4.  **Złącza:** Konfirmaty (tanie, widoczne) vs. złącza mimośrodowe/kołki (niewidoczne, wymagają precyzji CNC).

### ETAP 2: Zderzenie z rzeczywistością – Pomiar i Ergonomia

Zanim odpalisz komputer, musisz mieć bezbłędne dane wejściowe.

1.  **Inwentaryzacja z natury:** Używanie lasera krzyżowego i dalmierza. Sprawdzanie pionów, poziomów, kątów (reguła 3-4-5 lub kątownik budowlany).
2.  **Mapowanie instalacji:** Zaznaczanie wody, odpływu, gniazdek, wentylacji. Wyznaczanie stref kolizyjnych.
3.  **Ergonomia i trójkąt roboczy:** Gdzie lodówka, gdzie zlew, gdzie płyta. Odległości między nimi.
4.  **Planowanie luzów i blend:** Ile centymetrów zostawić na pasowanie do krzywych ścian i sufitu (blendy boczne i górne).

### ETAP 3: Środowisko CAD/CAM – Konfiguracja programu (Corpus)

Zasada GIGO (Garbage In, Garbage Out). Źle ustawisz program, maszyna źle wytnie.

1.  **Zmienne globalne:** Ustawienie domyślnych grubości płyt, szczelin między frontami (standard to 2-3 mm), wysokości cokołu (zazwyczaj 100 lub 150 mm).
2.  **Zarządzanie obrzeżami:** KRYTYCZNE. Konfiguracja programu tak, aby automatycznie odejmował grubość okleiny od wymiaru cięcia płyty (tzw. wymiar netto vs brutto).
3.  **Biblioteki okuć:** Wprowadzanie do programu schematów nawierceń (tzw. reguł obróbczych) dla zawiasów, prowadnic i złącz.

### ETAP 4: Konstruowanie brył – Od prostych do skomplikowanych

Teraz zaczynasz projektować.

1.  **Szafki dolne i górne (baza):** Konstrukcja wieńców (wieniec dolny między bokami czy pod bokami?), głębokości korpusów (np. dół 510-560 mm bez frontu, góra 300-320 mm).
2.  **Szafki narożne:** Ślepy narożnik vs. narożnik L. Wyliczanie szerokości słupków narożnych (blend), żeby fronty i uchwyty nie uderzały o siebie.
3.  **Zabudowa AGD (Strefa podwyższonego ryzyka):** Szafki pod zlew (brak pełnych pleców, wieniec przedni pionowy), szafki pod piekarnik, słupki lodówkowe (wentylacja!).
4.  **Szuflady:** Parametryzacja frontów szuflad w jednym słupku (np. układ 140-284-284 mm) z uwzględnieniem szczelin.

### ETAP 5: Weryfikacja i Generowanie Produkcji (CAM)

Ostatni moment, żeby uniknąć katastrofy finansowej.

1.  **Kontrola kolizji:** Sprawdzanie w 3D, czy szuflady nie uderzają o zawiasy, czy fronty się otwierają, czy AGD ma wentylację.
2.  **Optymalizacja rozkroju:** Układanie formatek na płycie (tzw. nesting lub cięcie na pilarce panelowej). Zwracanie uwagi na _usłojenie_ (kierunek słojów drewna na frontach i widocznych bokach).
3.  **Eksport na CNC:** Generowanie kodów na maszynę (nawierty, frezowania).
4.  **Dokumentacja montażowa:** Rysunki dla Ciebie na montaż – gdzie idzie która szafka, wymiary blend.

---

Cieszę się, że łapiesz tę inżynieryjną perspektywę. Stolarstwo to fizyka, geometria i przewidywanie, gdzie nie wsadzisz śrubokręta.

Co do **Lamello Cabineo** – to absolutnie genialny wybór do otwartych półek i szafek. Wymaga obróbki CNC tylko z jednej płaszczyzny (z góry), jest piekielnie mocne i w Corpusie łatwo je sparametryzować. Świetna decyzja, wchodzisz na poziom pro.

Oto Twoja rosnąca ściąga. Skopiuj to sobie.

---

### 🛠️ ŚCIĄGA STOLARZA / OPERATORA CORPUS (Wersja 1.0)

**1. SYSTEMY ŁĄCZEŃ W KUCHNI:**

- **Baza (90% szafek):** Konfirmaty. Widoczne boki maskujemy nakładaną płytą frontową (przykręcaną od wewnątrz).
- **Słupki pod sufit:** Składane w pionie! Wieniec górny na złącza mimośrodowe (np. Minifix, VB36). _Powód: Przekątna szafki przy podnoszeniu uderzy w sufit, a w pionie nie zmieścisz wiertarki nad szafką._
- **Otwarte półki/regały:** Lamello Cabineo (lub kołki+klej). _Powód: Estetyka, brak widocznych śrub._
- **Łączenie szafek w ciąg:** Śruby łączące M4 (w ukrytych miejscach, np. pod zawiasem) lub wkręty 4x30 mm. _Uwaga: 2x płyta 18mm = 36mm. Wkręt 30mm jest bezpieczny._
- **Łączenie blatów:** Frezowanie CNC (zamek męski/żeński) + śruby rzymskie + lamelki/kołki + uszczelniacz (silikon/klej PUR).
- **Cokoły i blendy:** Cokoły na klipsy do nóżek. Blendy przykręcane od wewnątrz szafki (wkręty 4x30).

---

### Co jeszcze musisz wiedzieć z działu "Materiałoznawstwo i Okucia"?

Zostały nam 3 krytyczne miny, na których amatorzy tracą pieniądze. Wybierz, co bierzemy na warsztat jako pierwsze:

**A. Plecy szafek (HDF 3mm) i systemy zawieszek.**
Jeśli przybijesz plecy na gwoździe (jak w tanich meblach), szafka nie będzie trzymać kąta prostego, a na ścianie będzie odstawać. Musisz poznać system "nutowania" (frezowania rowka) i zawieszki typu Camar. Błąd tutaj = szafka spadająca ze ściany.

**B. Matematyka Zawiasów.**
Zawias nakładany, bliźniaczy, wpuszczany, kątowy (np. 155 stopni do szafek z szufladami wewnętrznymi). Musisz wiedzieć, jak wyliczyć szczeliny i dlaczego standardowy prowadnik zawiasu montuje się dokładnie 37 mm od przedniej krawędzi korpusu. Błąd tutaj = fronty ocierają o siebie lub nie dają się wyregulować.

**C. Nóżki meblowe i Cokoły.**
Gdzie dokładnie umieścić nóżki pod szafką? Jeśli dasz je na samych rogach, nie zamontujesz cokołu (musi być cofnięty, żeby klient nie kopał w niego palcami). Jeśli dasz je źle pod szafką zmywakową lub lodówką, dno się zarwie.

Co wybierasz? A, B czy C?
