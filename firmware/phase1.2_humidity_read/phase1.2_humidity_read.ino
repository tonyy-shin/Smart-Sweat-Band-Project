#include <Wire.h>
#include <Adafruit_SHT4x.h>

// Create the SHT45 sensor object
Adafruit_SHT4x sht4 = Adafruit_SHT4x();

void setup() {
  Serial.begin(115200);
  
  while (!Serial) { 
    delay(10); 
  }
  
  Serial.println("Initializing SHT45 Humidity Sensor...");

  // Enable internal pull-up resistors for stability
  pinMode(D4, INPUT_PULLUP);
  pinMode(D5, INPUT_PULLUP);
  
  // Initialize I2C on D4 (SDA) and D5 (SCL)
  Wire.begin(D4, D5);

  // Initialize Adafruit SHT45
  if (!sht4.begin()) {
    Serial.println("ERROR: Couldn't find SHT45 sensor");
    while (1) delay(1); // Stop the program here if the sensor fails
  }
  Serial.println("SUCCESS: SHT45 sensor found");
  
  // Set SHT45 to highest precision 
  sht4.setPrecision(SHT4X_HIGH_PRECISION);
  
  // Ensure the internal heater is completely off to prevent false temperature readings
  sht4.setHeater(SHT4X_NO_HEATER);

  Serial.println("Starting data stream in 3 seconds...\n");
  delay(3000);
}

void loop() {
  sensors_event_t humidity, temp_sht45;
  
  sht4.getEvent(&humidity, &temp_sht45);
  
  Serial.println("====================================");
  
  Serial.print("SHT45 Ambient Temp:      "); 
  Serial.print(temp_sht45.temperature); 
  Serial.println(" C");

  Serial.print("SHT45 Relative Humidity: "); 
  Serial.print(humidity.relative_humidity); 
  Serial.println(" %");
  
  Serial.println("====================================\n");

  delay(1000); 
}