"""KATEGORIA: reguły prawne — hierarchia i numeracja dokumentów.

Drzewo dokumentów:
    Umowa Główna (RODZIC)      -> numer umowy MUSI być, pełne podpisy
      +- Załącznik nr 1        -> numer umowy BRAK, tylko parafka
      +- Załącznik nr 2        -> numer umowy BRAK, tylko parafka
    Protokół Odbioru (Dzień 30) -> numer umowy MUSI być, pełne podpisy

Załączniki są zszywane z umową w dniu podpisania, więc własnego numeru nieść
nie mogą. Protokół powstaje miesiąc później osobno — bez numeru straciłby
powiązanie z umową.
"""

import pytest

from conftest import KATALOG_PROJEKTU, podmien_w_szablonie

import generator as g

pytestmark = pytest.mark.prawne

TAG = "{{NUMER_UMOWY}}"


def spec_wg_pliku(nazwa):
    return next(s for s in g.DRZEWO_DOKUMENTOW if s.plik == nazwa)


# --- stan szablonów w repo --------------------------------------------------

def test_drzewo_ma_cztery_dokumenty():
    assert len(g.DRZEWO_DOKUMENTOW) == 4


@pytest.mark.parametrize("spec", g.DRZEWO_DOKUMENTOW, ids=lambda s: s.plik)
def test_szablon_istnieje_w_repo(spec):
    assert (KATALOG_PROJEKTU / spec.plik).is_file()


@pytest.mark.parametrize("plik", ["umowa_template.md", "protokol_template.md"])
def test_dokumenty_podpisywane_maja_numer_umowy(plik):
    assert TAG in (KATALOG_PROJEKTU / plik).read_text(encoding="utf-8")


@pytest.mark.parametrize("plik", ["zalacznik1_template.md", "instrukcja_template.md"])
def test_zalaczniki_nie_maja_numeru_umowy(plik):
    """Reguła nadrzędna: parafowany załącznik nie nosi numeru umowy."""
    assert TAG not in (KATALOG_PROJEKTU / plik).read_text(encoding="utf-8")


def test_konfiguracja_zgadza_sie_z_trescia_szablonow():
    for spec in g.DRZEWO_DOKUMENTOW:
        tresc = (KATALOG_PROJEKTU / spec.plik).read_text(encoding="utf-8")
        assert (TAG in tresc) is spec.numer_umowy, spec.plik


# --- reakcja na złamanie reguły ---------------------------------------------

@pytest.mark.parametrize("plik", ["zalacznik1_template.md", "instrukcja_template.md"])
def test_numer_wstrzykniety_do_zalacznika_zatrzymuje_generowanie(szablony, zmienne, plik):
    (szablony / plik).write_text(
        (szablony / plik).read_text(encoding="utf-8") + f"\n\nNr {TAG}\n", encoding="utf-8"
    )
    with pytest.raises(g.BladGeneratora, match="NIE MOŻE"):
        g.generuj_dokument(zmienne)


@pytest.mark.parametrize("plik", ["umowa_template.md", "protokol_template.md"])
def test_usuniety_numer_z_dokumentu_podpisywanego_zatrzymuje_generowanie(szablony, zmienne, plik):
    podmien_w_szablonie(szablony, plik, TAG, "____")
    with pytest.raises(g.BladGeneratora, match="MUSI"):
        g.generuj_dokument(zmienne)


def test_komunikat_bledu_wskazuje_plik_i_powod(szablony, zmienne):
    podmien_w_szablonie(szablony, "zalacznik1_template.md", "# ", f"{TAG}\n\n# ")
    with pytest.raises(g.BladGeneratora) as blad:
        g.generuj_dokument(zmienne)
    assert "zalacznik1_template.md" in str(blad.value)
    assert "parafką" in str(blad.value)


# --- niezmiennik w gotowym dokumencie ---------------------------------------

def test_numer_umowy_tylko_w_umowie_i_protokole(dokument, zmienne):
    """Sprawdzenie na wyniku, nie na szablonie — łapie też błąd sklejania."""
    czesci = dokument.split(g.ZNACZNIK_STRONY)
    numer = zmienne["NUMER_UMOWY"]
    assert len(czesci) == 4
    assert numer in czesci[0], "Umowa Główna bez numeru"
    assert numer not in czesci[1], "Załącznik nr 1 nie może nieść numeru"
    assert numer not in czesci[2], "Załącznik nr 2 nie może nieść numeru"
    assert numer in czesci[3], "Protokół bez odesłania do umowy"


def test_kolejnosc_dokumentow_w_pliku_wynikowym(dokument):
    czesci = dokument.split(g.ZNACZNIK_STRONY)
    assert "UMOWA O DZIEŁO NR" in czesci[0]
    assert "ZAŁĄCZNIK NR 1" in czesci[1]
    assert "ZAŁĄCZNIK NR 2" in czesci[2]
    assert "PROTOKÓŁ ZDAWCZO-ODBIORCZY" in czesci[3]


def test_zalaczniki_odwoluja_sie_do_parafki_a_nie_podpisu(dokument):
    czesci = dokument.split(g.ZNACZNIK_STRONY)
    assert "arafk" in czesci[1]
    assert "arafk" in czesci[2]


def test_protokol_odsyla_do_numeru_umowy_rodzica(dokument, zmienne):
    protokol = dokument.split(g.ZNACZNIK_STRONY)[3]
    assert zmienne["NUMER_UMOWY"] in protokol
    assert zmienne["DATA_UMOWY"] in protokol
