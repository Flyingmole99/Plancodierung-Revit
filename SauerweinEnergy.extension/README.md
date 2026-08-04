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
   **Plancodierung** und vier Buttons. (Die Buttons sind nur in
   Projektdokumenten aktiv, nicht im Familieneditor.)

## Voraussetzung im Projekt

Für jedes Feld mit Quelle `sheet_parameter` oder `mapping` muss der genannte
Shared Parameter existieren und an die Kategorie **Pläne** gebunden sein
(Verwalten → Projektparameter → Hinzufügen → Gemeinsam genutzter Parameter →
Kategorie „Pläne", **Typ Text**, Instanz). Empfohlen: `SE_Gewerk`,
`SE_Geschoss`, `SE_Planart` bereits in der Projektvorlage anlegen – dann
startet jedes Projekt fertig eingerichtet, inkl. gespeichertem Standardschema.

## Die vier Buttons

### 1. Konfigurieren
Öffnet den Schema-Editor (Tabelle, eine Zeile pro Feld):

| Spalte | Bedeutung |
|---|---|
| **Feld-ID** | Eindeutiger Kurzname, wird in Zählgruppen referenziert |
| **Quelle** | `projektinfo` (Projektinformationen), `sheet_parameter` (Parameter am Plan), `auto` (Laufnummer), `konstante` (fester Text aus „Werte"), `mapping` (Übersetzungstabelle) |
| **Parameter** | Parametername (bei projektinfo/sheet_parameter/mapping). Auswahl-Liste mit allen vorhandenen Parametern; „Projektnummer"/„Project Number" u. a. funktionieren sprachunabhängig. |
| **Länge** | 0 = beliebig, sonst Maximallänge. Überlange Werte sind **immer** ein Fehler – es wird nie stillschweigend gekürzt. |
| **Typ** | `freitext`, `liste` (Werte mit `;` getrennt), `regex` (Muster in „Werte", wird automatisch als Voll-Match geprüft – `^`/`$` sind nicht nötig) |
| **Werte** | Je nach Typ/Quelle: Werteliste `HZG;KAE;LUF` • Regex `UG\|EG\|[0-9]{2}` • Konstante `TGA` • Mapping `Erdgeschoss=EG;1. OG=01` |
| **Padding** | `keins` oder `nullen` (links mit 0 auffüllen – typisch für Laufnummern) |
| **Zählgruppe** | Nur bei Quelle `auto`: Feld-IDs mit `;` getrennt, über deren Kombination die Laufnummer hochzählt. Leer = eine durchgehende Nummer über alle Pläne. |

Weitere Funktionen: Zeilen hinzufügen/löschen/verschieben (Reihenfolge =
Code-Reihenfolge), Trennzeichen frei wählbar (unzulässige Revit-Zeichen wie
`; { } [ ]` werden abgefangen), **Live-Vorschau** an den ersten drei Plänen
(aktualisiert sich automatisch nach jeder Änderung), **Vorlage
laden/exportieren** (JSON – für die AG-Vorlagen-Bibliothek auf dem Server),
**Sheet-Parameter anzeigen**.

**Speichern** legt das Schema im Projekt ab. In der .rte-Projektvorlage
gespeichert, erbt es jedes neue Projekt automatisch.

### 2. Befüllen
Setzt einen **oder mehrere** Codierungs-Parameter für ausgewählte Pläne auf
einmal – mit Auswahl aus genau den im Schema erlaubten Werten (kein
Freitext-Tippfehler). Die Feldliste zeigt an, bei wie vielen der gewählten
Pläne der Wert noch leer ist.

### 3. Prüfen (Dry-Run)
Zeigt eine Tabelle Alt → Ziel für alle Pläne, markiert Validierungsfehler
(Wert nicht in Liste, Regex verletzt, Parameter leer/fehlt, doppelte
Zielnummer, Kollision mit Platzhalter- oder Fehler-Plänen, Laufnummer
übersteigt Feldlänge). Ändert nichts.

**Shift+Klick** exportiert die Tabelle zusätzlich als CSV – z. B. als
Konformitätsnachweis für BAP-/Namenskonventions-Prüfungen.

### 4. Anwenden
Schreibt die Plannummern in einer Transaction (Rückgängig über Strg+Z).

- **Umfang wählbar:** alle Pläne oder nur eine Auswahl. Bei Teilanwendung
  wird geprüft, dass keine Zielnummer mit Plänen außerhalb der Auswahl
  kollidiert.
- **Laufnummern sind dauerhaft („sticky"):** Die einmal vergebene Nummer
  eines Plans wird im Plan gespeichert (Extensible Storage) und bleibt
  erhalten – auch wenn später Pläne hinzukommen, die in der Sortierung davor
  liegen. Neue Pläne erhalten die nächste freie Nummer ihrer Zählgruppe;
  Nummern gelöschter Pläne werden **nicht** wiederverwendet (keine
  Verwechslungsgefahr bei bereits ausgegebenen Planständen). Wechselt ein
  Plan die Zählgruppe (z. B. anderes Gewerk), bekommt er dort eine neue
  Nummer.
- **Schalter „Laufnummern komplett neu vergeben":** nummeriert bewusst alles
  kompakt neu durch (1, 2, 3 … je Gruppe in natürlicher Sortierung nach
  aktueller Plannummer) – z. B. zum Aufräumen vor der ersten Planausgabe.
- Zwei-Pass-Verfahren (temporäre Nummern zuerst) verhindert Kollisionen beim
  Umnummerieren. Pläne mit Fehlern werden übersprungen und im Bericht
  ausgewiesen; bei Worksharing werden Pläne, die ein anderer Bearbeiter
  besitzt, vorab aussortiert statt den Lauf abzubrechen.

## Beispielschema (Standard)

`{Projektnummer}-{SE_Gewerk}-{SE_Geschoss}-{SE_Planart}-{Laufnr}`
→ z. B. `2609-HZG-EG-GR-001`, Laufnummer zählt je Kombination
Gewerk+Geschoss+Planart.

## Hinweise

- Platzhalter-Pläne (Placeholder Sheets) werden nie umnummeriert; ihre
  Nummern werden aber bei der Kollisionsprüfung berücksichtigt.
- Wiederholtes Anwenden ändert nichts, solange sich Parameter und
  Planbestand nicht ändern. Beim ersten Anwenden in einem Bestandsprojekt
  werden die vorhandenen Laufnummern übernommen und ab dann festgehalten.
- Pläne mit Validierungsfehlern verbrauchen keine neuen Laufnummern – erst
  wenn der Fehler behoben ist, bekommt der Plan die dann nächste freie
  Nummer.
- Die Schema-GUIDs in `lib/plancode/config_store.py` niemals ändern, sonst
  finden bestehende Projekte ihre gespeicherte Konfiguration bzw. ihren
  Laufnummern-Status nicht mehr.
- Speichern der Konfiguration schreibt ans Projektinformations-Element –
  bei Worksharing muss es verfügbar sein (ggf. erst synchronisieren).

## Entwicklung

Die gesamte Fachlogik (Validierung, Formatierung, Laufnummernvergabe,
Kollisionsprüfung) liegt Revit-frei in `lib/plancode/logik.py` und ist mit
pytest getestet:

```
pip install pytest
python -m pytest tests
```

`lib/plancode/interpreter.py` und `config_store.py` enthalten nur die
Revit-Anbindung (Parameter lesen, Extensible Storage, Sheets sammeln).
