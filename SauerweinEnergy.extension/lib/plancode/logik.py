# -*- coding: utf-8 -*-
"""
Reine Plancodierungs-Logik ohne Revit-API.

Alles in diesem Modul ist mit normalem Python (2.7 und 3.x) lauffaehig
und wird durch tests/test_logik.py abgedeckt. Revit-Zugriffe liegen in
interpreter.py und config_store.py.
"""
import re

QUELLEN = ["projektinfo", "sheet_parameter", "auto", "konstante", "mapping"]
TYPEN = ["freitext", "liste", "regex"]
PADDINGS = ["keins", "nullen"]
MODI_LAUFNUMMERN = ["beibehalten", "neu"]

# Zeichen, die Revit in Plannummern nicht akzeptiert
VERBOTENE_ZEICHEN = u"\\:{}[]|;<>?`~\n\r"

# Trenner fuer Zaehlgruppen-Schluessel (kommt in Parameterwerten nicht vor)
GRUPPEN_TRENNER = u"\u001f"

# Platzhalter fuer nicht vergebbare Laufnummern (Plan hat Fehler)
LAUFNR_PLATZHALTER = u"?"


# ------------------------------------------------------------------ Parsen
def parse_liste(werte):
    """'HZG;KAE;LUF' -> ['HZG', 'KAE', 'LUF']"""
    return [w.strip() for w in (werte or u"").split(u";") if w.strip()]


def parse_mapping(werte):
    """'Erdgeschoss=EG;1. OG=01' -> dict"""
    mapping = {}
    for pair in (werte or u"").split(u";"):
        if u"=" in pair:
            k, v = pair.split(u"=", 1)
            mapping[k.strip()] = v.strip()
    return mapping


def verbotene_zeichen_in(text):
    """Liefert die in Revit-Plannummern unzulaessigen Zeichen aus text."""
    return [z for z in VERBOTENE_ZEICHEN if z in (text or u"")]


def _laenge_von(feld):
    try:
        laenge = int(feld.get("laenge") or 0)
    except (TypeError, ValueError):
        return 0
    return laenge if laenge > 0 else 0


# ------------------------------------------------------------- Validierung
def validiere(wert, feld):
    """Wert gegen Typ (liste/regex) und Laenge pruefen. Liefert Fehlerliste."""
    fehler = []
    typ = feld.get("typ", "freitext")
    laenge = _laenge_von(feld)

    if not wert:
        if feld.get("quelle") != "auto":
            fehler.append(u"Feld '{}' ist leer".format(feld.get("id")))
        return fehler

    if typ == "liste":
        erlaubt = parse_liste(feld.get("werte"))
        if erlaubt and wert not in erlaubt:
            fehler.append(u"'{}' nicht in Werteliste ({})".format(
                wert, u";".join(erlaubt)))
    elif typ == "regex":
        muster = feld.get("werte") or u""
        if muster:
            try:
                # Vollmatch erzwingen - auch wenn der Anwender ^...$ vergisst
                if re.match(u"(?:{})\\Z".format(muster), wert) is None:
                    fehler.append(u"'{}' verletzt Muster {}".format(wert, muster))
            except re.error:
                fehler.append(u"Ungueltiges Regex-Muster: {}".format(muster))

    # Ueberlaenge ist immer ein Fehler - es wird nie stillschweigend gekuerzt
    if laenge > 0 and len(wert) > laenge:
        fehler.append(u"'{}' laenger als {} Zeichen".format(wert, laenge))

    return fehler


def formatiere(wert, feld):
    """Padding anwenden. Kuerzt NIE (Ueberlaenge meldet validiere/Laufnummernvergabe)."""
    wert = wert or u""
    laenge = _laenge_von(feld)
    if laenge > 0 and feld.get("padding") == "nullen":
        wert = wert.rjust(laenge, u"0")
    return wert


# ------------------------------------------------------------- Sortierung
def natuerlicher_sortkey(text):
    """
    Natuerliche Sortierung ('A2' vor 'A10'). Liefert typ-homogene Tupel,
    damit sorted() auch unter CPython 3 funktioniert.
    """
    teile = re.split(r"(\d+)", text or u"")
    key = []
    for t in teile:
        if t.isdigit():
            key.append((0, int(t), u""))
        else:
            key.append((1, 0, t.lower()))
    return key


# ---------------------------------------------------------- Laufnummern
def gruppen_key(feld, feldwerte):
    """Zaehlgruppen-Schluessel eines Auto-Feldes aus den Feldwerten bilden."""
    gruppe = parse_liste(feld.get("zaehlgruppe"))
    return GRUPPEN_TRENNER.join([feldwerte.get(g) or u"" for g in gruppe])


def vergebe_laufnummern(eintraege, modus="beibehalten"):
    """
    Laufnummern fuer ein Auto-Feld zuteilen.

    eintraege: Liste (in Plansortierung) von dicts:
        {"key": Zaehlgruppen-Schluessel (str),
         "gespeichert": {"key": str, "nr": int} oder None,
         "fehler": bool}
    Liefert Liste gleicher Laenge:
        {"nr": int oder None, "neu": bool}

    modus "beibehalten" (Standard):
      - Ein Plan behaelt seine gespeicherte Nummer, solange sein
        Zaehlgruppen-Schluessel unveraendert ist (sticky).
      - Gespeicherte Nummern bleiben in ihrer gespeicherten Gruppe
        reserviert - auch von Fehler-Plaenen oder nach Gruppenwechsel.
      - Neue Plaene erhalten max+1 der Gruppe. Nummern geloeschter
        Plaene werden NICHT wiederverwendet (keine Verwechslungsgefahr
        bei bereits ausgegebenen Planstaenden).
      - Beanspruchen zwei Plaene dieselbe Nummer (z. B. nach
        Plan-Duplizierung), behaelt sie der erste in Sortierreihenfolge.
      - Plaene mit Fehlern bekommen keine NEUE Nummer zugeteilt.

    modus "neu": Alles wird kompakt neu durchnummeriert (1, 2, 3 ... je
    Gruppe in Sortierreihenfolge); gespeicherte Nummern werden ignoriert.
    """
    ergebnis = [{"nr": None, "neu": False} for _ in eintraege]

    if modus == "neu":
        zaehler = {}
        for i, e in enumerate(eintraege):
            if e.get("fehler"):
                continue
            k = e["key"]
            zaehler[k] = zaehler.get(k, 0) + 1
            nr = zaehler[k]
            ergebnis[i]["nr"] = nr
            g = e.get("gespeichert")
            ergebnis[i]["neu"] = (g is None or g.get("key") != k
                                  or g.get("nr") != nr)
        return ergebnis

    belegt = {}    # gruppe -> set(nr)
    besitzer = {}  # (gruppe, nr) -> index des Plans, der sie behaelt

    def _reserviere(k, nr):
        belegt.setdefault(k, set()).add(nr)

    def _naechste_freie(k):
        nummern = belegt.get(k)
        return (max(nummern) + 1) if nummern else 1

    # Pass 1: alle gespeicherten Ansprueche reservieren
    for i, e in enumerate(eintraege):
        g = e.get("gespeichert")
        if not g or g.get("nr") is None:
            continue
        paar = (g.get("key"), g.get("nr"))
        if paar not in besitzer:
            besitzer[paar] = i
        _reserviere(paar[0], paar[1])

    # Pass 2: zuteilen
    for i, e in enumerate(eintraege):
        g = e.get("gespeichert")
        k = e["key"]
        behaelt = (g is not None and g.get("key") == k
                   and besitzer.get((k, g.get("nr"))) == i)
        if behaelt:
            ergebnis[i]["nr"] = g.get("nr")
            continue
        if e.get("fehler"):
            continue  # kein neuer Verbrauch durch fehlerhafte Plaene
        nr = _naechste_freie(k)
        _reserviere(k, nr)
        ergebnis[i]["nr"] = nr
        ergebnis[i]["neu"] = True
    return ergebnis


def laufnummer_als_text(nr, feld):
    """Nummer formatieren. Liefert (text, fehler_oder_None) bei Ueberlauf."""
    text = u"{}".format(nr)
    laenge = _laenge_von(feld)
    if laenge > 0 and len(text) > laenge:
        return text, (u"Laufnummer {} uebersteigt Feldlaenge {} "
                      u"(Feld '{}')".format(nr, laenge, feld.get("id")))
    return formatiere(text, feld), None


# ------------------------------------------------------------ Codes bauen
def baue_code(felder, feldwerte, separator):
    return (separator or u"").join(
        [feldwerte.get(f.get("id")) or u"" for f in felder])


def finde_duplikate(codes):
    """Indizes je mehrfach vorkommendem Code: {code: [i, j, ...]}."""
    gesehen = {}
    for i, code in enumerate(codes):
        gesehen.setdefault(code, []).append(i)
    return dict((code, idx) for code, idx in gesehen.items() if len(idx) > 1)


# ------------------------------------------- Konfigurations-Konsistenz
def pruefe_konfiguration(config):
    """Konfiguration selbst auf Konsistenz pruefen. Liefert Fehlerliste."""
    fehler = []
    felder = config.get("felder") or []
    if not isinstance(felder, list) or not felder:
        return [u"Keine Felder definiert."]

    sep = config.get("separator", u"-") or u""
    boese = verbotene_zeichen_in(sep)
    if boese:
        fehler.append(u"Trennzeichen enthaelt in Plannummern unzulaessige "
                      u"Zeichen: {}".format(u" ".join(boese)))

    ids = [f.get("id") for f in felder]
    if not all(ids):
        fehler.append(u"Feld ohne ID vorhanden.")
    if len(set(ids)) != len(ids):
        fehler.append(u"Feld-IDs sind nicht eindeutig.")

    auto_ids = set(f.get("id") for f in felder if f.get("quelle") == "auto")

    for f in felder:
        fid = f.get("id")
        q = f.get("quelle")
        if q not in QUELLEN:
            fehler.append(u"Feld '{}': unbekannte Quelle '{}'".format(fid, q))
        if f.get("typ") not in TYPEN:
            fehler.append(u"Feld '{}': unbekannter Typ '{}'".format(
                fid, f.get("typ")))
        if f.get("padding") not in PADDINGS:
            fehler.append(u"Feld '{}': unbekanntes Padding '{}'".format(
                fid, f.get("padding")))
        try:
            if int(f.get("laenge") or 0) < 0:
                fehler.append(u"Feld '{}': Laenge darf nicht negativ sein.".format(fid))
        except (TypeError, ValueError):
            fehler.append(u"Feld '{}': Laenge ist keine Zahl.".format(fid))

        if q in ("sheet_parameter", "projektinfo", "mapping") and not f.get("parameter"):
            fehler.append(u"Feld '{}': Parametername fehlt.".format(fid))

        if q == "auto":
            for g in parse_liste(f.get("zaehlgruppe")):
                if g not in ids:
                    fehler.append(u"Feld '{}': Zaehlgruppe verweist auf "
                                  u"unbekannte Feld-ID '{}'".format(fid, g))
                elif g in auto_ids:
                    fehler.append(u"Feld '{}': Zaehlgruppe darf nicht auf das "
                                  u"Auto-Feld '{}' verweisen".format(fid, g))

        if f.get("typ") == "regex" and f.get("werte"):
            try:
                re.compile(f.get("werte"))
            except re.error:
                fehler.append(u"Feld '{}': ungueltiges Regex-Muster.".format(fid))

        # Werte, die 1:1 im Code landen, duerfen keine verbotenen Zeichen tragen
        if q == "konstante":
            boese = verbotene_zeichen_in(f.get("werte"))
            if boese:
                fehler.append(u"Feld '{}': Konstante enthaelt unzulaessige "
                              u"Zeichen: {}".format(fid, u" ".join(boese)))
        elif q == "mapping":
            for ziel in parse_mapping(f.get("werte")).values():
                boese = verbotene_zeichen_in(ziel)
                if boese:
                    fehler.append(u"Feld '{}': Mapping-Zielwert '{}' enthaelt "
                                  u"unzulaessige Zeichen: {}".format(
                                      fid, ziel, u" ".join(boese)))
        elif f.get("typ") == "liste":
            for wert in parse_liste(f.get("werte")):
                boese = verbotene_zeichen_in(wert)
                if boese:
                    fehler.append(u"Feld '{}': Listenwert '{}' enthaelt "
                                  u"unzulaessige Zeichen: {}".format(
                                      fid, wert, u" ".join(boese)))
    return fehler
