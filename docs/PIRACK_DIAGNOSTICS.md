# PiRack Hardware Interface Detection
# ==================================

## PiRack System Detected

Since you mentioned **PiRack**, this changes the diagnostic approach significantly.
PiRack systems often have their own hardware interface methods.

## PiRack-Specific Checks:

### 1. Check for PiRack Hardware Interface
```bash
# Check for PiRack-specific devices
ls -la /dev/tty* | grep -i piface
ls -la /dev/spi*

# Check for PiRack modules in kernel
lsmod | grep -E "(piface|pirack)"

# Check for custom PiRack overlays
ls -la /boot/overlays/ | grep -i "piface\|pirack"
```

### 2. Check PiRack Documentation Path
```bash
# Look for PiRack-specific config files
find /etc -name "*piface*" -o -name "*pirack*" 2>/dev/null
find /opt -name "*piface*" -o -name "*pirack*" 2>/dev/null
```

### 3. Check PiRack Software Installation
```bash
# Check if PiRack software is installed
dpkg -l | grep -E "(piface|pirack)"
pip list | grep -E "(piface|pirack)"

# Check for PiRack services
systemctl list-units | grep -E "(piface|pirack)"
```

### 4. PiRack-Specific Hardware Detection
```bash
# PiRack may use different hardware interfaces
# Check for expansion boards
i2cdetect -y 1  # Already done - no devices
i2cdetect -y 2  # Check bus 2 (you have /dev/i2c-2)

# Check SPI devices (PiRack might use SPI)
ls -la /dev/spi*
```

## PiRack Temperature Sensor Integration:

PiRack systems typically provide:
1. **Hardware abstraction layer** - sensors might not appear in `/sys/bus/w1/devices/`
2. **Custom software interface** - may need specific libraries
3. **Different sensor paths** - could be in custom locations
4. **API-based access** - sensors accessed via network/software API

## Next Steps:

### A. Check what PiRack hardware you have connected:
```bash
# Try I2C bus 2 (since you have /dev/i2c-2)
sudo i2cdetect -y 2

# Check for PiRack-specific hardware signatures
dmesg | grep -i "piface\|pirack\|expansion"
```

### B. Check your PiRack documentation:
- What model PiRack do you have?
- Does it include temperature sensor interfaces?
- What software is required?

### C. Check if sensors are accessible via PiRack API:
```bash
# Look for PiRack web interface or API
netstat -tlnp | grep -E "(80|8080|3000|5000)"
curl -s http://localhost/api/sensors 2>/dev/null || echo "No API response"
```

## Update Your Configuration:

If PiRack provides **network/API access** to sensors, you might need to change your heating system config from file-based sensor reading to API-based reading.

**Example API-based sensor config:**
```yaml
sensors:
  type: "pirack_api"  # Custom sensor type
  base_url: "http://pirack-ip:port"
  # Instead of file paths
```

## Questions for You:

1. **What PiRack model/system do you have?**
2. **How are temperature sensors normally accessed on your PiRack?**  
3. **Do you have PiRack-specific software installed?**
4. **Does PiRack provide a web interface or API?**

Run the detection commands above and let me know what you find!