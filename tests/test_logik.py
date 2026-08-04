# -*- coding: utf-8 -*-
"""Tests fuer die Revit-freie Plancodierungs-Logik (lib/plancode/logik.py)."""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "SauerweinEnergy.extension", "lib"))

from plancode import logik  # noqa: E402


# ------------------------------------------------------------------ Parsen
def test_parse_liste():
    assert logik.parse_liste("HZG;KAE;LUF") == ["HZG", "KAE", "LUF"]
    assert logik.parse_liste(" HZG ; ;KAE ") == ["HZG", "KAE"]
    assert logik.parse_liste("") == []
    assert logik.parse_liste(None) == []


def test_parse_mapping():
    m = logik.parse_mapping("Erdgeschoss=EG;1. OG=01; Keller = UG ")
    assert m == {"Erdgeschoss": "EG", "1. OG": "01", "Keller": "UG"}
    assert logik.parse_mapping("ohne-gleichheitszeichen") == {}
    assert logik.parse_mapping(None) == {}


def test_verbotene_zeichen():
    assert logik.verbotene_zeichen_in("HZG-EG-001") == []
    assert ";" in logik.verbotene_zeichen_in("A;B")
    assert "{" in logik.verbotene_zeichen_in("A{B}")


# ------------------------------------------------------------- Validierung
def _feld(**kw):
    feld = {"id": "f1", "quelle": "sheet_parameter", "parameter": "P",
            "laenge": 0, "typ": "freitext", "werte": "",
            "padding": "keins", "zaehlgruppe": ""}
    feld.update(kw)
    return feld


def test_validiere_liste():
    feld = _feld(typ="liste", werte="HZG;KAE")
    assert logik.validiere("HZG", feld) == []
    assert logik.validiere("XXX", feld) != []


def test_validiere_regex_wird_voll_verankert():
    # Muster ohne ^...$ darf trotzdem keinen Teil-Match durchlassen
    feld = _feld(typ="regex", werte="UG|EG|[0-9]{2}")
    assert logik.validiere("EG", feld) == []
    assert logik.validiere("EGX", feld) != []
    assert logik.validiere("01", feld) == []
    assert logik.validiere("011", feld) != []


def test_validiere_regex_mit_ankern_weiter_ok():
    feld = _feld(typ="regex", werte="^(UG|EG)$")
    assert logik.validiere("EG", feld) == []
    assert logik.validiere("EGX", feld) != []


def test_validiere_ungueltiges_regex():
    feld = _feld(typ="regex", werte="([")
    assert logik.validiere("EG", feld) != []


def test_validiere_laenge_auch_mit_padding():
    # Ueberlaenge ist auch bei Padding 'nullen' ein Fehler (kein Abschneiden)
    feld = _feld(laenge=3, padding="nullen")
    assert logik.validiere("12", feld) == []
    assert logik.validiere("1234", feld) != []


def test_validiere_leer():
    feld = _feld()
    assert logik.validiere("", feld) != []
    auto = _feld(quelle="auto")
    assert logik.validiere("", auto) == []


def test_formatiere_padding_ohne_kuerzung():
    feld = _feld(laenge=3, padding="nullen")
    assert logik.formatiere("7", feld) == "007"
    # nie kuerzen - Ueberlaenge meldet die Validierung
    assert logik.formatiere("1234", feld) == "1234"
    keins = _feld(laenge=3, padding="keins")
    assert logik.formatiere("7", keins) == "7"


# ------------------------------------------------------------- Sortierung
def test_natuerlicher_sortkey():
    nummern = ["A10", "A2", "A1", "B1", "A2a"]
    s = sorted(nummern, key=logik.natuerlicher_sortkey)
    assert s == ["A1", "A2", "A2a", "A10", "B1"]


def test_sortkey_gemischt_crasht_nicht_unter_py3():
    # frueher: Vergleich int vs. str -> TypeError unter CPython 3
    nummern = ["100", "A100", "", "10A", "A", "2609-HZG-EG-GR-001"]
    sorted(nummern, key=logik.natuerlicher_sortkey)  # darf nicht werfen


# ---------------------------------------------------------- Laufnummern
def _e(key, gespeichert=None, fehler=False):
    return {"key": key, "gespeichert": gespeichert, "fehler": fehler}


def test_laufnummern_frisch():
    eintraege = [_e("A"), _e("A"), _e("B"), _e("A")]
    erg = logik.vergebe_laufnummern(eintraege)
    assert [x["nr"] for x in erg] == [1, 2, 1, 3]
    assert all(x["neu"] for x in erg)


def test_laufnummern_sticky_bleiben():
    eintraege = [
        _e("A", {"key": "A", "nr": 1}),
        _e("A", {"key": "A", "nr": 2}),
    ]
    erg = logik.vergebe_laufnummern(eintraege)
    assert [x["nr"] for x in erg] == [1, 2]
    assert not any(x["neu"] for x in erg)


def test_laufnummern_neuer_plan_verschiebt_nichts():
    # Neuer Plan sortiert VOR bestehenden -> bekommt max+1, verschiebt nichts
    eintraege = [
        _e("A"),                        # neu, sortiert zuerst
        _e("A", {"key": "A", "nr": 1}),
        _e("A", {"key": "A", "nr": 2}),
    ]
    erg = logik.vergebe_laufnummern(eintraege)
    assert [x["nr"] for x in erg] == [3, 1, 2]
    assert [x["neu"] for x in erg] == [True, False, False]


def test_laufnummern_geloeschte_nummer_wird_nicht_wiederverwendet():
    # Plan mit Nr. 2 wurde geloescht; neuer Plan bekommt 4, nicht 2
    eintraege = [
        _e("A", {"key": "A", "nr": 1}),
        _e("A", {"key": "A", "nr": 3}),
        _e("A"),
    ]
    erg = logik.vergebe_laufnummern(eintraege)
    assert [x["nr"] for x in erg] == [1, 3, 4]


def test_laufnummern_gruppenwechsel():
    # Plan wechselt von Gruppe A nach B: neue Nummer in B,
    # alte Nummer bleibt in A reserviert (kein Diebstahl durch Dritte)
    eintraege = [
        _e("B", {"key": "A", "nr": 2}),   # gewechselt
        _e("A", {"key": "A", "nr": 1}),
        _e("A"),                          # neu in A
    ]
    erg = logik.vergebe_laufnummern(eintraege)
    assert erg[0]["nr"] == 1          # erste Nummer in B
    assert erg[1]["nr"] == 1          # behaelt seine in A
    assert erg[2]["nr"] == 3          # 2 bleibt reserviert -> max+1 = 3


def test_laufnummern_doppelter_anspruch():
    # Zwei Plaene beanspruchen dieselbe Nummer (z. B. Duplizieren):
    # der erste behaelt sie, der zweite bekommt eine neue
    eintraege = [
        _e("A", {"key": "A", "nr": 1}),
        _e("A", {"key": "A", "nr": 1}),
    ]
    erg = logik.vergebe_laufnummern(eintraege)
    assert erg[0]["nr"] == 1 and not erg[0]["neu"]
    assert erg[1]["nr"] == 2 and erg[1]["neu"]


def test_laufnummern_fehlerplan_reserviert_aber_verbraucht_nicht():
    eintraege = [
        _e("A", {"key": "A", "nr": 1}, fehler=True),  # behaelt 1
        _e("A", fehler=True),                          # bekommt NICHTS
        _e("A"),                                       # bekommt 2
    ]
    erg = logik.vergebe_laufnummern(eintraege)
    assert erg[0]["nr"] == 1
    assert erg[1]["nr"] is None
    assert erg[2]["nr"] == 2


def test_laufnummern_modus_neu():
    eintraege = [
        _e("A", {"key": "A", "nr": 7}),
        _e("A"),
        _e("A", fehler=True),
        _e("B", {"key": "A", "nr": 9}),
    ]
    erg = logik.vergebe_laufnummern(eintraege, modus="neu")
    assert [x["nr"] for x in erg] == [1, 2, None, 1]
    # Plan 1: gespeichert war 7 -> Status muss neu geschrieben werden
    assert erg[0]["neu"] and erg[1]["neu"] and erg[3]["neu"]


def test_laufnummern_modus_neu_unveraendert_kein_neuschreiben():
    eintraege = [_e("A", {"key": "A", "nr": 1})]
    erg = logik.vergebe_laufnummern(eintraege, modus="neu")
    assert erg[0]["nr"] == 1 and not erg[0]["neu"]


def test_laufnummer_als_text_ueberlauf():
    feld = _feld(id="laufnr", laenge=3, padding="nullen")
    text, fehler = logik.laufnummer_als_text(7, feld)
    assert text == "007" and fehler is None
    text, fehler = logik.laufnummer_als_text(1000, feld)
    assert fehler is not None
    assert "1000" in text  # nicht abgeschnitten


# ------------------------------------------------------------ Codes bauen
def test_baue_code_und_duplikate():
    felder = [_feld(id="a"), _feld(id="b")]
    code = logik.baue_code(felder, {"a": "X", "b": "Y"}, "-")
    assert code == "X-Y"
    dups = logik.finde_duplikate(["A", "B", "A", "C", "B"])
    assert dups == {"A": [0, 2], "B": [1, 4]}


def test_gruppen_key():
    feld = _feld(quelle="auto", zaehlgruppe="gewerk;geschoss")
    key1 = logik.gruppen_key(feld, {"gewerk": "HZG", "geschoss": "EG"})
    key2 = logik.gruppen_key(feld, {"gewerk": "HZG", "geschoss": "01"})
    assert key1 != key2
    # fehlende Werte -> leerer Bestandteil, kein Crash
    logik.gruppen_key(feld, {})


# ------------------------------------------- Konfigurations-Konsistenz
def _config(felder, separator="-"):
    return {"schema_name": "T", "separator": separator, "felder": felder}


def test_konfig_ok():
    cfg = _config([
        _feld(id="gewerk", typ="liste", werte="HZG;KAE"),
        _feld(id="laufnr", quelle="auto", zaehlgruppe="gewerk"),
    ])
    assert logik.pruefe_konfiguration(cfg) == []


def test_konfig_leer_und_doppelte_ids():
    assert logik.pruefe_konfiguration(_config([])) != []
    cfg = _config([_feld(id="a"), _feld(id="a")])
    assert any("eindeutig" in f for f in logik.pruefe_konfiguration(cfg))


def test_konfig_separator_verboten():
    cfg = _config([_feld(id="a")], separator=";")
    assert any("Trennzeichen" in f for f in logik.pruefe_konfiguration(cfg))


def test_konfig_unbekannte_werte():
    cfg = _config([_feld(id="a", quelle="huh")])
    assert any("Quelle" in f for f in logik.pruefe_konfiguration(cfg))
    cfg = _config([_feld(id="a", typ="huh")])
    assert any("Typ" in f for f in logik.pruefe_konfiguration(cfg))
    cfg = _config([_feld(id="a", padding="huh")])
    assert any("Padding" in f for f in logik.pruefe_konfiguration(cfg))


def test_konfig_zaehlgruppe():
    cfg = _config([
        _feld(id="a"),
        _feld(id="laufnr", quelle="auto", zaehlgruppe="gibtsnicht"),
    ])
    assert any("unbekannte Feld-ID" in f
               for f in logik.pruefe_konfiguration(cfg))
    # Zaehlgruppe darf nicht auf ein Auto-Feld zeigen
    cfg = _config([
        _feld(id="l1", quelle="auto"),
        _feld(id="l2", quelle="auto", zaehlgruppe="l1"),
    ])
    assert any("Auto-Feld" in f for f in logik.pruefe_konfiguration(cfg))


def test_konfig_verbotene_zeichen_in_werten():
    cfg = _config([_feld(id="k", quelle="konstante", werte="TG{A}")])
    assert logik.pruefe_konfiguration(cfg) != []
    cfg = _config([_feld(id="m", quelle="mapping", parameter="P",
                         werte="Erdgeschoss=E;G")])  # Zielwert 'E' ok, 'G' ist eigener Eintrag ohne '='
    assert logik.pruefe_konfiguration(cfg) == []
    cfg = _config([_feld(id="l", typ="liste", werte="HZG;K[E")])
    assert logik.pruefe_konfiguration(cfg) != []


def test_konfig_regex_ungueltig():
    cfg = _config([_feld(id="r", typ="regex", werte="([")])
    assert any("Regex" in f for f in logik.pruefe_konfiguration(cfg))
