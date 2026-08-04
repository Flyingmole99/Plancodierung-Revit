# -*- coding: utf-8 -*-
"""
Generischer Interpreter: baut Plannummern aus einer beliebigen
Feld-Konfiguration, validiert Werte und vergibt Laufnummern
je konfigurierbarer Zaehlgruppe.
"""
import re

from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSheet, BuiltInParameter
)

QUELLEN = ["projektinfo", "sheet_parameter", "auto", "konstante", "mapping"]
TYPEN = ["freitext", "liste", "regex"]
PADDINGS = ["keins", "nullen"]

# Deutsche/englische UI-Namen auf BuiltInParameter mappen,
# damit Projektinfo-Felder unabhaengig von der Revit-Sprache funktionieren
_BUILTIN_MAP = {
    "projektnummer": BuiltInParameter.PROJECT_NUMBER,
    "project number": BuiltInParameter.PROJECT_NUMBER,
    "projektname": BuiltInParameter.PROJECT_NAME,
    "project name": BuiltInParameter.PROJECT_NAME,
    "auftraggeber": BuiltInParameter.CLIENT_NAME,
    "client name": BuiltInParameter.CLIENT_NAME,
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


def _parse_liste(werte):
    return [w.strip() for w in (werte or "").split(";") if w.strip()]


def _parse_mapping(werte):
    """'Erdgeschoss=EG;1. OG=01' -> dict"""
    mapping = {}
    for pair in (werte or "").split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            mapping[k.strip()] = v.strip()
    return mapping


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
        mapping = _parse_mapping(feld.get("werte"))
        if val.strip() in mapping:
            return mapping[val.strip()], None
        return "", u"Wert '{}' nicht in Mapping-Tabelle".format(val.strip())

    return "", u"Unbekannte Quelle '{}'".format(quelle)


def validiere(wert, feld):
    """Wert gegen Typ (liste/regex) und Laenge pruefen. Liefert Fehlerliste."""
    fehler = []
    typ = feld.get("typ", "freitext")
    laenge = int(feld.get("laenge") or 0)

    if not wert:
        if feld.get("quelle") != "auto":
            fehler.append(u"Feld '{}' ist leer".format(feld.get("id")))
        return fehler

    if typ == "liste":
        erlaubt = _parse_liste(feld.get("werte"))
        if erlaubt and wert not in erlaubt:
            fehler.append(u"'{}' nicht in Werteliste ({})".format(
                wert, ";".join(erlaubt)))
    elif typ == "regex":
        muster = feld.get("werte") or ""
        if muster:
            try:
                if not re.match(muster, wert):
                    fehler.append(u"'{}' verletzt Muster {}".format(wert, muster))
            except re.error:
                fehler.append(u"Ungueltiges Regex-Muster: {}".format(muster))

    if laenge > 0 and len(wert) > laenge and feld.get("padding") != "nullen":
        fehler.append(u"'{}' laenger als {} Zeichen".format(wert, laenge))

    return fehler


def formatiere(wert, feld):
    """Padding/Kuerzung anwenden."""
    laenge = int(feld.get("laenge") or 0)
    wert = wert or ""
    if laenge > 0:
        if feld.get("padding") == "nullen":
            wert = wert.rjust(laenge, "0")[-laenge:]
    return wert


def _sortkey(sheet):
    """Stabile, naturnahe Sortierung nach aktueller Plannummer."""
    num = sheet.SheetNumber or ""
    teile = re.split(r"(\d+)", num)
    return [int(t) if t.isdigit() else t.lower() for t in teile]


def alle_sheets(doc, nur_ids=None):
    sheets = list(FilteredElementCollector(doc)
                  .OfClass(ViewSheet)
                  .WhereElementIsNotElementType())
    sheets = [s for s in sheets if not s.IsPlaceholder]
    if nur_ids is not None:
        idset = set(nur_ids)
        sheets = [s for s in sheets if s.Id in idset]
    return sorted(sheets, key=_sortkey)


def baue_codes(doc, config, sheets=None):
    """
    Kernfunktion: baut fuer alle Sheets den Zielcode.
    Liefert Liste von dicts:
      {sheet, alt, neu, fehler(list), feldwerte(dict)}
    Laufnummern werden je Zaehlgruppe fortlaufend vergeben.
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
                fehler.extend(validiere(wert, feld))
                wert = formatiere(wert, feld)
            feldwerte[feld.get("id")] = wert
        ergebnisse.append({
            "sheet": sheet,
            "alt": sheet.SheetNumber,
            "neu": None,
            "fehler": fehler,
            "feldwerte": feldwerte,
        })

    # Laufnummern je Zaehlgruppe vergeben
    zaehler = {}
    for erg in ergebnisse:
        for feld in felder:
            if feld.get("quelle") != "auto":
                continue
            gruppe = _parse_liste(feld.get("zaehlgruppe"))
            key = (feld.get("id"),) + tuple(
                erg["feldwerte"].get(g, "") for g in gruppe)
            zaehler[key] = zaehler.get(key, 0) + 1
            wert = str(zaehler[key])
            erg["feldwerte"][feld.get("id")] = formatiere(wert, feld)

    # Codes zusammensetzen
    for erg in ergebnisse:
        teile = [erg["feldwerte"].get(f.get("id"), "") for f in felder]
        erg["neu"] = sep.join(teile)

    # Duplikate im Ergebnis markieren (z. B. bei Fehlern/Leerwerten)
    gesehen = {}
    for erg in ergebnisse:
        gesehen.setdefault(erg["neu"], []).append(erg)
    for code, gruppe in gesehen.items():
        if len(gruppe) > 1:
            for erg in gruppe:
                erg["fehler"].append(u"Zielnummer '{}' mehrfach vergeben".format(code))

    return ergebnisse


def pruefe_konfiguration(config):
    """Konfiguration selbst auf Konsistenz pruefen. Liefert Fehlerliste."""
    fehler = []
    felder = config.get("felder", [])
    if not felder:
        fehler.append(u"Keine Felder definiert.")
    ids = [f.get("id") for f in felder]
    for i in ids:
        if not i:
            fehler.append(u"Feld ohne ID vorhanden.")
    if len(set(ids)) != len(ids):
        fehler.append(u"Feld-IDs sind nicht eindeutig.")
    for f in felder:
        q = f.get("quelle")
        if q not in QUELLEN:
            fehler.append(u"Feld '{}': unbekannte Quelle '{}'".format(f.get("id"), q))
        if q in ("sheet_parameter", "projektinfo", "mapping") and not f.get("parameter"):
            fehler.append(u"Feld '{}': Parametername fehlt.".format(f.get("id")))
        if q == "auto":
            for g in _parse_liste(f.get("zaehlgruppe")):
                if g not in ids:
                    fehler.append(u"Feld '{}': Zaehlgruppe verweist auf unbekannte Feld-ID '{}'".format(f.get("id"), g))
        if f.get("typ") == "regex" and f.get("werte"):
            try:
                re.compile(f.get("werte"))
            except re.error:
                fehler.append(u"Feld '{}': ungueltiges Regex-Muster.".format(f.get("id")))
    return fehler
