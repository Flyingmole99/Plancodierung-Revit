# -*- coding: utf-8 -*-
"""
Speichert und laedt die Plancodierungs-Konfiguration (am
ProjectInformation-Element) sowie den Laufnummern-Status je Plan
(am ViewSheet-Element) im Extensible Storage.
Kompatibel mit IronPython 2.7 (pyRevit-Standard-Engine).
"""
import json

from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.DB.ExtensibleStorage import (
    Schema, SchemaBuilder, AccessLevel, Entity
)
from System import Guid, String

# Feste GUIDs - niemals aendern, sonst finden bestehende Projekte ihre
# gespeicherte Konfiguration bzw. ihren Laufnummern-Status nicht mehr!
SCHEMA_GUID = Guid("a3f5c821-6b94-4e37-9d12-8f0e4b7c5a10")
SCHEMA_NAME = "SEPlancodierung"
FIELD_NAME = "PlancodeConfig"

STATE_GUID = Guid("5d1c9e47-8b2a-4f6e-b3d0-2a7c91e4f8b3")
STATE_SCHEMA_NAME = "SEPlancodierungStatus"
STATE_FIELD = "PlancodeStatus"

CONFIG_VERSION = 1

# Ladeergebnis-Status
GELADEN_GESPEICHERT = "gespeichert"   # Konfiguration aus dem Projekt
GELADEN_STANDARD = "standard"         # nichts gespeichert -> Standardschema
GELADEN_LESEFEHLER = "lesefehler"     # gespeicherte Daten nicht lesbar!

# Standardschema, wenn im Projekt noch nichts gespeichert ist
DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "schema_name": "Standard SAUERWEIN ENERGY",
    "separator": "-",
    "felder": [
        {
            "id": "projekt",
            "quelle": "projektinfo",
            "parameter": "Projektnummer",
            "laenge": 0,
            "typ": "freitext",
            "werte": "",
            "padding": "keins",
            "zaehlgruppe": ""
        },
        {
            "id": "gewerk",
            "quelle": "sheet_parameter",
            "parameter": "SE_Gewerk",
            "laenge": 3,
            "typ": "liste",
            "werte": "HZG;KAE;LUF;SAN;ELT;MSR;GA",
            "padding": "keins",
            "zaehlgruppe": ""
        },
        {
            "id": "geschoss",
            "quelle": "sheet_parameter",
            "parameter": "SE_Geschoss",
            "laenge": 2,
            "typ": "regex",
            "werte": "^(UG|EG|DA|XX|[0-9]{2})$",
            "padding": "keins",
            "zaehlgruppe": ""
        },
        {
            "id": "planart",
            "quelle": "sheet_parameter",
            "parameter": "SE_Planart",
            "laenge": 3,
            "typ": "liste",
            "werte": "GR;SCH;DET;SN;AN",
            "padding": "keins",
            "zaehlgruppe": ""
        },
        {
            "id": "laufnr",
            "quelle": "auto",
            "parameter": "",
            "laenge": 3,
            "typ": "freitext",
            "werte": "",
            "padding": "nullen",
            "zaehlgruppe": "gewerk;geschoss;planart"
        }
    ]
}


def _hole_schema(guid, name, feldname):
    """Extensible-Storage-Schema holen oder einmalig erzeugen."""
    schema = Schema.Lookup(guid)
    if schema is None:
        builder = SchemaBuilder(guid)
        builder.SetSchemaName(name)
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField(feldname, String)
        schema = builder.Finish()
    return schema


def _get_schema():
    return _hole_schema(SCHEMA_GUID, SCHEMA_NAME, FIELD_NAME)


def _get_state_schema():
    return _hole_schema(STATE_GUID, STATE_SCHEMA_NAME, STATE_FIELD)


def _default_kopie():
    return json.loads(json.dumps(DEFAULT_CONFIG))


# ------------------------------------------------------------ Konfiguration
def load_config(doc):
    """
    Konfiguration aus dem Projekt laden.
    Liefert (config, status) mit status aus:
      GELADEN_GESPEICHERT - Konfiguration kommt aus dem Projekt
      GELADEN_STANDARD    - nichts gespeichert, Standardschema geliefert
      GELADEN_LESEFEHLER  - gespeicherte Daten vorhanden, aber nicht lesbar;
                            Standardschema geliefert. Der Aufrufer MUSS davor
                            warnen, die Projektkonfiguration zu ueberschreiben!
    """
    try:
        schema = _get_schema()
        entity = doc.ProjectInformation.GetEntity(schema)
        if entity is not None and entity.IsValid():
            raw = entity.Get[String](FIELD_NAME)
            if raw:
                cfg = json.loads(raw)
                if cfg.get("version") != CONFIG_VERSION:
                    # Platz fuer kuenftige Migrationslogik; bis dahin wird
                    # die Konfiguration unveraendert uebernommen.
                    pass
                return cfg, GELADEN_GESPEICHERT
    except Exception:
        return _default_kopie(), GELADEN_LESEFEHLER
    return _default_kopie(), GELADEN_STANDARD


def save_config(doc, config):
    """Konfiguration im Projekt speichern (eigene Transaction)."""
    config["version"] = CONFIG_VERSION
    schema = _get_schema()
    entity = Entity(schema)
    entity.Set(FIELD_NAME, json.dumps(config, ensure_ascii=False))
    t = Transaction(doc, "Plancodierung: Konfiguration speichern")
    t.Start()
    try:
        doc.ProjectInformation.SetEntity(entity)
        t.Commit()
    except Exception:
        t.RollBack()
        raise


# --------------------------------------------------- Laufnummern-Status
def lade_sheet_state(sheet):
    """
    Laufnummern-Status eines Plans lesen:
    {feld_id: {"key": zaehlgruppen_schluessel, "nr": nummer}, ...}
    Liefert {} wenn nichts gespeichert oder nicht lesbar.
    """
    try:
        entity = sheet.GetEntity(_get_state_schema())
        if entity is not None and entity.IsValid():
            raw = entity.Get[String](STATE_FIELD)
            if raw:
                state = json.loads(raw)
                if isinstance(state, dict):
                    return state
    except Exception:
        pass
    return {}


def schreibe_sheet_state(sheet, state):
    """
    Laufnummern-Status eines Plans schreiben.
    Muss innerhalb einer offenen Transaction des Aufrufers laufen.
    """
    entity = Entity(_get_state_schema())
    entity.Set(STATE_FIELD, json.dumps(state))
    sheet.SetEntity(entity)


# ------------------------------------------------------------ JSON-Vorlagen
def config_to_json(config):
    return json.dumps(config, ensure_ascii=False, indent=2)


def config_from_json(text):
    cfg = json.loads(text)
    if "felder" not in cfg or "separator" not in cfg:
        raise ValueError(
            "Ungueltige Konfigurationsdatei: 'felder' oder 'separator' fehlt.")
    return cfg
