"""KATEGORIA: walidacja danych wejściowych.

Pusty adres czy brak PESEL-u nie może po cichu wejść do umowy jako pusty
string — dokument wyszedłby z dziurą w oznaczeniu strony.
"""

import pytest

import generator as g


WYMAGANE = ["IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "MIEJSCOWOSC", "ADRES_MONTAZU"]


@pytest.mark.parametrize("brakujacy", WYMAGANE)
def test_brak_wymaganego_pola_zatrzymuje_generowanie(brakujacy, dzien, kwota):
    dane = dict(g.DANE_KLIENTA)
    del dane[brakujacy]
    with pytest.raises(g.BladGeneratora, match=brakujacy):
        g.zbuduj_zmienne(dane, kwota, dzien)


@pytest.mark.parametrize("puste", ["", "   ", "\t\n"])
def test_pole_z_samych_bialych_znakow_jest_brakiem(puste, dzien, kwota):
    dane = dict(g.DANE_KLIENTA, ADRES=puste)
    with pytest.raises(g.BladGeneratora, match="ADRES"):
        g.zbuduj_zmienne(dane, kwota, dzien)


def test_komunikat_wymienia_wszystkie_braki(dzien, kwota):
    dane = dict(g.DANE_KLIENTA, ADRES="", PESEL_NIP="")
    with pytest.raises(g.BladGeneratora) as blad:
        g.zbuduj_zmienne(dane, kwota, dzien)
    assert "ADRES" in str(blad.value)
    assert "PESEL_NIP" in str(blad.value)


def test_dane_firmy_trafiaja_do_zmiennych(zmienne):
    assert zmienne["FIRMA_NAZWA"] == g.DANE_FIRMY["FIRMA_NAZWA"]
    assert zmienne["FIRMA_NIP"] == g.DANE_FIRMY["FIRMA_NIP"]


def test_parametry_umowy_trafiaja_do_zmiennych(zmienne):
    assert zmienne["OKRES_GWARANCJI_MIESIACE"] == "24"
    assert zmienne["TERMIN_USTEREK_DNI"] == "14"
    assert zmienne["KOSZT_MAGAZYNOWANIA"] == "50"


def test_wartosci_liczbowe_konwertowane_na_tekst(dzien, kwota):
    """JSON potrafi podać liczbę zamiast stringa — podstawienie musi to znieść."""
    dane = dict(g.DANE_KLIENTA, TERMIN_TYGODNIE=8)
    zmienne = g.zbuduj_zmienne(dane, kwota, dzien)
    assert zmienne["TERMIN_TYGODNIE"] == "8"


def test_data_umowy_w_formacie_polskim(zmienne):
    assert zmienne["DATA_UMOWY"] == "27.08.2026"
