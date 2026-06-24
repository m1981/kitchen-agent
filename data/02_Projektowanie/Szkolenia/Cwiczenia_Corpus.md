Świetny wybór. Program Corpus to potężne narzędzie parametryczne. Jeśli dobrze ustawisz w nim zmienne (zależności między wymiarami), to wygenerowanie nowej kuchni zajmie Ci 15 minut, a na CNC lub piłę pójdą gotowe, bezbłędne formatki.

Jako Twój krytyczny doradca powiem tak: **nie modeluj w Corpusie wszystkiego, co Ci przyjdzie do głowy**. Zbuduj żelazną bibliotekę pod te konkretne style i układy (I, L, U), o których rozmawialiśmy.

Oto Twój katalog do ćwiczeń. Podzieliłem go na moduły, które musisz sparametryzować.

### 1. BAZA: Korpusy Dolne (Wysokość np. 720 mm + cokół)

To fundament. W ciemnych aneksach L i U to one robią całą robotę.

- **Szafka zlewowa (Zlew):**
    - _Parametry do ćwiczeń:_ Brak pełnego wieńca górnego (tylko listwy spinające), cofnięte plecy (na rury), szuflada z wycięciem na syfon (tzw. szuflada zlewowa U-kształtna) lub kosze na śmieci na dnie.
- **Szafka pod piekarnik:**
    - _Parametry do ćwiczeń:_ Obniżony wieniec dolny (żeby piekarnik licował się z frontami), brak pleców, szczelina wentylacyjna z tyłu.
- **Front zmywarki (45 cm i 60 cm):**
    - _Parametry do ćwiczeń:_ To nie szafka, to sam front. Przećwicz parametryzację cokołu pod zmywarką (często trzeba go podciąć, żeby front się otwierał).
- **Moduły szufladowe (3 i 4 szuflady):**
    - _Parametry do ćwiczeń:_ Równe podziały frontów vs. podziały asymetryczne (np. 1 mała, 2 duże). Automatyczne przeliczanie pozycji prowadnic w systemie 32.

### 2. PUŁAPKI: Narożniki (Układy L i U)

Tu stolarze tracą najwięcej nerwów.

- **Ślepy narożnik (tzw. "L-ka"):**
    - _Parametry do ćwiczeń:_ Szafka np. 100-120 cm, z jednymi drzwiami (np. 45-50 cm). **Kluczowe:** Blenda narożna (wypełniacz). W stylu _Modern Classic_ (uchwyty) blenda musi mieć min. 5x5 cm, żeby uchwyty o siebie nie haczyły. W _Nowoczesnym_ (Tip-on) może być mniejsza.
- **Narożnik L-kształtny (łamany 90x90 cm):**
    - _Parametry do ćwiczeń:_ Zawiasy z szerokim kątem otwarcia (np. 155 stopni) + zawiasy uzupełniające.

### 3. ZABUDOWA WYSOKA: Słupki

W aneksach często stoją na jednym z końców układu.

- **Słupek lodówkowy:**
    - _Parametry do ćwiczeń:_ Kratka wentylacyjna w cokole, komin wentylacyjny z tyłu (cofnięte plecy lub ich brak), wieniec górny cofnięty, żeby powietrze miało ujście.
- **Słupek Piekarnik + Mikrofala:**
    - _Parametry do ćwiczeń:_ Zmienna wysokość półek pod sprzęt. Zazwyczaj pod piekarnikiem są 2 szuflady, potem piekarnik, mikrofala i szafka otwierana do góry.

### 4. GÓRA: Szafki Wiszące

W aneksach deweloperskich robi się je pod sam sufit, żeby zmaksymalizować przechowywanie.

- **Szafka pod okap do zabudowy:**
    - _Parametry do ćwiczeń:_ Podniesiony wieniec dolny (okap musi być wyżej niż reszta szafek, jeśli to gaz, lub na równi przy indukcji), wycięcie w wieńcach i półkach na rurę spiro.
- **Szafki z frontami klapowymi (np. Blum Aventos):**
    - _Parametry do ćwiczeń:_ Zależność wagi frontu od siłownika.
- **Blenda podsufitowa (Shadow Gap):**
    - _Parametry do ćwiczeń:_ Sparametryzuj szafkę tak, aby górny wieniec był cofnięty, a front wystawał do góry, zostawiając np. 15 mm szczeliny cieniowej od sufitu.

### 5. WYZWANIA STYLOWE (To musisz mieć w Corpusie jako opcje):

- **System GOLA (Styl Nowoczesny):**
    - _Co ćwiczyć:_ Frezowania w bokach korpusów pod profile aluminiowe (poziome pod blatem i między szufladami, pionowe w słupkach). To zmienia całkowicie wymiary frontów!
- **Witryny z oświetleniem (Modern Classic / Japandi):**
    - _Co ćwiczyć:_ Parametryczne frezowanie rowka pod profil LED w wieńcu dolnym (np. 18 mm od krawędzi, głębokość 7 mm) oraz pionowe frezowania w bokach na kable.
- **Półki wiszące (Skandynawski):**
    - _Co ćwiczyć:_ Nawierty w tylnej krawędzi półki pod niewidoczne ramiona (np. system Triade).
- **Lamele i pogrubienia (Japandi):**
    - _Co ćwiczyć:_ Dodawanie paneli bocznych (tzw. boków nakładanych), które licują się z grubością frontu (np. korpus 18 mm, front 18 mm, bok nakładany 18 mm wysunięty do lica frontu).

**Zadanie domowe dla Ciebie:**
Odpal Corpusa i stwórz **jeden, idealny korpus dolny z szufladami**. Ustaw w nim zmienne tak, żeby po zmianie szerokości z 600 na 800 mm, program sam przeliczył szerokość dna szuflady, pleców i rozstaw nawiertów pod prowadnice. Jak to zrobisz, reszta pójdzie z górki.
