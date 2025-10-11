# Heizungssteuerung System

## Systembeschreibung
Die Heizungssteuerung ist ein modulares System zur Steuerung und Überwachung von Heizungskomponenten, entwickelt speziell für den Raspberry Pi. Das System unterstützt:

- Temperaturüberwachung via 1-Wire Sensoren
- Steuerung von zwei PiFace Digital I/O Boards
- EVCC (Electric Vehicle Charge Controller) Integration
- Automatische Pufferladung
- Heizstabsteuerung
- Sicherheitsüberwachung
- Logging und Monitoring

## Komponenten

### Hardware
- Raspberry Pi (empfohlen: Pi 4 oder neuer)
- 2x PiFace Digital I/O Boards
- 1-Wire Temperatursensoren (DS18B20)
- Relais für Heizstäbe
- Optional: Display für Statusanzeige

### Software-Module
- `main.py`: Hauptprogramm und Systemkoordination
- `config.py`: Konfigurationsmanagement
- `hardware.py`: PiFace-Steuerung
- `sensors.py`: Temperaturmessung
- `gpio.py`: GPIO-Konfiguration
- `logging_system.py`: Logging und Protokollierung
- `memory_monitor.py`: Systemressourcenüberwachung

## Installation

### 1. System-Vorbereitung
```bash
# Systemupdate
sudo apt update
sudo apt upgrade -y

# Notwendige Systempakete
sudo apt install -y python3-pip git i2c-tools python3-venv owfs owserver

# OWFS konfigurieren
sudo systemctl enable owserver
sudo systemctl start owserver

# 1-Wire und I2C aktivieren
sudo raspi-config
# -> Interface Options -> 1-Wire -> Enable
# -> Interface Options -> I2C -> Enable
```

### 2. Repository klonen
```bash
cd /home/pi/Documents
git clone [repository-url] HeizungPVMM
cd HeizungPVMM
```

### 3. Python-Umgebung einrichten
```bash
# Virtuelle Umgebung erstellen
python3 -m venv .venv
source .venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt
pip install -r requirements-raspberry-pi.txt
```

### 4. Konfiguration
```bash
# Konfigurationsdatei anpassen
cp heating_config.yaml.example heating_config.yaml
nano heating_config.yaml
```

### 5. Test der Installation
```bash
# GPIO-Test
python3 test/toggle_piface_outputs.py --mock

# Temperatur-Sensoren Test
python3 scripts/test_temperature_sensors.py
```

## Service-Installation

1. Service-Datei erstellen: