# OŚWIETLENIE LED – SYSTEM HÄFELE LOOX5 (Kompendium Praktyczne)

## 🎯 DLACZEGO TO JEST KRYTYCZNE?

**LED w kuchni to nie ozdoba – to funkcja.**  
Źle zaprojektowane oświetlenie = przepalony zasilacz, nierównomierne świecenie, przegrzane taśmy, reklamacje.  
Dobrze zaprojektowane = efekt WOW na odbiorze, klient robi zdjęcia i poleca Cię znajomym.

**Najczęstsze błędy (które będę Ci wytykał):**

- Klejenie taśm LED bezpośrednio do płyty (brak odprowadzania ciepła)
- Zbyt słaby zasilacz (brak zapasu mocy)
- Za długie obwody (spadki napięcia → nierównomierne świecenie)
- Brak dylatacji przewodów (przy montażu szarpiesz kabel i wyrywasz go z taśmy)

---

## 1. EKOSYSTEM HÄFELE LOOX5 – DLACZEGO TO STANDARD?

### **Plusy systemu Loox5:**

✅ **Plug & Play** – wszystko jest kompatybilne (taśmy, zasilacze, sterowniki, sensory)  
✅ **Napięcie 24V** – bezpieczniejsze niż 12V (mniejsze spadki napięcia na długich obwodach)  
✅ **Modułowa budowa** – łatwo rozbudowujesz system (dodajesz strefy, sterowniki RGB, czujniki ruchu)  
✅ **Dostępność w Polsce** – Häfele ma sklep online i hurtownie w każdym większym mieście  
✅ **Gwarancja 3 lata** – jak coś się spali, wymieniają bez pytań (ważne przy reklamacjach klientów)

### **Minusy:**

❌ Droższe niż chiński no-name z Allegro o ~40%  
❌ Wymaga planowania **przed wysłaniem projektu na CNC** (otwory pod sensory, rowki pod przewody)

**Moja rada:** Loox5 to inwestycja, która się zwraca. Klient widzi różnicę między "taśmą z Allegro" a systemem profesjonalnym.

---

## 2. PODSTAWY ELEKTRYCZNE (Żebyś nie spalił systemu)

### A) **Napięcie: 12V vs 24V**

| Parametr              | 12V                                     | 24V (Loox5)                                |
| --------------------- | --------------------------------------- | ------------------------------------------ |
| **Spadek napięcia**   | Duży (max 2m obwodu)                    | Mały (max 5m obwodu)                       |
| **Grubość przewodów** | Grubsze (większy prąd)                  | Cieńsze (mniejszy prąd)                    |
| **Zastosowanie**      | Krótkie odcinki (podświetlenie szuflad) | Długie obwody (blat roboczy, szafki górne) |

**ZŁOTA ZASADA:**  
W kuchni **ZAWSZE 24V** (Loox5), chyba że robisz tylko podświetlenie 1 szuflady (wtedy można 12V).

---

### B) **Moc taśmy i dobór zasilacza**

**Typowe moce taśm Loox5:**

| Typ taśmy                               | Moc na 1 metr  | Zastosowanie                          |
| --------------------------------------- | -------------- | ------------------------------------- |
| **Loox5 LED 2047** (biała ciepła 3000K) | **4,8 W/m**    | Oświetlenie blatu roboczego           |
| **Loox5 LED 2091** (RGB+W)              | **14,4 W/m**   | Efekty kolorystyczne (szafki górne)   |
| **Loox5 LED 3001** (moduły punktowe)    | **1,5 W/szt.** | Podświetlenie szuflad, wnętrza szafek |

**OBLICZANIE MOCY ZASILACZA:**

**Wzór:**

```
Moc zasilacza = (Długość taśmy × Moc na metr) × 1,2
```

**Przykład:**

- Taśma Loox5 LED 2047 (4,8 W/m)
- Długość: 3 metry (blat roboczy L-kształtny)
- Moc: 3m × 4,8 W/m = **14,4 W**
- Zasilacz: 14,4 W × 1,2 = **17,3 W** → wybierasz **zasilacz 24V / 20W** (nr katalogowy: **833.73.050**)

**⚠️ KRYTYCZNE:**  
Współczynnik 1,2 to **zapas mocy 20%** – bez tego zasilacz będzie pracował na 100% i spali się po roku.

---

### C) **Spadki napięcia – jak ich uniknąć**

**Problem:**  
Im dłuższy przewód od zasilacza do taśmy, tym większy spadek napięcia → taśma świeci słabiej na końcu.

**Maksymalne długości przewodów (24V):**

| Moc obwodu  | Max długość przewodu 2×0,75mm² | Max długość przewodu 2×1,5mm² |
| ----------- | ------------------------------ | ----------------------------- |
| do 20W      | **5 metrów**                   | **10 metrów**                 |
| 20-50W      | **3 metry**                    | **6 metrów**                  |
| powyżej 50W | **2 metry**                    | **4 metry**                   |

**ROZWIĄZANIE przy długich obwodach:**  
Zamiast jednego zasilacza → użyj **2 zasilaczy w różnych punktach** (zasilanie z dwóch stron).

**Przykład:**

- Kuchnia w kształcie U, blat roboczy 6 metrów
- Zamiast 1 zasilacz + 6m taśmy → zrób **2 zasilacze po 3 metry taśmy** (zasilanie z lewej i prawej strony)

---

## 3. MONTAŻ TAŚM LED – PROCEDURA KROK PO KROKU

### **KROK 1: Profil aluminiowy (OBOWIĄZKOWY!)**

**Dlaczego NIE kleisz taśmy bezpośrednio do płyty?**

- Płyta nie odprowadza ciepła → LED się przegrzewa → żywotność spada z 50 000h do 5 000h
- Taśma przyklejona do płyty odklejaa się po roku (para z gotowania + ciepło = rozpad kleju)

**ROZWIĄZANIE:**  
**Profil aluminiowy** – pełni rolę radiatora (odprowadza ciepło) + estetyka (osłona rozpraszająca światło).

**Typy profili Loox5:**

| Typ profilu                           | Nr katalogowy  | Zastosowanie                                        |
| ------------------------------------- | -------------- | --------------------------------------------------- |
| **Profil wpuszczany** (do rowka 12mm) | **833.72.701** | Blat roboczy (profil schowany pod szafkami górnymi) |
| **Profil natynkowy** (kątowy)         | **833.72.702** | Szafki górne (profil przyklejony pod dnем szafki)   |
| **Profil płaski** (z osłoną mleczną)  | **833.72.703** | Oświetlenie szuflad (wewnątrz korpusu)              |

**Długości profili:** 1m, 2m, 2,5m (można ciąć piłką do metalu)

---

### **KROK 2: Mocowanie profilu**

#### **A) Profil wpuszczany (do blatu roboczego):**

**Przygotowanie w Corpus LTR:**

- W dolnej powierzchni szafek górnych musisz zafrezować **rowek 12mm szerokości × 10mm głębokości**
- Odległość rowka od krawędzi przedniej: **30-50mm** (żeby światło nie raziło w oczy)

**Montaż:**

1. Wklej profil do rowka na **silikon neutralny** (nie kwasowy! – niszczy LED)
2. Wsuń taśmę LED do profilu (taśma ma klej z tyłu – przykleja się do dna profilu)
3. Załóż osłonę mleczną (rozprasza światło, eliminuje efekt "kropek LED")

#### **B) Profil natynkowy (szafki górne):**

**Montaż:**

1. Przyklej profil do dolnej powierzchni szafki górnej (30-50mm od krawędzi)
2. Użyj **taśmy dwustronnej 3M VHB** (nie zwykłej – to się odklejaa!)
3. Wsuń taśmę LED, załóż osłonę

---

### **KROK 3: Podłączenie do zasilacza**

**Schemat połączenia:**

```
[Gniazdko 230V] → [Zasilacz 24V] → [Sterownik/ściemniacz] → [Taśma LED]
```

**Złącza Loox5:**

- Wszystkie przewody mają **złącza wtykowe** (żaden lutowanie, żadne skrętki!)
- Kolory przewodów:
    - **Czerwony (+)** – plus 24V
    - **Czarny (–)** – masa (GND)
    - **Biały (S)** – sygnał sterujący (do czujników ruchu, ściemniaczy)

**⚠️ Najczęstszy błąd:**  
Zamieniasz + i – → LED nie świeci (ale się nie spali, Loox5 ma zabezpieczenie polaryzacji).

---

### **KROK 4: Prowadzenie przewodów**

**Gdzie chować przewody?**

1. **W korpusach szafek:**
    - Przewód prowadź **wzdłuż tylnej krawędzi** (przyklejony do płyty taśmą aluminiową)
    - W miejscach przejść między szafkami: wywierć **otwór 10mm** w ściankach bocznych (CNC to zrobi)

2. **Pod blatem roboczym:**
    - Przewód przyklejony do spodu blatu **nie bliżej niż 50mm od krawędzi** (żeby nie było widać)

3. **W cokole:**
    - Jeśli zasilacz jest w szafce dolnej, a taśma w górnej → przewód prowadź **w cokole** (wyfrež rowek 10mm w cokole)

**ZŁOTA ZASADA:**  
Przewody muszą mieć **luz 10-15cm** w miejscach połączeń (żeby przy montażu nie szarpać i nie wyrwać ze złącza).

---

## 4. STEROWANIE ŚWIATŁEM

### **A) Włącznik dotykowy (podstawowy)**

**Model:** Loox5 **12V sensor dotykowy** (nr **833.73.323**)  
**Montaż:** Wpuszczany w front/blat (otwór 8mm)  
**Funkcja:** Dotknięcie = włącz/wyłącz, przytrzymanie = ściemnianie

**Gdzie montować:**

- W blacie roboczym (30-50mm od krawędzi)
- W froncie szafki górnej (przy uchwycie)

**⚠️ Ważne:**  
Otwór pod sensor musi być **przewidziany w projekcie CNC** (średnica 8mm, głębokość na wylot).

---

### **B) Czujnik ruchu (premium)**

**Model:** Loox5 **czujnik ruchu PIR** (nr **833.73.650**)  
**Montaż:** Wpuszczany w dolną powierzchnię szafki górnej (otwór 12mm)  
**Funkcja:** Automatyczne włączanie światła przy zbliżeniu ręki

**Zastosowanie:**

- Oświetlenie blatu roboczego (ręka się zbliża → światło włącza)
- Szuflady (otwierasz szufladę → światło włącza wnętrze)

**Ustawienia:**

- Czas świecenia po wykryciu ruchu: 30s / 1min / 3min (regulowane DIP-switchami)
- Czułość: regulowana potencjometrem

---

### **C) Pilot/aplikacja (dla wymagających klientów)**

**Model:** Loox5 **sterownik RGB+W z Bluetooth** (nr **833.73.058**)  
**Funkcja:**

- Zmiana koloru światła (RGB)
- Ściemnianie (0-100%)
- Scenariusze (praca, relaks, kolacja)
- Sterowanie przez aplikację **Loox App** (iOS/Android)

**Cena:** ~300 zł (ale klient to doceni przy odbiorze – efekt premium!)

---

## 5. TYPOWE KONFIGURACJE (Gotowe schematy)

### **KONFIGURACJA 1: Mała kuchnia (2,5m blatu roboczego)**

**Komponenty:**

- Taśma LED 2047 (biała 3000K): **3 metry** (nr **833.73.001**)
- Profil wpuszczany: **2x 1,5m** (nr **833.73.701**)
- Zasilacz 24V/20W: **1 szt.** (nr **833.73.050**)
- Włącznik dotykowy: **1 szt.** (nr **833.73.323**)
- Przewód przedłużający 2m: **1 szt.** (nr **833.79.801**)

**Koszt:** ~350 zł (netto, zakup hurtowy)  
**Montaż:** 30 minut

---

### **KONFIGURACJA 2: Kuchnia w kształcie L (5m blatu + oświetlenie wnętrza szafek)**

**Komponenty:**

- Taśma LED 2047: **6 metrów** (2x 3m)
- Profil wpuszczany: **4x 1,5m**
- Zasilacz 24V/40W: **2 szt.** (zasilanie z dwóch stron – unikanie spadków napięcia)
- Czujnik ruchu PIR: **2 szt.** (blat roboczy + szafka narożna)
- Moduły punktowe LED: **6 szt.** (do szafek górnych ze szkłem)
- Przewody przedłużające: **3x 2m**

**Koszt:** ~800 zł (netto)  
**Montaż:** 1,5 godziny

---

### **KONFIGURACJA 3: Kuchnia premium (U-kształt + RGB + automatyka)**

**Komponenty:**

- Taśma RGB+W 2091: **8 metrów**
- Profil wpuszczany: **6x 1,5m**
- Zasilacz 24V/100W: **2 szt.**
- Sterownik RGB Bluetooth: **1 szt.**
- Czujniki ruchu: **4 szt.** (blat + szuflady)
- Taśma LED do szuflad: **4 metry** (+ profile płaskie)
- Przewody przedłużające: **5x 2m**

**Koszt:** ~1500 zł (netto)  
**Montaż:** 2,5 godziny  
**Efekt:** Klient robi film i wrzuca na Instagram → darmowy marketing

---

## 6. MONTAŻ W SZUFLADACH (Podświetlenie wnętrza)

### **System Loox5 do szuflad:**

**Problem:**  
Taśma LED w szufladzie musi:

- Włączać się przy otwieraniu
- Wyłączać przy zamykaniu
- Nie przeszkadzać w korzystaniu z szuflady

**ROZWIĄZANIE:**

**Model:** Loox5 **zestaw LED do szuflad** (nr **833.73.130**)

**Zawartość:**

- Moduły LED (2 szt. na szufladę)
- Czujnik kontaktronowy (włącza przy otwarciu szuflady)
- Zasilacz 24V
- Przewód przedłużający

**Montaż:**

1. Przyklej moduły LED do **boków wewnętrznych** szuflady (nie do tyłu – nie będzie widać!)
2. Zamontuj czujnik kontaktronowy w **górnej krawędzi frontu** szuflady
3. Podłącz do zasilacza (schowanego w korpusie szafki)

**Odległość LED od góry szuflady:** 50mm (żeby światło nie raziło w oczy przy wyciąganiu szuflady)

---

## 7. CHECKLISTA PRZED WYSŁANIEM PROJEKTU NA CNC

✅ **Czy w dolnej powierzchni szafek górnych masz rowek 12mm × 10mm pod profil LED?**  
✅ **Czy rowek jest 30-50mm od krawędzi przedniej (żeby światło nie raziło)?**  
✅ **Czy przewidziałeś otwory 8mm pod włączniki dotykowe?**  
✅ **Czy przewidziałeś otwory 12mm pod czujniki ruchu?**  
✅ **Czy w ściankach bocznych korpusów są otwory 10mm na przewody (miejsca połączeń między szafkami)?**  
✅ **Czy zasilacz zmieści się w szafce (wymiary 100×50×30mm)?**  
✅ **Czy obliczyłeś moc zasilacza z zapasem 20%?**  
✅ **Czy przewody mają luz 10-15cm w miejscach połączeń?**

---

## 8. NAJCZĘSTSZE BŁĘDY I JAK ICH UNIKNĄĆ

### ❌ **Błąd #1: Taśma przyklejona bezpośrednio do płyty (bez profilu aluminiowego)**

**Objaw:** Po roku taśma się odklejaa, LED świeci słabiej (przegrzanie)  
**Rozwiązanie:** **ZAWSZE montuj taśmę w profilu aluminiowym** (odprowadza ciepło)

---

### ❌ **Błąd #2: Za słaby zasilacz (brak zapasu mocy)**

**Objaw:** LED świeci słabo, zasilacz jest gorący, po roku się spala  
**Rozwiązanie:** Moc zasilacza = moc taśmy **× 1,2** (zapas 20%)

**Przykład błędu:**

- Taśma 5m × 4,8 W/m = 24W
- Stolarz kupuje zasilacz 24W (bez zapasu)
- Po roku zasilacz spala się → reklamacja

**Poprawnie:**

- Taśma 24W → zasilacz **30W** (24W × 1,2 = 28,8W → zaokrąglasz do 30W)

---

### ❌ **Błąd #3: Za długie obwody (spadki napięcia)**

**Objaw:** Koniec taśmy świeci słabiej niż początek (kolor żółtawy zamiast białego)  
**Rozwiązanie:** Max 5m taśmy na 1 zasilacz (24V) → jeśli więcej, użyj 2 zasilaczy (zasilanie z dwóch stron)

---

### ❌ **Błąd #4: Brak osłony mlecznej (widoczne "kropki" LED)**

**Objaw:** Zamiast równomiernego światła widać punkty LED (efekt "girlandy")  
**Rozwiązanie:** **Zawsze używaj profilu z osłoną mleczną** (rozprasza światło)

---

### ❌ **Błąd #5: Przewody bez luzu (wyrwanie ze złącza)**

**Objaw:** Przy montażu szarpiesz przewód → wyrywasz go ze złącza → trzeba wymieniać taśmę  
**Rozwiązanie:** Przewody **zawsze z luzem 10-15cm** w miejscach połączeń

---

### ❌ **Błąd #6: Silikon kwasowy (zamiast neutralnego)**

**Objaw:** Po 3 miesiącach LED zaczynają gasnąć (kwas niszczy obwody)  
**Rozwiązanie:** Do klejenia profili **tylko silikon neutralny** (typ NP – neutral purpose)

---

## 9. NUMERY KATALOGOWE – ŚCIĄGA ZAMÓWIENIOWA (Häfele Loox5)

### **Taśmy LED (najczęściej używane):**

| Typ      | Kolor                 | Moc      | Długość | Nr katalogowy  |
| -------- | --------------------- | -------- | ------- | -------------- |
| LED 2047 | Biała ciepła 3000K    | 4,8 W/m  | 5m      | **833.73.001** |
| LED 2048 | Biała neutralna 4000K | 4,8 W/m  | 5m      | **833.73.002** |
| LED 2091 | RGB+W                 | 14,4 W/m | 5m      | **833.73.050** |

### **Profile aluminiowe:**

| Typ                | Długość | Nr katalogowy  |
| ------------------ | ------- | -------------- |
| Wpuszczany (12mm)  | 2,5m    | **833.72.701** |
| Natynkowy (kątowy) | 2,5m    | **833.72.702** |
| Płaski (szuflady)  | 1m      | **833.72.703** |

### **Zasilacze 24V:**

| Moc  | Nr katalogowy  | Zastosowanie          |
| ---- | -------------- | --------------------- |
| 20W  | **833.73.050** | Kuchnia do 3m         |
| 40W  | **833.73.051** | Kuchnia 3-6m          |
| 100W | **833.73.053** | Kuchnia >6m (lub RGB) |

### **Sterowniki/czujniki:**

| Typ                     | Nr katalogowy  | Funkcja                    |
| ----------------------- | -------------- | -------------------------- |
| Włącznik dotykowy       | **833.73.323** | Włącz/wyłącz + ściemnianie |
| Czujnik ruchu PIR       | **833.73.650** | Automatyczne włączanie     |
| Sterownik RGB Bluetooth | **833.73.058** | Zmiana koloru + aplikacja  |

### **Akcesoria:**

| Typ               | Nr katalogowy  | Zastosowanie                          |
| ----------------- | -------------- | ------------------------------------- |
| Przewód 2m        | **833.79.801** | Przedłużenie między szafkami          |
| Zestaw do szuflad | **833.73.130** | Podświetlenie wnętrza szuflad         |
| Rozgałęźnik T     | **833.79.810** | Podłączenie wielu taśm do 1 zasilacza |

---

## 10. GDZIE KUPOWAĆ? (Hurtownie Wrocław i online)

### **Stacjonarne (Wrocław):**

- **Häfele Showroom** (ul. Strzegomska) – pełen asortyment Loox5, doradztwo techniczne, możliwość testowania systemu
- **Admar** – dobrze zaopatrzeni, darmowa dostawa >500 zł

### **Online:**

- **Hafele.pl** – oficjalny sklep, czasem promocje na zestawy (np. taśma + profil + zasilacz w pakiecie -15%)
- **Wurth.pl** – mają alternatywne systemy LED (Riga), kompatybilne z Loox5, czasem tańsze
- **Sklep-okucia.pl** – duży wybór, szybka wysyłka

### **Kiedy kupować hurtowo:**

- Przy zakupie >10 zestawów (np. budowa osiedla) → negocjuj rabat 20-30% z przedstawicielem Häfele

---

## 🎯 NASTĘPNY KROK:

Po opanowaniu LED przejdź do **SEKCJI 3: CHECKLISTA KOLIZJI** – bo najlepszy projekt z najlepszymi zawiasami i LED-ami pójdzie do kosza, jeśli uchwyt szuflady uderzy w front narożnika albo kosz na śmieci zablokuje syfon.

**Pytania do tego rozdziału? Coś niejasne? Teraz najlepszy moment, zanim przejdziemy do kolizji.**
