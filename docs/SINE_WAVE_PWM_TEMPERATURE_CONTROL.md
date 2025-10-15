# Adaptive Sine Wave PWM Temperature-Based On/Off Control

## Overview

The heat exchanger now uses **Adaptive Sine Wave PWM** to control pump operation based on **absolute temperature positioning** rather than simple temperature differences. This creates intelligent, self-adapting pump operation that learns and responds to temperature behavior.

## How Absolute Temperature Controls On/Off Behavior

### 1. Temperature Delta Calculation
```
Temperature Delta = Current Temperature - Target Temperature
Positive Delta = Above target (need cooling/less heating)
Negative Delta = Below target (need more heating)
```

### 2. Intelligent Control Modes Based on Absolute Temperature

#### 🔥 **Overshoot Protection** (Current > Target + 10°C)
- **Pump State**: Always ON (100% duty cycle for cooling)
- **When**: Temperature overshoots by more than 10°C above target
- **Example**: Current = 78°C, Target = 65°C → Delta = +13°C → Continuous cooling
- **Purpose**: Rapid cooling to prevent runaway heating

#### ❄️ **Undershoot Protection** (Current < Target - 10°C)
- **Pump State**: Always ON (100% duty cycle for heating)
- **When**: Temperature is more than 10°C below target
- **Example**: Current = 45°C, Target = 65°C → Delta = -20°C → Continuous heating
- **Purpose**: Rapid heating when far from target

#### � **Adaptive PWM Mode** (Target ± 10°C range)
- **Pump State**: Intelligent sine wave PWM with adaptive modulation
- **Frequency**: 10 Hz (100ms cycle time)
- **When**: Temperature within normal operating range around target

## Adaptive Sine Wave PWM Formula

```
Temperature Delta = Current Temperature - Target Temperature
Base Duty Cycle = f(temperature_delta)  // Smart positioning: 10-90%
Adaptive Sine Amplitude = f(|temperature_delta|)  // 5-12% based on proximity
Cooling Bias = -30% × Sine Amplitude (when above target)
Sine Modulation = Adaptive Amplitude × sin(2π × time / 60s) + Cooling Bias
Final Duty Cycle = Base Duty + Sine Modulation
```

## Absolute Temperature-to-Control Strategy Mapping

| Temperature Position | Base Duty | Sine Amp | Control Strategy |
|---------------------|-----------|----------|------------------|
| > Target + 10°C | 100% | - | **Overshoot cooling** |
| Target + 5°C to +10°C | 10% | ±12% | Reduce heating |
| Target + 2°C to +5°C | 20% | ±8% | Minimal heating |
| Target + 0.5°C to +2°C | 30% | ±5% | Gentle maintenance |
| Target ± 0.5°C | 40% | ±5% | **Balanced control** |
| Target -0.5°C to -2°C | 55% | ±8% | Moderate heating |
| Target -2°C to -5°C | 70% | ±8% | Increased heating |
| Target -5°C to -10°C | 85% | ±12% | Strong heating |
| < Target - 10°C | 100% | - | **Continuous heating** |

## Detailed Adaptive PWM Operation Examples

### Example 1: Slightly Below Target (-2°C Delta)
```
Current Temperature: 63°C
Target Temperature: 65°C
Temperature Delta: -2°C (below target)

Control Mode: Adaptive Sine Wave PWM
Base Duty Cycle: 55% (moderate heating)
Adaptive Sine Amplitude: ±8% (reasonably close to target)
Cooling Bias: None (below target)
PWM Frequency: 10 Hz (100ms cycles)

Time Series (adaptive sine wave modulation):
  0s: 55.0% duty (55ms ON, 45ms OFF) - sine = 0.00
 15s: 63.0% duty (63ms ON, 37ms OFF) - sine = +1.00 (peak heating)
 30s: 55.0% duty (55ms ON, 45ms OFF) - sine = 0.00
 45s: 47.0% duty (47ms ON, 53ms OFF) - sine = -1.00 (trough)
 60s: 55.0% duty (55ms ON, 45ms OFF) - sine = 0.00 (cycle repeats)
```

### Example 2: Above Target with Cooling Bias (+3°C Delta)
```
Current Temperature: 68°C
Target Temperature: 65°C
Temperature Delta: +3°C (above target)

Control Mode: Adaptive Sine Wave PWM with Cooling Bias
Base Duty Cycle: 20% (minimal heating)
Adaptive Sine Amplitude: ±8% (reasonably close)
Cooling Bias: -2.4% (30% of 8% downward)
PWM Frequency: 10 Hz (100ms cycles)

Time Series (biased toward cooling):
  0s: 17.6% duty (18ms ON, 82ms OFF) - sine = 0.00 + bias
 15s: 23.6% duty (24ms ON, 76ms OFF) - sine = +1.00 + bias
 30s: 17.6% duty (18ms ON, 82ms OFF) - sine = 0.00 + bias  
 45s: 11.6% duty (12ms ON, 88ms OFF) - sine = -1.00 + bias
 60s: 17.6% duty (18ms ON, 82ms OFF) - sine = 0.00 + bias
```

### Example 3: Severe Overshoot (+13°C Delta)
```
Current Temperature: 78°C
Target Temperature: 65°C
Temperature Delta: +13°C (overshoot protection)

Control Mode: Continuous Cooling
Duty Cycle: 100%
Pump State: Always ON for maximum cooling
No PWM switching - continuous operation until below 75°C
```

## Adaptive Sine Wave Benefits for Temperature Control

### 🎯 **Intelligent Positioning**
- **Absolute temperature awareness** - knows if above or below target
- **Adaptive response strategies** based on temperature position
- **Cooling bias** when above target automatically reduces heating

### 🔄 **Adaptive Oscillation**
- **Variable sine amplitude** (5-12%) based on proximity to target
- **60-second sine wave period** creates natural biological-like variation
- **Smart modulation** - larger swings when far from target, gentle when close

### 🌡️ **Temperature Response Intelligence**
- **Above target** → Lower base duty + cooling bias → Gentle cooling approach
- **Below target** → Higher base duty + normal sine → Aggressive heating
- **Close to target** → Fine control with small sine amplitudes
- **Far from target** → Strong control with large sine amplitudes

### ⚙️ **Mechanical & Safety Benefits**
- **Overshoot protection** prevents runaway heating (>10°C above target)
- **Undershoot protection** provides rapid heating when needed (<10°C below)
- **Smooth adaptive transitions** reduce pump stress more than fixed patterns
- **Self-learning behavior** adapts to thermal characteristics

## Real-World Operation Timeline

```
Target Temperature: 65°C

Time 0:00 - Current: 55°C (10°C difference)
└─ Mode: Continuous (100% duty)
   Pump: Always ON

Time 0:30 - Current: 62°C (3°C difference)  
└─ Mode: Sine Wave PWM (45% base duty)
   Pump: 45ms ON, 55ms OFF (10 Hz switching)

Time 1:00 - Current: 64.5°C (0.5°C difference)
└─ Mode: Sine Wave PWM (15% base duty) 
   Pump: 15ms ON, 85ms OFF (10 Hz switching)

Time 1:30 - Current: 65.0°C (0°C difference)
└─ Mode: Sine Wave PWM (15% base duty)
   Pump: Maintains gentle circulation
```

## Advanced Control Logic

### Safety Override
```python
if sensor_error:
    pump_state = ON  # Always ON for safety
    mode = "safety"
```

### Mode Transitions
```python
if temp_diff >= 10.0:
    mode = "continuous"
    duty_cycle = 100%
    
elif temp_diff < 10.0:
    mode = "sine_wave_pwm" 
    base_duty = calculate_base_duty(temp_diff)
    sine_mod = 10% * sin(2π * time / 60s)
    duty_cycle = base_duty + sine_mod
```

### PWM Timing Precision
```python
# 10 Hz = 100ms cycle time
cycle_time = 0.1 seconds
pump_on_time = cycle_time * (duty_cycle / 100)
pump_off_time = cycle_time - pump_on_time

# High-precision polling for accurate timing
polling_rate = 20ms  # 50 Hz polling for millisecond accuracy
```

## Configuration Parameters

```yaml
heat_exchanger:
  target_temperature: 65.0      # Target temperature in °C
  continuous_threshold: 10.0    # Switch to continuous mode at 10°C difference
  update_interval: 5.0          # Non-PWM mode update rate in seconds
  
  # PWM parameters (automatically calculated)
  # - Base frequency: 10 Hz (100ms cycles)
  # - Sine period: 60 seconds
  # - Sine amplitude: ±10%
  # - Duty range: 5% to 95%
```

## Monitoring and Diagnostics

The system provides real-time monitoring of sine wave PWM operation:

```json
{
  "sine_wave_pwm_control": {
    "base_frequency_hz": 10.0,
    "current_frequency_hz": 10.0,
    "duty_cycle_percent": 42.3,
    "pump_on_time_ms": 42.3,
    "pump_off_time_ms": 57.7,
    "cycle_time_ms": 100.0,
    "sine_wave_period_s": 60.0,
    "sine_elapsed_s": 23.5
  }
}
```

## Summary

The adaptive sine wave PWM system provides:

1. **Intelligent Temperature Targeting**: Uses absolute positioning instead of simple differences
2. **Adaptive Control Strategies**: Different approaches above vs below target temperature
3. **Overshoot Protection**: Automatic continuous cooling when >10°C above target
4. **Smart Modulation**: Variable sine amplitude (5-12%) based on proximity to target
5. **Cooling Bias**: Automatic downward sine bias when above target for gentle cooling
6. **Self-Learning Behavior**: Adapts control patterns to thermal characteristics
7. **Biological Intelligence**: Mimics natural temperature regulation with adaptive responses

This creates an advanced, intelligent temperature control system that learns and adapts its behavior based on absolute temperature positioning, providing professional-grade control with built-in safety protection and energy optimization.