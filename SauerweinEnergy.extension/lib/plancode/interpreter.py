# -*- coding: utf-8 -*-
"""
Revit-Anbindung des Plancodierungs-Interpreters: liest Parameter und
Laufnummern-Status aus dem Modell und baut mit der reinen Logik
(logik.py) die Zielnummern samt Validierung und Kollisionspruefung.
"""
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSheet, BuiltInParameter
)

from plancode import config_store, logik

# Re-Export fuer bestehende Aufrufer
QUELLEN = logik.QUELLEN
TYPEN = logik.TYPEN
PADDINGS = logik.PADDINGS
pruefe_konfiguration = logik.pruefe_konfiguration

# Deutsche/englische UI-Namen auf BuiltInParameter mappen,
# damit Projektinfo-Felder unabhaengig von der Revit-Sprache funktionieren
_BUILTIN_MAP = {
    "projektnummer": BuiltInParameter.PROJECT_NUMBER,
    "project number": BuiltInParameter.PROJECT_NUMBER,
    "projektname": BuiltInParameter.PROJECT_NAME,
    "project name": BuiltInParameter.PROJECT_NAME,
    "auftraggeber": BuiltInParameter.CLIENT_NAME,
    "bauherr": BuiltInParameter.CLIENT_NAME,
    "client name": BuiltInParameter.CLIENT_NAME,
    "projektstatus": BuiltInParameter.PROJECT_STATUS,
    "project status": BuiltInParameter.PROJECT_STATUS,
}


def _param_as_string(elem, name):
    """Parameterwert als String lesen - erst Name, dann BuiltIn-Fallback."""
    p = elem.LookupParameter(name)
    if p is None:
        bip = _BUILTIN_MAP.get((name or "").strip().lower())
        if bip is not None:
            p = elem.get_Parameter(bip)
    if p is None:
        return None  # Parameter existiert nicht
    val = p.AsString()
    if val is None:
        val = p.AsValueString()
    return val or ""


def hole_rohwert(feld, sheet, doc):
    """Rohwert eines Feldes ermitteln. Liefert (wert, fehler_oder_None)."""
    quelle = feld.get("quelle", "sheet_parameter")
    pname = feld.get("parameter", "")

    if quelle == "auto":
        return None, None  # wird spaeter je Zaehlgruppe vergeben

    if quelle == "konstante":
        return (feld.get("werte") or "").strip(), None

    if quelle == "projektinfo":
        val = _param_as_string(doc.ProjectInformation, pname)
        if val is None:
            return "", u"Projektinfo-Parameter '{}' nicht gefunden".format(pname)
        return val.strip(), None

    if quelle == "sheet_parameter":
        val = _param_as_string(sheet, pname)
        if val is None:
            return "", u"Sheet-Parameter '{}' nicht gefunden".format(pname)
        return val.strip(), None

    if quelle == "mapping":
        val = _param_as_string(sheet, pname)
        if val is None:
            return "", u"Sheet-Parameter '{}' nicht gefunden".format(pname)
        mapping = logik.parse_mapping(feld.get("werte"))
        if val.strip() in mapping:
            return mapping[val.strip()], None
        return "", u"Wert '{}' nicht in Mapping-Tabelle".format(val.strip())

    return "", u"Unbekannte Quelle '{}'".format(quelle)


def _sortkey(sheet):
    return logik.natuerlicher_sortkey(sheet.SheetNumber or u"")


def alle_sheets(doc, nur_ids=None, mit_platzhaltern=False):
    sheets = list(FilteredElementCollector(doc)
                  .OfClass(ViewSheet)
                  .WhereElementIsNotElementType())
    if not mit_platzhaltern:
        sheets = [s for s in sheets if not s.IsPlaceholder]
    if nur_ids is not None:
        idset = set(nur_ids)
        sheets = [s for s in sheets if s.Id in idset]
    return sorted(sheets, key=_sortkey)


def baue_codes(doc, config, sheets=None, modus="beibehalten"):
    """
    Kernfunktion: baut fuer alle Sheets den Zielcode.
    Liefert Liste von dicts:
      {sheet, alt, neu, fehler(list), feldwerte(dict), state_neu(dict|None)}

    modus "beibehalten": Plaene behalten ihre gespeicherte Laufnummer
    (sticky), neue Plaene bekommen die naechste freie Nummer der Gruppe.
    modus "neu": kompakt neu durchnummerieren.

    state_neu ist der zu persistierende Laufnummern-Status, wenn er vom
    gespeicherten abweicht - das Schreiben uebernimmt der Aufrufer
    (nur 'Anwenden'; 'Pruefen' bleibt ein reiner Dry-Run).
    """
    if sheets is None:
        sheets = alle_sheets(doc)
    felder = config.get("felder", [])
    sep = config.get("separator", "-")

    ergebnisse = []
    for sheet in sheets:
        feldwerte = {}
        fehler = []
        for feld in felder:
            wert, f = hole_rohwert(feld, sheet, doc)
            if f:
                fehler.append(f)
            if feld.get("quelle") != "auto":
                fehler.extend(logik.validiere(wert, feld))
                wert = logik.formatiere(wert, feld)
            feldwerte[feld.get("id")] = wert
        ergebnisse.append({
            "sheet": sheet,
            "alt": sheet.SheetNumber,
            "neu": None,
            "fehler": fehler,
            "feldwerte": feldwerte,
            "state": config_store.lade_sheet_state(sheet),
            "state_neu": None,
        })

    # Laufnummern je Auto-Feld vergeben (sticky oder neu)
    for feld in [f for f in felder if f.get("quelle") == "auto"]:
        fid = feld.get("id")
        eintraege = []
        for erg in ergebnisse:
            eintraege.append({
                "key": logik.gruppen_key(feld, erg["feldwerte"]),
                "gespeichert": (erg["state"] or {}).get(fid),
                "fehler": bool(erg["fehler"]),
            })
        zuteilung = logik.vergebe_laufnummern(eintraege, modus)
        for erg, ein, zu in zip(ergebnisse, eintraege, zuteilung):
            nr = zu["nr"]
            if nr is None:
                erg["feldwerte"][fid] = logik.LAUFNR_PLATZHALTER
                continue
            text, ueberlauf = logik.laufnummer_als_text(nr, feld)
            erg["feldwerte"][fid] = text
            if ueberlauf:
                erg["fehler"].append(ueberlauf)
                continue
            gespeichert = ein["gespeichert"] or {}
            if (gespeichert.get("key") != ein["key"]
                    or gespeichert.get("nr") != nr):
                neuer_state = dict(erg["state"] or {})
                neuer_state[fid] = {"key": ein["key"], "nr": nr}
                erg["state"] = neuer_state
                erg["state_neu"] = neuer_state

    # Codes zusammensetzen; verbotene Zeichen nur bei sonst fehlerfreien
    # Plaenen melden (Fehler-Plaene tragen den '?'-Platzhalter)
    for erg in ergebnisse:
        erg["neu"] = logik.baue_code(felder, erg["feldwerte"], sep)
        if not erg["fehler"]:
            boese = logik.verbotene_zeichen_in(erg["neu"])
            if boese:
                erg["fehler"].append(
                    u"Zielnummer enthaelt in Revit unzulaessige Zeichen: "
                    u"{}".format(u" ".join(boese)))

    # Doppelte Zielnummern markieren
    codes = [erg["neu"] for erg in ergebnisse]
    for code, indizes in logik.finde_duplikate(codes).items():
        for i in indizes:
            ergebnisse[i]["fehler"].append(
                u"Zielnummer '{}' mehrfach vergeben".format(code))

    # Kollisionen mit Nummern, die bestehen bleiben: Platzhalter-Plaene
    # und Plaene, die wegen Fehlern uebersprungen werden
    belegt = {}
    for s in alle_sheets(doc, mit_platzhaltern=True):
        if s.IsPlaceholder:
            belegt[s.SheetNumber] = u"Platzhalter-Plan '{}'".format(s.Name)
    for erg in ergebnisse:
        if erg["fehler"]:
            belegt.setdefault(
                erg["alt"],
                u"Plan '{}' (wird uebersprungen)".format(erg["sheet"].Name))
    for erg in ergebnisse:
        if erg["fehler"] or erg["neu"] == erg["alt"]:
            continue
        if erg["neu"] in belegt:
            erg["fehler"].append(
                u"Zielnummer '{}' ist bereits belegt durch {}".format(
                    erg["neu"], belegt[erg["neu"]]))

    return ergebnisse
