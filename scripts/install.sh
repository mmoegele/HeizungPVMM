#!/bin/bash
# Installationsskript für die Heizungssteuerung

# Prüfe, ob Script als root läuft
if [ "$EUID" -ne 0 ]; then 
    echo "Bitte als root ausführen (sudo)"
    exit 1
fi

# Konfigurationsdatei für 1-Wire
echo "# 1-Wire Konfiguration
dtoverlay=w1-gpio,gpiopin=4
dtparam=i2c_arm=on" >> /boot/config.txt

# Erstelle Log-Verzeichnis
mkdir -p /var/log/heating
chown -R pi:pi /var/log/heating

# Kopiere und aktiviere Service
cp heating-control.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable heating-control.service

# Erstelle Backup-Verzeichnis
mkdir -p /home/pi/Documents/HeizungPVMM/backups
chown -R pi:pi /home/pi/Documents/HeizungPVMM/backups

echo "Installation abgeschlossen. System neu starten mit: sudo reboot"