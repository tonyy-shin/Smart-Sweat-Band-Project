#include "sensors.h"

static Adafruit_SHT4x sht4 = Adafruit_SHT4x();
static const int GSR_PIN = A0;
static const float CALIBRATION_OFFSET = 63.8;

int gsr_baseline = 0;




void sensors_init() {
    pinMode(D4, INPUT_PULLUP);
    pinMode(D5, INPUT_PULLUP);
    Wire.begin(D4, D5);

    Wire.beginTransmission(0x48);
    Wire.write(0x01);
    Wire.write(0x00);
    Wire.endTransmission();
    delay(100);

    if (!sht4.begin()) {
        Serial.println("ERROR: Couldn't find SHT45 sensors");
        while (1) delay(1);
    }

    sht4.setPrecision(SHT4X_HIGH_PRECISION);
}


void gsr_calibrate() {
    while (analogRead(GSR_PIN) > 2300) {
        delay(500);
        Serial.print(".");
    }

    long sum = 0;
    for (int i = 0; i < 100; i++) {
        sum += analogRead(GSR_PIN);
        delay(50);
    }
    gsr_baseline = sum / 100;
}


SensorReading sensors_read() {
    sensors_event_t humidity, temp_sht45;
    sht4.getEvent(&humidity, &temp_sht45);

    float body_temp_c = 0.0;
    float raw_temp_c = 0.0;

    Wire.beginTransmission(0x48);
    Wire.write(0x00);
    Wire.endTransmission();
    Wire.requestFrom(0x48, 2);

    if (Wire.available() == 2) {
        byte msb = Wire.read();
        byte lsb = Wire.read();
        int16_t raw_temp = (msb << 8) | lsb;
        raw_temp_c = raw_temp * 0.00390625;
        body_temp_c = raw_temp_c + CALIBRATION_OFFSET;
    }

    SensorReading reading;
    reading.skin_temp_c = body_temp_c;
    reading.humidity_pct = humidity.relative_humidity;
    reading.chamber_temp_c = temp_sht45.temperature;
    reading.gsr_raw = analogRead(GSR_PIN);

    return reading;
}

bool gsr_is_sweating(int gsr_raw) {
    if (gsr_raw > 2300) { return false; }
    return gsr_raw < (gsr_baseline * 0.80);
}