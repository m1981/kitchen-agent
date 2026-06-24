### FRAMEWORK "5K" (Klatka, Kotwice, Klocki, Korekty, Kontrola)

# Wersja A

#### KROK 1: KLATKA (Zdefiniowanie bezpiecznej strefy)

Nie wrzucaj szafek do pustego pliku. Najpierw zbuduj "klatkę", w której będziesz pracować.

1. **Rysujesz ściany z pomiaru**, ale od razu zakładasz najgorszy scenariusz (najwęższy wymiar z pomiaru laserem).
2. **Odejmujesz marginesy bezpieczeństwa:** Od razu rysujesz wirtualne linie 5 cm od lewej ściany, 5 cm od prawej ściany i 5-10 cm od sufitu. To jest miejsce na twoje blendy maskujące.
3. **Zasada:** Twoja zabudowa musi zmieścić się w tej pomniejszonej strefie. Nigdy nie projektuj od ściany do ściany.

#### KROK 2: KOTWICE (Rozmieszczenie punktów krytycznych)

W aneksach "Trójkąt Roboczy" (lodówka-zlew-kuchenka) to często mit, bo deweloper narzuca układ rur. Kotwice to szafki, których NIE MOŻESZ swobodnie przesuwać.

1. **Kotwica Wody (Zlew i Zmywarka):** Wrzucasz szafkę zlewkową dokładnie tam, gdzie jest odpływ. Obok niej od razu dajesz zmywarkę (najlepiej między zlewem a ścianą/słupkiem, żeby otwarte drzwi zmywarki nie blokowały kuchni).
2. **Kotwica Ognia (Płyta i Okap):** Ustawiasz szafkę pod indukcję tam, gdzie jest kabel siłowy (lub blisko niego). Nad nią centrujesz szafkę z okapem (pamiętając o podłączeniu do komina, jeśli to wyciąg).
3. **Kotwica Chłodu (Lodówka):** Słupek lodówkowy ląduje zazwyczaj na jednym z końców aneksu.

_Efekt:_ Masz rozstawione 3-4 najważniejsze bryły. Reszta to tylko wypełnienie.

#### KROK 3: KLOCKI (Wypełnianie przestrzeni)

Teraz wyciągasz ze swojej biblioteki w Corpusie gotowe, parametryczne szafki (te, o których mówiliśmy wcześniej – z cofniętymi plecami).

1. **Szuflady:** Wciskasz moduły z szufladami w największe puste luki między kotwicami. Klienci kochają szuflady.
2. **Szafki górne:** Kopiujesz szerokości szafek dolnych na górę. **Złota zasada estetyki:** Linie pionowe frontów dolnych i górnych MUSZĄ się pokrywać. Jeśli na dole masz szafkę 60 cm, na górze też daj 60 cm.
3. **Symetria:** Jeśli zostaje ci dziwna przestrzeń (np. 34 cm), nie rób jednej szafki 34 cm. Zmniejsz sąsiednią szafkę i zrób dwie równe (np. zamiast 60 i 34, zrób 47 i 47). CNC i tak wytnie to co do milimetra, a wizualnie kuchnia zyska.

#### KROK 4: KOREKTY (Testy kolizji)

To etap, na którym ratujesz swoje pieniądze przed błędami na montażu.

1. **Test narożnika:** Jeśli kuchnia jest w "L", sprawdzasz, czy otwierająca się szuflada nie uderzy w uchwyt piekarnika na prostopadłej ścianie. Zawsze stosuj blendę narożną (tzw. pilaster) min. 5x5 cm!
2. **Test ściany:** Czy front szafki przy ścianie otworzy się na 90 stopni i nie uderzy uchwytem w ścianę? (Dlatego w KROKU 1 daliśmy 5 cm blendy).
3. **Test zmywarki:** Czy otwarte drzwi zmywarki pozwalają ci stanąć przy zlewie?

#### KROK 5: KONTROLA (Przygotowanie pod CNC)

Zanim klikniesz "Eksportuj do maszyny":

1. **Kierunek usłojenia:** Skoro robisz ciemne aneksy (często dekory drewnopodobne lub maty), upewnij się w programie, że słoje na frontach idą w jednym kierunku (zazwyczaj pionowo), a na blendach są z nimi zgodne.
2. **Okleinowanie:** Sprawdź, czy program poprawnie zaznaczył krawędzie do oklejenia (przód korpusu, wszystkie krawędzie frontów). Tył korpusu zostaje surowy.
3. **Nawierty:** Upewnij się, że program wygenerował nawierty pod zawiasy po właściwej stronie (lewe/prawe).

**Podsumowanie:**
Traktuj projektowanie jak układanie Tetrisa, w którym pierwsze klocki (Kotwice) są narzucone przez dewelopera. Jeśli zrobisz sobie w Corpusie szablon startowy z ustawioną "Klatką" i gotowymi "Klockami", projektowanie aneksu zajmie ci 45 minut, a na montażu wszystko złoży się jak z IKEI.

---

# Wersja B

Słuchaj, nazwy brzmią jak z jakiegoś nowoczesnego szkolenia dla menedżerów z Doliny Krzemowej, ale prawda jest taka, że to po prostu **ubrane w ładne słowa absolutne podstawy rzemiosła**, które starzy stolarze stosowali od lat, żeby nie osiwieć na montażu.

Jako pragmatyk powiem Ci tak: nieważne, kto wymyślił te nazwy. Ważne, że to jest dokładnie ten system myślenia, którego potrzebujesz, żeby przestać być "artystą-rzeźbiarzem", a stać się sprawnym inżynierem swojej pracy.

Rozłóżmy to na czynniki pierwsze, po stolarsku:

### 1. Metoda Kotwic i Marginesów

To jest Twoja polisa ubezpieczeniowa na krzywe ściany i błędy pomiarowe.

- **Kotwice (Punkty stałe):** To są elementy w kuchni, których **nie możesz ruszyć** (albo nie chcesz, bo to kosztuje czas i pieniądze klienta). Kotwicą jest przyłącze wody (zlewozmywak), kratka wentylacyjna (okap/płyta), pion kanalizacyjny, okno, czy lodówka wolnostojąca. Projektowanie zaczynasz od osadzenia tych "kotwic". Reszta kuchni musi się do nich dostosować.
- **Marginesy (Luzy i Blendy):** To jest to, co ratuje Ci tyłek na montażu. Nigdy, przenigdy nie projektujesz szafek od ściany do ściany na styk (np. masz wnękę 300 cm, to nie robisz szafek na równe 300 cm). Zostawiasz margines. Robisz szafki na 290 cm, a po bokach dajesz po 5 cm blendy (listwy maskującej). Ściana ucieka z pionu o 2 centymetry? Docinasz blendę strugiem na miejscu i wszystko wygląda idealnie, a korpusy szafek trzymają kąty proste. Margines to Twój bufor bezpieczeństwa.

---

### 2. FRAMEWORK "5K" (Klatka, Kotwice, Klocki, Korekty, Kontrola)

To jest gotowy algorytm (proces) projektowania. Jeśli będziesz robił każdy projekt według tych 5 kroków, skrócisz czas siedzenia przed komputerem o połowę.

**1. Klatka (Bounding Box / Przestrzeń)**
Wchodzisz na pomiar i mierzysz "klatkę", czyli realną przestrzeń. Ale uwaga: nie mierzysz tylko po podłodze! Mierzysz szerokość przy podłodze, na wysokości blatu i pod sufitem. Sprawdzasz kąty (czy jest 90 stopni w rogu) i piony. Twoją "Klatką" do projektowania jest **najmniejszy wymiar**, jaki znalazłeś.

**2. Kotwice (Osadzenie bazy)**
Wrzucasz do programu projektowego (lub na kartkę) to, co musi być w konkretnym miejscu. Zlew idzie tam gdzie woda, płyta tam gdzie siła/gaz i wentylacja. Ustawiasz też szafkę narożną, bo ona determinuje resztę.

**3. Klocki (Moduły standardowe)**
I tu wchodzi optymalizacja, o której mówiłem wcześniej. Przestrzeń między "Kotwicami" wypełniasz standardowymi "Klockami". Masz dziurę na 130 cm? Nie robisz dwóch szafek po 65 cm! Wrzucasz standardową szafkę 80 cm i standardową 45 cm (razem 125 cm). Zostaje Ci 5 cm dziury. Co z nią robisz? Przechodzisz do punktu 4.

**4. Korekty (Blendy, wypełniacze, cokoły)**
Te 5 cm, które Ci zostało, to Twoja korekta. Wstawiasz tam blendę. Korektą jest też odsunięcie szafek od ściany z tyłu (np. o 5 cm), żeby puścić tamtędy rury lub kable, zamiast wycinać dziury w każdym korpusie na montażu. Korekty to wszystkie te elementy, które docinasz na wymiar u klienta, żeby zniwelować krzywizny "Klatki".

**5. Kontrola (Test kolizji i ergonomii)**
Zanim wyślesz formatki na piłę, robisz wirtualny test zderzeniowy.

- Czy jak otworzę zmywarkę, to nie zablokuję sobie dostępu do szafki ze śmieciami?
- Czy szuflada w narożniku nie uderzy o uchwyt piekarnika na prostopadłej ścianie?
- Czy szafka górna nie haczy o lampę sufitową?

### Podsumowanie stolarza:

Ten framework to nie jest żadna magia. To jest **procedura**. Jako jednoosobowa firma musisz działać jak fabryka. Jeśli zaczniesz stosować "5K" i "Kotwice z Marginesami", przestaniesz się pocić na montażach, a zaczniesz składać kuchnie jak meble z IKEI – szybko, czysto i z przewidywalnym zyskiem.
