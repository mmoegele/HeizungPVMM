# Quick Fix for Your 1-Wire Sensor Issues
# ========================================

## CONFIRMED: You Have Direct GPIO Setup
Your I2C errors confirm you're using direct GPIO 1-Wire (not I2C host adapter).

## Step-by-Step Fix:

### 1. Enable 1-Wire Interface
```bash
sudo raspi-config
# → Interface Options → 1-Wire → Enable
# → Finish → Reboot
```

### 2. After Reboot, Load Modules
```bash
sudo modprobe w1-gpio
sudo modprobe w1-therm
```

### 3. Check for Sensors
```bash
ls -la /sys/bus/w1/devices/
```

**Expected Results:**
- If working: You'll see folders like `28-xxxxxxxxxxxx`
- If not working: Only `w1_bus_master1` folder

### 4. If No Sensors Found:

#### Check 1-Wire Status:
```bash
# Check if 1-Wire is enabled
sudo raspi-config nonint get_onewire
# Should return 0 (enabled) or 1 (disabled)

# Check kernel messages
dmesg | grep w1
# Should show w1-gpio initialization messages

# Check device tree overlay
grep w1 /boot/config.txt
# Should show: dtoverlay=w1-gpio
```

#### Check Physical Connections:
- **Data pin**: Connected to GPIO 4 (Pin 7)
- **Power**: 3.3V (Pin 1) and Ground (Pin 6)
- **Pull-up resistor**: 4.7kΩ between data and 3.3V

### 5. Test Reading Temperature:
```bash
# Replace xxxxxxxxxxxx with actual device ID from step 3
cat /sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave
```

**Expected output:**
```
a2 01 4b 46 7f ff 0c 10 1c : crc=1c YES
a2 01 4b 46 7f ff 0c 10 1c t=26125
```
Temperature = 26125 / 1000 = 26.125°C

### 6. Run Your Diagnostic Script:
```bash
python3 onewire_diagnostics.py --fix-paths
```

## Update Your Configuration:

Once sensors are detected, update `heating_config.yaml`:

```yaml
# Change from demo mode to real sensors
development:
  demo_mode: false      # Use real sensors
  mock_hardware: false  # Use real PiFace

# Update sensor paths (use actual device IDs from step 3)
sensors:
  one_wire_mount_point: "/sys/bus/w1/devices"
  temperature_sensors:
    puffer_k_mitte:
      path: "/sys/bus/w1/devices/28.ACTUAL_DEVICE_ID/w1_slave"
      description: "Konrad Buffer Middle"
    # ... repeat for all sensors
```

## If Still No Sensors:

### Hardware Troubleshooting:
1. **Check wiring** - Data to GPIO 4, power to 3.3V, ground to GND
2. **Check pull-up resistor** - 4.7kΩ between data and 3.3V
3. **Test with single sensor** - Disconnect all but one sensor
4. **Check sensor IDs** - Use multimeter to verify sensor is working

### Software Troubleshooting:
```bash
# Force reload kernel modules
sudo rmmod w1_therm w1_gpio
sudo modprobe w1_gpio
sudo modprobe w1_therm

# Check GPIO 4 is not used by other services
sudo lsof /dev/gpiomem
```

## Success Indicators:
- ✅ `ls /sys/bus/w1/devices/` shows `28-xxxxxxxxxxxx` folders
- ✅ `cat /sys/bus/w1/devices/28-xxx/w1_slave` shows temperature data
- ✅ No more sensor reading errors in heating system logs
- ✅ Dashboard shows real temperature readings