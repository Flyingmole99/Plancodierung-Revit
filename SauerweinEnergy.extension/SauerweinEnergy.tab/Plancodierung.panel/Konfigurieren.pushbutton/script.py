# -*- coding: utf-8 -*-
"""Plancodierung konfigurieren

Definiert das Codierungsschema (Felder, Laengen, erlaubte Inhalte)
direkt in Revit. Die Konfiguration wird im Projekt gespeichert."""
__title__ = "Konfigurieren"
__author__ = "SAUERWEIN ENERGY"

import io
import os

from pyrevit import forms, revit, script

from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs

from plancode import config_store, interpreter

doc = revit.doc
logger = script.get_logger()


# ---------------------------------------------------------------- Zeilenmodell
class FeldZeile(INotifyPropertyChanged):
    """Eine Zeile im DataGrid mit Property-Change-Benachrichtigung."""

    def __init__(self, feld=None):
        self._handlers = []
        feld = feld or {}
        self._werte = {
            "FeldID": feld.get("id", ""),
            "Quelle": feld.get("quelle", "sheet_parameter"),
            "Parameter": feld.get("parameter", ""),
            "Laenge": str(feld.get("laenge", 0)),
            "Typ": feld.get("typ", "freitext"),
            "Werte": feld.get("werte", ""),
            "Padding": feld.get("padding", "keins"),
            "Zaehlgruppe": feld.get("zaehlgruppe", ""),
        }

    # INotifyPropertyChanged (IronPython-Implementierung)
    def add_PropertyChanged(self, handler):
        self._handlers.append(handler)

    def remove_PropertyChanged(self, handler):
        if handler in self._handlers:
            self._handlers.remove(handler)

    def _notify(self, name):
        for h in self._handlers:
            h(self, PropertyChangedEventArgs(name))

    def _get(self, key):
        return self._werte[key]

    def _set(self, key, value):
        self._werte[key] = value or ""
        self._notify(key)

    FeldID = property(lambda s: s._get("FeldID"), lambda s, v: s._set("FeldID", v))
    Quelle = property(lambda s: s._get("Quelle"), lambda s, v: s._set("Quelle", v))
    Parameter = property(lambda s: s._get("Parameter"), lambda s, v: s._set("Parameter", v))
    Laenge = property(lambda s: s._get("Laenge"), lambda s, v: s._set("Laenge", v))
    Typ = property(lambda s: s._get("Typ"), lambda s, v: s._set("Typ", v))
    Werte = property(lambda s: s._get("Werte"), lambda s, v: s._set("Werte", v))
    Padding = property(lambda s: s._get("Padding"), lambda s, v: s._set("Padding", v))
    Zaehlgruppe = property(lambda s: s._get("Zaehlgruppe"), lambda s, v: s._set("Zaehlgruppe", v))

    def als_feld(self):
        try:
            laenge = int(self._werte["Laenge"] or 0)
        except ValueError:
            laenge = 0
        return {
            "id": self._werte["FeldID"].strip(),
            "quelle": self._werte["Quelle"],
            "parameter": self._werte["Parameter"].strip(),
            "laenge": laenge,
            "typ": self._werte["Typ"],
            "werte": self._werte["Werte"].strip(),
            "padding": self._werte["Padding"],
            "zaehlgruppe": self._werte["Zaehlgruppe"].strip(),
        }


# ---------------------------------------------------------------- Dialog
class ConfigDialog(forms.WPFWindow):

    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(
            os.path.dirname(__file__), "ConfigDialog.xaml"))

        config, _ = config_store.load_config(doc)
        self._lade_config(config)

        self.btnNeu.Click += self._neu
        self.btnLoeschen.Click += self._loeschen
        self.btnHoch.Click += lambda s, e: self._verschiebe(-1)
        self.btnRunter.Click += lambda s, e: self._verschiebe(1)
        self.btnParams.Click += self._zeige_parameter
        self.btnImport.Click += self._import
        self.btnExport.Click += self._export
        self.btnStandard.Click += self._standard
        self.btnVorschau.Click += lambda s, e: self._vorschau()
        self.btnSpeichern.Click += self._speichern
        self.btnAbbrechen.Click += lambda s, e: self.Close()

        self._vorschau()

    # ------------------------------------------------------------ Daten
    def _lade_config(self, config):
        self.txtSchemaName.Text = config.get("schema_name", "")
        self.txtSeparator.Text = config.get("separator", "-")
        self.zeilen = ObservableCollection[object]()
        for feld in config.get("felder", []):
            self.zeilen.Add(FeldZeile(feld))
        self.gridFelder.ItemsSource = self.zeilen

    def _aktuelle_config(self):
        return {
            "schema_name": self.txtSchemaName.Text.strip() or "Ohne Namen",
            "separator": self.txtSeparator.Text,
            "felder": [z.als_feld() for z in self.zeilen],
        }

    # ------------------------------------------------------------ Buttons
    def _neu(self, sender, args):
        self.zeilen.Add(FeldZeile({"id": "feld{}".format(self.zeilen.Count + 1)}))

    def _loeschen(self, sender, args):
        zeile = self.gridFelder.SelectedItem
        if zeile is not None:
            self.zeilen.Remove(zeile)

    def _verschiebe(self, richtung):
        idx = self.gridFelder.SelectedIndex
        neu = idx + richtung
        if idx < 0 or neu < 0 or neu >= self.zeilen.Count:
            return
        self.zeilen.Move(idx, neu)
        self.gridFelder.SelectedIndex = neu

    def _zeige_parameter(self, sender, args):
        """Alle am Sheet verfuegbaren Parameternamen anzeigen."""
        sheets = interpreter.alle_sheets(doc)
        if not sheets:
            forms.alert("Keine Plaene im Projekt vorhanden.")
            return
        namen = sorted(set(
            p.Definition.Name for p in sheets[0].Parameters))
        pinfo = sorted(set(
            p.Definition.Name for p in doc.ProjectInformation.Parameters))
        forms.alert(
            "Sheet-Parameter:\n{}\n\nProjektinfo-Parameter:\n{}".format(
                ", ".join(namen), ", ".join(pinfo)),
            title="Verfuegbare Parameter")

    def _import(self, sender, args):
        pfad = forms.pick_file(file_ext="json")
        if not pfad:
            return
        try:
            with io.open(pfad, "r", encoding="utf-8") as f:
                config = config_store.config_from_json(f.read())
            self._lade_config(config)
            self._vorschau()
        except Exception as ex:
            forms.alert("Vorlage konnte nicht geladen werden:\n{}".format(ex))

    def _export(self, sender, args):
        pfad = forms.save_file(file_ext="json")
        if not pfad:
            return
        try:
            with io.open(pfad, "w", encoding="utf-8") as f:
                f.write(config_store.config_to_json(self._aktuelle_config()))
            forms.alert("Vorlage gespeichert:\n{}".format(pfad))
        except Exception as ex:
            forms.alert("Export fehlgeschlagen:\n{}".format(ex))

    def _standard(self, sender, args):
        if forms.alert("Aktuelle Tabelle durch Standardschema ersetzen?",
                       yes=True, no=True):
            self._lade_config(config_store.DEFAULT_CONFIG)
            self._vorschau()

    # ------------------------------------------------------------ Vorschau
    def _vorschau(self):
        config = self._aktuelle_config()
        fehler = interpreter.pruefe_konfiguration(config)
        if fehler:
            self.lblVorschau.Text = "Vorschau: –"
            self.lblVorschauFehler.Text = "Konfiguration: " + " | ".join(fehler)
            return
        sheets = interpreter.alle_sheets(doc)
        if not sheets:
            self.lblVorschau.Text = "Vorschau: (keine Plaene im Projekt)"
            self.lblVorschauFehler.Text = ""
            return
        erg = interpreter.baue_codes(doc, config, sheets=sheets[:1])[0]
        self.lblVorschau.Text = u"Vorschau ({}):  {}  \u2192  {}".format(
            erg["sheet"].Name, erg["alt"], erg["neu"])
        self.lblVorschauFehler.Text = " | ".join(erg["fehler"])

    # ------------------------------------------------------------ Speichern
    def _speichern(self, sender, args):
        config = self._aktuelle_config()
        fehler = interpreter.pruefe_konfiguration(config)
        if fehler:
            forms.alert("Konfiguration unvollstaendig:\n\n- " +
                        "\n- ".join(fehler))
            return
        try:
            config_store.save_config(doc, config)
        except Exception as ex:
            forms.alert("Speichern fehlgeschlagen:\n{}".format(ex))
            return
        self.Close()


ConfigDialog().show_dialog()
