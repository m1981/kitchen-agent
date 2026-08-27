"""KATEGORIA: kwota słownie.

W kodzie wyjściowym KWOTA_SLOWNIE była wpisywana ręcznie. Każda zmiana kwoty
groziła rozjazdem cyfry ze słownie — a przy rozbieżności w umowie
rozstrzyga zapis słowny. Stąd generowanie i pełne testy odmiany.
"""

from decimal import Decimal

import pytest

import generator as g
from conftest import NBSP

pytestmark = pytest.mark.finanse


@pytest.mark.parametrize("liczba, oczekiwane", [
    (0, "zero"),
    (1, "jeden"),
    (5, "pięć"),
    (12, "dwanaście"),
    (15, "piętnaście"),
    (22, "dwadzieścia dwa"),
    (100, "sto"),
    (112, "sto dwanaście"),
    (200, "dwieście"),
    (999, "dziewięćset dziewięćdziesiąt dziewięć"),
    (1000, "tysiąc"),
    (2000, "dwa tysiące"),
    (5000, "pięć tysięcy"),
    (15000, "piętnaście tysięcy"),
    (21000, "dwadzieścia jeden tysięcy"),
    (30000, "trzydzieści tysięcy"),
    (1000000, "milion"),
    (2000000, "dwa miliony"),
    (5000000, "pięć milionów"),
])
def test_liczba_slownie(liczba, oczekiwane):
    assert g.liczba_slownie(liczba) == oczekiwane


def test_tysiac_bez_jeden():
    """Poprawnie: 'tysiąc złotych', nie 'jeden tysiąc złotych'."""
    assert not g.liczba_slownie(1000).startswith("jeden")


@pytest.mark.parametrize("liczba, forma", [
    (1, "złoty"),
    (2, "złote"),
    (3, "złote"),
    (4, "złote"),
    (5, "złotych"),
    (11, "złotych"),
    (12, "złotych"),   # wyjątek 12-14 mimo końcówki 2-4
    (13, "złotych"),
    (14, "złotych"),
    (22, "złote"),
    (25, "złotych"),
    (112, "złotych"),
    (122, "złote"),
    (0, "złotych"),
])
def test_odmiana_rzeczownika_zloty(liczba, forma):
    assert f" {forma} " in f" {g.kwota_slownie(Decimal(liczba))} "


@pytest.mark.parametrize("kwota, oczekiwane", [
    ("30000", "trzydzieści tysięcy złotych 00/100"),
    ("15000", "piętnaście tysięcy złotych 00/100"),
    ("1234.56", "tysiąc dwieście trzydzieści cztery złote 56/100"),
    ("47500", "czterdzieści siedem tysięcy pięćset złotych 00/100"),
    ("0.05", "zero złotych 05/100"),
])
def test_kwota_slownie(kwota, oczekiwane):
    assert g.kwota_slownie(Decimal(kwota)) == oczekiwane


def test_grosze_zawsze_dwucyfrowe():
    assert g.kwota_slownie(Decimal("10.5")).endswith("50/100")
    assert g.kwota_slownie(Decimal("10.05")).endswith("05/100")


def test_slownie_zgadza_sie_z_kwota_cyframi(zmienne):
    """Niezmiennik: obie reprezentacje pochodzą z tej samej liczby."""
    assert zmienne["KWOTA_BRUTTO"] == f"30{NBSP}000"
    assert zmienne["KWOTA_SLOWNIE"].startswith("trzydzieści tysięcy")


@pytest.mark.parametrize("zla", [-1, 10 ** 12])
def test_liczba_poza_zakresem(zla):
    with pytest.raises(g.BladGeneratora):
        g.liczba_slownie(zla)
