# -*- coding: utf-8 -*-
"""Plancodierung pruefen (Dry-Run)

Zeigt fuer alle Plaene die Zielnummer nach aktuellem Schema an,
ohne etwas zu aendern. Fehler werden markiert."""
__title__ = "Prüfen"
__author__ = "SAUERWEIN ENERGY"

from pyrevit import forms, revit, script

from plancode import config_store, interpreter

doc = revit.doc
output = script.get_output()

config, gespeichert = config_store.load_config(doc)
if not gespeichert:
    forms.alert("Im Projekt ist noch kein Schema gespeichert - "
                "es wird das Standardschema verwendet.\n"
                "Ueber 'Konfigurieren' kannst du es anpassen und speichern.")

konfig_fehler = interpreter.pruefe_konfiguration(config)
if konfig_fehler:
    forms.alert("Konfiguration fehlerhaft:\n\n- " + "\n- ".join(konfig_fehler))
    script.exit()

ergebnisse = interpreter.baue_codes(doc, config)
if not ergebnisse:
    forms.alert("Keine Plaene im Projekt vorhanden.")
    script.exit()

output.print_md("# Plancodierung – Prüfung (Dry-Run)")
output.print_md("**Schema:** {} &nbsp;&nbsp; **Trennzeichen:** `{}` "
                "&nbsp;&nbsp; **Pläne:** {}".format(
                    config.get("schema_name", "?"),
                    config.get("separator", "-"),
                    len(ergebnisse)))

zeilen = []
fehleranzahl = 0
unveraendert = 0
for erg in ergebnisse:
    if erg["fehler"]:
        fehleranzahl += 1
        status = ":warning: " + "; ".join(erg["fehler"])
    elif erg["alt"] == erg["neu"]:
        unveraendert += 1
        status = "unverändert"
    else:
        status = "wird geändert"
    zeilen.append([
        output.linkify(erg["sheet"].Id),
        erg["sheet"].Name,
        erg["alt"],
        erg["neu"],
        status,
    ])

output.print_table(
    table_data=zeilen,
    columns=["Plan", "Name", "Aktuell", "Ziel", "Status"],
    title="")

output.print_md("---")
output.print_md("**Ergebnis:** {} Pläne | {} unverändert | {} mit Fehlern".format(
    len(ergebnisse), unveraendert, fehleranzahl))
if fehleranzahl:
    output.print_md(":warning: **Pläne mit Fehlern werden beim Anwenden "
                    "übersprungen.** Fehlende Parameterwerte über den Button "
                    "*Befüllen* oder das Eigenschaftenfenster ergänzen.")
