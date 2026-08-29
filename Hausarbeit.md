# Hausarbeit

## Inhaltsverzeichnis

- [1. Einleitung](#1-einleitung)
  - [1.1 Motivation](#11-motivation)
  - [1.2 Zielsetzung](#12-zielsetzung)
- [2. Theoretische Grundlagen und Werkzeuge](#2-theoretische-grundlagen-und-werkzeuge)
  - [2.1 Technologien](#21-technologien)
  - [2.2 Bibliotheken und Pakete](#22-bibliotheken-und-pakete)
  - [2.3 Mensch und KI](#23-mensch-und-ki)
- [3. Konzept und Implementierung](#3-konzept-und-implementierung)
  - [3.1 Programmstruktur](#31-programmstruktur)
  - [3.2 Kernlogik](#32-kernlogik)
  - [3.3 Datenverarbeitung](#33-datenverarbeitung)
  - [3.4 Architektur- und Designentscheidungen](#34-architektur-und-designentscheidungen)
  - [3.5 KI-Konsultation bei Designentscheidungen](#35-ki-konsultation-bei-designentscheidungen)
  - [3.6 Code-Generierung](#36-code-generierung)
    - [3.6.1 KI-generierte Bestandteile](#361-ki-generierte-bestandteile)
    - [3.6.2 Selbst programmierte Bestandteile](#362-selbst-programmierte-bestandteile)
  - [3.7 Prompt-Engineering und Iteration](#37-prompt-engineering-und-iteration)
- [4. Ergebnisse](#4-ergebnisse)
  - [4.1 Funktionsnachweis](#41-funktionsnachweis)
  - [4.2 Beispieldurchlauf](#42-beispieldurchlauf)
- [5. Diskussion und Fazit](#5-diskussion-und-fazit)
  - [5.1 Zielerreichung](#51-zielerreichung)
  - [5.2 Herausforderungen und kritische Reflexion](#52-herausforderungen-und-kritische-reflexion)
  - [5.3 Abweichungen vom ursprünglichen Implementierungsplan](#53-abweichungen-vom-urspruenglichen-implementierungsplan)
  - [5.4 Kritische Würdigung](#54-kritische-würdigung)
  - [5.5 Ausblick](#55-ausblick)
- [6. Literatur- und Quellenverzeichnis](#6-literatur-und-quellenverzeichnis)
- [7. Anhang](#7-anhang)
  - [7.1 Bedienungsanleitung](#71-bedienungsanleitung)
  - [7.2 Ausgewählte Code-Snippets](#72-ausgewählte-code-snippets)

## 1. Einleitung

Dungeons and Dragons (D&D) ist ein beliebtes Pen and Paper-Rollenspiel, in dem taktische, rundenbasierte Kämpfe (Encounter) einen großen Teil des Spiels ausmachen. Üblicherweise kämpft ein Team von Spielern gegen ein Team von NPCs (Non-Player-Characters), die vom Spielleiter gesteuert werden. 
Das System Reference Document (SRD) 5.2.1 ist eine unter der Creative Commons License CC-BY-4.0 verfügbare Fassung der Spielregeln, die den größten Teil der Grundmechaniken des Spiels enthält, in der aber viele Inhalte des eigentlichen Spiels fehlen. So kann ein Spieler beispielsweise für seinen Charakter eine Klasse und Subklasse wählen, jedoch steht pro Klasse nur eine Subklasse zur Verfügung, während im proprietär lizensierten Spielerhandbuch pro Klasse vier Subklassen zur Auswahl stehen.
Dieses Programm, SRD Arena, setzt zunächst einen Teil des Kampfsystems des SRD 5.2.1 als rundenbasiertes 2D-Spiel um. Es gibt mehrere vordefinierte Kampfszenarien, die die umgesetzten Funktionalitäten demonstrieren. Anhand von Vorlagen können in weiteren Dateien auch weitere Szenarien vom Nutzer definiert und anschließend gespielt werden.

### 1.1 Motivation

Die meisten Spielleiter entwerfen die Kampfszenarien für ihre Spieler bereits vor dem eigentlichen Spieltermin. Aus Sicht des Spielleiters ist das Ziel eines Kampfes, den Spielern neben einem interessanten Narrativ auch eine taktische Herausforderung zu bieten, ohne dass der Kampf zu schwer wird.
Im Rahmen der umgesetzten Regeln können Spielleiter mit diesem Programm ihre Kampfszenarien vor dem eigentlichen Spiel ausprobieren. Das ist bereits vorteilhaft, weil im Programm viele Berechnungen und Würfe von Würfeln automatisch stattfinden, die sonst händisch geschehen müssten. Mittelfristig, aber nach Abgabe des Projektes, soll der gesamte Umfang der SRD-Regeln abgedeckt werden. 

Langfristig wäre es auch möglich, das Projekt um eine Option zu erweitern, die Kampfentscheidungen aller Teilnehmer durch Bots automatisiert. Dann könnten Kämpfe vielfach simuliert werden, was Daten erzeugen würde, die für den Spielleiter in noch robustere Kennzahlen über die Ausgewogenheit eines Kampfszenarios umgewandelt werden könnten. Das ist besonders
Diese Funktionalität ist geplant und stellt auch die eigentliche Motivation für das Projekt dar, kann aber aufgrund der beschränkten Bearbeitungszeit erst nach Abgabe des Projektes umgesetzt werden. 


### 1.2 Zielsetzung

SRD Arena ist eine Engine für taktische Kämpfe auf einem 2D-Spielfeld nach dem SRD 5.2.1-Regelwerk. Die Steuerung der Charaktere erfolgt wahlweise durch Nutzerinput, oder durch sehr simple Bots. 
Szenarien werden direkt über strukturierte Textdateien definiert, dafür werden eine Vorlage und mehrere Demo-Szenarien zur Verfügung gestellt.

#### Verwendete Pakete
##### Core:
* pydantic (JSON schema validation)
* PySide6 (GUI)
* scipy (Geometrie)

##### Dev:
* hypothesis (Property-Based Tests)
* mypy (Typechecker)
* pytest (Unit-Tests)
* pytest-cov (Test Coverage)
* ruff (Linter / Formatter)

#### Das Wesentliche
Wesentlich ist eine stabile Encounter-Engine für vorhandene Spieldaten. Der MVP umfasst ein klar abgegrenztes Subset der SRD-Kampfmechaniken.

##### Kampfablauf
* Initiative
* Turn-Struktur
* Action, Bonus Action und Movement
* Opportunity Attack als erste Reaktionsmechanik

##### Bewegung
* Grid-basierte Bewegung

##### Kampfmechaniken
* Nahkampfangriffe
* Fernkampfangriffe
* Zauber, deren zugrunde liegende Mechaniken unterstützt werden
* Attack Rolls
* Saving Throws
* Armor Class
* Critical Hits
* Waffen mit unterschiedlichen Schadenswürfeln

##### Effekte
* Radius-AoE
* Cone-AoE
* Heilung
* einfache Zustände
* Blinded
* Prone

##### Nicht Teil des MVP
* vollständige SRD-Abdeckung
* vollständige Zauberliste
* vollständige Klassenprogression
* vollständige Monster-KI

##### Erfolg ist erkennbar, wenn…
* Szenarien und Spieldaten über JSON geladen werden können.
* Ungültige Eingaben durch Schema-Validierung erkannt werden.
* Sich ein vollständiger Encounter ausführen lässt und anschließend das Text-Abenteuer fortgesetzt wird.
* Derselbe Seed denselben Encounter-Verlauf erzeugt.
* Ein Baseline-Agent einen vollständigen Encounter mit ausschließlich legalen Aktionen spielen kann.
* Aktionen, Würfe, Zustandsänderungen und Kampfende vollständig im Log enthalten sind.
* Alle unterstützten Mechaniken durch automatisierte Tests abgedeckt sind.

#### Nice to Have
* weitere Mechaniken:
* weitere AoE-Typen
* Flächeneffekte über mehrere Runden
* komplexere Zustände
* Summons (erzeugen neue Actors und fügen sie in die Initiative ein)
* weitere Reaktionsmechaniken
* Konzentration
* Grapple / Shove
* Vision / Light
* Hindernisse
* Line of Sight
* bessere Gegner-Agenten
* schönere GUI-Animationen







### Nächste Entscheidungen zur Implementierungsstrategie
* Feature-Abhängigkeitsgraph erstellen
* Abhängigkeiten zwischen Mechaniken dokumentieren
* Priorisierung späterer Erweiterungen
* JSON-Schemas finalisieren
* Format für Spieldaten, Szenarien und Traces festlegen
* Validierungsregeln definieren
* Schnittstelle zwischen Kernlogik und GUI festlegen
* Kernlogik entscheidet Regeln und Spielzustand
* GUI stellt Zustand und Eingabemöglichkeiten dar

### 8. Meilensteine
* Kernlogik aufräumen
* JSON-Schemas finalisieren
* Schnittstelle für Aktionen und Zielauswahl fertigstellen
* Determinismus sicherstellen
* Testabdeckung für alle MVP-Mechaniken
* Baseline-Agent stabilisieren
* GUI anbinden
* Optionale Erweiterungen

### 9. Erwartete Schwierigkeiten
* Reaktionen machen die Turn-Struktur deutlich komplizierter.
* Während des Zuges eines Teilnehmers können andere Teilnehmer kurzfristig handeln.
* AoE-Effekte erzeugen viele Randfälle.
* Im MVP werden nur ausgewählte AoE-Typen unterstützt.
* JSON-Daten können gültig sein, obwohl die benötigte Mechanik noch nicht implementiert ist.
* Schema-Validierung und Laufzeitfehler müssen deshalb getrennt behandelt werden.
* Viele Mechaniken bauen aufeinander auf.
* Fehlende Grundmechaniken können mehrere spätere Erweiterungen gleichzeitig blockieren.
* Die GUI kann mit wachsendem Funktionsumfang deutlich aufwändiger werden.
* Mit jeder neuen Mechanik steigt auch die Komplexität der Gegner-Agenten.
* Werden sie nicht angepasst, nutzen sie neue Möglichkeiten deutlich schlechter als der Spieler.


## 2. Theoretische Grundlagen und Werkzeuge

### 2.1 Technologien

### 2.2 Bibliotheken und Pakete   

> **Vorgabe:** Beschreiben, welche Pakete und Bibliotheken zum Einsatz kamen.
* Typechecker: mypy
* Linter / Formatter: ruff
* Tests: pytest
* Property-Tests: hypothesis
* Coverage: pytest-cov
* Datenvalidierung: pydantic
* Paketverwaltung: uv
* Konfiguration: pyproject.toml
* Debugging / Replay: logging und JSON-Traces

* non-python: 5e.tools json der SRD-Regeln als Grundlage für Authored content
### 2.3 Mensch und KI

> **Vorgabe:** Die Rolle der KI-Unterstützung im Projekt erläutern.

In diesem Projekt wurde der überwiegende Teil der Programmlogik mit KI generiert. 
Viele Ideen zur Struktur wurden auch mit KI-Unterstützung auf Lücken geprüft und angepasst.
Außerdem wurden Regelabschnitte, die in JSON-Dateien noch in Prosaform gegeben waren, mithilfe von KI in JSON-Form gebracht.

## 3. Konzept und Implementierung

### 3.1 Programmstruktur

### 3.2 Kernlogik

### 3.3 Datenverarbeitung

### 3.4 Architektur- und Designentscheidungen

> **Vorgabe:** Begründen, warum die Software auf diese Weise strukturiert wurde. Dazu gehören beispielsweise die Wahl bestimmter Entwurfsmuster, objektorientierter Strukturen oder funktionaler Ansätze sowie verworfene Alternativen und die Gründe für deren Verwerfung.

- Authored content in JSON-Dateien
- Content/Domain/Runtime/GUI Layer

#### 3.4.x Content Layer
filesystem
    │ load_spell_catalog()
    ▼
SpellCatalog containing SpellSchema objects (validated)
    │ find()
    ▼
SpellSchema
    │ build_spell()
    ▼
domain Spell

JSON file
   ↓ parse and validate
SpellSchema
   ↓ stored and indexed
SpellCatalog
### 3.5 KI-Konsultation bei Designentscheidungen

> **Vorgabe:** Darstellen, ob die KI bereits bei der Planung und Architektur des Projekts konsultiert wurde. Falls dies der Fall war, erläutern, welche Vorschläge übernommen wurden und an welchen Stellen bewusst von den Empfehlungen der KI abgewichen wurde, weil die eigene Einschätzung besser zum Projekt passte.
- Lernen über Layered Architecture
- Schemadesign für Laden von Content
- Lösungsvorschläge waren meist nach Iteration gut, aber das Erkennen der Problematik lag oft bei mir


1. Früheres Refactoring: Bei Implementierung von Zaubern wurde "Fahrplan" in Zusammenarbeit mit KI aufgestellt, aber der Code wurde schnell sehr unübersichtlich. Auf Nachfrage schlug Codex vor, dem Fahrplan vor einem Refactoring noch relativ weit zu folgen, aber ich entschloss, das Refactoring früher zu beginnen, um auch früher einen Zustand zu erreichen, in dem ich den Code leichter nachvollziehen und selbst anpassen kann.
2. SRD Arena hatte in der experimentellen Phase noch einen Spieler und einen Gegner. Daraus ist gewachsen, dass es eine "primäre" Kreatur auf dem Spielbrett gibt. Viele weitere Strukturen wurden dann parallel einmal für "den Spieler", dann für seine Verbündeten und seine Gegner geschrieben, obwohl die Logik eigentlich einheitlich sein sollte.
3. Recherche für Regelparsing in Grenzfällen, Beispiel Calm Emotions und Immunitäten.
4. Conditions: 
- Unconscious implies Incapacitated and causes the creature to fall Prone.
- When Unconscious ends, Incapacitated ends with it.
- Prone can remain independently.
-> Domänenwissen verhindert Abstraktion, die KI vornehmen wollte
5. Funktionsweise von Spells aus tagged Prosa extrahieren vs. JSON enrichen:
- Weniger Programmcode zum Parsen von Authored content
- Teile der Definition werden nicht in Logik versteckt
6. Beginnen Dodge, Disengage, etc. in Domain oder in content?

Die Vorschläge der KI wurden nicht unverändert übernommen. Beispielsweise empfahl die KI zunächst, vor der Umstrukturierung des Content-Pakets weitere repräsentative Zauber zu implementieren. Diese Reihenfolge wurde bewusst verworfen, da dadurch zusätzliche Funktionalität auf einer bereits als unübersichtlich erkannten Struktur aufgebaut worden wäre. Ebenso wurde eine erste Implementierung generischer Kreaturentyp-Anforderungen nicht übernommen. Stattdessen wurden zunächst die Zauberdaten um explizite ausführbare Mechaniken erweitert, um die spätere Implementierung auf einer konsistenten Datenbasis aufzubauen. Bei der Modellierung von Zuständen wurden Vorschläge der KI außerdem anhand des Regeltexts überprüft und korrigiert, insbesondere hinsichtlich der Unterscheidung zwischen Immunität und Unterdrückung einer Bedingung.
### 3.6 Code-Generierung

> **Vorgabe:** Erläutern, welche Bestandteile wie programmiert wurden.

- Nutzung von OpenAI Codex

#### 3.6.1 KI-generierte Bestandteile

> **Vorgabe:** Aufführen, welche Module, Funktionen oder Tests maßgeblich mit KI-Unterstützung, beispielsweise durch ChatGPT oder Copilot, erstellt wurden. Außerdem begründen, weshalb sich der KI-Einsatz dafür eignete, etwa bei Boilerplate-Code, Standardalgorithmen oder regulären Ausdrücken.

- Übersetzung von verbleibender Regelprosa in JSON (Spells)
- Schrittweise Implementierung von Regeln - Hit Points, Angriffe, Spells, etc.

#### 3.6.2 Selbst programmierte Bestandteile

> **Vorgabe:** Kernlogiken, komplexe Workarounds oder projektspezifische Funktionen beschreiben, die vollständig selbst programmiert wurden. Zudem erklären, warum die eigene Programmierleistung notwendig war, beispielsweise weil die KI den Kontext nicht ausreichend erfasste oder fehlerhaften Code erzeugte.

- Repo-Struktur "wieder einfangen" -> keine Programmierung
### 3.7 Prompt-Engineering und Iteration

> **Vorgabe:** Die Zusammenarbeit mit der KI beschreiben. Dabei insbesondere erläutern, ob generierter Code direkt übernommen oder in kritischen Iterationsschleifen geprüft und überarbeitet wurde. Dazu gehören auch manuelle Korrekturen von KI-Fehlern wie Halluzinationen oder veralteter Syntax.

## 4. Ergebnisse

### 4.1 Funktionsnachweis

### 4.2 Beispieldurchlauf

## 5. Diskussion und Fazit

### 5.1 Zielerreichung

> **Vorgabe:** Bewerten, inwiefern das gesetzte Ziel erreicht wurde.

### 5.2 Herausforderungen und kritische Reflexion

### 5.3 Abweichungen vom ursprünglichen Implementierungsplan

### 5.4 Kritische Würdigung

> **Vorgabe:** Reflektieren, was gut lief, welche unerwarteten technischen Probleme oder Schwierigkeiten bei der Zusammenarbeit mit der KI auftraten und was bei einem zukünftigen Projekt anders gemacht werden würde.

### 5.5 Ausblick

> **Vorgabe:** Der Ausblick darf auch eine subjektive Einschätzung enthalten.

## 6. Literatur- und Quellenverzeichnis

> **Vorgabe:** Dieser Abschnitt ist nur erforderlich, wenn zitierfähige Quellen verwendet wurden.

## 7. Anhang

> **Vorgabe:** In den Anhang gehören Inhalte, die für den Haupttext zu umfangreich sind.

### 7.1 Bedienungsanleitung

### 7.2 Ausgewählte Code-Snippets

> **Vorgabe:** Die ausgewählten Code-Snippets sollten jeweils nicht länger als eine Seite sein.
