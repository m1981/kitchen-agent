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
    python generator.py                    # dane z DANE_KLIENTA poniżej
    python generator.py klient.json        # dane z pliku JSON (nadpisują domyślne)
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# --- Ścieżki liczone względem pliku skryptu, nie względem cwd ----------------
BAZA = Path(__file__).resolve().parent
KATALOG_WYNIKOWY = BAZA / "wygenerowane"

ZNACZNIK_STRONY = "<div style='page-break-after: always;'></div>"
WZORZEC_ZMIENNEJ = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")

# ============================================================================
# 1. DANE WEJŚCIOWE
# ============================================================================

DANE_FIRMY = {
    "FIRMA_NAZWA": "Stolarnia Premium Sp. z o.o.",
    "FIRMA_ADRES": "ul. Stolarska 10, 50-123 Wrocław",
    "FIRMA_NIP": "899-123-45-67",
    "FIRMA_REPREZENTANT": "Jan Kowalski",
}

# Parametry umowne wspólne dla wszystkich dokumentów
PARAMETRY_UMOWY = {
    "OKRES_GWARANCJI_MIESIACE": "24",
    "TERMIN_USTEREK_DNI": "14",
    "KOSZT_MAGAZYNOWANIA": "50",
}

DANE_KLIENTA = {
    "IMIE_NAZWISKO": "Anna Nowak",
    "ADRES": "ul. Kwiatowa 15/2, 50-001 Wrocław",
    "PESEL_NIP": "90010112345",
    "TELEFON": "500 600 700",
    "EMAIL": "anna.nowak@email.com",
    "MIEJSCOWOSC": "Wrocław",
    "ADRES_MONTAZU": "ul. Kwiatowa 15/2, 50-001 Wrocław",
    "TERMIN_TYGODNIE": "6",
}

KWOTA_CALKOWITA = Decimal("30000")

# Proporcje transz. Suma musi wynosić dokładnie 1.
PODZIAL_TRANSZ = {
    "ZADATEK": Decimal("0.50"),
    "TRANSZA_2": Decimal("0.40"),
    "TRANSZA_3": Decimal("0.10"),
}

# ============================================================================
# 2. REGUŁY PRAWNE (hierarchia dokumentów)
# ============================================================================


class DokumentSpec:
    """Opis jednego dokumentu w drzewie i jego reguł numeracji."""

    def __init__(self, plik: str, tytul: str, numer_umowy: bool):
        self.plik = plik
        self.tytul = tytul
        self.numer_umowy = numer_umowy  # True = MUSI zawierać, False = NIE MOŻE


DRZEWO_DOKUMENTOW = [
    DokumentSpec("umowa_template.md", "Umowa Główna", numer_umowy=True),
    DokumentSpec("zalacznik1_template.md", "Załącznik nr 1 (Projekt i Specyfikacja)", numer_umowy=False),
    DokumentSpec("instrukcja_template.md", "Załącznik nr 2 (Karta Pielęgnacji)", numer_umowy=False),
    DokumentSpec("protokol_template.md", "Protokół Zdawczo-Odbiorczy", numer_umowy=True),
]


class BladGeneratora(Exception):
    """Błąd krytyczny — przerywa generowanie, by nie wypuścić wadliwej umowy."""


# ============================================================================
# 3. FINANSE
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
# 4. KWOTA SŁOWNIE (polskie liczebniki + odmiana "złoty")
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
# 5. NUMER UMOWY
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
# 6. BUDOWA SŁOWNIKA ZMIENNYCH
# ============================================================================


def zbuduj_zmienne(dane_klienta: dict, kwota: Decimal, dzien: datetime.date) -> dict[str, str]:
    braki = [k for k in ("IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "MIEJSCOWOSC", "ADRES_MONTAZU")
             if not str(dane_klienta.get(k, "")).strip()]
    if braki:
        raise BladGeneratora("Brak wymaganych danych klienta: " + ", ".join(braki))

    transze = podziel_na_transze(kwota)

    zmienne: dict[str, str] = {}
    zmienne.update(DANE_FIRMY)
    zmienne.update(PARAMETRY_UMOWY)
    zmienne.update({k: str(v) for k, v in dane_klienta.items()})

    zmienne["DATA_UMOWY"] = f"{dzien:%d.%m.%Y}"
    zmienne["NUMER_UMOWY"] = dane_klienta.get("NUMER_UMOWY") or generuj_numer_umowy(
        dane_klienta["IMIE_NAZWISKO"], dzien
    )

    zmienne["KWOTA_BRUTTO"] = formatuj_kwote(kwota)
    zmienne["KWOTA_SLOWNIE"] = kwota_slownie(kwota)
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
# 7. RENDEROWANIE I WALIDACJA
# ============================================================================


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

    nieuzyte = sorted(zmienne.keys() - wszystkie_uzyte)
    if nieuzyte:
        print(f"  [!]  Zmienne zdefiniowane, ale nieużyte w szablonach: {', '.join(nieuzyte)}")

    separator = f"\n\n{ZNACZNIK_STRONY}\n\n"
    return separator.join(czesci) + "\n"


def bezpieczna_nazwa(tekst: str) -> str:
    tekst = _bez_ogonkow(tekst)
    tekst = re.sub(r"[^A-Za-z0-9]+", "_", tekst).strip("_")
    return tekst or "Klient"


# ============================================================================
# 8. URUCHOMIENIE
# ============================================================================


def main(argv: list[str]) -> int:
    dane_klienta = dict(DANE_KLIENTA)
    kwota = KWOTA_CALKOWITA

    if len(argv) > 1:
        sciezka_json = Path(argv[1]).expanduser().resolve()
        try:
            wczytane = json.loads(sciezka_json.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"BŁĄD: nie znaleziono pliku danych: {sciezka_json}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as exc:
            print(f"BŁĄD: niepoprawny JSON w {sciezka_json}: {exc}", file=sys.stderr)
            return 1
        if "KWOTA_CALKOWITA" in wczytane:
            kwota = Decimal(str(wczytane.pop("KWOTA_CALKOWITA")))
        dane_klienta.update(wczytane)

    try:
        dzien = datetime.date.today()
        zmienne = zbuduj_zmienne(dane_klienta, kwota, dzien)

        print(f"Umowa nr {zmienne['NUMER_UMOWY']} | {zmienne['IMIE_NAZWISKO']} | {zmienne['KWOTA_BRUTTO']} zł")
        dokument = generuj_dokument(zmienne)

        KATALOG_WYNIKOWY.mkdir(parents=True, exist_ok=True)
        nazwa = f"Umowa_{zmienne['NUMER_UMOWY'].replace('/', '-')}_{bezpieczna_nazwa(zmienne['IMIE_NAZWISKO'])}.md"
        plik = KATALOG_WYNIKOWY / nazwa
        plik.write_text(dokument, encoding="utf-8", newline="\n")
    except BladGeneratora as exc:
        print(f"\nBŁĄD KRYTYCZNY: {exc}", file=sys.stderr)
        print("Nie wygenerowano żadnego pliku.", file=sys.stderr)
        return 1

    print(f"\nGotowe: {plik}")
    print(f"PDF:    pandoc '{plik.name}' -o '{plik.stem}.pdf' --pdf-engine=xelatex -V mainfont='DejaVu Serif'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
