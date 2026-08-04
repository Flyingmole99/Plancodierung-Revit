# -*- coding: utf-8 -*-
"""Sheet-Parameter befuellen

Setzt einen oder mehrere Codierungs-Parameter fuer ausgewaehlte
Plaene - mit Auswahl aus genau den im Schema erlaubten Werten."""
__title__ = "Befüllen"
__author__ = "SAUERWEIN ENERGY"
__context__ = "doc-project"

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction, StorageType

from plancode import config_store, logik

doc = revit.doc

config, status = config_store.load_config(doc)
if status == config_store.GELADEN_LESEFEHLER:
    forms.alert(
        "Die im Projekt gespeicherte Konfiguration konnte nicht gelesen "
        "werden (beschaedigt?).\n"
        "Bitte zuerst ueber 'Konfigurieren' pruefen und neu speichern.")
    script.exit()

# Nur Felder anbieten, die aus einem Sheet-Parameter gespeist werden
felder = [f for f in config.get("felder", [])
          if f.get("quelle") in ("sheet_parameter", "mapping")
          and f.get("parameter")]
if not felder:
    forms.alert("Das Schema enthaelt keine Sheet-Parameter-Felder.")
    script.exit()

# Zuerst die Plaene waehlen - dann kann die Feldliste anzeigen,
# wo noch Werte fehlen
sheets = forms.select_sheets(title="Plaene auswaehlen", use_selection=True)
if not sheets:
    script.exit()
sheets = [s for s in sheets if not s.IsPlaceholder]
if not sheets:
    forms.alert("Nur Platzhalter-Plaene gewaehlt - nichts zu tun.")
    script.exit()


def _leere_anzahl(feld):
    n = 0
    for s in sheets:
        p = s.LookupParameter(feld["parameter"])
        if p is None or not (p.AsString() or "").strip():
            n += 1
    return n


beschriftungen = []
for f in felder:
    leer = _leere_anzahl(f)
    text = u"{}  ({})".format(f["id"], f["parameter"])
    if leer:
        text += u"  –  {} von {} leer".format(leer, len(sheets))
    beschriftungen.append(text)

feld_wahl = forms.SelectFromList.show(
    beschriftungen,
    title="Welche Felder befuellen? ({} Plaene)".format(len(sheets)),
    multiselect=True)
if not feld_wahl:
    script.exit()
gewaehlte_felder = [felder[beschriftungen.index(w)] for w in feld_wahl]

# Werte je Feld abfragen (Abbrechen ueberspringt das jeweilige Feld)
werte_plan = []  # (feld, wert)
uebersprungene_felder = []
for feld in gewaehlte_felder:
    if feld.get("typ") == "liste" and feld.get("werte"):
        optionen = logik.parse_liste(feld["werte"])
        wert = forms.SelectFromList.show(
            optionen, title="Wert fuer '{}'".format(feld["parameter"]),
            multiselect=False)
    elif feld.get("quelle") == "mapping" and feld.get("werte"):
        # Beim Mapping wird der ROHWERT (linke Seite) gesetzt
        optionen = sorted(logik.parse_mapping(feld["werte"]).keys())
        wert = forms.SelectFromList.show(
            optionen, title="Rohwert fuer '{}'".format(feld["parameter"]),
            multiselect=False)
    else:
        wert = forms.ask_for_string(
            prompt="Wert fuer '{}':".format(feld["parameter"]),
            title="Plancodierung")
    if wert is None:
        uebersprungene_felder.append(feld["parameter"])
        continue
    werte_plan.append((feld, wert))

if not werte_plan:
    script.exit()

probleme = []  # (plan, parameter, grund)
gesetzt = 0
t = Transaction(doc, "Plancodierung: Parameter befuellen")
t.Start()
try:
    for sheet in sheets:
        for feld, wert in werte_plan:
            p = sheet.LookupParameter(feld["parameter"])
            if p is None:
                probleme.append((sheet, feld["parameter"],
                                 "Parameter fehlt"))
                continue
            if p.IsReadOnly:
                probleme.append((sheet, feld["parameter"],
                                 "schreibgeschuetzt"))
                continue
            if p.StorageType != StorageType.String:
                probleme.append((sheet, feld["parameter"],
                                 "kein Text-Parameter"))
                continue
            p.Set(wert)
            gesetzt += 1
    t.Commit()
except Exception as ex:
    t.RollBack()
    forms.alert("Fehler, keine Aenderungen geschrieben:\n{}".format(ex))
    script.exit()

msg = "{} Werte auf {} Plaenen gesetzt:\n".format(gesetzt, len(sheets))
for feld, wert in werte_plan:
    msg += "\n  {} = '{}'".format(feld["parameter"], wert)
if uebersprungene_felder:
    msg += "\n\nOhne Wert uebersprungen: " + ", ".join(uebersprungene_felder)
if probleme:
    msg += "\n\nNicht gesetzt:"
    for sheet, pname, grund in probleme[:15]:
        msg += "\n- {} / {}: {}".format(sheet.SheetNumber, pname, grund)
    if len(probleme) > 15:
        msg += "\n- ... und {} weitere".format(len(probleme) - 15)
    msg += ("\n\nHinweis: Shared Parameter muss als TEXT-Parameter an die "
            "Kategorie 'Plaene' gebunden sein.")
forms.alert(msg)
