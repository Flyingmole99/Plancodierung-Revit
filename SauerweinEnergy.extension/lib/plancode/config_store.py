# -*- coding: utf-8 -*-
"""
Speichert und laedt die Plancodierungs-Konfiguration als JSON-String
im Extensible Storage am ProjectInformation-Element.
Kompatibel mit IronPython 2.7 (pyRevit-Standard-Engine).
"""
import json

from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.DB.ExtensibleStorage import (
    Schema, SchemaBuilder, AccessLevel, Entity
)
from System import Guid, String

# Feste GUID - niemals aendern, sonst wird gespeicherte Konfiguration
# in bestehenden Projekten nicht mehr gefunden!
SCHEMA_GUID = Guid("a3f5c821-6b94-4e37-9d12-8f0e4b7c5a10")
SCHEMA_NAME = "SEPlancodierung"
FIELD_NAME = "PlancodeConfig"

CONFIG_VERSION = 1

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


def _get_schema():
    """Extensible-Storage-Schema holen oder einmalig erzeugen."""
    schema = Schema.Lookup(SCHEMA_GUID)
    if schema is None:
        builder = SchemaBuilder(SCHEMA_GUID)
        builder.SetSchemaName(SCHEMA_NAME)
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField(FIELD_NAME, String)
        schema = builder.Finish()
    return schema


def load_config(doc):
    """Konfiguration aus dem Projekt laden. Liefert Standard, wenn leer."""
    try:
        schema = _get_schema()
        entity = doc.ProjectInformation.GetEntity(schema)
        if entity is not None and entity.IsValid():
            raw = entity.Get[String](FIELD_NAME)
            if raw:
                cfg = json.loads(raw)
                if cfg.get("version") == CONFIG_VERSION:
                    return cfg, True
                # Platz fuer kuenftige Migrationslogik
                return cfg, True
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_CONFIG)), False


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


def config_to_json(config):
    return json.dumps(config, ensure_ascii=False, indent=2)


def config_from_json(text):
    cfg = json.loads(text)
    if "felder" not in cfg or "separator" not in cfg:
        raise ValueError("Ungueltige Konfigurationsdatei: 'felder' oder 'separator' fehlt.")
    return cfg
