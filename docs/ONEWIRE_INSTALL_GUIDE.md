# One-Wire Temperature Sensor Installation Guide
# ==============================================

## Method 1: Direct GPIO One-Wire (Your Current Setup)

This is the standard Raspberry Pi approach using GPIO pins directly.

### 1. Enable One-Wire Interface
```bash
sudo raspi-config
# → Interface Options → 1-Wire → Enable
# → Reboot when prompted
```

### 2. Load One-Wire Kernel Modules
```bash
sudo modprobe w1-gpio
sudo modprobe w1-therm
```

### 3. Make Modules Load at Boot (Optional)
```bash
# Add to /etc/modules
echo "w1-gpio" | sudo tee -a /etc/modules
echo "w1-therm" | sudo tee -a /etc/modules
```

### 4. Check if Sensors are Detected
```bash
ls -la /sys/bus/w1/devices/
# Should show devices like "28-xxxxxxxxxxxx"
```

### 5. Test Reading Temperatures
```bash
# Replace xxxxxxxxxxxx with your actual device ID
cat /sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave
```

### 6. Run Diagnostic Script
```bash
python3 onewire_diagnostics.py --fix-paths
```

---

## Method 2: I2C Host Adapter (Sheepwalk Electronics RPI2)

If you're using a dedicated 1-Wire host adapter like the Sheepwalk RPI2 board:

### 1. Enable I2C Interface
```bash
sudo raspi-config
# → Interface Options → I2C → Enable
# OR manually edit /boot/config.txt and add:
# dtparam=i2c_arm=on
```

### 2. Load I2C Modules
```bash
sudo modprobe i2c-bcm2708
sudo modprobe i2c-dev
```

### 3. Make I2C Modules Load at Boot
```bash
# Add to /etc/modules
echo "i2c-bcm2708" | sudo tee -a /etc/modules  
echo "i2c-dev" | sudo tee -a /etc/modules
```

### 4. Install I2C Tools
```bash
sudo apt-get install i2c-tools
```

### 5. Detect the Host Adapter
```bash
# For newer Pi models (Pi 2, 3, 4):
sudo i2cdetect -y 1

# For original Pi Model A/B:
sudo i2cdetect -y 0

# Should show device at address 0x18 (DS2482-100)
# If you see all "--" like this:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:                         -- -- -- -- -- -- -- --
# 10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
# This means no I2C devices detected - see troubleshooting below
```

### 6. Install OWFS for I2C Interface
```bash
sudo apt-get install owfs ow-shell
```

### 7. Configure OWFS for I2C
```bash
sudo nano /etc/owfs.conf

# Comment out this line:
# server: FAKE = DS18S20,DS2405

# Add this line (use i2c-0 for older Pi models):
server: device=/dev/i2c-1
```

### 8. Restart OWFS Service
```bash
sudo service owserver restart
```

### 9. Test OWFS Detection
```bash
owdir
# Should list your temperature sensors like:
# /28.FC6711040000
# /28.B26518040000

# Read a temperature:
owread /28.FC6711040000/temperature
```

### 10. Mount OWFS for File Access (Optional)
```bash
sudo mkdir -p /mnt/1wire
sudo owfs --i2c=/dev/i2c-1 /mnt/1wire

# Then you can access sensors as files:
# /mnt/1wire/28.FC6711040000/temperature
```

### 11. Reading Temperatures from OWFS Mount Point

Once OWFS is mounted, you can read temperatures directly from files:

```bash
# List all available sensors
ls -la /mnt/1wire/
# Shows folders like: 28.FC6711040000, 28.B26518040000, etc.

# Read temperature from a specific sensor
cat /mnt/1wire/28.FC6711040000/temperature
# Returns: 23.125 (temperature in Celsius)

# Read multiple sensor properties
cat /mnt/1wire/28.FC6711040000/temperature    # Current temperature
cat /mnt/1wire/28.FC6711040000/family         # Sensor family (28 for DS18B20)
cat /mnt/1wire/28.FC6711040000/id             # Full sensor ID
cat /mnt/1wire/28.FC6711040000/alias          # Human-readable name (if set)

# Read all temperatures at once
for sensor in /mnt/1wire/28.*; do
  if [ -d "$sensor" ]; then
    id=$(basename "$sensor")
    temp=$(cat "$sensor/temperature" 2>/dev/null || echo "Error")
    echo "$id: ${temp}°C"
  fi
done
```

### 12. Programming Interface for OWFS

**Python example:**
```python
# Method 1: Direct file reading
def read_owfs_temperature(sensor_id):
    try:
        with open(f'/mnt/1wire/{sensor_id}/temperature', 'r') as f:
            return float(f.read().strip())
    except Exception as e:
        print(f"Error reading {sensor_id}: {e}")
        return None

# Usage
temp = read_owfs_temperature('28.FC6711040000')
print(f"Temperature: {temp}°C")

# Method 2: Using pyownet library
pip install pyownet

import pyownet
ow = pyownet.protocol.proxy(host="localhost", port=4304)
temp = ow.read('/28.FC6711040000/temperature')
print(f"Temperature: {float(temp)}°C")
```

**Shell script example:**
```bash
#!/bin/bash
# read_sensors.sh

OWFS_PATH="/mnt/1wire"

# Function to read temperature
read_temperature() {
    local sensor_id=$1
    local temp_file="${OWFS_PATH}/${sensor_id}/temperature"
    
    if [ -f "$temp_file" ]; then
        cat "$temp_file"
    else
        echo "ERROR: Sensor $sensor_id not found"
    fi
}

# Read specific sensor
read_temperature "28.FC6711040000"

# Read all sensors
for sensor in ${OWFS_PATH}/28.*; do
    if [ -d "$sensor" ]; then
        id=$(basename "$sensor")
        temp=$(read_temperature "$id")
        echo "$id: ${temp}°C"
    fi
done
```

### 13. OWFS Mount Point Advantages

**Benefits over direct owread commands:**
- **File-based access** - use standard file operations
- **No network calls** - direct filesystem access
- **Cacheable** - OWFS handles caching automatically
- **Standard tools** - use cat, grep, awk, etc.
- **Programming friendly** - easy to integrate into scripts

**Performance comparison:**
```bash
# Method A: OWFS mount (faster for multiple reads)
cat /mnt/1wire/28.FC6711040000/temperature

# Method B: owread command (network call each time)
owread /28.FC6711040000/temperature
```

### 14. Troubleshooting OWFS Mount

**Mount not working:**
```bash
# Check if OWFS daemon is running
sudo systemctl status owserver

# Check mount point
mount | grep 1wire
df -h /mnt/1wire

# Manual mount with debugging
sudo owfs -d --i2c=/dev/i2c-1 /mnt/1wire

# Unmount if needed
sudo umount /mnt/1wire
```

**No sensors appearing:**
```bash
# Check OWFS can see sensors
owdir

# Check I2C connection
sudo i2cdetect -y 1  # Should show device at 0x18

# Restart OWFS service
sudo systemctl restart owserver
sudo umount /mnt/1wire
sudo owfs --i2c=/dev/i2c-1 /mnt/1wire
```

---

## Which Method to Use?

### Determine Your Current Setup:

**Check what you actually have connected:**

```bash
# Method 1: Check for direct GPIO 1-Wire
ls -la /sys/bus/w1/devices/
# If you see "28-xxxxxxxxxxxx" folders, you have direct GPIO setup

# Method 2: Check for I2C host adapter  
sudo i2cdetect -y 1
sudo i2cdetect -y 0
# If you see device at 0x18, you have I2C host adapter

# Method 3: Check enabled interfaces
sudo raspi-config nonint get_onewire  # 0=enabled, 1=disabled
sudo raspi-config nonint get_i2c      # 0=enabled, 1=disabled

# Note: I2C can be enabled (returns 0) but have no devices connected
# This is normal - focus on whether you see actual devices, not just interface status
```

### Use Direct GPIO (Method 1) if:
- You have sensors connected directly to GPIO pins
- You see devices in `/sys/bus/w1/devices/`
- You want simpler setup with fewer components
- You have a small number of sensors (< 10)
- **This is what your current config expects**

### Use I2C Host Adapter (Method 2) if:
- You have the Sheepwalk RPI2 or similar I2C adapter
- `i2cdetect` shows device at address 0x18
- You need better electrical isolation
- You have many sensors on long cable runs
- You need more reliable communication

### Your Current Situation:
**CONFIRMED**: You have **Method 1 (Direct GPIO)** setup. 
- I2C is enabled but no I2C devices detected (no host adapter connected)
- `/dev/i2c-0` error confirms no I2C hardware in use
- You should use the Direct GPIO method above
- Skip all I2C-related instructions

---

## Troubleshooting

### No Sensors Detected (Direct GPIO):
```bash
# Check if GPIO 4 is configured for 1-Wire
dmesg | grep w1
# Should show w1-gpio messages

# Check device tree overlay
ls -la /boot/overlays/w1-gpio*
```

### No I2C Device Detected:
```bash
# Your situation: I2C enabled (returns 0) but no devices detected
# This means:
# - I2C interface is enabled but no I2C hardware connected
# - You don't have an I2C host adapter (like RPI2)
# - This confirms you should use Method 1 (Direct GPIO)

# Check I2C status:
sudo raspi-config nonint get_i2c   # Should return 0 (enabled) ✅
lsmod | grep i2c                   # Should show i2c modules ✅
ls -la /dev/i2c*                  # Should show /dev/i2c-1 ✅  
sudo i2cdetect -y 1               # Should show all "--" (no devices) ✅

# This is normal - I2C enabled but no I2C hardware connected
# Your system: I2C properly configured but not used for 1-Wire
```

### **CONFIRMED: You Have Direct GPIO Setup**
Since you get I2C errors, you should focus on **Method 1 (Direct GPIO)** setup.

### Update Your Heating Config

For **Direct GPIO** sensors, use paths like:
```yaml
sensors:
  one_wire_mount_point: "/sys/bus/w1/devices"
  temperature_sensors:
    sensor_name:
      path: "/sys/bus/w1/devices/28.xxxxxxxxxxxx/w1_slave"
```

For **OWFS mounted** sensors, use paths like:  
```yaml
sensors:
  one_wire_mount_point: "/mnt/1wire"
  temperature_sensors:
    sensor_name:
      path: "/mnt/1wire/28.xxxxxxxxxxxx"
```