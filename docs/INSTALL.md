# Heizungssteuerung System

## Systembeschreibung
Die Heizungssteuerung ist ein modulares System zur Steuerung und Überwachung von Heizungskomponenten, entwickelt speziell für den Raspberry Pi. Das System unterstützt:

- Temperaturüberwachung via 1-Wire Sensoren (GPIO oder I2C Host Adapter)
- Steuerung von zwei PiFace Digital I/O Boards
- EVCC (Electric Vehicle Charge Controller) Integration
- Automatische Pufferladung
- Heizstabsteuerung mit PV-Überschusserkennung
- Sicherheitsüberwachung und Fehlerbehandlung
- Web-Dashboard für Fernüberwachung
- Logging und Monitoring

## Komponenten

### Hardware
- Raspberry Pi (empfohlen: Pi 4 oder neuer, getestet mit Pi Model B Rev 2)
- PiRack Expansion System (optional für saubere Verkabelung)
- **Option A:** Direkte GPIO 1-Wire Anschlüsse für Temperatursensoren
- **Option B:** I2C 1-Wire Host Adapter (z.B. Sheepwalk RPI2)
- 2x PiFace Digital I/O Boards (SPI-Interface)
- DS18B20 Temperatursensoren (1-Wire)
- Relais für Heizstäbe und Pumpensteuerung
- Optional: Display für lokale Statusanzeige

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

# Notwendige Systempakete installieren
sudo apt install -y python3-pip git python3-venv
sudo apt install -y i2c-tools spi-tools
sudo apt install -y owfs ow-shell owserver
sudo apt install -y python3-yaml python3-requests
```

### 2. Hardware-Interface aktivieren
```bash
# Interfaces über raspi-config aktivieren
sudo raspi-config
# -> Interface Options -> I2C -> Enable  (für I2C Host Adapter)
# -> Interface Options -> SPI -> Enable  (für PiFace Boards)
# -> Interface Options -> 1-Wire -> Enable (für direkte GPIO Sensoren)
# -> Reboot when prompted

# Alternativ: Direkt in /boot/config.txt
echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt
echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
echo "dtoverlay=w1-gpio" | sudo tee -a /boot/config.txt
```

### 3A. 1-Wire Setup: Direkte GPIO-Verbindung
Für direkte Verbindung der Sensoren an GPIO Pin 4:

```bash
# Kernel-Module laden
sudo modprobe w1-gpio
sudo modprobe w1-therm

# Module beim Boot laden
echo "w1-gpio" | sudo tee -a /etc/modules
echo "w1-therm" | sudo tee -a /etc/modules

# Sensoren prüfen
ls -la /sys/bus/w1/devices/
# Sollte Ordner wie "28-xxxxxxxxxxxx" anzeigen
```

### 3B. 1-Wire Setup: I2C Host Adapter (Sheepwalk RPI2)
Für I2C-basierte 1-Wire Host Adapter:

```bash
# I2C-Module laden
sudo modprobe i2c-bcm2708
sudo modprobe i2c-dev

# Module beim Boot laden  
echo "i2c-bcm2708" | sudo tee -a /etc/modules
echo "i2c-dev" | sudo tee -a /etc/modules

# I2C Host Adapter erkennen
sudo i2cdetect -y 1
# Sollte Gerät bei Adresse 0x18 anzeigen (DS2482-100)

# OWFS für I2C konfigurieren
sudo cp /etc/owfs.conf /etc/owfs.conf.backup
sudo tee /etc/owfs.conf << 'EOF'
# OWFS Configuration for I2C Host Adapter
# Comment out fake devices
#server: FAKE = DS18S20,DS2405

# I2C Host Adapter Configuration
server: device=/dev/i2c-1

# Network configuration
server: port=4304
http: port=2121

# Filesystem options
mountpoint=/mnt/1wire
allow_other
EOF

# OWFS Mount Point erstellen
sudo mkdir -p /mnt/1wire
sudo chmod 755 /mnt/1wire

# OWFS Service konfigurieren
sudo systemctl enable owserver
sudo systemctl enable owhttpd
sudo systemctl start owserver
sudo systemctl start owhttpd

# OWFS automatisch mounten
echo "owfs /mnt/1wire fuse.owfs allow_other,server=localhost:4304 0 0" | sudo tee -a /etc/fstab

# OWFS Mount testen
sudo systemctl restart owserver
sleep 2
sudo mount /mnt/1wire

# Sensoren prüfen
owdir
ls -la /mnt/1wire/28.*
```

### 4. OWFS Service Automatisierung
```bash
# OWFS Mount Service erstellen
sudo tee /etc/systemd/system/owfs-mount.service << 'EOF'
[Unit]
Description=OWFS Filesystem Mount
After=owserver.service
Requires=owserver.service
Before=heating-control.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 2
ExecStart=/bin/mount /mnt/1wire
ExecStop=/bin/umount /mnt/1wire
TimeoutSec=30

[Install]
WantedBy=multi-user.target
EOF

# Service aktivieren
sudo systemctl daemon-reload
sudo systemctl enable owfs-mount.service
sudo systemctl start owfs-mount.service

# Status prüfen
sudo systemctl status owserver
sudo systemctl status owfs-mount
mount | grep 1wire
```

### 5. Repository klonen und Python-Umgebung einrichten
```bash
# Repository klonen
cd /home/pi/Documents
git clone [repository-url] HeizungPVMM
cd HeizungPVMM

# Virtuelle Python-Umgebung erstellen
python3 -m venv .venv
source .venv/bin/activate

# Python-Abhängigkeiten installieren
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-raspberry-pi.txt

# PiFace-Bibliotheken installieren
pip install pifacecommon pifacedigitalio

# Optional: OWFS Python-Bibliothek
pip install pyownet
```

### 6. Hardware-Tests durchführen
```bash
# Aktiviere virtuelle Umgebung
source .venv/bin/activate

# Test 1: OWFS System prüfen
sudo systemctl status owserver
sudo systemctl status owfs-mount
mount | grep 1wire

# Test 2: OWFS Sensoren erkennen
owdir
ls -la /mnt/1wire/28.*

# Test 3: Temperaturwerte lesen
echo "=== OWFS Sensor Test ==="
for sensor in /mnt/1wire/28.*; do
  if [ -d "$sensor" ]; then
    id=$(basename "$sensor")
    temp=$(cat "$sensor/temperature" 2>/dev/null || echo "Error")
    echo "$id: ${temp}°C"
  fi
done

# Test 4: I2C Host Adapter prüfen (falls verwendet)
sudo i2cdetect -y 1
# Sollte Gerät bei 0x18 zeigen für DS2482-100

# Test 5: PiFace Boards testen
python3 diagnostics/toggle_piface_outputs.py --boards 2
# Sollte beide Boards erkennen und Outputs schalten

# Test 6: Temperatur-Sensoren diagnostizieren
python3 diagnostics/onewire_diagnostics.py --fix-paths

# Test 7: Komplett-System-Diagnose
python3 diagnostics/dashboard_diagnostics.py
```

### 7. Systemkonfiguration anpassen
```bash
# Hauptkonfigurationsdatei bearbeiten
cp heating_config.yaml heating_config.yaml.backup
nano heating_config.yaml

# Für OWFS Setup (empfohlen - unterstützt sowohl I2C als auch GPIO):
# - demo_mode: false
# - mock_hardware: false  
# - sensors.one_wire_mount_point: "/mnt/1wire"
# - sensor paths: "/mnt/1wire/28.DEVICE_ID/temperature"

# WICHTIG: Sensor-Pfade müssen "/temperature" am Ende enthalten!

# Sensor IDs ermitteln:
owdir
ls -la /mnt/1wire/28.*

# Temperatur testen:
cat /mnt/1wire/28.DEVICE_ID/temperature
# Sollte direkt einen Temperaturwert (z.B. "23.125") zurückgeben

# Beispiel-Konfiguration:
# sensors:
#   one_wire_mount_point: "/mnt/1wire"
#   temperature_sensors:
#     sensor_name:
#       path: "/mnt/1wire/28.70204A050000/temperature"
#       description: "Sensor Description"

# Alle Sensoren automatisch finden und testen:
for sensor in /mnt/1wire/28.*; do
  if [ -d "$sensor" ]; then
    id=$(basename "$sensor")
    temp=$(cat "$sensor/temperature" 2>/dev/null || echo "Error")
    echo "$id: ${temp}°C"
  fi
done
```

### 8. Benutzerberechtigungen einrichten
```bash
# Benutzer zu relevanten Gruppen hinzufügen
sudo usermod -a -G spi,i2c,gpio pi

# udev-Regeln für Hardware-Zugriff erstellen
sudo tee /etc/udev/rules.d/99-heating-hardware.rules << 'EOF'
# PiFace Digital I/O access
SUBSYSTEM=="spi", GROUP="spi", MODE="0664"
KERNEL=="spidev*", GROUP="spi", MODE="0664"

# I2C access for 1-Wire host adapter
SUBSYSTEM=="i2c-dev", GROUP="i2c", MODE="0664"

# GPIO access
SUBSYSTEM=="gpio", GROUP="gpio", MODE="0664"
KERNEL=="gpiochip*", GROUP="gpio", MODE="0664"
EOF

# udev-Regeln neu laden
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 9. Systemdienste einrichten

#### Für I2C Host Adapter Setup:
```bash
# OWFS-Dienste konfigurieren (falls nicht bereits geschehen)
# owfs-mount.service sollte bereits erstellt worden sein

# Hauptheizungsdienst installieren
sudo cp scripts/heating-control.service /etc/systemd/system/

# Service-Abhängigkeiten für I2C Host Adapter anpassen
sudo mkdir -p /etc/systemd/system/heating-control.service.d/
sudo tee /etc/systemd/system/heating-control.service.d/i2c-override.conf << 'EOF'
[Unit]
After=owfs-mount.service
Requires=owfs-mount.service

[Service]
# Warte bis OWFS bereit ist
ExecStartPre=/bin/bash -c 'until [ -d /mnt/1wire ]; do sleep 1; done'
ExecStartPre=/bin/bash -c 'until ls /mnt/1wire/28.* 2>/dev/null; do sleep 2; done'
EOF

# WICHTIG: Erst owfs-mount.service erstellen, falls noch nicht geschehen
# OPTION A: Service mit fstab (erfordert fstab-Eintrag)
# OPTION B: Service ohne fstab (empfohlen - funktioniert direkt)

# EMPFOHLENE LÖSUNG: Service ohne fstab-Abhängigkeit
sudo tee /etc/systemd/system/owfs-mount.service << 'EOF'
[Unit]
Description=OWFS Filesystem Mount
After=owserver.service
Requires=owserver.service
Before=heating-control.service

[Service]
Type=forking
RemainAfterExit=yes
ExecStartPre=/bin/sleep 3
ExecStartPre=/bin/mkdir -p /mnt/1wire
ExecStart=/usr/bin/owfs --server=localhost:4304 /mnt/1wire --allow_other --background
ExecStop=/bin/umount /mnt/1wire
TimeoutSec=30

[Install]
WantedBy=multi-user.target
EOF

# ALTERNATIVE: Wenn du fstab verwenden möchtest
# Erst fstab-Eintrag erstellen:
# echo "owfs /mnt/1wire fuse.owfs allow_other,server=localhost:4304 0 0" | sudo tee -a /etc/fstab
# Dann die originale Service-Datei verwenden:
# sudo tee /etc/systemd/system/owfs-mount.service << 'EOF'
# [Unit]
# Description=OWFS Filesystem Mount
# After=owserver.service
# Requires=owserver.service
# Before=heating-control.service
# 
# [Service]
# Type=oneshot
# RemainAfterExit=yes
# ExecStartPre=/bin/sleep 2
# ExecStart=/bin/mount /mnt/1wire
# ExecStop=/bin/umount /mnt/1wire
# TimeoutSec=30
# 
# [Install]
# WantedBy=multi-user.target
# EOF

# Alle Services aktivieren
sudo systemctl daemon-reload
sudo systemctl enable owserver.service
sudo systemctl enable owfs-mount.service  
sudo systemctl enable heating-control.service

# Services in korrekter Reihenfolge starten
sudo systemctl start owserver.service
sleep 2
sudo systemctl start owfs-mount.service
sleep 3
sudo systemctl start heating-control.service

# Status überprüfen
sudo systemctl status owserver.service
sudo systemctl status owfs-mount.service
sudo systemctl status heating-control.service
```

#### Für direktes GPIO Setup:
```bash
# Hauptheizungsdienst installieren
sudo cp scripts/heating-control.service /etc/systemd/system/

# Service aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable heating-control.service
sudo systemctl start heating-control.service
sudo systemctl status heating-control.service
```

### 10. Installation testen
```bash
# Aktiviere virtuelle Umgebung
source .venv/bin/activate

echo "=== 1. OWFS Service Status ==="
sudo systemctl status owserver.service
sudo systemctl status owfs-mount.service
mount | grep 1wire

echo "=== 2. OWFS Sensor Detection ==="
owdir
echo -e "\nDetected sensors in /mnt/1wire:"
ls -la /mnt/1wire/28.* 2>/dev/null || echo "No sensors found"

echo -e "\n=== 3. Temperature Reading Test ==="
for sensor in /mnt/1wire/28.*; do
  if [ -d "$sensor" ]; then
    id=$(basename "$sensor")
    temp=$(cat "$sensor/temperature" 2>/dev/null || echo "Read Error")
    echo "  $id: ${temp}°C"
  fi
done

echo -e "\n=== 4. I2C Host Adapter Test (if using I2C) ==="
sudo i2cdetect -y 1

echo -e "\n=== 5. PiFace Hardware Test ==="
python3 diagnostics/toggle_piface_outputs.py --boards 2 --duration 0.5

echo -e "\n=== 6. Temperature Sensor Diagnostics ==="
python3 diagnostics/onewire_diagnostics.py

echo -e "\n=== 7. Complete System Diagnostics ==="
python3 diagnostics/dashboard_diagnostics.py

echo -e "\n=== 8. Web Dashboard Test ==="
python3 -c "
import requests
try:
    response = requests.get('http://localhost:8080/api/status', timeout=5)
    print(f'✅ Dashboard Status: {response.status_code}')
    data = response.json()
    if 'sensors' in data:
        print(f'✅ Sensors detected: {len(data[\"sensors\"])}')
    else:
        print('⚠️  No sensor data in response')
except Exception as e:
    print(f'❌ Dashboard nicht erreichbar: {e}')
    print('   Tipp: Starte heating-control.service neu')
"

echo -e "\n=== 9. Service Status Check ==="
sudo systemctl status heating-control.service --no-pager -l

echo -e "\n=== 10. Recent Service Logs ==="
sudo journalctl -u heating-control.service --no-pager -n 20 --since "5 minutes ago"

echo -e "\n=== Installation Complete! ==="
echo "✅ Wenn alle Tests erfolgreich sind, läuft das System korrekt"
echo "🌐 Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo "📊 Logs: sudo journalctl -u heating-control.service -f"
```

## Fehlerbehebung

### OWFS Mount Probleme
```bash
# SCHRITT 1: Service Status prüfen
sudo systemctl status owserver.service
sudo systemctl status owfs-mount.service
mount | grep 1wire

# SCHRITT 2: Fehlerdetails anzeigen
journalctl -xeu owfs-mount.service
journalctl -xeu owserver.service

# SCHRITT 3: Voraussetzungen prüfen
# a) Mount Point existiert?
ls -la /mnt/1wire
# Falls nicht: sudo mkdir -p /mnt/1wire && sudo chmod 755 /mnt/1wire

# b) OWFS Server läuft?
sudo systemctl status owserver.service
# Falls nicht: sudo systemctl start owserver.service

# c) fstab Eintrag korrekt?
grep 1wire /etc/fstab
# Sollte zeigen: owfs /mnt/1wire fuse.owfs allow_other,server=localhost:4304 0 0

# SCHRITT 4: Manueller Mount-Test
sudo owfs --server=localhost:4304 /mnt/1wire --allow_other
# oder für I2C direkt:
sudo owfs --i2c=/dev/i2c-1 /mnt/1wire --allow_other

# SCHRITT 5: Sensoren testen nach manuellem Mount
ls -la /mnt/1wire/28.*
owdir

# SCHRITT 6: Service-Datei korrigieren (Alternative ohne fstab)
sudo tee /etc/systemd/system/owfs-mount.service << 'EOF'
[Unit]
Description=OWFS Filesystem Mount
After=owserver.service
Requires=owserver.service
Before=heating-control.service

[Service]
Type=forking
RemainAfterExit=yes
ExecStartPre=/bin/sleep 2
ExecStartPre=/bin/mkdir -p /mnt/1wire
ExecStart=/usr/bin/owfs --server=localhost:4304 /mnt/1wire --allow_other
ExecStop=/bin/umount /mnt/1wire
TimeoutSec=30
PIDFile=/var/run/owfs.pid

[Install]
WantedBy=multi-user.target
EOF

# Service neu laden und testen
sudo systemctl daemon-reload
sudo systemctl restart owfs-mount.service
sudo systemctl status owfs-mount.service

# SCHRITT 7: Alternative - OWFS ohne Service direkt starten
# Falls Services problematisch sind, OWFS manuell im Hintergrund starten:
sudo pkill -f owfs
sudo owfs --i2c=/dev/i2c-1 /mnt/1wire --allow_other --background
# oder via Server:
sudo owfs --server=localhost:4304 /mnt/1wire --allow_other --background
```

### Sensor Reading Probleme  
```bash
# Sensor-Pfade testen
for sensor in /mnt/1wire/28.*; do
  echo "Testing: $sensor"
  if [ -f "$sensor/temperature" ]; then
    temp=$(cat "$sensor/temperature" 2>/dev/null)
    echo "  ✅ $sensor/temperature: $temp°C"
  else
    echo "  ❌ $sensor/temperature: File not found"
  fi
done

# Python Sensor Test
python3 -c "
import os
sensors = [d for d in os.listdir('/mnt/1wire') if d.startswith('28.')]
for sensor in sensors:
    path = f'/mnt/1wire/{sensor}/temperature'
    try:
        with open(path, 'r') as f:
            temp = f.read().strip()
        print(f'✅ {sensor}: {temp}°C')
    except Exception as e:
        print(f'❌ {sensor}: {e}')
"

# Sensor Konfiguration prüfen
grep -A5 -B5 "temperature_sensors:" heating_config.yaml
```

### I2C Host Adapter Probleme
```bash
# I2C-Module prüfen
lsmod | grep i2c

# I2C-Geräte scannen
sudo i2cdetect -y 1

# Wenn kein Gerät bei 0x18:
# 1. Hardware-Verbindungen prüfen
# 2. I2C in raspi-config aktivieren
# 3. Neustart erforderlich

# OWFS Debug
sudo owserver -d /dev/i2c-1 --i2c=0x18 -p 4304 -F
```

### PiFace Probleme
```bash
# SPI-Module prüfen
lsmod | grep spi

# PiFace-Test mit Debug
python3 -c "
import pifacedigitalio as pfd
try:
    board = pfd.PiFaceDigital()
    print('PiFace erfolgreich initialisiert')
    board.cleanup()
except Exception as e:
    print(f'PiFace-Fehler: {e}')
"

# Berechtigungen prüfen
ls -la /dev/spidev0.*
groups $USER
```

### Service-Debug und Log-Reading
```bash
# === HEATING SERVICE LOGS LESEN ===

# 1. Service-Status mit kurzen Logs
sudo systemctl status heating-control.service

# 2. Service-Status mit vollständigen Logs (empfohlen)
sudo systemctl status heating-control.service -l --no-pager

# 3. Aktuelle Logs in Echtzeit verfolgen (Live-Monitoring)
sudo journalctl -u heating-control.service -f

# 4. Letzte 50 Log-Einträge anzeigen
sudo journalctl -u heating-control.service -n 50

# 5. Logs seit bestimmter Zeit
sudo journalctl -u heating-control.service --since "1 hour ago"
sudo journalctl -u heating-control.service --since "today"
sudo journalctl -u heating-control.service --since "2025-10-12 20:00:00"

# 6. Logs mit Zeitstempel und Details
sudo journalctl -u heating-control.service -o verbose

# 7. Alle Logs des Services (von Anfang an)
sudo journalctl -u heating-control.service --no-pager

# 8. Logs aller verwandter Services zusammen
sudo journalctl -u owserver.service -u owfs-mount.service -u heating-control.service -f

# === BUFFER LOAD CONTROLLER LOGS SPEZIELL ===

# 1. Zuerst prüfen: Läuft der Service überhaupt?
sudo systemctl status heating-control.service

# 2. Alle aktuellen Logs anzeigen (ohne Filter)
sudo journalctl -u heating-control.service -n 50

# 3. Nur Buffer Load Controller Logs anzeigen
sudo journalctl -u heating-control.service | grep -i "buffer"

# 4. Falls keine Buffer Logs: Nach "initialize" oder "controller" suchen
sudo journalctl -u heating-control.service | grep -iE "(initialize|controller.*start|main.*start)"

# 5. Buffer Controller Logs in Echtzeit
sudo journalctl -u heating-control.service -f | grep -i "buffer"

# 6. Falls immer noch nichts: Service-Start prüfen
sudo journalctl -u heating-control.service --since "10 minutes ago" | head -20

# 3. Buffer Controller Initialisierung prüfen
sudo journalctl -u heating-control.service | grep -E "(buffer.*initialized|buffer.*started|Pump port)"

# 4. Buffer Pump Aktivierung prüfen
sudo journalctl -u heating-control.service | grep -E "(pump.*ON|pump.*OFF|Buffer pump)"

# 5. Buffer Controller Temperaturen anzeigen
sudo journalctl -u heating-control.service | grep -E "(Konrad.*Michael|temperature.*check)"

# 6. Buffer Controller Fehler finden
sudo journalctl -u heating-control.service | grep -iE "(buffer.*error|buffer.*fail|Invalid port)"

# 7. Letzte Buffer Aktivitäten (30 Min)
sudo journalctl -u heating-control.service --since "30 minutes ago" | grep -i "buffer"

# 8. Buffer Status mit Kontext (3 Zeilen vor/nach jedem Match)
sudo journalctl -u heating-control.service -n 100 | grep -A3 -B3 -i "buffer"

# 9. Erwartete Buffer Logs bei korrekter Funktion:
# "Simple buffer load controller initialized"
# "Konrad sensor: puffer_k_mitte"
# "Michael sensor: puffer_m_mitte"  
# "Pump port: puffer_lade_pumpe"
# "Buffer pump ON: Konrad=47.5°C > Michael=40.7°C"
# "Buffer pump OFF: Konrad=45.0°C <= Michael=44.0°C"

# === OWFS SERVICE LOGS LESEN ===

# OWFS Mount Service Logs
sudo journalctl -u owfs-mount.service -n 20
sudo journalctl -xeu owfs-mount.service  # Mit Erklärungen

# OWFS Server Logs  
sudo journalctl -u owserver.service -n 20

# === LOG-FILTERUNG ===

# Nur Fehler anzeigen
sudo journalctl -u heating-control.service -p err

# Nur Warnungen und Fehler
sudo journalctl -u heating-control.service -p warning

# Nach spezifischen Begriffen suchen
sudo journalctl -u heating-control.service | grep -i "error\|fail\|exception"
sudo journalctl -u heating-control.service | grep -i "temperature"
sudo journalctl -u heating-control.service | grep -i "sensor"

# === SYSTEM-LOGS ===

# Alle System-Logs der letzten Stunde
sudo journalctl --since "1 hour ago"

# Kernel-Logs (für Hardware-Probleme)
dmesg | tail -20

# === LOG-EXPORT ===

# Logs in Datei speichern
sudo journalctl -u heating-control.service --since "today" > heating_logs_$(date +%Y%m%d).txt

# Kompakte Log-Zusammenfassung
sudo journalctl -u heating-control.service --since "1 hour ago" --no-pager -o short

# === HILFREICHE KOMBINATIONEN ===

# Service-Status + aktuelle Logs
sudo systemctl status heating-control.service -l && echo "=== RECENT LOGS ===" && sudo journalctl -u heating-control.service -n 10

# Alle Services prüfen
sudo systemctl list-units --all | grep -E "(owserver|owfs|heating)"

# Service neu starten und Logs verfolgen
sudo systemctl restart heating-control.service && sudo journalctl -u heating-control.service -f
```

### Häufige Service-Probleme
```bash
# Fehler: "Unit file owfs-mount.service does not exist"
# Lösung: Service-Datei manuell erstellen
sudo tee /etc/systemd/system/owfs-mount.service << 'EOF'
[Unit]
Description=OWFS Filesystem Mount
After=owserver.service
Requires=owserver.service
Before=heating-control.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 2
ExecStart=/bin/mount /mnt/1wire
ExecStop=/bin/umount /mnt/1wire
TimeoutSec=30

[Install]
WantedBy=multi-user.target
EOF

# Dann systemctl daemon-reload und enable erneut ausführen
sudo systemctl daemon-reload
sudo systemctl enable owfs-mount.service

# Fehler: "heating-control.service does not exist"
# Lösung: Service-Datei aus scripts/ Ordner kopieren
sudo cp scripts/heating-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable heating-control.service

# Services in korrekter Reihenfolge prüfen
sudo systemctl list-dependencies heating-control.service

# === BUFFER LOAD CONTROLLER DEBUG ===

# Buffer Controller sollte bei Temperaturdifferenz > 2°C laufen
# Prüfen warum Buffer Load Controller nicht läuft:

# 1. Service Status prüfen
sudo journalctl -u heating-control.service | grep -i "buffer"

# 2. Temperaturen und Controller Status über API prüfen
curl -s http://localhost:8080/api/status | python3 -m json.tool | grep -A5 -B5 "buffer"

# 3. Buffer Controller Logs in Echtzeit
sudo journalctl -u heating-control.service -f | grep -i "buffer"

# 4. Manuelle Temperatur-Kontrolle
echo "=== Buffer Temperature Check ==="
echo "Konrad (puffer_k_mitte):" $(cat /mnt/1wire/28.CBF849050000/temperature 2>/dev/null || echo "Error")
echo "Michael (puffer_m_mitte):" $(cat /mnt/1wire/28.XXX/temperature 2>/dev/null || echo "Error - check sensor path")

# 5. Konfiguration prüfen
grep -A10 "buffer_load:" heating_config.yaml

# 6. PiFace Output Status prüfen (Buffer Load Pump)
# Welcher Port ist puffer_lade_pumpe?
grep -A5 "puffer_lade_pumpe:" heating_config.yaml

# 7. Controller direkt testen (Python)
cd /path/to/HeizungPVMM
source .venv/bin/activate
python3 -c "
from config import load_config
from sensors import create_sensor_manager
import logging

config = load_config()
sensor_manager = create_sensor_manager(config, None)
temps = sensor_manager.get_valid_temperatures()

konrad_temp = temps.get('puffer_k_mitte', 'Missing')
michael_temp = temps.get('puffer_m_mitte', 'Missing')

print(f'Konrad: {konrad_temp}°C')
print(f'Michael: {michael_temp}°C')

if isinstance(konrad_temp, (int, float)) and isinstance(michael_temp, (int, float)):
    diff = konrad_temp - michael_temp
    print(f'Difference: {diff:.1f}°C')
    print(f'Should pump run? {diff > 2.0}')
else:
    print('ERROR: Missing temperature readings!')
"

# 8. Buffer Controller Status via Dashboard API
curl -s "http://localhost:8080/api/buffer_load" 2>/dev/null || echo "API not available"

# 9. Häufige Buffer Controller Probleme

# Fehler: "Invalid port reference: X" (wo X eine Zahl ist)
# Problem: Config-Klassen hatten pump_port als int definiert, sollte aber string sein
# Lösung: In config.py beide Config-Klassen korrigieren:
# 
# BufferLoadConfig:
# pump_port: str = "puffer_lade_pumpe"  # statt pump_port: int = 6
# 
# HeatExchangerConfig: 
# pump_port: str = "wt_pumpe"  # statt pump_port: int = 7
# 
# Diese Änderung macht die Konfiguration konsistent mit der YAML-Datei.

# KRITISCHER BUGFIX: YAML Parsing war unvollständig!
# Problem: config.py from_yaml() Method hat buffer_load und heat_exchanger nicht geparst
# Lösung: Fehlende Parsing-Logik in config.py hinzugefügt für beide Konfigurationssektionen

# Wenn nach der Änderung immer noch "Pump port: 6" in Logs steht:
# 1. Python Bytecode Cache leeren:
find /path/to/HeizungPVMM -name "*.pyc" -delete
find /path/to/HeizungPVMM -name "__pycache__" -type d -exec rm -rf {} +

# 2. Service komplett neu starten:
sudo systemctl stop heating-control.service
sleep 2
sudo systemctl start heating-control.service

# 3. Konfiguration debuggen:
cd /path/to/HeizungPVMM
source .venv/bin/activate
python3 -c "
from config import load_complete_config
config, _ = load_complete_config('heating_config.yaml')
print('Buffer Load Configuration:')
print('  pump_port:', repr(config.buffer_load.pump_port))
print('  type:', type(config.buffer_load.pump_port))
print('  source_sensor:', repr(config.buffer_load.source_sensor))
print('  target_sensor:', repr(config.buffer_load.target_sensor))
"

# 4. YAML-Datei direkt prüfen:
grep -A5 -B5 "pump_port" heating_config.yaml

# Fehler: "Buffer controller not starting"  
# Prüfen ob heating_config.yaml korrekt ist:
grep -A5 "buffer_load:" heating_config.yaml
# Sollte zeigen:
# buffer_load:
#   source_sensor: "puffer_k_mitte"
#   target_sensor: "puffer_m_mitte"  
#   pump_port: "puffer_lade_pumpe"

# Und outputs Sektion sollte haben:
grep -A3 "puffer_lade_pumpe:" heating_config.yaml
# Sollte zeigen:
# puffer_lade_pumpe:
#   board: 0
#   port: 6
#   description: "Buffer Charging Pump"
```

## Simplified Heat Exchanger Controller

### Übersicht
Der Wärmetauscher-Controller wurde vereinfacht und verwendet jetzt eine selbstverwaltete Thread-Architektur mit intelligenter temperaturbasierter Pumpensteuerung.

### Funktionsweise
**Temperaturbasierte Steuerungsstrategie:**

1. **Große Temperaturdifferenz (>10°C vom Zielwert)**: 
   - Pumpe läuft **kontinuierlich**
   - Beispiel: Ziel 65°C, aktuell 50°C → Differenz 15°C → kontinuierlich

2. **Kleine Temperaturdifferenz (<3°C vom Zielwert)**:
   - **Intervall-Modus**: 15s AN / 45s AUS
   - Beispiel: Ziel 65°C, aktuell 63°C → Differenz 2°C → Intervall

3. **Mittlere Temperaturdifferenz (3-10°C)**:
   - Pumpe läuft **kontinuierlich**

4. **Sensorfehler oder ungültige Werte**:
   - **Sicherheitsmodus**: Pumpe AN (Überhitzungsschutz)

### Konfiguration (heating_config.yaml)
```yaml
heat_exchanger:
  target_temperature: 65.0      # Zieltemperatur (°C)
  continuous_threshold: 10.0    # Schwelle für kontinuierlichen Betrieb (°C)
  interval_threshold: 3.0       # Schwelle für Intervall-Modus (°C)
  pump_on_time: 15.0           # Pumpe AN-Zeit im Intervall-Modus (Sekunden)
  pump_off_time: 45.0          # Pumpe AUS-Zeit im Intervall-Modus (Sekunden)  
  update_interval: 5.0         # Prüfintervall (Sekunden)
  pump_port: "wt_pumpe"        # Pumpensteuerung
  temperature_sensor: "bhkw_vorlauf"  # Temperatursensor
```

### Thread-Management
- **Self-Managed Threading**: Der Controller verwaltet seinen eigenen Thread
- **Automatischer Start/Stop**: `.start()` und `.stop()` Methoden
- **Thread Monitoring**: Automatische Überwachung und Neustart bei Ausfall
- **Graceful Shutdown**: Sauberes Herunterfahren mit Pumpe AUS

### Logs und Debugging
```bash
# Heat Exchanger Logs anschauen:
sudo journalctl -u heating-control.service | grep "heat_exchanger\|Heat exchanger"

# Typische Log-Meldungen:
[INFO] 🚀 Heat exchanger controller started
[INFO] 💧 Heat exchanger pump: ON  
[INFO] 💧 Heat exchanger pump: OFF
[INFO] 🌡️ Continuous mode: 55.2°C (diff: 9.8°C)
[INFO] 🔄 Interval mode: Pump ON (waited 45.0s)
[INFO] ⚠️ Temperature sensor error - pump ON for safety
[INFO] 🛑 Heat exchanger controller stopped

# Status abfragen:
curl http://localhost:8080/api/status | jq '.heat_exchanger'
```

### Troubleshooting Heat Exchanger
```bash
# 1. Controller Status prüfen:
grep -A10 "heat_exchanger:" heating_config.yaml

# 2. Sensor verfügbar?
curl http://localhost:8080/api/sensors | grep bhkw_vorlauf

# 3. Pump Port konfiguriert?
grep -A3 "wt_pumpe:" heating_config.yaml

# 4. Thread läuft?
sudo journalctl -u heating-control.service --since "5 min ago" | grep "Heat exchanger"

# 5. Manueller Test der Pumpe:
cd /path/to/HeizungPVMM
source .venv/bin/activate  
python3 test/test_simplified_heat_exchanger.py
```

### Häufige Heat Exchanger Probleme

#### Problem: "Temperature sensor error - pump ON for safety"
```bash
# Sensor prüfen:
owdir | grep 28.
ls -la /mnt/1wire/28.*/temperature

# OWFS neu starten:
sudo systemctl restart owfs-mount.service
```

#### Problem: "Pump läuft nicht im Intervall-Modus"
```bash
# Konfiguration prüfen:
python3 -c "
from config import load_complete_config
config, _ = load_complete_config('heating_config.yaml')
print('Heat Exchanger Config:')
print('  target_temp:', config.heat_exchanger.target_temperature)
print('  continuous_threshold:', getattr(config.heat_exchanger, 'continuous_threshold', 'NOT SET'))
print('  interval_threshold:', getattr(config.heat_exchanger, 'interval_threshold', 'NOT SET'))
"
```

#### Problem: "Thread monitoring meldet Heat Exchanger Neustart"
```bash
# Zu häufige Neustarts können auf Speichermangel hindeuten:
free -h
sudo journalctl -u heating-control.service | grep "Heat exchanger.*died" | tail -10
```

## Thread Monitoring & Automatische Wiederherstellung

### Übersicht
Das System implementiert umfassendes Thread-Monitoring für alle kritischen Komponenten:
- **Buffer Load Controller**: Pufferladesteuerung-Thread  
- **Heat Exchanger**: Wärmetauscher-Thread (main.py verwaltet)
- **Mixer Controllers**: Mischer-Controller-Threads (pro Mischer ein Thread)
- **HTTP Service**: Webinterface-Thread

### Funktionsweise
Das System prüft **alle 50 Sekunden** (alle 10 Hauptschleifeniterationen) die Gesundheit aller Threads:

```bash
# In den Logs erkennbar durch:
[INFO] 📊 Thread monitoring: Checking all critical threads...
[INFO] 🔄 Buffer load controller thread died, restarting...
[INFO] ✅ Buffer load controller thread restarted successfully
[INFO] 📊 Mixer thread monitoring: 1 threads restarted
[INFO] 🔄 Heat exchanger thread died, restarting...
[INFO] ✅ Heat exchanger thread restarted successfully
```

### Thread Restart Strategie
Bei erkanntem Thread-Ausfall:
1. **Sauberer Stop**: Vorhandenen Thread ordnungsgemäß beenden
2. **Kurze Pause**: 1 Sekunde warten für vollständige Bereinigung
3. **Neustart**: Neuen Thread mit identischer Konfiguration starten
4. **Logging**: Erfolg/Fehler protokollieren

### Monitoring Details

#### Buffer Load Controller
```python
# Überwacht in main.py _check_and_restart_threads():
if self.buffer_load_controller.running and (
    not self.buffer_load_controller.thread or 
    not self.buffer_load_controller.thread.is_alive()
):
    # Automatischer Neustart
```

#### Mixer Controller
```python  
# Überwacht über MixerManager.check_and_restart_threads():
restart_status = self.mixer_manager.check_and_restart_threads()
# Gibt Dict zurück: {"mixer1": False, "mixer2": True} 
# True = Thread wurde neu gestartet
```

#### Heat Exchanger & HTTP Service
```python
# Direkt in main.py überwacht:
if not self.heat_exchanger_thread.is_alive():
    # Neuen Thread erstellen und starten
    
if not self.http_service.server_thread.is_alive():  
    # HTTP Service neu starten
```

### Troubleshooting Thread-Probleme

#### Häufige Thread-Ausfälle
```bash
# Logs nach Thread-Neustarts durchsuchen:
sudo journalctl -u heating-control.service | grep "thread died\|thread restarted"

# Häufige Ursachen:
# 1. Sensorfehler -> Buffer/Mixer Controller Crash
# 2. Hardware-Kommunikationsfehler -> PiFace-Thread Crash  
# 3. Speichermangel -> Zufällige Thread-Ausfälle
# 4. Konfigurationsfehler -> Controller-Initialisierung schlägt fehl
```

#### Thread Monitoring deaktivieren (Debugging)
```python
# In main.py run() Methode:
# Kommentiere diese Zeile aus:
# if loop_count % 10 == 0:
#     self._check_and_restart_threads()
```

#### Manueller Thread-Neustart (Emergency)
```bash
# Kompletten Service neu starten:
sudo systemctl restart heating-control.service

# Oder Python-Prozess neu starten:
sudo pkill -f "python.*main.py"
sudo systemctl start heating-control.service
```

#### Thread-Status prüfen  
```bash
# Aktuelle Thread-Anzahl prüfen:
ps -eLf | grep python | grep heating | wc -l

# Detaillierte Thread-Info:
ps -eLf | grep python | grep heating

# Memory-Usage pro Thread:
top -H -p $(pgrep -f "python.*main.py")
```

### Test Thread Monitoring
```bash
# Thread Monitoring Tests ausführen:
cd /path/to/HeizungPVMM
source .venv/bin/activate

# Basis Thread Monitoring Test:
python test/test_thread_monitoring.py

# Umfassender Test aller Komponenten:
python test/test_comprehensive_thread_monitoring.py
```

## Deinstallation
```bash
# Services stoppen und deaktivieren
sudo systemctl stop heating-control.service
sudo systemctl disable heating-control.service
sudo systemctl stop owfs-mount.service
sudo systemctl disable owfs-mount.service
sudo systemctl stop owserver.service
sudo systemctl disable owserver.service

# Service-Dateien entfernen
sudo rm /etc/systemd/system/heating-control.service
sudo rm /etc/systemd/system/owfs-mount.service
sudo rm -rf /etc/systemd/system/heating-control.service.d/

# systemd neu laden
sudo systemctl daemon-reload

# OWFS deinstallieren (optional)
sudo apt remove --purge owfs-fuse owfs-common owserver

# Mount-Punkt entfernen
sudo umount /mnt/1wire 2>/dev/null || true
sudo rmdir /mnt/1wire

# udev-Regeln entfernen
sudo rm /etc/udev/rules.d/99-heating-hardware.rules
sudo udevadm control --reload-rules
```