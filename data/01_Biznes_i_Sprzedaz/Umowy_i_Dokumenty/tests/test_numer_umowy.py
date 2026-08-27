"""KATEGORIA: numer umowy i rejestr (książka umów).

Drzewo dokumentów wymaga UNIKALNEGO numeru — numer wiąże Protokół Odbioru
z Umową Główną miesiąc po podpisaniu. Poprzednia numeracja po inicjałach
(RRRR/MM/AN) dawała ten sam numer czterem różnym klientom w jednym miesiącu,
więc nie identyfikowała rodzica. Teraz numeracja jest porządkowa NN/RRRR,
a rejestr jest jedynym źródłem prawdy o wydanych numerach.
"""

import datetime
import json

import pytest

from conftest import DANE_TESTOWE, DZIEN_TESTOWY, dane_testowe, podmien_w_szablonie

import generator as g

pytestmark = pytest.mark.prawne

ROK = DZIEN_TESTOWY.year


def wpis(numer, imie="Anna Nowak", data="27.08.2026"):
    return {"numer": numer, "imie_nazwisko": imie, "data_umowy": data}


# --- przydzielanie numeru ---------------------------------------------------

def test_pierwszy_numer_w_roku():
    numer, nowy = g.przydziel_numer([], "Anna Nowak", DZIEN_TESTOWY)
    assert numer == f"1/{ROK}"
    assert nowy is True


def test_numeracja_rosnie():
    wpisy = [wpis(f"1/{ROK}"), wpis(f"2/{ROK}")]
    numer, _ = g.przydziel_numer(wpisy, "Jan Kowalski", DZIEN_TESTOWY)
    assert numer == f"3/{ROK}"


def test_numeracja_po_luce_bierze_najwyzszy():
    """Skasowany wpis nie może spowodować ponownego wydania numeru."""
    wpisy = [wpis(f"1/{ROK}"), wpis(f"7/{ROK}")]
    numer, _ = g.przydziel_numer(wpisy, "Jan Kowalski", DZIEN_TESTOWY)
    assert numer == f"8/{ROK}"


def test_numeracja_resetuje_sie_co_rok():
    wpisy = [wpis("12/2025"), wpis("13/2025")]
    numer, _ = g.przydziel_numer(wpisy, "Jan Kowalski", datetime.date(2026, 1, 3))
    assert numer == "1/2026"


def test_numer_idzie_za_data_umowy_a_nie_dniem_uruchomienia():
    """Umowa datowana wstecz trafia do numeracji swojego roku."""
    numer, _ = g.przydziel_numer([wpis("5/2026")], "Jan Kowalski", datetime.date(2025, 12, 30))
    assert numer == "1/2025"


# --- unikalność -------------------------------------------------------------

def test_dwoch_klientow_o_tych_samych_inicjalach_ma_rozne_numery():
    """Regresja: numeracja po inicjałach dawała obu 'RRRR/MM/JK'."""
    wpisy = []
    numery = []
    for imie in ["Jan Kowalski", "Joanna Kwiatkowska", "Jakub Kaczmarek", "Julia Kowal"]:
        numer, _ = g.przydziel_numer(wpisy, imie, DZIEN_TESTOWY)
        wpisy = g.dopisz_do_rejestru(wpisy, numer, imie, DZIEN_TESTOWY)
        numery.append(numer)
    assert len(set(numery)) == 4


def test_zajety_numer_odrzucony():
    wpisy = [wpis(f"1/{ROK}", "Anna Nowak")]
    with pytest.raises(g.BladGeneratora, match="już zajęty"):
        g.przydziel_numer(wpisy, "Piotr Zieliński", DZIEN_TESTOWY, zadany=f"1/{ROK}")


def test_komunikat_kolizji_wskazuje_wlasciciela_numeru():
    wpisy = [wpis(f"1/{ROK}", "Anna Nowak", "27.08.2026")]
    with pytest.raises(g.BladGeneratora) as blad:
        g.przydziel_numer(wpisy, "Piotr Zieliński", DZIEN_TESTOWY, zadany=f"1/{ROK}")
    assert "Anna Nowak" in str(blad.value)
    assert "27.08.2026" in str(blad.value)


def test_wlasny_numer_z_ksiegowosci_akceptowany():
    numer, nowy = g.przydziel_numer([], "Anna Nowak", DZIEN_TESTOWY, zadany="FV/2026/114")
    assert numer == "FV/2026/114"
    assert nowy is True


# --- ponowne generowanie tej samej umowy ------------------------------------

def test_ponowne_generowanie_odzyskuje_numer():
    """Poprawka literówki w adresie nie może spalić kolejnego numeru."""
    wpisy = [wpis(f"4/{ROK}", "Anna Nowak", "27.08.2026")]
    numer, nowy = g.przydziel_numer(wpisy, "Anna Nowak", DZIEN_TESTOWY)
    assert numer == f"4/{ROK}"
    assert nowy is False


def test_ten_sam_klient_inna_data_dostaje_nowy_numer():
    """Druga umowa z tym samym klientem to osobne zlecenie."""
    wpisy = [wpis(f"4/{ROK}", "Anna Nowak", "27.08.2026")]
    numer, nowy = g.przydziel_numer(wpisy, "Anna Nowak", datetime.date(2026, 11, 5))
    assert numer == f"5/{ROK}"
    assert nowy is True


def test_sprzeczny_numer_dla_znanej_umowy():
    wpisy = [wpis(f"4/{ROK}", "Anna Nowak", "27.08.2026")]
    with pytest.raises(g.BladGeneratora, match="ma już numer"):
        g.przydziel_numer(wpisy, "Anna Nowak", DZIEN_TESTOWY, zadany=f"9/{ROK}")


# --- plik rejestru ----------------------------------------------------------

def test_pusty_rejestr_gdy_brak_pliku(tmp_path):
    assert g.wczytaj_rejestr(tmp_path / "nie_ma.json") == []


def test_zapis_i_odczyt_rejestru(tmp_path):
    sciezka = tmp_path / "numery.json"
    g.zapisz_rejestr(sciezka, [wpis(f"1/{ROK}")])
    assert g.wczytaj_rejestr(sciezka) == [wpis(f"1/{ROK}")]


def test_rejestr_zapisany_w_utf8(tmp_path):
    sciezka = tmp_path / "numery.json"
    g.zapisz_rejestr(sciezka, [wpis("1/2026", "Łucja Żółć")])
    assert "Łucja Żółć" in sciezka.read_text(encoding="utf-8")


def test_uszkodzony_rejestr_nie_jest_nadpisywany(tmp_path):
    """Książka umów jest zbyt cenna, żeby ją milcząco zastąpić pustą."""
    sciezka = tmp_path / "numery.json"
    sciezka.write_text("{ zepsuty", encoding="utf-8")
    with pytest.raises(g.BladGeneratora, match="uszkodzony"):
        g.wczytaj_rejestr(sciezka)
    assert sciezka.read_text(encoding="utf-8") == "{ zepsuty"


def test_rejestr_o_zlej_strukturze(tmp_path):
    sciezka = tmp_path / "numery.json"
    sciezka.write_text('{"cos_innego": []}', encoding="utf-8")
    with pytest.raises(g.BladGeneratora, match="struktur"):
        g.wczytaj_rejestr(sciezka)


# --- integracja z generowaniem ----------------------------------------------

def test_numer_trafia_do_rejestru_po_wygenerowaniu(szablony, plik_danych):
    assert g.main(["generator.py", plik_danych()]) == 0
    wpisy = g.wczytaj_rejestr(szablony / "numery.json")
    assert len(wpisy) == 1
    assert wpisy[0]["numer"] == f"1/{ROK}"
    assert wpisy[0]["imie_nazwisko"] == "Anna Nowak"


def test_kolejne_umowy_dostaja_kolejne_numery(szablony, plik_danych):
    g.main(["generator.py", plik_danych()])
    drugi = dane_testowe(IMIE_NAZWISKO="Jan Kowalski", PESEL_NIP="85030512345")
    g.main(["generator.py", plik_danych(drugi, "drugi.json")])
    numery = [w["numer"] for w in g.wczytaj_rejestr(szablony / "numery.json")]
    assert numery == [f"1/{ROK}", f"2/{ROK}"]


def test_nieudane_generowanie_nie_pali_numeru(szablony, plik_danych):
    """Rejestr aktualizujemy dopiero po udanym zapisie plików."""
    (szablony / "instrukcja_template.md").unlink()
    assert g.main(["generator.py", plik_danych()]) == 1
    assert g.wczytaj_rejestr(szablony / "numery.json") == []


def test_powtorne_generowanie_nie_dopisuje_wpisu(szablony, plik_danych):
    plik = plik_danych()
    g.main(["generator.py", plik])
    g.main(["generator.py", plik])
    assert len(g.wczytaj_rejestr(szablony / "numery.json")) == 1


def test_kolizja_numeru_zatrzymuje_generowanie(szablony, plik_danych, capsys):
    g.main(["generator.py", plik_danych()])
    kolidujacy = dane_testowe(IMIE_NAZWISKO="Piotr Zieliński",
                              PESEL_NIP="85030512345", NUMER_UMOWY=f"1/{ROK}")
    assert g.main(["generator.py", plik_danych(kolidujacy, "kolizja.json")]) == 1
    assert "unikalny" in capsys.readouterr().err


def test_numer_w_nazwie_pliku_i_w_dokumencie(szablony, plik_danych):
    g.main(["generator.py", plik_danych()])
    pliki = sorted(p.name for p in (szablony / "wygenerowane").glob("*.md"))
    assert pliki == [f"Protokol_1-{ROK}_Anna_Nowak.md", f"Umowa_1-{ROK}_Anna_Nowak.md"]


def test_wypis_rejestru(szablony, plik_danych, capsys):
    g.main(["generator.py", plik_danych()])
    assert g.main(["generator.py", "--rejestr"]) == 0
    wypis = capsys.readouterr().out
    assert f"1/{ROK}" in wypis
    assert "Anna Nowak" in wypis


def test_wypis_pustego_rejestru(szablony, capsys):
    assert g.main(["generator.py", "--rejestr"]) == 0
    assert "pusty" in capsys.readouterr().out


# --- nazwa pliku ------------------------------------------------------------

@pytest.mark.parametrize("imie, oczekiwane", [
    ("Anna Nowak", "Anna_Nowak"),
    ("Łucja Żółć", "Lucja_Zolc"),
    ("Śliwiński Łukasz", "Sliwinski_Lukasz"),
    ("Jan Nowak-Kowalski", "Jan_Nowak_Kowalski"),
])
def test_nazwa_pliku_bez_polskich_znakow(imie, oczekiwane):
    """Regresja: Ł nie ma dekompozycji NFD, unicodedata samo go nie usunie."""
    assert g.bezpieczna_nazwa(imie) == oczekiwane
