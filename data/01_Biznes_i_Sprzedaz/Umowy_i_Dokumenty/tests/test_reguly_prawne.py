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
        g.generuj_pakiet(zmienne)


@pytest.mark.parametrize("plik", ["umowa_template.md", "protokol_template.md"])
def test_usuniety_numer_z_dokumentu_podpisywanego_zatrzymuje_generowanie(szablony, zmienne, plik):
    podmien_w_szablonie(szablony, plik, TAG, "____")
    with pytest.raises(g.BladGeneratora, match="MUSI"):
        g.generuj_pakiet(zmienne)


def test_komunikat_bledu_wskazuje_plik_i_powod(szablony, zmienne):
    podmien_w_szablonie(szablony, "zalacznik1_template.md", "# ", f"{TAG}\n\n# ")
    with pytest.raises(g.BladGeneratora) as blad:
        g.generuj_pakiet(zmienne)
    assert "zalacznik1_template.md" in str(blad.value)
    assert "parafką" in str(blad.value)


# --- niezmiennik w gotowym dokumencie ---------------------------------------

def test_numer_umowy_tylko_w_umowie_i_protokole(dokumenty, zmienne):
    """Sprawdzenie na wyniku, nie na szablonie — łapie też błąd sklejania."""
    czesci = dokumenty
    numer = zmienne["NUMER_UMOWY"]
    assert len(czesci) == 4
    assert numer in czesci[0], "Umowa Główna bez numeru"
    assert numer not in czesci[1], "Załącznik nr 1 nie może nieść numeru"
    assert numer not in czesci[2], "Załącznik nr 2 nie może nieść numeru"
    assert numer in czesci[3], "Protokół bez odesłania do umowy"


def test_kolejnosc_dokumentow_w_pliku_wynikowym(dokumenty):
    czesci = dokumenty
    assert "UMOWA O DZIEŁO NR" in czesci[0]
    assert "ZAŁĄCZNIK NR 1" in czesci[1]
    assert "ZAŁĄCZNIK NR 2" in czesci[2]
    assert "PROTOKÓŁ ZDAWCZO-ODBIORCZY" in czesci[3]


def test_zalaczniki_odwoluja_sie_do_parafki_a_nie_podpisu(dokumenty):
    czesci = dokumenty
    assert "arafk" in czesci[1]
    assert "arafk" in czesci[2]


def test_protokol_odsyla_do_numeru_umowy_rodzica(dokumenty, zmienne):
    protokol = dokumenty[3]
    assert zmienne["NUMER_UMOWY"] in protokol
    assert zmienne["DATA_UMOWY"] in protokol


# ============================================================================
# Znaleziska audytu drzewa dokumentów — strażnicy regresji
# ============================================================================

def test_zalaczniki_sa_przypisywalne_bez_numeru_umowy(dokumenty, zmienne):
    """
    Reguła zabrania numeru umowy w załącznikach, ale po rozpięciu zszywki
    dokument musi dać się przypisać do klienta — inaczej nie da się wykazać,
    że TEN klient zaakceptował TEN załącznik. Identyfikacja: oznaczenie
    Zamawiającego i data zawarcia umowy.
    """
    for zalacznik, nazwa in ((dokumenty[1], "Załącznik nr 1"), (dokumenty[2], "Załącznik nr 2")):
        assert zmienne["NUMER_UMOWY"] not in zalacznik, f"{nazwa}: numer umowy zabroniony"
        assert zmienne["IMIE_NAZWISKO"] in zalacznik, f"{nazwa}: brak oznaczenia Zamawiającego"
        assert zmienne["DATA_UMOWY"] in zalacznik, f"{nazwa}: brak daty zawarcia umowy"


def test_zalacznik_2_wskazuje_zamawiajacego_w_oswiadczeniu(dokumenty, zmienne):
    """Oświadczenie o zapoznaniu się z zasadami pielęgnacji warunkuje
    wyłączenie gwarancji z §6.3c — musi wskazywać osobę składającą parafę."""
    oswiadczenie = dokumenty[2].split("OŚWIADCZENIE ZAMAWIAJĄCEGO")[-1]
    assert zmienne["IMIE_NAZWISKO"] in oswiadczenie


def test_protokol_odsyla_do_specyfikacji(dokumenty, zmienne):
    """Odbiór następuje wobec Załącznika nr 1 — protokół musi go przywołać,
    inaczej pętla rodzic -> dziecko -> dokument zamykający się nie domyka."""
    protokol = dokumenty[3]
    assert zmienne["ZAL_1_N"] in protokol
    assert zmienne["ZAL_1_TYTUL"] in protokol


def test_protokol_pozwala_zapisac_odstepstwa_od_projektu(dokumenty):
    assert "Odstępstwa" in dokumenty[3]


def test_zalacznik_1_parafowany_na_kazdej_stronie(dokumenty):
    """Specyfikacja to cała wartość dowodowa załącznika. Parafa wyłącznie
    na ostatniej stronie pozwoliłaby podmienić stronę z tabelą materiałów."""
    zalacznik = dokumenty[1]
    assert zalacznik.count("Parafa Zamawiającego") >= 4
    assert "każdą stronę" in zalacznik


def test_umowa_wymaga_paraf_na_kazdej_stronie_zalacznika(dokumenty):
    assert "na każdej stronie" in dokumenty[0]


def test_protokol_powstaje_w_osobnym_pliku(pakiet):
    """Drzewo: protokół NIE jest zszyty z umową (powstaje miesiąc później)."""
    assert "PROTOKÓŁ" not in pakiet[1]
    assert pakiet[2].lstrip().startswith("###")


@pytest.mark.parametrize("spec", g.DRZEWO_DOKUMENTOW, ids=lambda s: s.plik)
def test_kazdy_dokument_ma_przypisana_faze(spec):
    assert spec.faza in g.FAZY


def test_faza_zgadza_sie_z_obiegiem_dokumentu():
    fazy = {spec.prefiks: spec.faza for spec in g.DRZEWO_DOKUMENTOW}
    assert fazy == {"UMOWA": 1, "ZAL_1": 1, "ZAL_2": 1, "PROTOKOL": 2}
