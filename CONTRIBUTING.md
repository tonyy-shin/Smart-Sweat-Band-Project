# Contributing to Smart Sweat-Band (SSB)

Thank you for contributing to the Smart Sweat-Band project! This document outlines the development workflow, coding standards, and testing requirements.

## Table of Contents
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Standards](#code-standards)
- [Commit Guidelines](#commit-guidelines)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)

---

## Development Setup

### Prerequisites
- PlatformIO (https://platformio.org/install)
- VS Code (recommended IDE)
- Git

### Initial Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/Smart-Sweat-Band.git
   cd Smart-Sweat-Band
   ```

2. **Install PlatformIO CLI**
   ```bash
   pip install platformio
   ```

3. **Install VS Code Extension** (Optional but recommended)
   - Search for "PlatformIO IDE" in VS Code extensions

4. **Verify Hardware Connection**
   - Connect XIAO ESP32S3 via USB-C
   - Run: `pio device list`

5. **Build & Upload Test**
   ```bash
   pio run -t upload
   pio device monitor --speed 115200
   ```

---

## Project Structure

```
Smart-Sweat-Band/
├── firmware/
│   ├── phase1.0_baseline_thermometry/
│   ├── phase1.1_temp_read/
│   ├── phase1.2_humidity_read/
│   ├── phase1.3_temp_humidity_read/
│   ├── phase1.4_gsr_read/
│   └── phase1.5_sensor_fusion/
│       └── phase.1.5_sensor_fusion.ino
├── hardware/
│   ├── BOM.md
│   ├── photos/
│   └── schematics/
├── platformio.ini          # Build configuration
├── .editorconfig           # Code style rules
├── .gitignore              # Git exclusions
├── CONTRIBUTING.md         # This file
├── README.md               # Project overview
└── libraries.md            # Dependency documentation
```

---

## Code Standards

### Naming Conventions
| Element | Convention | Example |
|---------|-----------|---------|
| Variables | snake_case | `gsr_baseline`, `body_temp_c` |
| Constants | UPPER_SNAKE_CASE | `MAX_GSR_VALUE`, `I2C_ADDR_SHT45` |
| Functions | snake_case | `read_temperature()`, `calibrate_gsr()` |
| Classes | PascalCase | `SensorArray`, `DataLogger` |

### Indentation & Formatting
- **Spaces:** 2 spaces (enforced by `.editorconfig`)
- **Line Length:** Max 100 characters
- **Braces:** Allman style (opening brace on new line for functions)

```cpp
void read_sensor_data()
{
  int value = analogRead(GSR_PIN);
  if (value > 2300) {
    Serial.println("Band removed");
  }
}
```

### Comments
- Add comments only for **WHY**, not WHAT
- Use `//` for single-line comments
- Use `/* */` for multi-line comments at file header

**Good ✓**
```cpp
// GSR uses inverted scale: higher resistance = lower conductivity
int sweat_threshold = gsr_baseline * 0.80;
```

**Bad ✗**
```cpp
int sweat_threshold = gsr_baseline * 0.80;  // Sets sweat threshold to 80% of baseline
```

### Magic Numbers → Named Constants
```cpp
// BAD
if (gsrValue > 2300) { /* ... */ }

// GOOD
const int GSR_DISCONNECTED_THRESHOLD = 2300;
if (gsrValue > GSR_DISCONNECTED_THRESHOLD) { /* ... */ }
```

### Serial Output Format
```cpp
Serial.println("====================================");
Serial.print("Skin Temp (MAX30205):    "); 
Serial.print(bodyTempC); 
Serial.println(" °C");
Serial.println("====================================\n");
```

---

## Commit Guidelines

### Commit Message Format
```
<type>: <subject>

<body>

<footer>
```

### Types
- `feat:` New sensor reading or feature
- `fix:` Bug fix in existing code
- `refactor:` Code reorganization without behavior change
- `docs:` Documentation updates
- `test:` Test additions or fixes
- `chore:` Build config, dependencies

### Examples

**Good ✓**
```
feat: add BLE telemetry streaming to mobile app

- Implements GATT characteristics for real-time data
- Adds service UUID 180A for device info
- Configures 250ms broadcast interval for low power

Closes #42
```

**Bad ✗**
```
updated code
fixed stuff
new version
```

---

## Testing Requirements

### Before Pushing

1. **Code Compiles**
   ```bash
   pio run
   ```

2. **Device Uploads Successfully**
   ```bash
   pio run -t upload
   pio device monitor --speed 115200
   ```

3. **Serial Output Verification**
   - Check that all sensors output valid readings
   - Verify no I2C errors in serial monitor
   - Test GSR calibration sequence

4. **Hardware Test Checklist**
   - [ ] MAX30205 reads skin temperature (30-42°C range)
   - [ ] SHT45 reads chamber humidity and temperature
   - [ ] GSR calibration completes in < 10 seconds
   - [ ] All three sensors output simultaneously
   - [ ] Device remains stable for 60+ seconds

---

## Pull Request Process

### Before Creating a PR

1. **Branch Naming**
   ```bash
   git checkout -b feat/bluetooth-comms
   git checkout -b fix/i2c-timeout
   git checkout -b docs/api-reference
   ```

2. **Commit Your Changes**
   ```bash
   git add <files>
   git commit -m "feat: your commit message"
   ```

3. **Sync with Main**
   ```bash
   git fetch origin
   git rebase origin/main
   ```

4. **Push to Remote**
   ```bash
   git push origin feat/bluetooth-comms
   ```

### PR Description Template

```markdown
## Description
Brief summary of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Changes
- Item 1
- Item 2

## Testing
- [ ] Code compiles without errors
- [ ] Device uploads and runs without crashes
- [ ] Serial output is correct

## Related Issues
Closes #123
```

### Review Requirements
- [ ] Code follows style guidelines (checked by `.editorconfig`)
- [ ] All tests pass
- [ ] Documentation is updated
- [ ] No compiler warnings

---

## Troubleshooting

### PlatformIO Issues
```bash
# Clean and rebuild
pio run --target clean
pio run

# Reset environment
rm -rf .pio/
pio run
```

### Serial Monitor Not Working
```bash
# List available ports
pio device list

# Connect to specific port
pio device monitor --port /dev/ttyACM0 --speed 115200
```

### I2C Communication Errors
- Verify pull-up resistors on SDA/SCL
- Check address conflicts (use `phase1.0_baseline_thermometry/i2c_scanner`)
- Ensure Qwiic connectors are seated properly

---

## Questions?

- Open an issue on GitHub
- Check existing issues for similar questions
- Review README.md for hardware pinout reference

**Thank you for contributing!**
