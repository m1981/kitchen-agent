"""KATEGORIA: szablony i podstawianie zmiennych.

Najgroźniejszy błąd kodu wyjściowego: brakujący plik szablonu był tylko
drukowany na ekran, a skrypt i tak zapisywał umowę — bez paragrafu
o płatnościach. Tu pilnujemy, że każdy problem szablonu jest krytyczny.
"""

import pytest

from conftest import KATALOG_PROJEKTU, NAZWY_SZABLONOW, podmien_w_szablonie

import generator as g


# --- pliki szablonów --------------------------------------------------------

@pytest.mark.parametrize("nazwa", NAZWY_SZABLONOW)
def test_szablon_jest_poprawnym_utf8(nazwa):
    tresc = (KATALOG_PROJEKTU / nazwa).read_text(encoding="utf-8")
    assert tresc.strip()


@pytest.mark.parametrize("nazwa", NAZWY_SZABLONOW)
def test_szablon_zawiera_polskie_znaki(nazwa):
    """Kontrola kodowania — mojibake w umowie jest nie do przyjęcia."""
    tresc = (KATALOG_PROJEKTU / nazwa).read_text(encoding="utf-8")
    assert any(znak in tresc for znak in "ąćęłńóśźż")


def test_brak_pliku_szablonu_zatrzymuje_generowanie(szablony, zmienne):
    """Regresja: kod wyjściowy zapisywał wtedy niekompletną umowę."""
    (szablony / "instrukcja_template.md").unlink()
    with pytest.raises(g.BladGeneratora, match="Nie znaleziono szablonu"):
        g.generuj_dokument(zmienne)


def test_szablon_w_zlym_kodowaniu_zatrzymuje_generowanie(szablony, zmienne):
    (szablony / "umowa_template.md").write_bytes("Umowa {{NUMER_UMOWY}} — ąę".encode("cp1250"))
    with pytest.raises(g.BladGeneratora, match="UTF-8"):
        g.generuj_dokument(zmienne)


# --- zmienne ----------------------------------------------------------------

def test_nieznana_zmienna_zatrzymuje_generowanie(szablony, zmienne):
    """Literówka w nazwie zmiennej nie może trafić do PDF u klienta."""
    podmien_w_szablonie(szablony, "umowa_template.md", "{{TELEFON}}", "{{TELEFON_KOMORKOWY}}")
    with pytest.raises(g.BladGeneratora, match="TELEFON_KOMORKOWY"):
        g.generuj_dokument(zmienne)


def test_komunikat_wskazuje_plik_z_bledna_zmienna(szablony, zmienne):
    podmien_w_szablonie(szablony, "protokol_template.md", "{{ADRES_MONTAZU}}", "{{ADRES_MONTAZU_KLIENTA}}")
    with pytest.raises(g.BladGeneratora) as blad:
        g.generuj_dokument(zmienne)
    assert "protokol_template.md" in str(blad.value)


def test_wszystkie_zmienne_podstawione(dokument):
    assert "{{" not in dokument
    assert "}}" not in dokument


def test_zmienne_z_bialymi_znakami_w_tagu(szablony, zmienne):
    """{{ NUMER_UMOWY }} ma działać tak samo jak {{NUMER_UMOWY}}."""
    podmien_w_szablonie(szablony, "umowa_template.md", "{{TELEFON}}", "{{ TELEFON }}")
    dokument = g.generuj_dokument(zmienne)
    assert zmienne["TELEFON"] in dokument


@pytest.mark.parametrize("klucz", [
    "IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "ADRES_MONTAZU",
    "FIRMA_NAZWA", "FIRMA_NIP", "FIRMA_REPREZENTANT",
    "NUMER_UMOWY", "DATA_UMOWY", "KWOTA_BRUTTO", "KWOTA_SLOWNIE",
    "ZADATEK", "TRANSZA_2", "TRANSZA_3", "TERMIN_TYGODNIE",
    "OKRES_GWARANCJI_MIESIACE",
])
def test_slownik_zawiera_wymagane_klucze(zmienne, klucz):
    assert zmienne[klucz]


def test_kazda_zmienna_uzyta_w_szablonach_ma_wartosc(zmienne):
    """Spójność w drugą stronę: szablon nie odwołuje się do nieznanego klucza."""
    for nazwa in NAZWY_SZABLONOW:
        tresc = (KATALOG_PROJEKTU / nazwa).read_text(encoding="utf-8")
        for uzyta in g.WZORZEC_ZMIENNEJ.findall(tresc):
            assert uzyta in zmienne, f"{nazwa}: {uzyta}"
