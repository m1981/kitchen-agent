"""KATEGORIA: end-to-end — sklejanie i zapis pliku wynikowego.

Cztery dokumenty w jednym pliku, rozdzielone znacznikiem podziału strony,
gotowe do eksportu do PDF. Reguła nadrzędna całego skryptu: przy jakimkolwiek
błędzie NIE POWSTAJE żaden plik — wadliwa umowa nie może trafić do druku.
"""

import json

import pytest

from conftest import KATALOG_PROJEKTU, podmien_w_szablonie

import generator as g
from conftest import NBSP

pytestmark = pytest.mark.e2e


# --- struktura dokumentu ----------------------------------------------------

def test_cztery_dokumenty_i_trzy_podzialy_stron(dokument):
    assert dokument.count(g.ZNACZNIK_STRONY) == 3
    assert len(dokument.split(g.ZNACZNIK_STRONY)) == 4


def test_dokumenty_nie_sa_puste(dokument):
    for czesc in dokument.split(g.ZNACZNIK_STRONY):
        assert len(czesc.strip()) > 200


def test_dane_klienta_w_dokumencie(dokument, zmienne):
    for klucz in ("IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "ADRES_MONTAZU"):
        assert zmienne[klucz] in dokument


def test_kwoty_w_dokumencie(dokument):
    assert f"30{NBSP}000" in dokument
    assert f"15{NBSP}000" in dokument
    assert f"12{NBSP}000" in dokument
    assert f"3{NBSP}000" in dokument


def test_umowa_i_protokol_maja_miejsce_na_pelne_podpisy(dokument):
    umowa, _, _, protokol = dokument.split(g.ZNACZNIK_STRONY)
    for czesc in (umowa, protokol):
        assert "podpis" in czesc.lower()


# --- zapis pliku ------------------------------------------------------------

def test_main_zapisuje_plik(szablony, monkeypatch):
    assert g.main(["generator.py"]) == 0
    pliki = list((szablony / "wygenerowane").glob("*.md"))
    assert len(pliki) == 1
    assert pliki[0].name == "Umowa_2026-08-AN_Anna_Nowak.md"


def test_nazwa_pliku_bez_polskich_znakow(szablony, monkeypatch):
    monkeypatch.setattr(g, "DANE_KLIENTA", dict(g.DANE_KLIENTA, IMIE_NAZWISKO="Łucja Żółć"))
    assert g.main(["generator.py"]) == 0
    pliki = list((szablony / "wygenerowane").glob("*.md"))
    assert pliki[0].name == "Umowa_2026-08-LZ_Lucja_Zolc.md"


def test_zapis_w_utf8_z_koncami_linii_lf(szablony):
    g.main(["generator.py"])
    plik = next((szablony / "wygenerowane").glob("*.md"))
    surowe = plik.read_bytes()
    assert b"\r\n" not in surowe
    assert "Dzieła" in surowe.decode("utf-8")


@pytest.mark.parametrize("plik, podmiana", [
    ("instrukcja_template.md", None),
    ("umowa_template.md", ("{{TELEFON}}", "{{NIE_ISTNIEJE}}")),
])
def test_blad_nie_zostawia_zadnego_pliku(szablony, plik, podmiana):
    """Najważniejszy niezmiennik: albo komplet, albo nic."""
    if podmiana is None:
        (szablony / plik).unlink()
    else:
        podmien_w_szablonie(szablony, plik, *podmiana)
    assert g.main(["generator.py"]) == 1
    katalog = szablony / "wygenerowane"
    assert not katalog.exists() or not list(katalog.glob("*.md"))


# --- wejście JSON -----------------------------------------------------------

def test_dane_z_pliku_json(szablony, tmp_path):
    dane = {
        "IMIE_NAZWISKO": "Łukasz Śliwiński",
        "ADRES": "ul. Krzywoustego 8/3, 51-165 Wrocław",
        "PESEL_NIP": "85030512345",
        "MIEJSCOWOSC": "Wrocław",
        "ADRES_MONTAZU": "ul. Krzywoustego 8/3, 51-165 Wrocław",
        "TERMIN_TYGODNIE": "8",
        "KWOTA_CALKOWITA": "47500",
    }
    plik_json = tmp_path / "klient.json"
    plik_json.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")

    assert g.main(["generator.py", str(plik_json)]) == 0
    wynik = next((szablony / "wygenerowane").glob("*.md")).read_text(encoding="utf-8")
    assert "Łukasz Śliwiński" in wynik
    assert f"47{NBSP}500" in wynik
    assert "czterdzieści siedem tysięcy pięćset złotych" in wynik
    assert f"23{NBSP}750" in wynik


def test_brak_pliku_json(szablony, tmp_path, capsys):
    assert g.main(["generator.py", str(tmp_path / "nie_ma.json")]) == 1
    assert "nie znaleziono pliku" in capsys.readouterr().err.lower()


def test_uszkodzony_json(szablony, tmp_path, capsys):
    plik_json = tmp_path / "zly.json"
    plik_json.write_text("{ to nie jest json", encoding="utf-8")
    assert g.main(["generator.py", str(plik_json)]) == 1
    assert "json" in capsys.readouterr().err.lower()


def test_puste_dane_w_json(szablony, tmp_path):
    plik_json = tmp_path / "puste.json"
    plik_json.write_text(json.dumps({"IMIE_NAZWISKO": "", "ADRES": ""}), encoding="utf-8")
    assert g.main(["generator.py", str(plik_json)]) == 1


def test_przyklad_json_w_repo_jest_poprawny():
    dane = json.loads((KATALOG_PROJEKTU / "klient_przyklad.json").read_text(encoding="utf-8"))
    for klucz in ("IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "MIEJSCOWOSC", "ADRES_MONTAZU"):
        assert dane[klucz]
