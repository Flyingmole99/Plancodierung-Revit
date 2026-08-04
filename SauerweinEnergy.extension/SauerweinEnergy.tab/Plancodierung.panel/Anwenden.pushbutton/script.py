# -*- coding: utf-8 -*-
"""Plancodierung anwenden

Schreibt die Plannummern nach dem im Projekt gespeicherten Schema.
Bestehende Laufnummern bleiben erhalten (sticky), neue Plaene erhalten
die naechste freie Nummer. Plaene mit Validierungsfehlern werden
uebersprungen."""
__title__ = "Anwenden"
__author__ = "SAUERWEIN ENERGY"
__context__ = "doc-project"

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction, WorksharingUtils, CheckoutStatus

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
    if not forms.alert(
            "Im Projekt ist kein Schema gespeichert.\n"
            "Standardschema verwenden?", yes=True, no=True):
        script.exit()

konfig_fehler = logik.pruefe_konfiguration(config)
if konfig_fehler:
    forms.alert("Konfiguration fehlerhaft:\n\n- " + "\n- ".join(konfig_fehler))
    script.exit()

# ------------------------------------------------------- Umfang und Modus
antwort = forms.CommandSwitchWindow.show(
    ["Alle Pläne", "Pläne auswählen…"],
    switches=["Laufnummern komplett neu vergeben"],
    message="Plancodierung anwenden auf:")
if isinstance(antwort, tuple):
    umfang, schalter = antwort
else:
    umfang, schalter = antwort, {}
if not umfang:
    script.exit()

modus = "neu" if schalter.get("Laufnummern komplett neu vergeben") else "beibehalten"
if modus == "neu" and umfang != "Alle Pläne":
    forms.alert("Die komplette Neuvergabe nummeriert immer ALLE Plaene - "
                "die Auswahl wird ignoriert.")
    umfang = "Alle Pläne"

auswahl_ids = None
if umfang != "Alle Pläne":
    gewaehlt = forms.select_sheets(title="Plaene auswaehlen",
                                   use_selection=True)
    if not gewaehlt:
        script.exit()
    auswahl_ids = set(s.Id for s in gewaehlt if not s.IsPlaceholder)
    if not auswahl_ids:
        script.exit()

# Laufnummern werden IMMER ueber den Gesamtbestand gerechnet, damit die
# Zaehler stimmen - angewendet wird danach ggf. nur auf die Auswahl.
ergebnisse = interpreter.baue_codes(doc, config, modus=modus)
if not ergebnisse:
    forms.alert("Keine Plaene im Projekt vorhanden.")
    script.exit()

im_umfang = [e for e in ergebnisse
             if auswahl_ids is None or e["sheet"].Id in auswahl_ids]
aenderungen = [e for e in im_umfang
               if not e["fehler"] and e["alt"] != e["neu"]]
uebersprungen = [e for e in im_umfang if e["fehler"]]

# Bei Teilanwendung: Zielnummern duerfen nicht mit Nummern von Plaenen
# kollidieren, die ausserhalb der Auswahl liegen (und daher nicht mitziehen)
vorab_fehl = []
if auswahl_ids is not None:
    nummern_aussen = {}
    for s in interpreter.alle_sheets(doc, mit_platzhaltern=True):
        if s.Id not in auswahl_ids:
            nummern_aussen[s.SheetNumber] = s.Name
    for e in list(aenderungen):
        if e["neu"] in nummern_aussen:
            aenderungen.remove(e)
            vorab_fehl.append((e, u"Zielnummer belegt durch Plan '{}' "
                               u"ausserhalb der Auswahl - Plan mitwaehlen "
                               u"oder auf alle Plaene anwenden".format(
                                   nummern_aussen[e["neu"]])))

# Worksharing: Plaene, die ein anderer Bearbeiter besitzt, vorab aussortieren
if doc.IsWorkshared:
    for e in list(aenderungen):
        try:
            st = WorksharingUtils.GetCheckoutStatus(doc, e["sheet"].Id)
        except Exception:
            continue
        if st == CheckoutStatus.OwnedByOtherUser:
            aenderungen.remove(e)
            vorab_fehl.append((e, u"Plan ist von einem anderen Bearbeiter "
                               u"belegt - erst synchronisieren"))

if not aenderungen:
    hinweise = []
    if uebersprungen:
        hinweise.append("{} Plaene mit Fehlern - siehe 'Pruefen'".format(
            len(uebersprungen)))
    if vorab_fehl:
        hinweise.append("{} Plaene nicht anwendbar (Kollision/belegt)".format(
            len(vorab_fehl)))
    forms.alert("Keine Plannummern zu aendern.{}".format(
        "\n(" + "; ".join(hinweise) + ")" if hinweise else ""))
    script.exit()

if not forms.alert(
        "{} Plannummern werden geaendert ({}).\n"
        "{} Plaene werden wegen Fehlern uebersprungen.\n"
        "{} Plaene sind nicht anwendbar (Kollision/belegt).\n\n"
        "Fortfahren?".format(
            len(aenderungen),
            "Laufnummern-Neuvergabe" if modus == "neu"
            else "bestehende Laufnummern bleiben erhalten",
            len(uebersprungen), len(vorab_fehl)),
        yes=True, no=True):
    script.exit()

# Zwei-Pass-Verfahren: erst temporaere Nummern, dann Zielnummern.
# Verhindert Kollisionen, wenn Ziel A der alten Nummer von B entspricht.
fehlgeschlagen = []       # (erg, meldung) - zurueckgesetzt auf alte Nummer
haengengeblieben = []     # (erg, meldung) - steht noch auf TMP-Nummer!
state_fehler = 0

t = Transaction(doc, "Plancodierung anwenden")
t.Start()
try:
    for i, erg in enumerate(aenderungen):
        erg["sheet"].SheetNumber = u"__PLANCODE_TMP_{}__".format(i)
    for erg in aenderungen:
        try:
            erg["sheet"].SheetNumber = erg["neu"]
        except Exception as ex:
            # Kollision mit nicht verwaltetem Plan o. ae. - zuruecksetzen,
            # und wenn selbst das scheitert, NICHT die ganze Transaction
            # reissen, sondern den Plan im Bericht ausweisen
            try:
                erg["sheet"].SheetNumber = erg["alt"]
                fehlgeschlagen.append((erg, str(ex)))
            except Exception:
                haengengeblieben.append((erg, str(ex)))

    # Laufnummern-Status persistieren: fuer erfolgreich angewendete Plaene
    # und fuer fehlerfreie Plaene, deren Nummer bereits stimmt
    problem_ids = set(id(f[0]) for f in fehlgeschlagen + haengengeblieben)
    for erg in ergebnisse:
        if erg["fehler"] or not erg["state_neu"]:
            continue
        angewendet = (id(erg) not in problem_ids
                      and (erg["alt"] == erg["neu"]
                           or any(erg is a for a in aenderungen)))
        if not angewendet:
            continue
        try:
            config_store.schreibe_sheet_state(erg["sheet"], erg["state_neu"])
        except Exception:
            state_fehler += 1
    t.Commit()
except Exception as ex:
    t.RollBack()
    forms.alert("Abbruch, keine Aenderungen geschrieben:\n{}".format(ex))
    script.exit()

# ------------------------------------------------------------- Bericht
output.print_md("# Plancodierung – Ergebnis")
problem_ids = set(id(f[0]) for f in fehlgeschlagen + haengengeblieben)
zeilen = [[output.linkify(e["sheet"].Id), e["sheet"].Name, e["alt"], e["neu"]]
          for e in aenderungen if id(e) not in problem_ids]
if zeilen:
    output.print_table(table_data=zeilen,
                       columns=["Plan", "Name", "Alt", "Neu"],
                       title="Geänderte Pläne")

if haengengeblieben:
    output.print_md("## :cross_mark: Plaene stehen auf temporaerer Nummer!")
    output.print_md("Zielnummer UND alte Nummer waren belegt. Bitte manuell "
                    "korrigieren oder Strg+Z und Konflikt beheben.")
    output.print_table(
        table_data=[[output.linkify(f[0]["sheet"].Id), f[0]["sheet"].Name,
                     f[0]["alt"], f[0]["neu"], f[1]]
                    for f in haengengeblieben],
        columns=["Plan", "Name", "Alte Nummer", "Zielnummer", "Fehler"],
        title="")

if fehlgeschlagen:
    output.print_md("## :warning: Nicht geschrieben (Kollision)")
    output.print_table(
        table_data=[[f[0]["sheet"].Name, f[0]["neu"], f[1]]
                    for f in fehlgeschlagen],
        columns=["Plan", "Zielnummer", "Fehler"], title="")

if vorab_fehl:
    output.print_md("## Nicht anwendbar")
    output.print_table(
        table_data=[[v[0]["sheet"].Name, v[0]["neu"], v[1]]
                    for v in vorab_fehl],
        columns=["Plan", "Zielnummer", "Grund"], title="")

if uebersprungen:
    output.print_md("## Übersprungen (Validierungsfehler)")
    output.print_table(
        table_data=[[e["sheet"].Name, e["alt"], "; ".join(e["fehler"])]
                    for e in uebersprungen],
        columns=["Plan", "Aktuell", "Fehler"], title="")

output.print_md("---")
output.print_md("**{} geändert, {} fehlgeschlagen, {} übersprungen, "
                "{} nicht anwendbar.**".format(
                    len(aenderungen) - len(fehlgeschlagen) - len(haengengeblieben),
                    len(fehlgeschlagen) + len(haengengeblieben),
                    len(uebersprungen), len(vorab_fehl)))
if state_fehler:
    output.print_md(":warning: Laufnummern-Status von {} Plaenen konnte "
                    "nicht gespeichert werden (z. B. von anderem Bearbeiter "
                    "belegt) - wird beim naechsten Anwenden erneut "
                    "versucht.".format(state_fehler))
output.print_md("Rueckgaengig: Strg+Z (eine Transaction).")
