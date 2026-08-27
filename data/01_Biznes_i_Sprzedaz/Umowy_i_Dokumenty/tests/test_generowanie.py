"""KATEGORIA: end-to-end — sklejanie i zapis pliku wynikowego.

Cztery dokumenty w jednym pliku, rozdzielone znacznikiem podziału strony,
gotowe do eksportu do PDF. Reguła nadrzędna całego skryptu: przy jakimkolwiek
błędzie NIE POWSTAJE żaden plik — wadliwa umowa nie może trafić do druku.
"""

import json

import pytest

from conftest import DZIEN_TESTOWY, KATALOG_PROJEKTU, dane_testowe, podmien_w_szablonie

import generator as g
from conftest import NBSP

pytestmark = pytest.mark.e2e


# --- struktura dokumentu ----------------------------------------------------

def test_pakiet_dzieli_sie_na_dwie_fazy(pakiet):
    """Faza 1 zszywana w dniu podpisania, faza 2 powstaje ok. miesiąc później."""
    assert sorted(pakiet) == [1, 2]


def test_faza_1_ma_trzy_dokumenty(pakiet):
    assert pakiet[1].count(g.ZNACZNIK_STRONY) == 2
    assert len(pakiet[1].split(g.ZNACZNIK_STRONY)) == 3


def test_faza_2_ma_wylacznie_protokol(pakiet):
    assert g.ZNACZNIK_STRONY not in pakiet[2]
    assert "PROTOKÓŁ ZDAWCZO-ODBIORCZY" in pakiet[2]
    assert "UMOWA O DZIEŁO NR" not in pakiet[2]


def test_umowa_nie_zawiera_protokolu(pakiet):
    """Protokół nie może wyjść z drukarki razem z umową w dniu 0."""
    assert "PROTOKÓŁ ZDAWCZO-ODBIORCZY" not in pakiet[1]


def test_dokumenty_nie_sa_puste(dokumenty):
    for czesc in dokumenty:
        assert len(czesc.strip()) > 200


def test_dane_klienta_w_dokumencie(dokument, zmienne):
    for klucz in ("IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "ADRES_MONTAZU"):
        assert zmienne[klucz] in dokument


def test_kwoty_w_dokumencie(dokument):
    assert f"30{NBSP}000" in dokument
    assert f"15{NBSP}000" in dokument
    assert f"12{NBSP}000" in dokument
    assert f"3{NBSP}000" in dokument


def test_umowa_i_protokol_maja_miejsce_na_pelne_podpisy(dokumenty):
    umowa, _, _, protokol = dokumenty
    for czesc in (umowa, protokol):
        assert "czytelny podpis" in czesc.lower()


# --- zapis pliku ------------------------------------------------------------

def test_main_zapisuje_dwa_pliki(szablony, plik_danych):
    """Jeden plik na fazę — protokół nie jest zszywany z umową."""
    assert g.main(["generator.py", plik_danych()]) == 0
    pliki = sorted(p.name for p in (szablony / "wygenerowane").glob("*.md"))
    assert len(pliki) == 2
    assert pliki[0].startswith("Protokol_")
    assert pliki[1].startswith("Umowa_")
    assert all(p.endswith("_Anna_Nowak.md") for p in pliki)


def test_nazwa_pliku_bez_polskich_znakow(szablony, plik_danych):
    dane = dane_testowe(IMIE_NAZWISKO="Łucja Żółć", DATA_UMOWY="27.08.2026")
    assert g.main(["generator.py", plik_danych(dane)]) == 0
    pliki = sorted(p.name for p in (szablony / "wygenerowane").glob("*.md"))
    assert pliki == ["Protokol_1-2026_Lucja_Zolc.md", "Umowa_1-2026_Lucja_Zolc.md"]


@pytest.mark.parametrize("wzorzec", ["Umowa_*.md", "Protokol_*.md"])
def test_zapis_w_utf8_z_koncami_linii_lf(szablony, plik_danych, wzorzec):
    g.main(["generator.py", plik_danych()])
    plik = next((szablony / "wygenerowane").glob(wzorzec))
    surowe = plik.read_bytes()
    assert b"\r\n" not in surowe
    assert "ł" in surowe.decode("utf-8")


@pytest.mark.parametrize("plik, podmiana", [
    ("instrukcja_template.md", None),
    ("umowa_template.md", ("{{TELEFON}}", "{{NIE_ISTNIEJE}}")),
])
def test_blad_nie_zostawia_zadnego_pliku(szablony, plik_danych, plik, podmiana):
    """Najważniejszy niezmiennik: albo komplet, albo nic."""
    if podmiana is None:
        (szablony / plik).unlink()
    else:
        podmien_w_szablonie(szablony, plik, *podmiana)
    assert g.main(["generator.py", plik_danych()]) == 1
    katalog = szablony / "wygenerowane"
    assert not katalog.exists() or not list(katalog.glob("*.md"))


# --- wejście JSON -----------------------------------------------------------

def test_dane_z_pliku_json(szablony, plik_danych):
    dane = dane_testowe(
        IMIE_NAZWISKO="Łukasz Śliwiński",
        ADRES="ul. Krzywoustego 8/3, 51-165 Wrocław",
        PESEL_NIP="85030512345",
        ADRES_MONTAZU="ul. Krzywoustego 8/3, 51-165 Wrocław",
        TERMIN_TYGODNIE="8",
        KWOTA_CALKOWITA="47500",
    )
    assert g.main(["generator.py", plik_danych(dane)]) == 0
    wynik = next((szablony / "wygenerowane").glob("*.md")).read_text(encoding="utf-8")
    assert "Łukasz Śliwiński" in wynik
    assert f"47{NBSP}500" in wynik
    assert "czterdzieści siedem tysięcy pięćset złotych" in wynik
    assert f"23{NBSP}750" in wynik


def test_brak_pliku_json(szablony, tmp_path, capsys):
    assert g.main(["generator.py", str(tmp_path / "nie_ma.json")]) == 1
    assert "nie znaleziono pliku" in capsys.readouterr().err.lower()


def test_bez_argumentu_pokazuje_uzycie(szablony, capsys):
    """Dane muszą przyjść z zewnątrz — samo uruchomienie nic nie generuje."""
    assert g.main(["generator.py"]) == 1
    assert "DANE.json" in capsys.readouterr().err


def test_pomoc_konczy_sie_sukcesem(capsys):
    assert g.main(["generator.py", "--help"]) == 0
    assert "--szablon" in capsys.readouterr().out


def test_szablon_tworzy_formularz(tmp_path):
    docelowy = tmp_path / "nowy_klient.json"
    assert g.main(["generator.py", "--szablon", str(docelowy)]) == 0
    formularz = json.loads(docelowy.read_text(encoding="utf-8"))
    assert "IMIE_NAZWISKO" in formularz
    assert formularz["IMIE_NAZWISKO"] == ""


def test_szablon_nie_nadpisuje_istniejacego(tmp_path, capsys):
    istniejacy = tmp_path / "jest.json"
    istniejacy.write_text("{}", encoding="utf-8")
    assert g.main(["generator.py", "--szablon", str(istniejacy)]) == 1
    assert "już istnieje" in capsys.readouterr().err
    assert istniejacy.read_text(encoding="utf-8") == "{}"


def test_szablon_bez_nazwy_pliku(capsys):
    assert g.main(["generator.py", "--szablon"]) == 1


def test_uszkodzony_json(szablony, tmp_path, capsys):
    plik_json = tmp_path / "zly.json"
    plik_json.write_text("{ to nie jest json", encoding="utf-8")
    assert g.main(["generator.py", str(plik_json)]) == 1
    assert "json" in capsys.readouterr().err.lower()


def test_puste_dane_w_json(szablony, plik_danych):
    assert g.main(["generator.py", plik_danych({"IMIE_NAZWISKO": "", "ADRES": ""})]) == 1


def test_literowka_w_json_nie_generuje_umowy(szablony, plik_danych, capsys):
    dane = dane_testowe()
    dane["ADRES_MONTARZU"] = dane.pop("ADRES_MONTAZU")
    assert g.main(["generator.py", plik_danych(dane)]) == 1
    assert "czy chodziło o 'ADRES_MONTAZU'" in capsys.readouterr().err
    assert not list((szablony / "wygenerowane").glob("*.md")) if (szablony / "wygenerowane").exists() else True


def test_przyklad_json_w_repo_przechodzi_walidacje():
    """Plik przykładowy musi być gotowy do skopiowania i uruchomienia."""
    dane = json.loads((KATALOG_PROJEKTU / "klient_przyklad.json").read_text(encoding="utf-8"))
    g.zwaliduj_dane(dane, DZIEN_TESTOWY)
