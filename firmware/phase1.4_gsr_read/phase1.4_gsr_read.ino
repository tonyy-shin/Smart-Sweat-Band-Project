// Define Analog Pin for GSR Sensor
// On XIAO ESP32S3, Pin D0 acts as Analog Pin A0
const int GSR_PIN = A0; 

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  
  Serial.println("Initializing Calibrated GSR Sensor...");
  Serial.println("Starting data stream in 3 seconds...\n");
  delay(3000);
}

void loop() {
  // Read analog value from the GSR sensor
  // ESP32S3 has 12-bit ADC, meaning values 0 - 4095
  int gsrValue = analogRead(GSR_PIN);

  Serial.print("Grove GSR Conductivity: "); 
  Serial.print(gsrValue); 

  /* THRESHOLD REASONING
   * The Grove GSR uses INVERTED analog scale on ESP32S3:
   * * 1. Empty Probes / Band Off: Floats around 2400 - 2500. 
   * Reasoning: open circuit defaults to ~1.9V.
   * * 2. Resting / Dry Skin: Sits around 1600 - 1800.
   * Reasoning: Skin contact closes the loop, dropping the voltage baseline.
   * * 3. Active Sweating / Moisture: Drops drastically to 380 - 650.
   * Reasoning: Electrolytes in sweat highly conduct electricity, crashing 
   * the circuit's resistance and pulling the analog voltage close to 0V.
   */
  
  if (gsrValue > 2300) {
    // High resistance = Open circuit
    Serial.println("  --> [Status: OFFLINE / BAND REMOVED]");
    
  } else if (gsrValue > 1000) {
    // Medium resistance = Skin contact, but dry
    Serial.println("  --> [Status: DRY SKIN / BAND ON]");
    
  } else {
    // Low resistance = Electrolytes/Moisture detected!
    Serial.println("  --> [Status: ACTIVE SWEATING / WET]");
  }
  
  delay(500); 
}