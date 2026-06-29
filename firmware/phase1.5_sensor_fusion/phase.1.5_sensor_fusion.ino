#include <Wire.h>
#include <Adafruit_SHT4x.h>

Adafruit_SHT4x sht4 = Adafruit_SHT4x();
const int GSR_PIN = A0; // XIAO D0 = Analog A0

int gsr_baseline = 0; // Will store dry-skin baseline

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  
  Serial.println("Initializing Sensors...");

  // I2C INITIALIZATION
  pinMode(D4, INPUT_PULLUP);
  pinMode(D5, INPUT_PULLUP);
  Wire.begin(D4, D5);

  // 1. Initialize MAX30205
  Wire.beginTransmission(0x48);
  Wire.write(0x01);
  Wire.write(0x00);
  Wire.endTransmission();
  delay(100);
  Serial.println("SUCCESS: MAX30205 hardware bypass configured");

  // 2. Initialize Adafruit SHT45
  if (!sht4.begin()) {
    Serial.println("ERROR: Couldn't find SHT45 sensor");
    while (1) delay(1);
  }
  Serial.println("SUCCESS: SHT45 sensor found");
  sht4.setPrecision(SHT4X_HIGH_PRECISION);

  // 3. GSR CALIBRATION
  Serial.println("\nGSR CALIBRATION REQUIRED");
  Serial.println("Please put on the GSR sensor (or pinch the hooks).");
  Serial.print("Waiting for skin contact ");

  // The code pauses here and waits until it detects a human (value drops below 2300)
  while(analogRead(GSR_PIN) > 2300) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nSkin contact detected. Hold still for 5 seconds...");

  /* WHY WE WAIT 5 SECONDS & AVERAGE 100 SAMPLES FOR THE BASELINE
   * * 1. INDIVIDUAL SKIN VARIABILITY
   * GSR measures skin conductance (the inverse of electrical resistance). 
   * Every athlete has completely unique skin characteristics.
   * - Athlete A might have dry skin, giving a resting baseline of 1800.
   * - Athlete B might have naturally moist skin, giving a resting baseline of 900.
   * If we used a hardcoded threshold (like "Sweating = < 1000"), the device would 
   * falsely claim Athlete B is permanently sweating.
   * * 2. SOFTWARE FILTERING
   * - The 5-second delay gives the physical connection time to settle and stabilize 
   * on the athlete's skin.
   * - The loop takes 100 consecutive readings over those 5 seconds (50ms spacing).
   * - Summing them and dividing by 100 creates a filter.
   */
  long sum = 0;
  for(int i = 0; i < 100; i++) {
    sum += analogRead(GSR_PIN); // Gather the raw data points
    delay(50);                  // Space the readings evenly across 5 seconds (100 * 50ms = 5000ms)
  }
  gsr_baseline = sum / 100;    // average

  Serial.print("SUCCESS: Dry Skin Baseline set to: ");
  Serial.println(gsr_baseline);
  
  Serial.println("\nStarting master data stream in 3 seconds...\n");
  delay(3000);
}

void loop() {
  // 1. READ SHT45 (AMBIENT CLIMATE)
  sensors_event_t humidity, temp_sht45;
  sht4.getEvent(&humidity, &temp_sht45);
  
  // 2. READ MAX30205 (SKIN TEMPERATURE)
  float bodyTempC = 0.0;
  float raw_tempC = 0.0;
  
  Wire.beginTransmission(0x48);
  Wire.write(0x00);
  Wire.endTransmission();
  Wire.requestFrom(0x48, 2);
  
  if (Wire.available() == 2) {
    byte msb = Wire.read();
    byte lsb = Wire.read();
    int16_t raw = (int16_t)(msb << 8 | lsb);
    raw_tempC = raw * 0.00390625;
    float calibration_offset = 63.8;
    bodyTempC = raw_tempC + calibration_offset;
  }

  // 3. READ GSR (SWEAT METRICS)
  int gsrValue = analogRead(GSR_PIN);

  // PRINT DASHBOARD TO SERIAL MONITOR
  Serial.println("====================================");
  
  Serial.print("Chamber Temp (SHT45):    "); 
  Serial.print(temp_sht45.temperature); 
  Serial.println(" °C");

  Serial.print("Chamber Hum (SHT45):     "); 
  Serial.print(humidity.relative_humidity); 
  Serial.println(" %");

  Serial.print("Skin Temp (MAX30205):    "); 
  Serial.print(bodyTempC); 
  Serial.print(" °C  (Raw: ");
  Serial.print(raw_tempC);
  Serial.println(" °C)");

  Serial.print("Sweat Metric (GSR):      "); 
  Serial.print(gsrValue); 
  
  // SWEAT LOGIC
  // A 20% drop from their calculated baseline dictates significant sweating or sympathetic stress.
  int sweat_threshold = gsr_baseline * 0.80; 

  if (gsrValue > 2300) {
    Serial.println(" -> [Status: OFFLINE / BAND REMOVED]");
  } 
  else if (gsrValue < sweat_threshold) {
    // analog value below the 20% threshold drop
    Serial.println(" -> [Status: ACTIVE SWEATING / WET]");
  } 
  else {
    // Current value remains close to their personalized calibration point
    Serial.println(" -> [Status: DRY SKIN / RESTING]");
  }
  
  Serial.println("====================================\n");
  
  delay(1000); // Main loop runs once per second
}