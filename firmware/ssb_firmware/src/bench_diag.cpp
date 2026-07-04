// BENCH DIAGNOSTIC — throwaway. Built only by [env:bench_diag]. Delete when done.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_SHT4x.h>
#include <Protocentral_MAX30205.h>

static Adafruit_SHT4x sht4 = Adafruit_SHT4x();
static MAX30205 tempSensor(MAX30205_ADDRESS2); // 0x48 — the driver defaults to 0x49!
static const int GSR_PIN = A0;

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10); // USB CDC: wait for the monitor so no prints are lost

    analogReadResolution(12);
    Wire.begin(D4, D5); // once, before any sensor begin()

    Serial.println("I2C scan 0x08-0x77:");
    int found = 0;
    for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("  ACK at 0x%02X\n", addr);
            found++;
        }
    }
    Serial.printf("Scan done: %d device(s). Expect 0x44 (SHT45) and 0x48 (MAX30205).\n", found);

    if (!tempSensor.begin()) Serial.println("ERROR: MAX30205 begin() failed");
    if (!sht4.begin())       Serial.println("ERROR: SHT45 begin() failed");
    sht4.setPrecision(SHT4X_HIGH_PRECISION);
    Wire.beginTransmission(0x48);
    Wire.write(0x01);                 // pointer → config register
    Wire.endTransmission(false);      // repeated START, hold the bus
    Wire.requestFrom(0x48, 1);
    if (Wire.available()) {
        uint8_t cfg = Wire.read();
        Serial.printf("MAX30205 config=0x%02X  DATA_FORMAT(bit5)=%d\n", cfg, (cfg >> 5) & 1);
    } else {
    Serial.println("MAX30205 config readback: no data");
    }
}

void loop() {
    // Strictly sequential: each call finishes its full bus transaction (STOP)
    // before the next one starts.
    float max_temp_c = tempSensor.getTemperature();   // raw sensor degC, no +63.8 offset
    int16_t max_raw = (int16_t)lroundf(max_temp_c * 256.0f);

    sensors_event_t humidity, temp;
    sht4.getEvent(&humidity, &temp);

    int gsr = analogRead(GSR_PIN);

    Serial.printf("MAX30205=%.2fC raw=0x%04X  SHT45=%.2fC %.1f%%RH  GSR=%d\n",
                  max_temp_c, (uint16_t)max_raw,
                  temp.temperature, humidity.relative_humidity, gsr);

    delay(1000);
}
