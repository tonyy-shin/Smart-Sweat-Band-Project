#include <Wire.h>

void setup() {
  Serial.begin(9600);
  
  // Enable internal pull-up resistors on the I2C pins.
  pinMode(D4, INPUT_PULLUP);
  pinMode(D5, INPUT_PULLUP);
  
  // Initialize I2C on the XIAO ESP32-S3's hardware I2C pins.
  // D4 = SDA, D5 = SCL
  Wire.begin(D4, D5);

  // Write 0x00 to the configuration register (0x01) to set the sensor
  // to continuous conversion mode and clear any previous configuration.
  Wire.beginTransmission(0x48);
  Wire.write(0x01); // Point to configuration register
  Wire.write(0x00); // 0x00 = continuous mode, active, all defaults
  Wire.endTransmission();

  // delay to allow the sensor to stabilize after configuration
  delay(100);
}

void loop() {
  // Step 1: Point the sensor's internal register pointer to the
  // Temperature Register (0x00) so the next read pulls temperature data
  Wire.beginTransmission(0x48);
  Wire.write(0x00);
  Wire.endTransmission();

  // Step 2: Request 2 bytes of data from the sensor.
  // The MAX30205 temperature register is 16 bits (2 bytes): MSB first, LSB second.
  Wire.requestFrom(0x48, 2);
  
  // Step 3: Only proceed if both bytes arrived successfully
  if (Wire.available() == 2) {
    byte msb = Wire.read();
    byte lsb = Wire.read();

    // Combine MSB and LSB into a signed 16-bit integer.
    // The MAX30205 uses two's complement format, so int16_t is required.
    int16_t raw = (int16_t)(msb << 8 | lsb);

    // Convert raw value to Celsius.
    // Resolution is 1/256 = 0.00390625 degrees per LSB.
    float raw_temp = raw * 0.00390625;

    // --- SOFTWARE CALIBRATION ---
    // The ZIZEV clone of the MAX30205 has a consistent ~60°C offset baked in
    // at the hardware level. The root cause is unknown but it is likely a manufacturing
    // defect or misconfigured internal reference on the clone chip.
    //
    // Evidence: Raw output was stable at ~-36°C in a ~24°C room environment.
    // The sensor responded correctly to temperature changes (blowing hot air into the sensor
    // confirmed accurate relative tracking), so only the absolute baseline
    // is wrong, not the sensor's ability to detect changes.
    //
    // Fix: A +60°C software offset is applied to correct the absolute baseline.
    // This offset was determined by comparing raw output to room temperature. 
    // If this sketch is used with a genuine Protocentral MAX30205, remove the calibration_offset line.
    float calibration_offset = 60.0;
    float temp = raw_temp + calibration_offset;

    // Print both calibrated and raw values for debugging
    Serial.print("Calibrated Temp: ");
    Serial.print(temp);
    Serial.print(" C  |  Raw Sensor Output: ");
    Serial.print(raw_temp);
    Serial.println(" C");
  }

  // Wait 1 second before taking next reading
  delay(1000);
}
