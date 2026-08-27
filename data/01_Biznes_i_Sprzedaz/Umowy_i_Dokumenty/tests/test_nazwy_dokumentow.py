"""KATEGORIA: spójność nazw dokumentów.

Audyt wykrył, że Załącznik nr 2 występował pod czterema nazwami, w tym
w §6.3c jako "Instrukcja Użytkowania" — dokument o takiej nazwie nie istniał,
więc wyłączenie gwarancji odsyłało w próżnię. NAZWY_DOKUMENTOW to jedyne
źródło prawdy; detektor pilnuje, żeby nikt nie wpisał nazwy z ręki.
"""

import pytest

from conftest import KATALOG_PROJEKTU, podmien_w_szablonie, rozbij, zbuduj_zmienne

import generator as g

pytestmark = pytest.mark.prawne

PRZYPADKI_GRAMATYCZNE = ("M", "D", "C", "B", "N", "MS")


# --- kompletność konfiguracji -----------------------------------------------

def test_kazdy_dokument_ma_pelny_paradygmat():
    """Brakująca odmiana ujawniłaby się dopiero przy renderowaniu umowy."""
    for prefiks, formy in g.NAZWY_DOKUMENTOW.items():
        for przypadek in PRZYPADKI_GRAMATYCZNE + ("TYTUL",):
            assert formy.get(przypadek, "").strip(), f"{prefiks}.{przypadek}"


def test_walidacja_wykrywa_brakujaca_odmiane(monkeypatch):
    okrojone = {k: dict(v) for k, v in g.NAZWY_DOKUMENTOW.items()}
    del okrojone["ZAL_2"]["MS"]
    monkeypatch.setattr(g, "NAZWY_DOKUMENTOW", okrojone)
    with pytest.raises(g.BladGeneratora, match="MS"):
        g.sprawdz_kompletnosc_nazw()


def test_kazdy_dokument_w_drzewie_ma_nazwy():
    for spec in g.DRZEWO_DOKUMENTOW:
        assert spec.prefiks in g.NAZWY_DOKUMENTOW


def test_rozwiniecie_daje_warianty_wielkimi_literami():
    zmienne = g.rozwin_nazwy_dokumentow()
    assert zmienne["ZAL_2_M"] == "Załącznik nr 2"
    assert zmienne["ZAL_2_M_CAPS"] == "ZAŁĄCZNIK NR 2"
    assert zmienne["ZAL_2_D"] == "Załącznika nr 2"
    assert zmienne["ZAL_2_N"] == "Załącznikiem nr 2"


def test_rozwiniecie_pokrywa_wszystkie_dokumenty_i_przypadki():
    zmienne = g.rozwin_nazwy_dokumentow()
    for prefiks in g.NAZWY_DOKUMENTOW:
        for przypadek in PRZYPADKI_GRAMATYCZNE:
            assert f"{prefiks}_{przypadek}" in zmienne
            assert f"{prefiks}_{przypadek}_CAPS" in zmienne


# --- detektor nazw wpisanych na twardo --------------------------------------

@pytest.mark.parametrize("nazwa_na_twardo", [
    "Załącznik nr 1",
    "Załącznika nr 2",
    "ZAŁĄCZNIK NR 2",
    "Protokół Zdawczo-Odbiorczy",
    "Protokołu Zdawczo-Odbiorczego",
    "Karta Pielęgnacji i Użytkowania",
    "Umowa o Dzieło",
    "Instrukcja Użytkowania",
])
def test_nazwa_wpisana_recznie_zatrzymuje_generowanie(szablony, zmienne, nazwa_na_twardo):
    podmien_w_szablonie(szablony, "umowa_template.md",
                        "### § 1. Przedmiot Umowy",
                        f"### § 1. Przedmiot Umowy\n\nOdesłanie do {nazwa_na_twardo}.")
    with pytest.raises(g.BladGeneratora, match="na twardo"):
        g.generuj_pakiet(zmienne)


def test_komunikat_detektora_wskazuje_linie(szablony, zmienne):
    podmien_w_szablonie(szablony, "umowa_template.md",
                        "### § 1. Przedmiot Umowy",
                        "### § 1. Przedmiot Umowy\n\nPatrz Załącznik nr 1.")
    with pytest.raises(g.BladGeneratora) as blad:
        g.generuj_pakiet(zmienne)
    assert "linia" in str(blad.value)
    assert "NAZWY_DOKUMENTOW" in str(blad.value)


@pytest.mark.parametrize("dozwolone", [
    "Instrukcji obsługi zamontowanych systemów okuć",
    "Instrukcja obsługi zmywarki",
])
def test_dokumenty_producentow_agd_sa_dozwolone(szablony, zmienne, dozwolone):
    """To dokumenty osób trzecich, nie nasze drzewo — detektor ma je przepuścić."""
    podmien_w_szablonie(szablony, "umowa_template.md",
                        "### § 1. Przedmiot Umowy",
                        f"### § 1. Przedmiot Umowy\n\n{dozwolone}.")
    g.generuj_pakiet(zmienne)


def test_liczba_mnoga_jest_rzeczownikiem_pospolitym(szablony, zmienne):
    """'wymienione załączniki' to nie nazwa własna konkretnego dokumentu."""
    podmien_w_szablonie(szablony, "umowa_template.md",
                        "### § 1. Przedmiot Umowy",
                        "### § 1. Przedmiot Umowy\n\nWszystkie załączniki parafowane.")
    g.generuj_pakiet(zmienne)


def test_szablony_w_repo_przechodza_detektor(zmienne):
    """Strażnik regresji — nikt nie wpisał nazwy z ręki przy kolejnej edycji."""
    g.generuj_pakiet(zmienne)


# --- propagacja zmiany nazwy ------------------------------------------------

def test_zmiana_nazwy_propaguje_sie_na_wszystkie_dokumenty(szablony, monkeypatch, dzien):
    """Sedno refaktoru: jedna zmiana w configu, spójny wynik w 4 dokumentach."""
    nowa = "Instrukcja Pielęgnacji i Konserwacji Mebli"
    stara = g.NAZWY_DOKUMENTOW["ZAL_2"]["TYTUL"]
    podmieniony = {k: dict(v) for k, v in g.NAZWY_DOKUMENTOW.items()}
    podmieniony["ZAL_2"]["TYTUL"] = nowa
    monkeypatch.setattr(g, "NAZWY_DOKUMENTOW", podmieniony)

    pakiet = g.generuj_pakiet(zbuduj_zmienne(dzien=dzien))
    calosc = "\n".join(pakiet[faza] for faza in sorted(pakiet))

    assert stara not in calosc, "stara nazwa przetrwała gdzieś w dokumencie"
    assert calosc.count(nowa) >= 5
    assert nowa.upper() in calosc, "nagłówek H1 załącznika nie został zaktualizowany"

    czesci = rozbij(pakiet)
    assert nowa in czesci[0], "umowa nie odsyła do nowej nazwy"
    assert nowa.upper() in czesci[2], "sam załącznik ma starą nazwę"
    assert nowa in czesci[3], "protokół nie odsyła do nowej nazwy"


def test_zmiana_numeru_zalacznika_propaguje_odmiane(szablony, monkeypatch, dzien):
    podmieniony = {k: dict(v) for k, v in g.NAZWY_DOKUMENTOW.items()}
    podmieniony["ZAL_1"].update({
        "M": "Załącznik nr 1A", "D": "Załącznika nr 1A", "C": "Załącznikowi nr 1A",
        "B": "Załącznik nr 1A", "N": "Załącznikiem nr 1A", "MS": "Załączniku nr 1A",
    })
    monkeypatch.setattr(g, "NAZWY_DOKUMENTOW", podmieniony)
    calosc = "\n".join(g.generuj_pakiet(zbuduj_zmienne(dzien=dzien)).values())
    assert "Załącznika nr 1A" in calosc
    assert "Załącznik nr 1 " not in calosc


# --- niezmienniki gotowego dokumentu ----------------------------------------

def test_zalacznik_2_ma_jedna_nazwe_w_calym_dokumencie(dokument):
    """Regresja audytowa: nazwa występowała w 4 wariantach naraz."""
    tytul = g.NAZWY_DOKUMENTOW["ZAL_2"]["TYTUL"]
    for wariant in ("Instrukcją Użytkowania", "Instrukcja Pielęgnacji i Użytkowania",
                    "Karta Pielęgnacji i Użytkowania,"):
        assert wariant not in dokument
    assert tytul in dokument


def test_wylaczenie_gwarancji_odsyla_do_istniejacego_dokumentu(dokumenty):
    """§6.3c musi wskazywać dokument, który klient faktycznie parafuje."""
    umowa, _, zalacznik_2, _ = dokumenty
    klauzula = next(l for l in umowa.splitlines() if "szorstkich gąbek" in l)
    tytul = g.NAZWY_DOKUMENTOW["ZAL_2"]["TYTUL"]
    assert tytul in klauzula
    assert g.NAZWY_DOKUMENTOW["ZAL_2"]["N"] in klauzula
    assert tytul.upper() in zalacznik_2


def test_zalacznik_1_ma_jedna_nazwe(dokument):
    assert "Projekt i Specyfikacja)" not in dokument
    assert "(Projektu)" not in dokument
    assert g.NAZWY_DOKUMENTOW["ZAL_1"]["TYTUL"] in dokument


def test_tytul_dokumentu_w_logach_pochodzi_z_tego_samego_zrodla():
    """Komunikaty błędów nie mogą rozjechać się z treścią umowy."""
    for spec in g.DRZEWO_DOKUMENTOW:
        assert g.NAZWY_DOKUMENTOW[spec.prefiks]["TYTUL"] in spec.tytul
