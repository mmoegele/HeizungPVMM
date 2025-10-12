# Quick Raspberry Pi Model Check
# ==============================

## Command Line Methods:

### Method 1: Check CPU Info
```bash
cat /proc/cpuinfo | grep -E "(Model|Revision)"
```

### Method 2: Device Tree Model
```bash
cat /sys/firmware/devicetree/base/model; echo
```

### Method 3: OS Release Info
```bash
cat /etc/os-release | grep PRETTY_NAME
```

### Method 4: Kernel and Hardware
```bash
uname -a
```

### Method 5: Hardware Detection
```bash
# Check GPIO chip
ls -la /dev/gpiochip*

# Check I2C buses available  
ls -la /dev/i2c*
sudo i2cdetect -y 1
# Check system hardware info
lscpu | grep -E "(Architecture|Model name)"
```

## I2C Bus Reference:

| Pi Model | I2C Bus | Notes |
|----------|---------|--------|
| Pi 1 Rev 1 | i2c-0 | Original model |  
| **Pi 1 Rev 2** | **i2c-1** | **Your Model - Use bus 1** |
| Pi 2/3/4 | i2c-1 | Standard |
| Pi Zero | i2c-1 | Same as Pi 2+ |

### Your System Details:
- **Model:** Raspberry Pi Model B Rev 2
- **Revision:** 000e  
- **I2C Bus:** Use `i2c-1` ✅
- **Available I2C devices:** `/dev/i2c-1`, `/dev/i2c-2`

## GPIO Pin Reference for 1-Wire:

| Pi Model | 1-Wire Data Pin | Physical Pin |
|----------|-----------------|--------------|
| All Models | GPIO 4 | Pin 7 |
| Power | 3.3V | Pin 1 |
| Ground | GND | Pin 6 |

## Quick Model Identification:

Run this one-liner:
```bash
echo "Pi Model: $(cat /sys/firmware/devicetree/base/model)" && echo "Revision: $(cat /proc/cpuinfo | grep Revision | cut -d':' -f2 | xargs)"
```