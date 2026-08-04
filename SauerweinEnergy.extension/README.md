# SAUERWEIN ENERGY – Plancodierung (pyRevit-Extension)

Konfigurierbare, automatische Plannummern-Vergabe in Revit. Das Codierungsschema
(Anzahl der Felder, Feldlängen, erlaubte Inhalte, Trennzeichen, Zählgruppen)
wird **direkt in Revit** definiert und im Projekt gespeichert (Extensible
Storage) – es wandert also mit der .rvt-Datei, auch bei Worksharing.

## Installation

1. pyRevit installieren (https://github.com/pyrevitlabs/pyRevit), falls noch
   nicht vorhanden. Getestet mit der Standard-Engine (IronPython 2.7).
2. Diesen Ordner `SauerweinEnergy.extension` an einen festen Ort legen,
   z. B. `C:\pyRevit-Extensions\SauerweinEnergy.extension`.
3. In Revit: **pyRevit → Settings → Custom Extension Directories** →
   übergeordneten Ordner (`C:\pyRevit-Extensions`) hinzufügen → **Save
   Settings & Reload**.
4. Es erscheint der Reiter **SauerweinEnergy** mit dem Panel
   **Plancodierung** und vier Buttons.

## Voraussetzung im Projekt

Für jedes Feld mit Quelle `sheet_parameter` oder `mapping` muss der genannte
Shared Parameter existieren und an die Kategorie **Pläne** gebunden sein
(Verwalten → Projektparameter → Hinzufügen → Gemeinsam genutzter Parameter →
Kategorie „Pläne", Typ Text, Instanz). Empfohlen: `SE_Gewerk`, `SE_Geschoss`,
`SE_Planart` bereits in der Projektvorlage anlegen – dann startet jedes
Projekt fertig eingerichtet, inkl. gespeichertem Standardschema.

## Die vier Buttons

### 1. Konfigurieren
Öffnet den Schema-Editor (Tabelle, eine Zeile pro Feld):

| Spalte | Bedeutung |
|---|---|
| **Feld-ID** | Eindeutiger Kurzname, wird in Zählgruppen referenziert |
| **Quelle** | `projektinfo` (Projektinformationen), `sheet_parameter` (Parameter am Plan), `auto` (Laufnummer), `konstante` (fester Text aus „Werte"), `mapping` (Übersetzungstabelle) |
| **Parameter** | Parametername (bei projektinfo/sheet_parameter/mapping). „Projektnummer"/„Project Number" funktioniert sprachunabhängig. |
| **Länge** | 0 = beliebig. Bei Padding „nullen" wird auf diese Länge aufgefüllt/gekürzt, sonst ist es die Maximallänge (Validierung). |
| **Typ** | `freitext`, `liste` (Werte mit `;` getrennt), `regex` (Muster in „Werte") |
| **Werte** | Je nach Typ/Quelle: Werteliste `HZG;KAE;LUF` • Regex `^(UG\|EG\|[0-9]{2})$` • Konstante `TGA` • Mapping `Erdgeschoss=EG;1. OG=01` |
| **Padding** | `keins` oder `nullen` (links mit 0 auffüllen – typisch für Laufnummern) |
| **Zählgruppe** | Nur bei Quelle `auto`: Feld-IDs mit `;` getrennt, über deren Kombination die Laufnummer hochzählt. Leer = eine durchgehende Nummer über alle Pläne. |

Weitere Funktionen: Zeilen hinzufügen/löschen/verschieben (Reihenfolge =
Code-Reihenfolge), Trennzeichen frei wählbar, **Live-Vorschau** am ersten
Plan, **Vorlage laden/exportieren** (JSON – für die AG-Vorlagen-Bibliothek
auf dem Server), **Sheet-Parameter anzeigen** (listet verfügbare
Parameternamen gegen Tippfehler).

**Speichern** legt das Schema im Projekt ab. In der .rte-Projektvorlage
gespeichert, erbt es jedes neue Projekt automatisch.

### 2. Befüllen
Setzt einen Codierungs-Parameter für mehrere ausgewählte Pläne auf einmal –
mit Auswahl aus genau den im Schema erlaubten Werten (kein Freitext-Tippfehler).

### 3. Prüfen (Dry-Run)
Zeigt eine Tabelle Alt → Ziel für alle Pläne, markiert Validierungsfehler
(Wert nicht in Liste, Regex verletzt, Parameter leer/fehlt, doppelte
Zielnummer). Ändert nichts. Die Tabelle eignet sich auch als
Konformitätsnachweis für BAP-/Namenskonventions-Prüfungen.

### 4. Anwenden
Schreibt die Plannummern in einer Transaction. Zwei-Pass-Verfahren
(temporäre Nummern zuerst) verhindert Kollisionen beim Umnummerieren.
Pläne mit Fehlern werden übersprungen und im Bericht ausgewiesen.
Rückgängig über Strg+Z möglich (eine Transaction).

## Beispielschema (Standard)

`{Projektnummer}-{SE_Gewerk}-{SE_Geschoss}-{SE_Planart}-{Laufnr}`
→ z. B. `2609-HZG-EG-GR-001`, Laufnummer zählt je Kombination
Gewerk+Geschoss+Planart.

## Hinweise

- Die Laufnummernvergabe sortiert stabil nach aktueller Plannummer
  (natürliche Sortierung). Wiederholtes Anwenden ändert nichts, solange
  sich Parameter und Planbestand nicht ändern.
- Platzhalter-Pläne (Placeholder Sheets) werden ignoriert.
- Die Schema-GUID in `lib/plancode/config_store.py` niemals ändern, sonst
  finden bestehende Projekte ihre gespeicherte Konfiguration nicht mehr.
