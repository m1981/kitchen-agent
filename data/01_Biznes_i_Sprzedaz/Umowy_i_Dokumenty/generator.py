#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generator dokumentacji prawnej dla zabudowy meblowej.

Skleja 4 szablony Markdown w jeden plik wynikowy gotowy do eksportu do PDF:
    1. umowa_template.md       -> Umowa Główna        (RODZIC, numer umowy: TAK)
    2. zalacznik1_template.md  -> Załącznik nr 1      (DZIECKO, numer umowy: NIE)
    3. instrukcja_template.md  -> Załącznik nr 2      (DZIECKO, numer umowy: NIE)
    4. protokol_template.md    -> Protokół odbioru    (ZAMYKAJĄCY, numer umowy: TAK)

Użycie:
    python generator.py klient.json        # generuje komplet dokumentów
    python generator.py --szablon nowy.json  # tworzy pusty formularz do wypełnienia

Dane klienta zawsze pochodzą z pliku JSON — nigdy z kodu.
"""

from __future__ import annotations

import datetime
import difflib
import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

# --- Ścieżki liczone względem pliku skryptu, nie względem cwd ----------------
BAZA = Path(__file__).resolve().parent
KATALOG_WYNIKOWY = BAZA / "wygenerowane"

ZNACZNIK_STRONY = "<div style='page-break-after: always;'></div>"
WZORZEC_ZMIENNEJ = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")

# ============================================================================
# 1. DANE WYKONAWCY I PARAMETRY UMOWNE
# ============================================================================

DANE_FIRMY = {
    "FIRMA_NAZWA": "DuoDraft",
    "FIRMA_ADRES": "ul. Inowroclawska 19/10, 53-653 Wrocław",
    "FIRMA_NIP": "967-108-45-72",
    "FIRMA_REPREZENTANT": "Michał Nakiewicz",
    "FIRMA_TELEFON": "519 687 702",
    "FIRMA_EMAIL": "biuro@duodraft.pl",
}

# Parametry umowne wspólne dla wszystkich dokumentów
PARAMETRY_UMOWY = {
    "OKRES_GWARANCJI_MIESIACE": "24",
    "TERMIN_USTEREK_DNI": "14",
    "KOSZT_MAGAZYNOWANIA": "50",
}

# --- Nazwy dokumentów: JEDNO ŹRÓDŁO PRAWDY ---------------------------------
# Odmieniamy wyłącznie część rodzajową nazwy ("Załącznik nr 1", "Umowa o Dzieło").
# Tytuł opisowy (TYTUL) jest nieodmienny i występuje jako cytat w nawiasie —
# zgodnie z praktyką legislacyjną. Dzięki temu zmiana nazwy dokumentu w tym
# jednym miejscu propaguje się na wszystkie 4 szablony w poprawnej gramatyce.
#
# Przypadki: M mianownik, D dopełniacz, C celownik, B biernik,
#            N narzędnik, MS miejscownik. Każdy dostaje też wariant _CAPS.
NAZWY_DOKUMENTOW = {
    "UMOWA": {
        "TYTUL": "Projekt, Wykonanie i Montaż Zabudowy Meblowej",
        "M": "Umowa o Dzieło",
        "D": "Umowy o Dzieło",
        "C": "Umowie o Dzieło",
        "B": "Umowę o Dzieło",
        "N": "Umową o Dzieło",
        "MS": "Umowie o Dzieło",
    },
    "ZAL_1": {
        "TYTUL": "Projekt i Specyfikacja Materiałowa",
        "M": "Załącznik nr 1",
        "D": "Załącznika nr 1",
        "C": "Załącznikowi nr 1",
        "B": "Załącznik nr 1",
        "N": "Załącznikiem nr 1",
        "MS": "Załączniku nr 1",
    },
    "ZAL_2": {
        "TYTUL": "Karta Pielęgnacji i Użytkowania Zabudowy Kuchennej",
        "M": "Załącznik nr 2",
        "D": "Załącznika nr 2",
        "C": "Załącznikowi nr 2",
        "B": "Załącznik nr 2",
        "N": "Załącznikiem nr 2",
        "MS": "Załączniku nr 2",
    },
    "PROTOKOL": {
        "TYTUL": "Protokół Zdawczo-Odbiorczy Zabudowy Meblowej",
        "M": "Protokół Zdawczo-Odbiorczy",
        "D": "Protokołu Zdawczo-Odbiorczego",
        "C": "Protokołowi Zdawczo-Odbiorczemu",
        "B": "Protokół Zdawczo-Odbiorczy",
        "N": "Protokołem Zdawczo-Odbiorczym",
        "MS": "Protokole Zdawczo-Odbiorczym",
    },
}

# Dane klienta i kwota NIE MOGĄ mieszkać w kodzie — każda umowa dotyczy innej
# osoby, a PESEL w repozytorium to wyciek danych osobowych. Wchodzą wyłącznie
# plikiem JSON i przechodzą walidację (patrz SCHEMAT_DANYCH).

# Proporcje transz. Suma musi wynosić dokładnie 1.
PODZIAL_TRANSZ = {
    "ZADATEK": Decimal("0.50"),
    "TRANSZA_2": Decimal("0.40"),
    "TRANSZA_3": Decimal("0.10"),
}

# ============================================================================
# 2. SCHEMAT I WALIDACJA DANYCH WEJŚCIOWYCH
# ============================================================================


class Pole:
    """Jedno pole formularza klienta wraz z regułą poprawności."""

    def __init__(self, opis: str, przyklad: str, walidator=None, wymagane: bool = True):
        self.opis = opis
        self.przyklad = przyklad
        self.walidator = walidator
        self.wymagane = wymagane


def _same_cyfry(wartosc: str) -> str:
    return re.sub(r"\D", "", wartosc)


def waliduj_imie_nazwisko(wartosc: str) -> None:
    czlony = [c for c in re.split(r"[\s\-]+", wartosc.strip()) if c]
    if len(czlony) < 2:
        raise ValueError("podaj imię i nazwisko (min. dwa człony)")
    if not all(re.fullmatch(r"[^\W\d_]{2,}", c, re.UNICODE) for c in czlony):
        raise ValueError("dopuszczalne są wyłącznie litery")


def waliduj_pesel_lub_nip(wartosc: str) -> None:
    """PESEL (11 cyfr) albo NIP (10 cyfr) — obie sumy kontrolne łapią
    przestawione i przekręcone cyfry, czyli najczęstszą literówkę."""
    cyfry = _same_cyfry(wartosc)
    if len(cyfry) == 11:
        wagi = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
        suma = sum(int(c) * w for c, w in zip(cyfry, wagi))
        if (10 - suma % 10) % 10 != int(cyfry[10]):
            raise ValueError("niepoprawna suma kontrolna PESEL")
    elif len(cyfry) == 10:
        wagi = (6, 5, 7, 2, 3, 4, 5, 6, 7)
        suma = sum(int(c) * w for c, w in zip(cyfry, wagi))
        if suma % 11 != int(cyfry[9]):
            raise ValueError("niepoprawna suma kontrolna NIP")
    else:
        raise ValueError(f"oczekiwano 11 cyfr (PESEL) lub 10 cyfr (NIP), jest {len(cyfry)}")


def waliduj_email(wartosc: str) -> None:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", wartosc.strip()):
        raise ValueError("to nie wygląda na adres e-mail")


def waliduj_telefon(wartosc: str) -> None:
    cyfry = _same_cyfry(wartosc)
    if cyfry.startswith("48") and len(cyfry) == 11:
        cyfry = cyfry[2:]
    if len(cyfry) != 9:
        raise ValueError(f"polski numer ma 9 cyfr, podano {len(cyfry)}")


def waliduj_adres(wartosc: str) -> None:
    if len(wartosc.strip()) < 10:
        raise ValueError("adres wygląda na niekompletny")
    if not any(z.isdigit() for z in wartosc):
        raise ValueError("brak numeru budynku/lokalu")


def waliduj_miejscowosc(wartosc: str) -> None:
    if not re.fullmatch(r"[^\W\d_][^\d_]{1,}", wartosc.strip(), re.UNICODE):
        raise ValueError("nazwa miejscowości nie może zawierać cyfr")


def waliduj_kwote(wartosc) -> None:
    try:
        kwota = Decimal(str(wartosc).replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except InvalidOperation:
        raise ValueError("to nie jest liczba") from None
    if kwota <= 0:
        raise ValueError("kwota musi być dodatnia")
    if kwota != kwota.quantize(GROSZ, rounding=ROUND_HALF_UP):
        raise ValueError("maksymalna dokładność to grosze (2 miejsca po przecinku)")
    if kwota > Decimal("10000000"):
        raise ValueError("kwota wygląda na pomyłkę (powyżej 10 mln zł)")


def waliduj_tygodnie(wartosc) -> None:
    try:
        tygodnie = int(str(wartosc).strip())
    except ValueError:
        raise ValueError("podaj liczbę całkowitą tygodni") from None
    if not 1 <= tygodnie <= 104:
        raise ValueError("termin poza rozsądnym zakresem 1-104 tygodni")


def waliduj_date(wartosc: str) -> None:
    try:
        datetime.datetime.strptime(str(wartosc).strip(), "%d.%m.%Y")
    except ValueError:
        raise ValueError("oczekiwany format DD.MM.RRRR") from None


SCHEMAT_DANYCH = {
    "IMIE_NAZWISKO": Pole("Imię i nazwisko Zamawiającego", "Anna Nowak", waliduj_imie_nazwisko),
    "ADRES": Pole("Adres zamieszkania", "ul. Kwiatowa 15/2, 50-001 Wrocław", waliduj_adres),
    "PESEL_NIP": Pole("PESEL lub NIP Zamawiającego", "90010112349", waliduj_pesel_lub_nip),
    "TELEFON": Pole("Telefon kontaktowy", "500 600 700", waliduj_telefon),
    "EMAIL": Pole("Adres e-mail", "anna.nowak@example.com", waliduj_email),
    "MIEJSCOWOSC": Pole("Miejscowość zawarcia umowy", "Wrocław", waliduj_miejscowosc),
    "ADRES_MONTAZU": Pole("Adres montażu zabudowy", "ul. Kwiatowa 15/2, 50-001 Wrocław", waliduj_adres),
    "KWOTA_CALKOWITA": Pole("Wynagrodzenie brutto w zł", "30000", waliduj_kwote),
    "TERMIN_TYGODNIE": Pole("Termin realizacji w tygodniach", "6", waliduj_tygodnie),
    "DATA_UMOWY": Pole("Data zawarcia umowy (domyślnie dzisiaj)", "27.08.2026",
                       waliduj_date, wymagane=False),
    "NUMER_UMOWY": Pole("Własna numeracja (domyślnie RRRR/MM/INICJAŁY)", "12/2026",
                        None, wymagane=False),
}


class DaneUmowy:
    """Zwalidowany komplet danych jednej umowy."""

    def __init__(self, pola: dict, kwota: Decimal, dzien: datetime.date):
        self.pola = pola
        self.kwota = kwota
        self.dzien = dzien


def zwaliduj_dane(surowe: dict, dzien_domyslny: datetime.date) -> DaneUmowy:
    """
    Sprawdza komplet danych i zbiera WSZYSTKIE błędy naraz — poprawianie
    formularza po jednym błędzie na uruchomienie byłoby udręką.
    Klucze zaczynające się od "_" traktujemy jak komentarze w pliku JSON.
    """
    if not isinstance(surowe, dict):
        raise BladGeneratora("Plik z danymi musi zawierać obiekt JSON (klucz: wartość).")

    dane = {k: v for k, v in surowe.items() if not k.startswith("_")}
    bledy: list[str] = []

    # Literówka w nazwie pola jest groźniejsza niż brak pola: dane po cichu
    # wypadłyby z umowy. Podpowiadamy najbliższy poprawny klucz.
    for klucz in dane:
        if klucz not in SCHEMAT_DANYCH:
            podpowiedzi = difflib.get_close_matches(klucz, SCHEMAT_DANYCH, n=1, cutoff=0.6)
            wskazowka = f" — czy chodziło o '{podpowiedzi[0]}'?" if podpowiedzi else ""
            bledy.append(f"  {klucz}: nieznane pole{wskazowka}")

    for klucz, pole in SCHEMAT_DANYCH.items():
        wartosc = dane.get(klucz)
        pusta = wartosc is None or not str(wartosc).strip()
        if pusta:
            if pole.wymagane:
                bledy.append(f"  {klucz}: brak wartości ({pole.opis}, np. {pole.przyklad})")
            continue
        if pole.walidator:
            try:
                pole.walidator(wartosc)
            except ValueError as exc:
                bledy.append(f"  {klucz}: {exc} (podano: {str(wartosc).strip()!r})")

    if bledy:
        raise BladGeneratora("Dane wejściowe zawierają błędy:\n" + "\n".join(sorted(bledy)))

    pola = {k: str(v).strip() for k, v in dane.items() if str(v).strip()}
    kwota = Decimal(pola.pop("KWOTA_CALKOWITA").replace(" ", "").replace("\u00a0", "").replace(",", "."))
    if "DATA_UMOWY" in pola:
        dzien = datetime.datetime.strptime(pola.pop("DATA_UMOWY"), "%d.%m.%Y").date()
    else:
        dzien = dzien_domyslny
    return DaneUmowy(pola, kwota, dzien)


def pusty_formularz() -> dict:
    """Szkielet pliku JSON do wypełnienia."""
    formularz = {"_opis": "Dane jednej umowy. Pola opcjonalne można usunąć."}
    for klucz, pole in SCHEMAT_DANYCH.items():
        etykieta = pole.opis if pole.wymagane else f"{pole.opis} [opcjonalne]"
        formularz[f"_{klucz}"] = f"{etykieta}, np. {pole.przyklad}"
        formularz[klucz] = ""
    return formularz


# ============================================================================
# 3. REGUŁY PRAWNE (hierarchia dokumentów)
# ============================================================================


class DokumentSpec:
    """Opis jednego dokumentu w drzewie i jego reguł numeracji."""

    def __init__(self, plik: str, prefiks: str, numer_umowy: bool):
        self.plik = plik
        self.prefiks = prefiks  # klucz w NAZWY_DOKUMENTOW
        self.numer_umowy = numer_umowy  # True = MUSI zawierać, False = NIE MOŻE

    @property
    def tytul(self) -> str:
        """Nazwa dokumentu — z tego samego źródła co szablony, żeby logi i
        komunikaty błędów nie rozjechały się z treścią umowy."""
        formy = NAZWY_DOKUMENTOW[self.prefiks]
        if formy["TYTUL"].startswith(formy["M"]):
            return formy["TYTUL"]
        return f"{formy['M']} — {formy['TYTUL']}"


DRZEWO_DOKUMENTOW = [
    DokumentSpec("umowa_template.md", "UMOWA", numer_umowy=True),
    DokumentSpec("zalacznik1_template.md", "ZAL_1", numer_umowy=False),
    DokumentSpec("instrukcja_template.md", "ZAL_2", numer_umowy=False),
    DokumentSpec("protokol_template.md", "PROTOKOL", numer_umowy=True),
]


# Nazwy własne dokumentów, które NIE MOGĄ pojawić się w szablonie na twardo —
# muszą wejść przez {{ZMIENNĄ}}, inaczej tracimy gwarancję spójności.
WZORCE_NAZW_WLASNYCH = (
    re.compile(r"Za[łl]\w*cznik\w*(?:\s+nr\s*\d+)?", re.IGNORECASE),
    re.compile(r"Protok[oó][l\u0142]\w*", re.IGNORECASE),
    re.compile(r"Umow\w*\s+o\s+[Dd]zie[łl]\w*", re.IGNORECASE),
    re.compile(r"Kart\w*\s+Piel\w*gnacji", re.IGNORECASE),
    re.compile(r"Instrukcj\w*", re.IGNORECASE),
)

# Frazy odnoszące się do dokumentów OSÓB TRZECICH (producenci AGD, okuć),
# a nie do naszego drzewa dokumentów — detektor musi je przepuścić.
WYJATKI_NAZW = (
    "Instrukcji obsługi",
    "Instrukcja obsługi",
    "instrukcji obsługi",
    # Liczba mnoga to rzeczownik pospolity ("wymienione załączniki"),
    # a nie nazwa własna konkretnego dokumentu.
    "Załączniki",
    "załączniki",
    "załączników",
    "załącznikami",
)


class BladGeneratora(Exception):
    """Błąd krytyczny — przerywa generowanie, by nie wypuścić wadliwej umowy."""


# ============================================================================
# 4. FINANSE
# ============================================================================

GROSZ = Decimal("0.01")


def zaokraglij(kwota: Decimal) -> Decimal:
    return Decimal(kwota).quantize(GROSZ, rounding=ROUND_HALF_UP)


def formatuj_kwote(kwota: Decimal) -> str:
    """30000 -> '30 000'; 12345.5 -> '12 345,50' (separator tysięcy: spacja nierozdzielająca)."""
    kwota = zaokraglij(kwota)
    zlote, grosze = divmod(int(kwota * 100), 100)
    calosc = f"{zlote:,}".replace(",", " ")
    return calosc if grosze == 0 else f"{calosc},{grosze:02d}"


def podziel_na_transze(calosc: Decimal) -> dict[str, Decimal]:
    """
    Dzieli kwotę na transze. Ostatnia transza to reszta, dzięki czemu
    suma transz ZAWSZE równa się kwocie umowy (brak zgubionych groszy
    przy zaokrąglaniu — w umowie to błąd nie do obrony).
    """
    if calosc <= 0:
        raise BladGeneratora(f"Kwota umowy musi być dodatnia (otrzymano: {calosc}).")

    suma_proporcji = sum(PODZIAL_TRANSZ.values())
    if suma_proporcji != Decimal("1"):
        raise BladGeneratora(f"Proporcje transz muszą sumować się do 100% (jest: {suma_proporcji * 100}%).")

    nazwy = list(PODZIAL_TRANSZ)
    transze: dict[str, Decimal] = {}
    for nazwa in nazwy[:-1]:
        transze[nazwa] = zaokraglij(calosc * PODZIAL_TRANSZ[nazwa])
    transze[nazwy[-1]] = zaokraglij(calosc) - sum(transze.values())
    return transze


# ============================================================================
# 5. KWOTA SŁOWNIE (polskie liczebniki + odmiana "złoty")
# ============================================================================

_JEDNOSCI = ["", "jeden", "dwa", "trzy", "cztery", "pięć", "sześć", "siedem", "osiem", "dziewięć"]
_NASTKI = ["dziesięć", "jedenaście", "dwanaście", "trzynaście", "czternaście",
           "piętnaście", "szesnaście", "siedemnaście", "osiemnaście", "dziewiętnaście"]
_DZIESIATKI = ["", "", "dwadzieścia", "trzydzieści", "czterdzieści", "pięćdziesiąt",
               "sześćdziesiąt", "siedemdziesiąt", "osiemdziesiąt", "dziewięćdziesiąt"]
_SETKI = ["", "sto", "dwieście", "trzysta", "czterysta", "pięćset",
          "sześćset", "siedemset", "osiemset", "dziewięćset"]
_GRUPY = [("", "", ""),
          ("tysiąc", "tysiące", "tysięcy"),
          ("milion", "miliony", "milionów"),
          ("miliard", "miliardy", "miliardów")]


def _forma(n: int, f1: str, f2: str, f5: str) -> str:
    """Wybór formy gramatycznej: 1 / 2-4 / 5+ (z wyjątkiem 12-14)."""
    if n == 1:
        return f1
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f2
    return f5


def _do_999(n: int) -> list[str]:
    slowa = []
    if n >= 100:
        slowa.append(_SETKI[n // 100])
        n %= 100
    if 10 <= n <= 19:
        slowa.append(_NASTKI[n - 10])
        return slowa
    if n >= 20:
        slowa.append(_DZIESIATKI[n // 10])
        n %= 10
    if n:
        slowa.append(_JEDNOSCI[n])
    return slowa


def liczba_slownie(n: int) -> str:
    if n == 0:
        return "zero"
    if n < 0 or n >= 10 ** 12:
        raise BladGeneratora(f"Nie potrafię zapisać słownie liczby: {n}.")

    grupy: list[int] = []
    while n:
        grupy.append(n % 1000)
        n //= 1000

    slowa: list[str] = []
    for idx in range(len(grupy) - 1, -1, -1):
        wartosc = grupy[idx]
        if wartosc == 0:
            continue
        # "tysiąc", nie "jeden tysiąc"
        if not (wartosc == 1 and idx > 0):
            slowa.extend(_do_999(wartosc))
        if idx > 0:
            slowa.append(_forma(wartosc, *_GRUPY[idx]))
    return " ".join(slowa)


def kwota_slownie(kwota: Decimal) -> str:
    """30000 -> 'trzydzieści tysięcy złotych 00/100'."""
    kwota = zaokraglij(kwota)
    zlote, grosze = divmod(int(kwota * 100), 100)
    return f"{liczba_slownie(zlote)} {_forma(zlote, 'złoty', 'złote', 'złotych')} {grosze:02d}/100"


# ============================================================================
# 6. NUMER UMOWY
# ============================================================================


# Ł/ł nie mają dekompozycji NFD — trzeba je zmapować ręcznie.
_TRANSLITERACJA = str.maketrans({"Ł": "L", "ł": "l"})


def _bez_ogonkow(tekst: str) -> str:
    tekst = unicodedata.normalize("NFD", tekst.translate(_TRANSLITERACJA))
    return "".join(c for c in tekst if unicodedata.category(c) != "Mn")


def generuj_numer_umowy(imie_nazwisko: str, dzien: datetime.date) -> str:
    """'Anna Nowak' -> '2026/08/AN'. Obsługuje nazwiska dwuczłonowe i podwójne spacje."""
    czlony = [c for c in re.split(r"[\s\-]+", imie_nazwisko.strip()) if c]
    if not czlony:
        raise BladGeneratora("Brak imienia i nazwiska — nie mogę wygenerować numeru umowy.")
    inicjaly = "".join(_bez_ogonkow(c)[0] for c in czlony).upper()
    return f"{dzien:%Y}/{dzien:%m}/{inicjaly}"


# ============================================================================
# 7. BUDOWA SŁOWNIKA ZMIENNYCH
# ============================================================================


def zbuduj_zmienne(dane: DaneUmowy) -> dict[str, str]:
    """Składa słownik podstawień z danych wykonawcy, parametrów umownych,
    nazw dokumentów i zwalidowanych danych klienta."""
    transze = podziel_na_transze(dane.kwota)

    sprawdz_kompletnosc_nazw()

    zmienne: dict[str, str] = {}
    zmienne.update(DANE_FIRMY)
    zmienne.update(PARAMETRY_UMOWY)
    zmienne.update(rozwin_nazwy_dokumentow())
    zmienne.update(dane.pola)

    zmienne["DATA_UMOWY"] = f"{dane.dzien:%d.%m.%Y}"
    zmienne["NUMER_UMOWY"] = dane.pola.get("NUMER_UMOWY") or generuj_numer_umowy(
        dane.pola["IMIE_NAZWISKO"], dane.dzien
    )

    zmienne["KWOTA_BRUTTO"] = formatuj_kwote(dane.kwota)
    zmienne["KWOTA_SLOWNIE"] = kwota_slownie(dane.kwota)
    for nazwa, wartosc in transze.items():
        zmienne[nazwa] = formatuj_kwote(wartosc)
        zmienne[f"{nazwa}_SLOWNIE"] = kwota_slownie(wartosc)
    for nazwa, proporcja in PODZIAL_TRANSZ.items():
        procent = proporcja * 100
        # Decimal("0.50")*100 -> "50.00"; w umowie ma być "50".
        zmienne[f"PROCENT_{nazwa}"] = (
            str(int(procent)) if procent == procent.to_integral_value() else str(procent.normalize())
        )

    return zmienne


# ============================================================================
# 8. RENDEROWANIE I WALIDACJA
# ============================================================================


PRZYPADKI = ("TYTUL", "M", "D", "C", "B", "N", "MS")


def sprawdz_kompletnosc_nazw() -> None:
    """Brakująca forma = {{ZAL_2_MS}} bez odpowiednika i wysypka przy renderowaniu."""
    for prefiks, formy in NAZWY_DOKUMENTOW.items():
        braki = [k for k in PRZYPADKI if not formy.get(k, "").strip()]
        if braki:
            raise BladGeneratora(f"NAZWY_DOKUMENTOW['{prefiks}']: brakuje form: {', '.join(braki)}")


def rozwin_nazwy_dokumentow() -> dict[str, str]:
    """
    NAZWY_DOKUMENTOW -> płaskie zmienne szablonu.
    "ZAL_1" + "D" -> {{ZAL_1_D}} = "Załącznika nr 1"
                     {{ZAL_1_D_CAPS}} = "ZAŁĄCZNIKA NR 1"
    """
    zmienne: dict[str, str] = {}
    for prefiks, formy in NAZWY_DOKUMENTOW.items():
        for przypadek, tekst in formy.items():
            zmienne[f"{prefiks}_{przypadek}"] = tekst
            zmienne[f"{prefiks}_{przypadek}_CAPS"] = tekst.upper()
    return zmienne


def kontrola_nazw_dokumentow(spec: DokumentSpec, tresc: str) -> None:
    """
    Wyłapuje nazwę dokumentu wpisaną w szablonie na twardo zamiast przez zmienną.
    Bez tego jedna literówka ("Instrukcja Użytkowania" zamiast "Karta Pielęgnacji")
    tworzy w umowie odesłanie do nieistniejącego dokumentu.
    """
    tekst = WZORZEC_ZMIENNEJ.sub("", tresc)  # tagi {{...}} są z definicji spójne
    for wyjatek in WYJATKI_NAZW:
        tekst = tekst.replace(wyjatek, "")

    trafienia: list[str] = []
    for nr, linia in enumerate(tekst.splitlines(), start=1):
        for wzorzec in WZORCE_NAZW_WLASNYCH:
            for dopasowanie in wzorzec.finditer(linia):
                trafienia.append(f"    linia {nr}: {dopasowanie.group(0)!r}")

    if trafienia:
        raise BladGeneratora(
            f"{spec.plik}: nazwa dokumentu wpisana na twardo zamiast przez zmienną "
            f"(patrz NAZWY_DOKUMENTOW):\n" + "\n".join(trafienia)
        )


def sprawdz_regule_numeracji(spec: DokumentSpec, tresc: str) -> None:
    """Reguła prawna: załączniki są parafowane i zszywane — nie wolno im nosić numeru umowy."""
    zawiera = "{{NUMER_UMOWY}}" in tresc
    if spec.numer_umowy and not zawiera:
        raise BladGeneratora(
            f"{spec.plik}: '{spec.tytul}' MUSI zawierać {{{{NUMER_UMOWY}}}} (dokument podpisywany samodzielnie)."
        )
    if not spec.numer_umowy and zawiera:
        raise BladGeneratora(
            f"{spec.plik}: '{spec.tytul}' NIE MOŻE zawierać {{{{NUMER_UMOWY}}}} "
            f"(załącznik autoryzowany parafką, zszywany z Umową Główną)."
        )


def renderuj(spec: DokumentSpec, zmienne: dict[str, str]) -> tuple[str, set[str]]:
    sciezka = BAZA / spec.plik
    try:
        tresc = sciezka.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BladGeneratora(f"Nie znaleziono szablonu: {sciezka}") from exc
    except UnicodeDecodeError as exc:
        raise BladGeneratora(f"Szablon {spec.plik} nie jest w UTF-8: {exc}") from exc

    sprawdz_regule_numeracji(spec, tresc)
    kontrola_nazw_dokumentow(spec, tresc)

    uzyte = set(WZORZEC_ZMIENNEJ.findall(tresc))
    nieznane = sorted(uzyte - zmienne.keys())
    if nieznane:
        raise BladGeneratora(
            f"{spec.plik}: zmienne bez odpowiednika w słowniku Pythona: {', '.join(nieznane)}"
        )

    wynik = WZORZEC_ZMIENNEJ.sub(lambda m: zmienne[m.group(1)], tresc)

    pozostale = WZORZEC_ZMIENNEJ.findall(wynik)
    if pozostale:
        raise BladGeneratora(f"{spec.plik}: nie podstawiono zmiennych: {', '.join(sorted(set(pozostale)))}")

    return wynik.strip(), uzyte


def generuj_dokument(zmienne: dict[str, str]) -> str:
    czesci: list[str] = []
    wszystkie_uzyte: set[str] = set()

    for spec in DRZEWO_DOKUMENTOW:
        tresc, uzyte = renderuj(spec, zmienne)
        czesci.append(tresc)
        wszystkie_uzyte |= uzyte
        print(f"  [OK] {spec.plik:<26} {spec.tytul}")

    # Odmiany nazw to gotowy słownik do dyspozycji szablonów — nieużyty
    # przypadek nie jest usterką. Ostrzegamy tylko o danych konkretnej umowy.
    nieuzyte = sorted(zmienne.keys() - wszystkie_uzyte - rozwin_nazwy_dokumentow().keys())
    if nieuzyte:
        print(f"  [!]  Zmienne zdefiniowane, ale nieużyte w szablonach: {', '.join(nieuzyte)}")

    separator = f"\n\n{ZNACZNIK_STRONY}\n\n"
    return separator.join(czesci) + "\n"


def bezpieczna_nazwa(tekst: str) -> str:
    tekst = _bez_ogonkow(tekst)
    tekst = re.sub(r"[^A-Za-z0-9]+", "_", tekst).strip("_")
    return tekst or "Klient"


# ============================================================================
# 9. URUCHOMIENIE
# ============================================================================


UZYCIE = """Użycie:
  python generator.py DANE.json            generuje komplet dokumentów
  python generator.py --szablon NOWY.json  tworzy pusty formularz do wypełnienia

Dane klienta zawsze pochodzą z pliku JSON — nigdy z kodu."""


def wczytaj_json(sciezka: Path) -> dict:
    try:
        return json.loads(sciezka.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BladGeneratora(f"Nie znaleziono pliku z danymi: {sciezka}") from None
    except UnicodeDecodeError as exc:
        raise BladGeneratora(f"Plik {sciezka.name} nie jest w UTF-8: {exc}") from None
    except json.JSONDecodeError as exc:
        raise BladGeneratora(
            f"Niepoprawny JSON w {sciezka.name}, linia {exc.lineno}: {exc.msg}"
        ) from None


def zapisz_szablon(sciezka: Path) -> int:
    if sciezka.exists():
        print(f"BŁĄD: plik {sciezka} już istnieje — nie nadpisuję.", file=sys.stderr)
        return 1
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(
        json.dumps(pusty_formularz(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"Formularz do wypełnienia: {sciezka}")
    print("Pola opisowe zaczynają się od '_' i są ignorowane przy generowaniu.")
    return 0


def main(argv: list[str]) -> int:
    argumenty = argv[1:]

    if not argumenty or argumenty[0] in ("-h", "--help"):
        print(UZYCIE, file=sys.stderr if not argumenty else sys.stdout)
        return 1 if not argumenty else 0

    if argumenty[0] == "--szablon":
        if len(argumenty) < 2:
            print("BŁĄD: podaj nazwę pliku, np. --szablon jan_kowalski.json", file=sys.stderr)
            return 1
        return zapisz_szablon(Path(argumenty[1]).expanduser())

    try:
        sciezka = Path(argumenty[0]).expanduser().resolve()
        dane = zwaliduj_dane(wczytaj_json(sciezka), datetime.date.today())
        zmienne = zbuduj_zmienne(dane)

        print(f"Umowa nr {zmienne['NUMER_UMOWY']} | {zmienne['IMIE_NAZWISKO']} | {zmienne['KWOTA_BRUTTO']} zł")
        dokument = generuj_dokument(zmienne)

        KATALOG_WYNIKOWY.mkdir(parents=True, exist_ok=True)
        nazwa = f"Umowa_{zmienne['NUMER_UMOWY'].replace('/', '-')}_{bezpieczna_nazwa(zmienne['IMIE_NAZWISKO'])}.md"
        plik = KATALOG_WYNIKOWY / nazwa
        plik.write_text(dokument, encoding="utf-8", newline="\n")
    except BladGeneratora as exc:
        print(f"\nBŁĄD: {exc}", file=sys.stderr)
        print("\nNie wygenerowano żadnego pliku.", file=sys.stderr)
        return 1

    print(f"\nGotowe: {plik}")
    print(f"PDF:    pandoc '{plik.name}' -o '{plik.stem}.pdf' --pdf-engine=xelatex -V mainfont='DejaVu Serif'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
