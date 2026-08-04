# -*- coding: utf-8 -*-
"""Sheet-Parameter befuellen

Setzt einen Codierungs-Parameter fuer ausgewaehlte Plaene -
mit Auswahl aus genau den im Schema erlaubten Werten."""
__title__ = "Befüllen"
__author__ = "SAUERWEIN ENERGY"

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

from plancode import config_store, interpreter

doc = revit.doc

config, _ = config_store.load_config(doc)

# Nur Felder anbieten, die aus einem Sheet-Parameter gespeist werden
felder = [f for f in config.get("felder", [])
          if f.get("quelle") in ("sheet_parameter", "mapping")
          and f.get("parameter")]
if not felder:
    forms.alert("Das Schema enthaelt keine Sheet-Parameter-Felder.")
    script.exit()

feld_wahl = forms.SelectFromList.show(
    ["{}  ({})".format(f["id"], f["parameter"]) for f in felder],
    title="Welches Feld befuellen?", multiselect=False)
if not feld_wahl:
    script.exit()
feld = felder[["{}  ({})".format(f["id"], f["parameter"])
               for f in felder].index(feld_wahl)]

# Plaene waehlen
sheets = forms.select_sheets(title="Plaene auswaehlen", use_selection=True)
if not sheets:
    script.exit()

# Wert bestimmen: Liste -> Auswahl, sonst Freitext
if feld.get("typ") == "liste" and feld.get("werte"):
    optionen = [w.strip() for w in feld["werte"].split(";") if w.strip()]
    wert = forms.SelectFromList.show(
        optionen, title="Wert fuer '{}'".format(feld["parameter"]),
        multiselect=False)
elif feld.get("quelle") == "mapping" and feld.get("werte"):
    # Beim Mapping wird der ROHWERT (linke Seite) gesetzt
    optionen = [p.split("=", 1)[0].strip()
                for p in feld["werte"].split(";") if "=" in p]
    wert = forms.SelectFromList.show(
        optionen, title="Rohwert fuer '{}'".format(feld["parameter"]),
        multiselect=False)
else:
    wert = forms.ask_for_string(
        prompt="Wert fuer '{}':".format(feld["parameter"]),
        title="Plancodierung")

if wert is None:
    script.exit()

fehlend = []
t = Transaction(doc, "Plancodierung: Parameter befuellen")
t.Start()
try:
    for sheet in sheets:
        p = sheet.LookupParameter(feld["parameter"])
        if p is None or p.IsReadOnly:
            fehlend.append(sheet.Name)
            continue
        p.Set(wert)
    t.Commit()
except Exception as ex:
    t.RollBack()
    forms.alert("Fehler, keine Aenderungen geschrieben:\n{}".format(ex))
    script.exit()

msg = "'{}' = '{}' fuer {} Plaene gesetzt.".format(
    feld["parameter"], wert, len(sheets) - len(fehlend))
if fehlend:
    msg += ("\n\nParameter fehlt/schreibgeschuetzt bei:\n- " +
            "\n- ".join(fehlend) +
            "\n\nHinweis: Shared Parameter muss an die Kategorie "
            "'Plaene' gebunden sein.")
forms.alert(msg)
