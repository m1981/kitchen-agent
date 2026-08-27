"""KATEGORIA: finanse.

Rozliczenie transz w umowie musi się domykać co do grosza. Kod wyjściowy
liczył na float i obcinał przez int() — przy kwotach nieokrągłych transze
nie sumowały się do wartości umowy, co w dokumencie prawnym jest wadą
nie do obrony.
"""

from decimal import Decimal

import pytest

import generator as g
from conftest import NBSP, zbuduj_zmienne

pytestmark = pytest.mark.finanse

KWOTY_BRZEGOWE = ["30000", "27333.33", "10000.01", "999999.99", "1", "0.03", "1234567.89", "100.05"]


# --- podział na transze -----------------------------------------------------

@pytest.mark.parametrize("kwota", KWOTY_BRZEGOWE)
def test_suma_transz_rowna_sie_kwocie_umowy(kwota):
    """Niezmiennik nadrzędny: klient nie może zapłacić mniej ani więcej niż umowa."""
    transze = g.podziel_na_transze(Decimal(kwota))
    assert sum(transze.values()) == Decimal(kwota)


def test_podzial_50_40_10():
    transze = g.podziel_na_transze(Decimal("30000"))
    assert transze["ZADATEK"] == Decimal("15000")
    assert transze["TRANSZA_2"] == Decimal("12000")
    assert transze["TRANSZA_3"] == Decimal("3000")


def test_ostatnia_transza_przejmuje_reszte_zaokraglenia():
    """Regresja: 27333.33 * 0.5/0.4/0.1 zaokrąglone niezależnie gubi grosz."""
    transze = g.podziel_na_transze(Decimal("27333.33"))
    assert transze["ZADATEK"] == Decimal("13666.67")
    assert transze["TRANSZA_2"] == Decimal("10933.33")
    assert transze["TRANSZA_3"] == Decimal("2733.33")


def test_brak_obciecia_do_pelnych_zlotych():
    """Regresja po int(kwota) w kodzie wyjściowym — grosze znikały."""
    transze = g.podziel_na_transze(Decimal("100.05"))
    assert any(t % 1 != 0 for t in transze.values())
    assert sum(transze.values()) == Decimal("100.05")


@pytest.mark.parametrize("zla_kwota", ["0", "-1", "-30000"])
def test_kwota_niedodatnia_zatrzymuje_generowanie(zla_kwota):
    with pytest.raises(g.BladGeneratora, match="dodatnia"):
        g.podziel_na_transze(Decimal(zla_kwota))


def test_proporcje_nie_sumujace_sie_do_100_procent(monkeypatch):
    monkeypatch.setattr(g, "PODZIAL_TRANSZ", {
        "ZADATEK": Decimal("0.50"),
        "TRANSZA_2": Decimal("0.40"),
        "TRANSZA_3": Decimal("0.05"),
    })
    with pytest.raises(g.BladGeneratora, match="100%"):
        g.podziel_na_transze(Decimal("30000"))


def test_dowolne_proporcje_dalej_sie_domykaja(monkeypatch):
    monkeypatch.setattr(g, "PODZIAL_TRANSZ", {
        "ZADATEK": Decimal("0.335"),
        "TRANSZA_2": Decimal("0.335"),
        "TRANSZA_3": Decimal("0.33"),
    })
    transze = g.podziel_na_transze(Decimal("30000"))
    assert sum(transze.values()) == Decimal("30000")


# --- formatowanie -----------------------------------------------------------

@pytest.mark.parametrize("kwota, oczekiwane", [
    ("30000", f"30{NBSP}000"),
    ("999", "999"),
    ("1000000", f"1{NBSP}000{NBSP}000"),
    ("12345.50", f"12{NBSP}345,50"),
    ("100.05", "100,05"),
    ("0.03", "0,03"),
])
def test_formatowanie_kwoty(kwota, oczekiwane):
    assert g.formatuj_kwote(Decimal(kwota)) == oczekiwane


def test_separator_tysiecy_jest_spacja_nierozdzielajaca():
    """Decyzja projektowa: PDF nie może złamać '15 | 000' na końcu wiersza."""
    assert g.formatuj_kwote(Decimal("15000")) == f"15{NBSP}000"
    assert " " not in g.formatuj_kwote(Decimal("15000")), "zwykła spacja pozwoli złamać kwotę"


def test_przecinek_dziesietny_nie_kropka():
    """Polski zapis kwot w dokumencie prawnym."""
    assert g.formatuj_kwote(Decimal("1234.56")) == f"1{NBSP}234,56"


# --- procenty ---------------------------------------------------------------

def test_procenty_bez_zbednych_zer(zmienne):
    """Regresja: Decimal('0.50') * 100 renderowało się jako '50.00%'."""
    assert zmienne["PROCENT_ZADATEK"] == "50"
    assert zmienne["PROCENT_TRANSZA_2"] == "40"
    assert zmienne["PROCENT_TRANSZA_3"] == "10"


def test_procenty_ulamkowe_zachowuja_precyzje(monkeypatch, dzien):
    monkeypatch.setattr(g, "PODZIAL_TRANSZ", {
        "ZADATEK": Decimal("0.335"),
        "TRANSZA_2": Decimal("0.335"),
        "TRANSZA_3": Decimal("0.33"),
    })
    zmienne = zbuduj_zmienne(dzien=dzien)
    assert zmienne["PROCENT_ZADATEK"] == "33.5"
    assert zmienne["PROCENT_TRANSZA_3"] == "33"


def test_kazda_transza_ma_kwote_i_slownie(zmienne):
    for nazwa in ("ZADATEK", "TRANSZA_2", "TRANSZA_3"):
        assert zmienne[nazwa]
        assert zmienne[f"{nazwa}_SLOWNIE"]
