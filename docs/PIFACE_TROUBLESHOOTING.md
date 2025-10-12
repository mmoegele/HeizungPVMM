# PiFace Digital I/O Troubleshooting Guide

## When `toggle_piface_outputs.py` isn't doing anything

### 1. **Run with Verbose Output**

First, try the improved version with more diagnostic output:

```bash
python3 test/toggle_piface_outputs.py --boards 2
```

### 2. **Test in Mock Mode First**

To verify the script logic works:

```bash
python3 test/toggle_piface_outputs.py --boards 2 --mock
```

If this works but real hardware doesn't, it's a hardware/driver issue.

### 3. **Run Complete Diagnostics**

Use the comprehensive diagnostic script:

```bash
python3 piface_diagnostics.py
python3 piface_diagnostics.py --verbose  # More detailed output
```

### 4. **Common Issues and Solutions**

#### A. **No Output at All**
- **Check SPI is enabled**: `sudo raspi-config` → Interface Options → SPI → Enable
- **Check permissions**: Try running with `sudo python3 test/toggle_piface_outputs.py --boards 2`
- **Check hardware connections**: Ensure PiFace boards are properly seated

#### B. **Import Errors**
```bash
# Install PiFace libraries
pip3 install pifacedigitalio

# Or if using system Python:
sudo apt-get update
sudo apt-get install python3-pifacedigitalio
```

#### C. **GPIO/Interrupt Errors**
The system includes a GPIO patch, but if you see GPIO-related errors:
```bash
# Test the GPIO fix directly
python3 -c "from gpio import test_gpio_functionality; test_gpio_functionality()"
```

#### D. **Hardware Not Responding**
```bash
# Test hardware detection
lsmod | grep spi        # Should show SPI modules loaded
ls /dev/spi*            # Should show SPI devices

# Test with direct PiFace tools (if installed)
python3 -c "import pifacedigitalio; pifacedigitalio.PiFaceDigital(0).output_pins[0].turn_on()"
```

### 5. **Expected Output from Working System**

When the script works correctly, you should see:

```
🔧 Starting PiFace test with 2 boards
   Mock mode: False
   Duration: 2.0s
   Delay between pins: 0.03s
🔍 Hardware diagnostics:
   GPIO patch applied: True
   Mock mode active: False
   Board status: {0: {'available': True, 'responsive': True}, 1: {'available': True, 'responsive': True}}

🔛 Turning all outputs ON
   Board 0: ✅✅✅✅✅✅✅✅
   Board 1: ✅✅✅✅✅✅✅✅

⏰ All outputs ON — waiting 2.0 seconds

🔲 Turning all outputs OFF
   Board 0: ✅✅✅✅✅✅✅✅
   Board 1: ✅✅✅✅✅✅✅✅

✅ Completed toggling outputs
```

### 6. **Quick Status Check**

Add this to your main application to check PiFace status at startup:

```python
# In main.py, after hardware initialization
if hasattr(self.hardware, 'run_board_diagnostics'):
    diag = self.hardware.run_board_diagnostics()
    print(f"PiFace Status: {diag}")
```

### 7. **Manual Hardware Test**

If everything else fails, test manually:

```python
python3 -c "
import pifacedigitalio
board = pifacedigitalio.PiFaceDigital(0)
print('Turning on output 0')
board.output_pins[0].turn_on()
input('Press Enter to turn off...')
board.output_pins[0].turn_off()
print('Done')
"
```

### 8. **Check System Logs**

```bash
# Check for hardware-related errors
dmesg | grep -i spi
dmesg | grep -i piface

# Check system logs
sudo journalctl -u your-heating-service --since "10 minutes ago"
```

### Remember:

1. Always run on the actual Raspberry Pi, not remotely
2. Make sure no other process is using the PiFace boards
3. Check physical connections and power
4. Try with `sudo` if you get permission errors
5. The improved scripts now show exactly what's happening at each step