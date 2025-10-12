# Quick Fixes for Dashboard Issues
# ====================================

## Problem 1: No Sensors Showing

The main issue is your configuration has demo/mock mode enabled:

```yaml
development:
  demo_mode: true        # ← This enables mock sensors
  mock_hardware: true    # ← This enables mock hardware
```

**Fix Options:**

### Option A: Use Real Hardware (Recommended for Production)
Edit `heating_config.yaml`:
```yaml
development:
  demo_mode: false       # Use real sensors
  mock_hardware: false   # Use real PiFace hardware
```

### Option B: Keep Mock Mode but Add Mock Data
If you want to test with mock data, run this on your Raspberry Pi:

```bash
python3 -c "
from sensors import create_sensor_manager
from config import Config
import logging

config = Config()
logger = logging.getLogger('test')
sensor_manager = create_sensor_manager(config, logger)

# Add some mock temperature data
mock_temps = {
    'puffer_k_mitte': 45.5,
    'puffer_k_rueck': 42.3, 
    'puffer_k_vorlauf': 48.1,
    'puffer_m_vorlauf': 46.8,
    'puffer_m_mitte': 44.2,
    'puffer_m_rueck': 41.9,
    'solar_vorlauf': 35.7,
    'solar_ruecklauf': 32.4,
    'bhkw_vorlauf': 62.5,
    'mischer_fussboden': 28.3,
    'mischer_heizung': 51.2
}

for sensor_id, temp in mock_temps.items():
    sensor_manager.set_mock_temperature(sensor_id, temp)

print('Mock temperatures set!')
"
```

## Problem 2: Port Switching Not Working

**Root Cause:** Mock hardware mode + missing PiFace library

**Fix Steps:**

### Step 1: Install Missing Dependencies
```bash
pip install pifacecommon pifacedigitalio
```

### Step 2: Enable Real Hardware
In `heating_config.yaml`:
```yaml
development:
  mock_hardware: false   # Use real PiFace boards
```

### Step 3: Verify PiFace Setup
```bash
# Enable SPI interface
sudo raspi-config
# → Interface Options → SPI → Enable

# Test PiFace detection
sudo python3 -c "
import pifacedigitalio
try:
    board = pifacedigitalio.PiFaceDigital(0)
    print('✅ PiFace Board 0 detected')
    board.output_pins[0].turn_on()
    board.output_pins[0].turn_off()
    print('✅ Output control working')
except Exception as e:
    print(f'❌ PiFace error: {e}')
"
```

### Step 4: Test Output Control
```bash
# Use your improved test script
python3 test/toggle_piface_outputs.py --boards 2 --duration 1.0
```

## Problem 3: Dashboard API Issues

**Quick Test:**
```bash
# Check if API is responding
curl http://localhost:8080/api/health

# Check temperature endpoint
curl http://localhost:8080/api/temperatures

# Check IO status
curl http://localhost:8080/api/io/status
```

**If API isn't running:**
Make sure your main heating system is started:
```bash
python3 main.py
```

## Comprehensive Diagnostic

Run the comprehensive diagnostic script:
```bash
python3 dashboard_diagnostics.py --test-api --verbose
```

This will test:
- Local system components
- Sensor readings
- Hardware control
- API endpoints
- Output control

## Expected Results After Fixes:

### Dashboard Should Show:
- **11 temperature sensors** with real readings (or mock data)
- **10 controllable outputs** (heating elements, pumps, mixers)
- **16 digital inputs** (8 per board)
- **System status indicators** all green
- **Clickable output toggles** that actually control hardware

### API Should Return:
```json
// /api/temperatures
{
  "temperatures": {
    "puffer_k_mitte": 45.5,
    "puffer_k_rueck": 42.3,
    // ... 9 more sensors
  }
}

// /api/io/status  
{
  "outputs": {
    "0-0": false, "0-1": false, // ... 16 outputs
  },
  "inputs": {
    "0-0": false, "0-1": false, // ... 16 inputs  
  }
}
```

## Priority Order:
1. **Install pifacecommon** (fixes port switching)
2. **Disable mock_hardware** (enables real PiFace control)  
3. **Disable demo_mode** (enables real sensor readings)
4. **Test with diagnostic scripts**
5. **Verify dashboard functionality**