# -*- coding: utf-8 -*-
"""Plancodierung anwenden

Schreibt die Plannummern nach dem im Projekt gespeicherten Schema.
Plaene mit Validierungsfehlern werden uebersprungen."""
__title__ = "Anwenden"
__author__ = "SAUERWEIN ENERGY"

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

from plancode import config_store, interpreter

doc = revit.doc
output = script.get_output()

config, gespeichert = config_store.load_config(doc)
if not gespeichert:
    if not forms.alert(
            "Im Projekt ist kein Schema gespeichert.\n"
            "Standardschema verwenden?", yes=True, no=True):
        script.exit()

konfig_fehler = interpreter.pruefe_konfiguration(config)
if konfig_fehler:
    forms.alert("Konfiguration fehlerhaft:\n\n- " + "\n- ".join(konfig_fehler))
    script.exit()

ergebnisse = interpreter.baue_codes(doc, config)
if not ergebnisse:
    forms.alert("Keine Plaene im Projekt vorhanden.")
    script.exit()

aenderungen = [e for e in ergebnisse
               if not e["fehler"] and e["alt"] != e["neu"]]
uebersprungen = [e for e in ergebnisse if e["fehler"]]

if not aenderungen:
    forms.alert("Alle Plannummern sind bereits aktuell.{}".format(
        "\n({} Plaene mit Fehlern - siehe 'Pruefen')".format(len(uebersprungen))
        if uebersprungen else ""))
    script.exit()

if not forms.alert(
        "{} Plannummern werden geaendert.\n"
        "{} Plaene werden wegen Fehlern uebersprungen.\n\n"
        "Fortfahren?".format(len(aenderungen), len(uebersprungen)),
        yes=True, no=True):
    script.exit()

# Zwei-Pass-Verfahren: erst temporaere Nummern, dann Zielnummern.
# Verhindert Kollisionen, wenn Ziel A der alten Nummer von B entspricht.
fehlgeschlagen = []
t = Transaction(doc, "Plancodierung anwenden")
t.Start()
try:
    for i, erg in enumerate(aenderungen):
        erg["sheet"].SheetNumber = u"__TMP_{}__".format(i)
    for erg in aenderungen:
        try:
            erg["sheet"].SheetNumber = erg["neu"]
        except Exception as ex:
            # Kollision mit nicht verwaltetem Plan o. ae.
            erg["sheet"].SheetNumber = erg["alt"]
            fehlgeschlagen.append((erg, str(ex)))
    t.Commit()
except Exception as ex:
    t.RollBack()
    forms.alert("Abbruch, keine Aenderungen geschrieben:\n{}".format(ex))
    script.exit()

output.print_md("# Plancodierung – Ergebnis")
fehl_set = set(id(f[0]) for f in fehlgeschlagen)
zeilen = [[output.linkify(e["sheet"].Id), e["sheet"].Name, e["alt"], e["neu"]]
          for e in aenderungen if id(e) not in fehl_set]
output.print_table(table_data=zeilen,
                   columns=["Plan", "Name", "Alt", "Neu"],
                   title="Geänderte Pläne")

if fehlgeschlagen:
    output.print_md("## :warning: Nicht geschrieben (Kollision)")
    output.print_table(
        table_data=[[f[0]["sheet"].Name, f[0]["neu"], f[1]]
                    for f in fehlgeschlagen],
        columns=["Plan", "Zielnummer", "Fehler"], title="")

if uebersprungen:
    output.print_md("## Übersprungen (Validierungsfehler)")
    output.print_table(
        table_data=[[e["sheet"].Name, e["alt"], "; ".join(e["fehler"])]
                    for e in uebersprungen],
        columns=["Plan", "Aktuell", "Fehler"], title="")

output.print_md("---")
output.print_md("**{} geändert, {} fehlgeschlagen, {} übersprungen.**".format(
    len(aenderungen) - len(fehlgeschlagen),
    len(fehlgeschlagen), len(uebersprungen)))
