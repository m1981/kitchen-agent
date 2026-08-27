"""KATEGORIA: walidacja danych wejściowych.

Dane klienta zawsze przychodzą z zewnątrz plikiem JSON, więc to jedyne
miejsce, w którym literówka może wejść do umowy. Reguła: wychwycić ją
zanim powstanie dokument, i pokazać wszystkie błędy naraz.
"""

import datetime
from decimal import Decimal

import pytest

from conftest import DANE_TESTOWE, DZIEN_TESTOWY, dane_testowe

import generator as g

POLA_WYMAGANE = [k for k, p in g.SCHEMAT_DANYCH.items() if p.wymagane]
POLA_OPCJONALNE = [k for k, p in g.SCHEMAT_DANYCH.items() if not p.wymagane]


def bledy(dane):
    with pytest.raises(g.BladGeneratora) as blad:
        g.zwaliduj_dane(dane, DZIEN_TESTOWY)
    return str(blad.value)


# --- dane nie mieszkają w kodzie --------------------------------------------

def test_kod_nie_zawiera_danych_klienta():
    """Wymóg: PESEL i adres klienta nigdy w repozytorium."""
    assert not hasattr(g, "DANE_KLIENTA")
    assert not hasattr(g, "KWOTA_CALKOWITA")


def test_komplet_poprawnych_danych_przechodzi():
    dane = g.zwaliduj_dane(DANE_TESTOWE, DZIEN_TESTOWY)
    assert dane.kwota == Decimal("30000")
    assert dane.dzien == DZIEN_TESTOWY
    assert dane.pola["IMIE_NAZWISKO"] == "Anna Nowak"


# --- braki i literówki w nazwach pól ----------------------------------------

@pytest.mark.parametrize("brakujace", POLA_WYMAGANE)
def test_brak_wymaganego_pola(brakujace):
    dane = dane_testowe()
    del dane[brakujace]
    assert brakujace in bledy(dane)


@pytest.mark.parametrize("puste", ["", "   ", "\t\n"])
def test_pole_z_bialych_znakow_jest_brakiem(puste):
    assert "ADRES" in bledy(dane_testowe(ADRES=puste))


@pytest.mark.parametrize("literowka, poprawne", [
    ("IMIE_NAZWISKA", "IMIE_NAZWISKO"),
    ("ADRES_MONTARZU", "ADRES_MONTAZU"),
    ("TELEPHON", "TELEFON"),
    ("KWOTA_CALKOWITE", "KWOTA_CALKOWITA"),
    ("PESEL", "PESEL_NIP"),
])
def test_literowka_w_nazwie_pola_z_podpowiedzia(literowka, poprawne):
    """Bez tego pole po cichu wypadłoby z umowy."""
    dane = dane_testowe()
    dane[literowka] = dane.pop(poprawne)
    komunikat = bledy(dane)
    assert f"{literowka}: nieznane pole" in komunikat
    assert f"czy chodziło o '{poprawne}'" in komunikat


def test_zupelnie_obce_pole_bez_podpowiedzi():
    komunikat = bledy(dane_testowe(KOLOR_FRONTOW="biały"))
    assert "KOLOR_FRONTOW: nieznane pole" in komunikat
    assert "czy chodziło" not in komunikat


def test_klucze_z_podkreslnikiem_sa_komentarzami():
    dane = dane_testowe(_notatka="klient z polecenia", _opis="cokolwiek")
    assert g.zwaliduj_dane(dane, DZIEN_TESTOWY).pola["IMIE_NAZWISKO"] == "Anna Nowak"


def test_wszystkie_bledy_pokazane_naraz():
    """Poprawianie formularza po jednym błędzie na uruchomienie to udręka."""
    komunikat = bledy({"EMAIL": "zly", "TELEFON": "123"})
    for pole in ("IMIE_NAZWISKO", "ADRES", "PESEL_NIP", "EMAIL", "TELEFON", "KWOTA_CALKOWITA"):
        assert pole in komunikat


def test_json_nie_bedacy_obiektem():
    with pytest.raises(g.BladGeneratora, match="obiekt JSON"):
        g.zwaliduj_dane(["Anna Nowak"], DZIEN_TESTOWY)


# --- PESEL / NIP ------------------------------------------------------------

@pytest.mark.parametrize("poprawny", ["90010112349", "85030512345", "9671084572", "525-000-12-33"])
def test_pesel_i_nip_poprawne(poprawny):
    g.waliduj_pesel_lub_nip(poprawny)


@pytest.mark.parametrize("zly, powod", [
    ("90010112345", "suma kontrolna PESEL"),
    ("90010112340", "suma kontrolna PESEL"),
    ("9671084571", "suma kontrolna NIP"),
    ("123", "oczekiwano 11 cyfr"),
    ("900101123456789", "oczekiwano 11 cyfr"),
])
def test_pesel_i_nip_niepoprawne(zly, powod):
    with pytest.raises(ValueError, match=powod):
        g.waliduj_pesel_lub_nip(zly)


PESEL_POPRAWNY = "90010112349"


def test_kazda_pojedyncza_zla_cyfra_pesel_wykryta():
    """Wagi PESEL są względnie pierwsze z 10, więc pomyłka w jednej cyfrze
    zawsze zmienia sumę kontrolną. Sprawdzamy wszystkie 99 wariantów."""
    for i in range(len(PESEL_POPRAWNY)):
        for cyfra in "0123456789":
            if cyfra == PESEL_POPRAWNY[i]:
                continue
            zly = PESEL_POPRAWNY[:i] + cyfra + PESEL_POPRAWNY[i + 1:]
            with pytest.raises(ValueError):
                g.waliduj_pesel_lub_nip(zly)


@pytest.mark.parametrize("przestawiony", [
    "09010112349", "90100112349", "90001112349", "90011012349",
    "90010121349", "90010113249", "90010112439",
])
def test_przestawione_sasiednie_cyfry_pesel_wykryte(przestawiony):
    """Druga najczęstsza literówka przy przepisywaniu z dowodu."""
    with pytest.raises(ValueError):
        g.waliduj_pesel_lub_nip(przestawiony)


def test_znana_luka_algorytmu_pesel():
    """Zamiana ostatniej cyfry z kontrolną przechodzi — to ograniczenie
    samego algorytmu, nie naszej implementacji. Zapisane, żeby nikt nie
    uznał sumy kontrolnej za gwarancję poprawności numeru."""
    g.waliduj_pesel_lub_nip("90010112394")


# --- pozostałe walidatory ---------------------------------------------------

@pytest.mark.parametrize("email", ["a@b.pl", "anna.nowak@example.com", "x_y+z@sub.domena.co.uk"])
def test_email_poprawny(email):
    g.waliduj_email(email)


@pytest.mark.parametrize("email", ["anna.nowak@email", "anna.nowak", "@example.com", "a b@c.pl", ""])
def test_email_niepoprawny(email):
    with pytest.raises(ValueError):
        g.waliduj_email(email)


@pytest.mark.parametrize("telefon", ["500600700", "500 600 700", "500-600-700", "+48 500 600 700", "48500600700"])
def test_telefon_poprawny(telefon):
    g.waliduj_telefon(telefon)


@pytest.mark.parametrize("telefon", ["500 600 70", "5006007000", "abc"])
def test_telefon_niepoprawny(telefon):
    with pytest.raises(ValueError, match="9 cyfr"):
        g.waliduj_telefon(telefon)


@pytest.mark.parametrize("adres", ["Kwiatowa", "ul. Kwiatowa", "krótki"])
def test_adres_niepelny(adres):
    with pytest.raises(ValueError):
        g.waliduj_adres(adres)


def test_adres_bez_numeru_budynku():
    with pytest.raises(ValueError, match="numeru"):
        g.waliduj_adres("ul. Kwiatowa, Wrocław")


@pytest.mark.parametrize("imie", ["Anna", "A N", "Anna 2Nowak", "123 456"])
def test_imie_nazwisko_niepoprawne(imie):
    with pytest.raises(ValueError):
        g.waliduj_imie_nazwisko(imie)


@pytest.mark.parametrize("imie", ["Anna Nowak", "Jan Nowak-Kowalski", "Łucja Żółć", "Anna Maria Wiśniewska"])
def test_imie_nazwisko_poprawne(imie):
    g.waliduj_imie_nazwisko(imie)


def test_miejscowosc_z_cyframi():
    with pytest.raises(ValueError, match="cyfr"):
        g.waliduj_miejscowosc("Wrocław 2")


@pytest.mark.parametrize("kwota", ["30000", "30 000", "30000,50", "1.5", 30000, 30000.5])
def test_kwota_poprawna(kwota):
    g.waliduj_kwote(kwota)


@pytest.mark.parametrize("kwota, powod", [
    ("30 000 zl", "nie jest liczba"),
    ("-100", "dodatnia"),
    ("0", "dodatnia"),
    ("100.005", "grosze"),
    ("50000000", "pomyłkę"),
])
def test_kwota_niepoprawna(kwota, powod):
    with pytest.raises(ValueError, match=powod):
        g.waliduj_kwote(kwota)


@pytest.mark.parametrize("tygodnie", ["sześć", "0", "105", "-3", "6.5"])
def test_termin_niepoprawny(tygodnie):
    with pytest.raises(ValueError):
        g.waliduj_tygodnie(tygodnie)


@pytest.mark.parametrize("data", ["2026-08-27", "27/08/2026", "32.01.2026", "wczoraj"])
def test_data_niepoprawna(data):
    with pytest.raises(ValueError, match="DD.MM.RRRR"):
        g.waliduj_date(data)


# --- pola opcjonalne --------------------------------------------------------

@pytest.mark.parametrize("opcjonalne", POLA_OPCJONALNE)
def test_pole_opcjonalne_moze_byc_pominiete(opcjonalne):
    dane = dane_testowe()
    dane.pop(opcjonalne, None)
    g.zwaliduj_dane(dane, DZIEN_TESTOWY)


def test_data_z_pliku_nadpisuje_dzien_dzisiejszy():
    """Umowa może być datowana wstecz — numer musi iść za datą umowy."""
    dane = g.zwaliduj_dane(dane_testowe(DATA_UMOWY="15.03.2027"), DZIEN_TESTOWY)
    assert dane.dzien == datetime.date(2027, 3, 15)
    assert g.zbuduj_zmienne(dane)["NUMER_UMOWY"] == "2027/03/AN"


def test_brak_daty_oznacza_dzisiaj():
    assert g.zwaliduj_dane(DANE_TESTOWE, DZIEN_TESTOWY).dzien == DZIEN_TESTOWY


# --- dane wykonawcy ---------------------------------------------------------

@pytest.mark.parametrize("klucz", [
    "FIRMA_NAZWA", "FIRMA_ADRES", "FIRMA_NIP",
    "FIRMA_REPREZENTANT", "FIRMA_TELEFON", "FIRMA_EMAIL",
])
def test_dane_wykonawcy_kompletne(klucz):
    assert g.DANE_FIRMY[klucz].strip()


def test_kontakt_wykonawcy_poprawny():
    g.waliduj_email(g.DANE_FIRMY["FIRMA_EMAIL"])
    g.waliduj_telefon(g.DANE_FIRMY["FIRMA_TELEFON"])
    g.waliduj_pesel_lub_nip(g.DANE_FIRMY["FIRMA_NIP"])


def test_parametry_umowy_trafiaja_do_zmiennych(zmienne):
    assert zmienne["OKRES_GWARANCJI_MIESIACE"] == "24"
    assert zmienne["TERMIN_USTEREK_DNI"] == "14"
    assert zmienne["KOSZT_MAGAZYNOWANIA"] == "50"


# --- formularz --------------------------------------------------------------

def test_pusty_formularz_zawiera_wszystkie_pola():
    formularz = g.pusty_formularz()
    for klucz in g.SCHEMAT_DANYCH:
        assert klucz in formularz
        assert f"_{klucz}" in formularz, "brak opisu pola"


def test_pusty_formularz_nie_przechodzi_walidacji():
    """Szkielet trzeba wypełnić — pusty nie może wygenerować umowy."""
    with pytest.raises(g.BladGeneratora):
        g.zwaliduj_dane(g.pusty_formularz(), DZIEN_TESTOWY)


def test_kazde_pole_ma_opis_i_przyklad():
    for klucz, pole in g.SCHEMAT_DANYCH.items():
        assert pole.opis.strip(), klucz
        assert pole.przyklad.strip(), klucz


def test_przyklady_w_formularzu_przechodza_wlasna_walidacje():
    """Przykład, którego nie da się skopiować, jest gorszy niż jego brak."""
    for klucz, pole in g.SCHEMAT_DANYCH.items():
        if pole.walidator:
            pole.walidator(pole.przyklad)


def test_formularz_wypelniony_przykladami_generuje_umowe(szablony):
    """Formularz z --szablon po wpisaniu podpowiadanych wartości musi działać."""
    dane = {k: p.przyklad for k, p in g.SCHEMAT_DANYCH.items() if p.wymagane}
    g.zbuduj_zmienne(g.zwaliduj_dane(dane, DZIEN_TESTOWY))
