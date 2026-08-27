"""KATEGORIA: numer umowy.

Numer wiąże Umowę Główną z Protokołem Odbioru powstającym miesiąc później.
Kod wyjściowy budował inicjały przez czlon[0] — gubił drugi człon nazwiska
i wywracał się na polskich znakach.
"""

import datetime

import pytest

import generator as g

DZIEN = datetime.date(2026, 8, 27)


@pytest.mark.parametrize("imie_nazwisko, oczekiwane", [
    ("Anna Nowak", "2026/08/AN"),
    ("Jan Kowalski", "2026/08/JK"),
    ("Anna Maria Wiśniewska", "2026/08/AMW"),
])
def test_inicjaly(imie_nazwisko, oczekiwane):
    assert g.generuj_numer_umowy(imie_nazwisko, DZIEN) == oczekiwane


def test_nazwisko_dwuczlonowe_z_mysnikiem():
    """Regresja: 'Nowak-Kowalski' dawało samo 'N'."""
    assert g.generuj_numer_umowy("Jan Nowak-Kowalski", DZIEN) == "2026/08/JNK"


@pytest.mark.parametrize("imie_nazwisko, oczekiwane", [
    ("Łucja Żółć", "2026/08/LZ"),
    ("Śliwiński Łukasz", "2026/08/SL"),
    ("Ćwikła Źrebiec", "2026/08/CZ"),
])
def test_polskie_znaki_transliterowane(imie_nazwisko, oczekiwane):
    """Regresja: Ł nie ma dekompozycji NFD, unicodedata samo go nie usunie."""
    assert g.generuj_numer_umowy(imie_nazwisko, DZIEN) == oczekiwane


def test_nadmiarowe_spacje_ignorowane():
    assert g.generuj_numer_umowy("  Anna   Nowak  ", DZIEN) == "2026/08/AN"


@pytest.mark.parametrize("puste", ["", "   ", "\t"])
def test_brak_nazwiska_zatrzymuje_generowanie(puste):
    with pytest.raises(g.BladGeneratora, match="numeru umowy"):
        g.generuj_numer_umowy(puste, DZIEN)


def test_format_rok_miesiac_inicjaly():
    numer = g.generuj_numer_umowy("Anna Nowak", datetime.date(2027, 1, 5))
    assert numer == "2027/01/AN"


def test_numer_z_danych_wejsciowych_ma_pierwszenstwo(dzien, kwota):
    """Pozwala wpiąć własną numerację księgową bez zmiany kodu."""
    dane = dict(g.DANE_KLIENTA, NUMER_UMOWY="12/2026")
    zmienne = g.zbuduj_zmienne(dane, kwota, dzien)
    assert zmienne["NUMER_UMOWY"] == "12/2026"


def test_numer_generowany_gdy_brak_w_danych(zmienne):
    assert zmienne["NUMER_UMOWY"] == "2026/08/AN"
