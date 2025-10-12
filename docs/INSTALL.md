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

# Test 1: I2C Host Adapter erkennen (falls verwendet)
sudo i2cdetect -y 1
# Sollte Gerät bei 0x18 zeigen für DS2482-100

# Test 2: PiFace Boards testen
python3 diagnostics/toggle_piface_outputs.py --boards 2
# Sollte beide Boards erkennen und Outputs schalten

# Test 3: Temperatur-Sensoren testen
python3 diagnostics/onewire_diagnostics.py --fix-paths

# Test 4: Komplett-Diagnose
python3 diagnostics/dashboard_diagnostics.py
```

### 7. Systemkonfiguration anpassen
```bash
# Hauptkonfigurationsdatei bearbeiten
cp heating_config.yaml heating_config.yaml.backup
nano heating_config.yaml

# Für I2C Host Adapter Setup:
# - demo_mode: false
# - mock_hardware: false  
# - sensors.one_wire_mount_point: "/mnt/1wire"
# - sensor paths: "/mnt/1wire/28.DEVICE_ID" (ohne /temperature)

# Für direkte GPIO Setup:
# - sensors.one_wire_mount_point: "/sys/bus/w1/devices"  
# - sensor paths: "/sys/bus/w1/devices/28.DEVICE_ID/w1_slave"

# Sensor IDs ermitteln:
# I2C Host Adapter: ls -la /mnt/1wire/28.*
# Direkte GPIO: ls -la /sys/bus/w1/devices/28.*
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

# Komplette System-Diagnose durchführen
python3 diagnostics/dashboard_diagnostics.py

# Einzelne Komponenten testen
echo "=== I2C Host Adapter Test ==="
sudo i2cdetect -y 1

echo "=== OWFS Mount Test ==="
ls -la /mnt/1wire/28.*

echo "=== PiFace Test ==="
python3 diagnostics/toggle_piface_outputs.py --boards 2 --duration 0.5

echo "=== Temperatur Test ==="
python3 diagnostics/onewire_diagnostics.py

echo "=== Web-Dashboard Test ==="
python3 -c "
import requests
try:
    response = requests.get('http://localhost:8080/api/status', timeout=5)
    print(f'Dashboard Status: {response.status_code}')
    print(f'Response: {response.json()}')
except Exception as e:
    print(f'Dashboard nicht erreichbar: {e}')
"

# Log-Ausgaben prüfen
echo "=== Service Logs ==="
sudo journalctl -u heating-control.service --no-pager -n 20
```

## Fehlerbehebung

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

### Service-Debug
```bash
# Service-Status detailliert
sudo systemctl status heating-control.service -l

# Service-Logs in Echtzeit
sudo journalctl -u heating-control.service -f

# Alle heating-bezogenen Services
sudo systemctl list-units --all | grep -E "(owserver|owfs|heating)"

# Service neu starten
sudo systemctl restart heating-control.service
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