# Complete Hardware Setup Diagnostic
# ===================================
# Your Setup: 1-Wire Host Adapter + 2x PiFace + PiRack

## Your Hardware Configuration:

### 1. **1-Wire Host Adapter** (I2C-based)
- Should appear at I2C address **0x18** (DS2482-100)
- Handles temperature sensors via I2C-to-1-Wire bridge
- Uses **Method 2** from our installation guide

### 2. **Two PiFace Digital Boards**  
- Digital I/O for pumps, valves, heating elements
- Connected via PiRack expansion system
- Uses SPI interface (not I2C)

### 3. **PiRack System**
- Provides expansion and connectivity
- Allows multiple boards to connect cleanly

## Diagnostic Commands for Your Setup:

### A. Check 1-Wire Host Adapter (I2C)
```bash
# Check I2C bus 1 for host adapter
sudo i2cdetect -y 1
# Should show device at 0x18

# Check I2C bus 2 (you have this device)  
sudo i2cdetect -y 2
# May show PiRack-related I2C devices
```

### B. Check PiFace Boards (SPI)
```bash
# Check SPI devices (PiFace uses SPI)
ls -la /dev/spi*

# Check for PiFace kernel modules
lsmod | grep spi
lsmod | grep piface

# Check PiFace detection
sudo python3 -c "
try:
    import pifacedigitalio
    board0 = pifacedigitalio.PiFaceDigital(0)
    board1 = pifacedigitalio.PiFaceDigital(1)
    print('✅ Both PiFace boards detected')
except Exception as e:
    print(f'❌ PiFace error: {e}')
"
```

### C. Check OWFS for 1-Wire Sensors
```bash
# Install OWFS if not already installed
sudo apt-get install owfs ow-shell

# Check OWFS configuration
cat /etc/owfs.conf | grep -v "^#" | grep -v "^$"

# Test OWFS detection
owdir
owread --dirall /

# Check for temperature sensors
find /mnt/1wire -name "temperature" 2>/dev/null | head -5
```

## Expected Results:

### ✅ **Working Setup Should Show:**

**I2C Detection:**
```bash
sudo i2cdetect -y 1
# Should show:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 10: -- -- -- -- -- -- -- -- 18 -- -- -- -- -- -- --
#                               ^^^ DS2482 1-Wire host adapter
```

**PiFace Detection:**
```bash
# Should load without errors
python3 test/toggle_piface_outputs.py --boards 2
```

**OWFS Temperature Sensors:**
```bash
owdir
# Should show:
# /28.FC6711040000
# /28.B26518040000
# ... (your temperature sensors)
```

## Troubleshooting Your Setup:

### Issue 1: No 1-Wire Host Adapter (0x18 missing)
```bash
# Check I2C is enabled
sudo raspi-config → Interface Options → I2C → Enable

# Check physical connections via PiRack
# - Is 1-Wire host adapter properly seated?
# - Are I2C pins (SDA/SCL) connected through PiRack?
```

### Issue 2: PiFace Boards Not Detected
```bash
# Check SPI is enabled  
sudo raspi-config → Interface Options → SPI → Enable

# Install PiFace libraries
pip install pifacecommon pifacedigitalio

# Check PiRack connections
# - Are PiFace boards properly connected to PiRack?
# - Is SPI routed through PiRack correctly?
```

### Issue 3: OWFS Not Finding Sensors
```bash
# Configure OWFS for I2C host adapter
sudo nano /etc/owfs.conf

# Comment out:
# server: FAKE = DS18S20,DS2405

# Add:
server: device=/dev/i2c-1

# Restart OWFS
sudo service owserver restart
```

## Update Your Configuration:

### For Your Setup, Use These Paths:
```yaml
# heating_config.yaml
development:
  demo_mode: false      # Use real sensors
  mock_hardware: false  # Use real PiFace boards

# OWFS-based sensor paths (not direct GPIO)
sensors:
  one_wire_mount_point: "/mnt/1wire"
  temperature_sensors:
    puffer_k_mitte:
      path: "/mnt/1wire/28.ACTUAL_DEVICE_ID"  # No /w1_slave suffix
      description: "Konrad Buffer Middle"
    # ... etc for all sensors

hardware:
  piface:
    board_count: 2  # Your two PiFace boards
```

## Quick Test Sequence:

Run these in order:

1. **Check hardware detection:**
   ```bash
   sudo i2cdetect -y 1    # Look for 0x18
   sudo i2cdetect -y 2    # Check PiRack I2C
   ```

2. **Test PiFace:**
   ```bash
   python3 test/toggle_piface_outputs.py --boards 2
   ```

3. **Test 1-Wire sensors:**
   ```bash
   owdir
   ```

4. **Test complete system:**
   ```bash
   python3 main.py  # Should work without sensor errors
   ```

Let me know what you see from the detection commands!