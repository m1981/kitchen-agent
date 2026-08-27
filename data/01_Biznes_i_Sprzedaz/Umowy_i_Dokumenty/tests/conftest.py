"""Wspólne fixture'y. Testy nigdy nie modyfikują szablonów w repo —
pracują na kopii w tmp_path, a BAZA generatora jest tam przekierowana."""

import datetime
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

KATALOG_PROJEKTU = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KATALOG_PROJEKTU))

import generator as g  # noqa: E402

NAZWY_SZABLONOW = [spec.plik for spec in g.DRZEWO_DOKUMENTOW]

# Data ustalona na sztywno — numer umowy zależy od daty, więc test
# nie może losować dnia uruchomienia.
# Separator tysięcy to spacja NIEROZDZIELAJĄCA (U+00A0) — w teście musi być
# jawna, bo od zwykłej spacji nie da się jej odróżnić wzrokiem.
NBSP = "\u00a0"

DZIEN_TESTOWY = datetime.date(2026, 8, 27)
KWOTA_TESTOWA = Decimal("30000")

# Dane klienta żyją poza kodem produkcyjnym, więc testy trzymają własny
# komplet. PESEL ma poprawną sumę kontrolną — walidator go sprawdza.
DANE_TESTOWE = {
    "IMIE_NAZWISKO": "Anna Nowak",
    "ADRES": "ul. Kwiatowa 15/2, 50-001 Wrocław",
    "PESEL_NIP": "90010112349",
    "TELEFON": "500 600 700",
    "EMAIL": "anna.nowak@example.com",
    "MIEJSCOWOSC": "Wrocław",
    "ADRES_MONTAZU": "ul. Kwiatowa 15/2, 50-001 Wrocław",
    "KWOTA_CALKOWITA": "30000",
    "TERMIN_TYGODNIE": "6",
}


def dane_testowe(**nadpisania):
    """Kopia danych wejściowych z punktowymi zmianami."""
    return {**DANE_TESTOWE, **nadpisania}


@pytest.fixture
def dzien():
    return DZIEN_TESTOWY


@pytest.fixture
def kwota():
    return KWOTA_TESTOWA


@pytest.fixture
def szablony(tmp_path, monkeypatch):
    """Kopia wszystkich szablonów w katalogu tymczasowym."""
    for nazwa in NAZWY_SZABLONOW:
        shutil.copy(KATALOG_PROJEKTU / nazwa, tmp_path / nazwa)
    monkeypatch.setattr(g, "BAZA", tmp_path)
    monkeypatch.setattr(g, "KATALOG_WYNIKOWY", tmp_path / "wygenerowane")
    return tmp_path


@pytest.fixture
def dane():
    return g.zwaliduj_dane(DANE_TESTOWE, DZIEN_TESTOWY)


@pytest.fixture
def zmienne(dane):
    return g.zbuduj_zmienne(dane)


@pytest.fixture
def plik_danych(tmp_path):
    """Ścieżka do pliku JSON z danymi — buduje go z podanego słownika."""
    def zbuduj(dane=None, nazwa="klient.json"):
        sciezka = tmp_path / nazwa
        sciezka.write_text(json.dumps(dane if dane is not None else DANE_TESTOWE,
                                      ensure_ascii=False), encoding="utf-8")
        return str(sciezka)
    return zbuduj


@pytest.fixture
def dokument(szablony, zmienne):
    """Gotowy, sklejony dokument wynikowy (4 dokumenty w jednym pliku)."""
    return g.generuj_dokument(zmienne)


def podmien_w_szablonie(katalog: Path, plik: str, stare: str, nowe: str) -> None:
    """Punktowa modyfikacja kopii szablonu; twardo sprawdza, że wzorzec istnieje,
    żeby test nie przechodził dlatego, że nic nie podmienił."""
    sciezka = katalog / plik
    tresc = sciezka.read_text(encoding="utf-8")
    assert stare in tresc, f"{plik}: brak wzorca {stare!r} — test wymaga aktualizacji"
    sciezka.write_text(tresc.replace(stare, nowe), encoding="utf-8")
