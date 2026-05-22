#include <Wire.h>
#include <Adafruit_SHT4x.h>

// Create SHT45 sensor object
Adafruit_SHT4x sht4 = Adafruit_SHT4x();

void setup() {
  Serial.begin(115200);
  while (!Serial) { 
    delay(10); 
  }
  
  Serial.println("Initializing Sensors...");

  // Enable internal pull-up resistors for the clone MAX30205
  // Stabilizes the I2C line for BOTH sensors
  pinMode(D4, INPUT_PULLUP);
  pinMode(D5, INPUT_PULLUP);
  
  // Initialize I2C on D4 (SDA) and D5 (SCL)
  Wire.begin(D4, D5);

  // 1. Initialize MAX30205
  Wire.beginTransmission(0x48);
  Wire.write(0x01);
  Wire.write(0x00);
  Wire.endTransmission();
  
  // Delay to allow the sensor to stabilize
  delay(100);
  Serial.println("SUCCESS: MAX30205 hardware bypass configured");

  // 2. Initialize Adafruit SHT45
  if (!sht4.begin()) {
    Serial.println("ERROR: Couldn't find SHT45 sensor");
    while (1) delay(1);
  }
  Serial.println("SUCCESS: SHT45 sensor found");
  
  // Set SHT45 to highest precision 
  sht4.setPrecision(SHT4X_HIGH_PRECISION);

  Serial.println("Starting data stream in 3 seconds...\n");
  delay(3000);
}

void loop() {
  sensors_event_t humidity, temp_sht45;
  sht4.getEvent(&humidity, &temp_sht45);
  
  float bodyTempC = 0.0;
  float raw_tempC = 0.0;
  
  Wire.beginTransmission(0x48);
  Wire.write(0x00);
  Wire.endTransmission();

  Wire.requestFrom(0x48, 2);
  
  if (Wire.available() == 2) {
    byte msb = Wire.read();
    byte lsb = Wire.read();

    // Combine MSB and LSB into a signed 16-bit integer
    int16_t raw = (int16_t)(msb << 8 | lsb);

    // Convert raw value to Celsius
    raw_tempC = raw * 0.00390625;

    // Apply the 63.8 degree software offset for the ZIZEV clone
    float calibration_offset = 63.8;
    bodyTempC = raw_tempC + calibration_offset;
  }

  // --- Print Unified Output to Serial Monitor ---
  Serial.println("====================================");
  
  // Print Calibrated Body Temp
  Serial.print("MAX30205 Body Temp:      "); 
  Serial.print(bodyTempC); 
  Serial.print(" C  (Raw: ");
  Serial.print(raw_tempC);
  Serial.println(" C)");

  // Print Ambient Temp
  Serial.print("SHT45 Ambient Temp:      "); 
  Serial.print(temp_sht45.temperature); 
  Serial.println(" C");

  // Print Humidity
  Serial.print("SHT45 Relative Humidity: "); 
  Serial.print(humidity.relative_humidity); 
  Serial.println(" %");
  
  Serial.println("====================================\n");
  
  delay(1000); 
}