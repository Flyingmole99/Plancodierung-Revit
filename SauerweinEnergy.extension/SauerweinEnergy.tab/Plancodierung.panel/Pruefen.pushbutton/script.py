# -*- coding: utf-8 -*-
"""Plancodierung pruefen (Dry-Run)

Zeigt fuer alle Plaene die Zielnummer nach aktuellem Schema an,
ohne etwas zu aendern. Fehler werden markiert.

Shift+Klick: exportiert die Tabelle zusaetzlich als CSV
(z. B. als Konformitaetsnachweis fuer BAP-Pruefungen)."""
__title__ = "Prüfen"
__author__ = "SAUERWEIN ENERGY"
__context__ = "doc-project"

import io

from pyrevit import forms, revit, script, EXEC_PARAMS

from plancode import config_store, interpreter, logik

doc = revit.doc
output = script.get_output()

config, status = config_store.load_config(doc)
if status == config_store.GELADEN_LESEFEHLER:
    forms.alert(
        "Die im Projekt gespeicherte Konfiguration konnte nicht gelesen "
        "werden (beschaedigt?).\n"
        "Bitte zuerst ueber 'Konfigurieren' pruefen und neu speichern.")
    script.exit()
if status == config_store.GELADEN_STANDARD:
    forms.alert("Im Projekt ist noch kein Schema gespeichert - "
                "es wird das Standardschema verwendet.\n"
                "Ueber 'Konfigurieren' kannst du es anpassen und speichern.")

konfig_fehler = logik.pruefe_konfiguration(config)
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
csv_zeilen = []
fehleranzahl = 0
unveraendert = 0
for erg in ergebnisse:
    if erg["fehler"]:
        fehleranzahl += 1
        status_text = ":warning: " + "; ".join(erg["fehler"])
        csv_status = "FEHLER: " + "; ".join(erg["fehler"])
    elif erg["alt"] == erg["neu"]:
        unveraendert += 1
        status_text = "unverändert"
        csv_status = "unveraendert"
    else:
        status_text = "wird geändert"
        csv_status = "wird geaendert"
    zeilen.append([
        output.linkify(erg["sheet"].Id),
        erg["sheet"].Name,
        erg["alt"],
        erg["neu"],
        status_text,
    ])
    csv_zeilen.append([erg["alt"], erg["neu"], erg["sheet"].Name, csv_status])

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

# ------------------------------------------------- CSV-Export (Shift+Klick)
if EXEC_PARAMS.config_mode:
    pfad = forms.save_file(file_ext="csv")
    if pfad:
        def _feld(text):
            return (text or u"").replace(u";", u",").replace(u"\n", u" ")
        try:
            # utf-8-sig, damit Excel Umlaute korrekt erkennt
            with io.open(pfad, "w", encoding="utf-8-sig") as f:
                f.write(u"Aktuelle Nummer;Zielnummer;Planname;Status\n")
                for z in csv_zeilen:
                    f.write(u";".join(_feld(t) for t in z) + u"\n")
            output.print_md("CSV exportiert: `{}`".format(pfad))
        except Exception as ex:
            forms.alert("CSV-Export fehlgeschlagen:\n{}".format(ex))
