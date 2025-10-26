# Heizungssteuerung Dokumentation

## Projektübersicht
Dieses Projekt implementiert eine moderne Heizungssteuerung mit EVCC-Integration (Electric Vehicle Charge Controller) und unterstützt verschiedene Hardwarekomponenten wie Temperatursensoren, Pumpen und Heizstäbe.

## Hauptkomponenten

### 1. Konfiguration (`config.py`)
- Lädt und verwaltet die Systemkonfiguration aus `heating_config.yaml`
- Unterstützt YAML-basierte Konfiguration für bessere Lesbarkeit und Wartbarkeit

### 2. Hardware-Steuerung (`hardware.py`)
- Steuert die PiFace-Digital-Hardware
- Verwaltet digitale Ein- und Ausgänge
- Implementiert Sicherheitsfunktionen für Hardware-Zugriffe
- **Automatische Board-Reinitialisierung**: Alle 6 Stunden werden die PiFace-Boards automatisch reinitialisiert, um SPI-Kommunikationsprobleme zu vermeiden

### 3. Sensor-Management (`sensors.py`)
- Verwaltet Temperatursensoren
- Implementiert Caching und Fehlerbehandlung
- Unterstützt One-Wire-Sensoren

### 4. Logging-System (`logging_system.py`)
- Implementiert umfangreiches Logging direkt an systemd journal
- Verwendet nur stdout/stderr für optimale systemd-Integration
- Unterstützt verschiedene Log-Level
- Keine separaten Log-Dateien - alles über `journalctl` verfügbar

### 5. GPIO-Fixes (`gpio.py`)
- Stellt GPIO-Kompatibilität sicher
- Implementiert Workarounds für bekannte Hardware-Probleme

### 6. Speicherüberwachung (`memory_monitor.py`)
- Überwacht Systemressourcen
- Verhindert Speicherlecks
- Implementiert Watchdog-Funktionalität

### 7. Hauptprogramm (`main.py`)
- Initialisiert und koordiniert alle Komponenten
- Implementiert Hauptsteuerungslogik
- Verwaltet Shutdown und Fehlerbehandlung

## Systemanforderungen

### Python-Pakete
Diese Pakete müssen installiert sein:
\`\`\`
yaml            # Konfigurationsverarbeitung
pifacecommon    # PiFace-Grundfunktionen
pifacedigitalio # PiFace Digital I/O
psutil          # Systemressourcenüberwachung
requests        # HTTP-Anfragen für EVCC
flask           # REST-API-Server
flask_limiter   # API-Ratenlimitierung
werkzeug        # Webserver-Utilities
\`\`\`

## Installation

1. Installieren Sie die erforderlichen Pakete:
\`\`\`bash
pip install -r requirements.txt
pip install -r requirements-raspberry-pi.txt  # Für Raspberry Pi spezifische Pakete
\`\`\`

2. Konfigurieren Sie die Heizungssteuerung in `heating_config.yaml`

3. Starten Sie das System:
\`\`\`bash
python main.py  # Normaler Modus
python main.py --demo  # Demo-Modus
\`\`\`

## Demo-Modus

Der Demo-Modus ermöglicht das Testen der Heizungssteuerung ohne physische Hardware. 
Dies ist nützlich für:
- Entwicklung und Tests auf einem normalen Computer
- Überprüfen der Steuerungslogik ohne Raspberry Pi
- Testen von Konfigurationsänderungen

Im Demo-Modus:
- Hardware-Zugriffe werden simuliert
- Temperatursensoren liefern Testdaten
- Alle Logs werden wie im normalen Betrieb geschrieben
- Die Web-Oberfläche ist voll funktionsfähig
- EVCC-Integration kann getestet werden

Starten im Demo-Modus:
\`\`\`bash
python main.py --demo
\`\`\`

Sie können auch GPIO-Tests im Demo-Modus durchführen:
\`\`\`bash
python test/toggle_piface_outputs.py --mock
\`\`\`

## Konfiguration

Die Hauptkonfiguration erfolgt in `heating_config.yaml`. Wichtige Einstellungen sind:

- Temperatursensor-Zuordnungen
- GPIO-Port-Konfigurationen
- EVCC-Integration-Einstellungen
- Logging-Parameter
- Sicherheitsgrenzen

## Sicherheitsfunktionen

- Watchdog-Timer für Systemüberwachung
- Temperaturgrenzen für sicheren Betrieb
- Notabschaltung bei kritischen Zuständen
- Ressourcenüberwachung

## Log-Zugriff

Das System verwendet ausschließlich systemd journal für alle Logs. 

### Systemd Journal Befehle:
```bash
# Service Status prüfen
sudo systemctl status heating-control

# Live Logs anzeigen
sudo journalctl -u heating-control -f

# Letzte 100 Zeilen
sudo journalctl -u heating-control -n 100

# Logs von heute
sudo journalctl -u heating-control --since today

# Fehler suchen
sudo journalctl -u heating-control | grep -E "(ERROR|WARNING|CRITICAL)"

# Buffer Controller Logs
sudo journalctl -u heating-control | grep -i "buffer\|pump"

# PiFace/Hardware Logs  
sudo journalctl -u heating-control | grep -i "piface\|spi\|board"
```

### Web-API Zugriff:
```bash
# Logs über HTTP API abrufen
curl http://192.168.191.206:8080/api/system/logs
```

Die API liest automatisch aus dem systemd journal und liefert gefilterte System-Logs zurück.

## Fehlerbehebung

### Bekannte Probleme in main.py:

1. String-Formatierung in Logging-Aufrufen
   - Problem: Verwendet f-Strings statt %-Formatierung
   - Lösung: Verwenden Sie lazy %-Formatierung für bessere Performance

2. Zu allgemeine Exception-Handler
   - Problem: Fängt alle Exceptions mit `except Exception`
   - Empfehlung: Spezifischere Exception-Typen verwenden

3. Ungenutzte Imports
   - Problem: Nicht verwendete Imports
   - Lösung: Entfernen Sie ungenutzte Imports

### Hardware-Probleme

1. GPIO-Zugriffsprobleme
   - Prüfen Sie die Berechtigungen
   - Verwenden Sie `gpio.py`

2. Sensor-Fehler
   - Überprüfen Sie die Sensor-Verkabelung
   - Validieren Sie die Sensor-IDs in der Konfiguration

3. PiFace/SPI-Kommunikationsprobleme
   - Das System reinitialisiert automatisch alle 6 Stunden die PiFace-Boards
   - Bei anhaltenden Problemen kann eine manuelle Reinitialisierung durchgeführt werden
   - Überprüfen Sie SPI-Einstellungen: `sudo raspi-config` → Interface Options → SPI

## Wartung

- Regelmäßige Überprüfung der Logdateien
- Monitoring der Systemressourcen
- Backup der Konfigurationsdateien
- Aktualisierung der Python-Pakete

## Entwicklung

### Code-Stil
- PEP 8 Konventionen befolgen
- Docstrings für alle Funktionen
- Typ-Hinweise verwenden
- Aussagekräftige Variablennamen

### Tests
- Unit-Tests für kritische Komponenten
- Integration-Tests für Systemzusammenhänge
- Manuelle Tests für Hardware-Interaktionen

## Lizenz
Alle Rechte vorbehalten.

## Support
Bei Problemen oder Fragen wenden Sie sich an den Systemadministrator.