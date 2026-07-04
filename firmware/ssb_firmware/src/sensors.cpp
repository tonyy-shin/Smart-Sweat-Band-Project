#include "sensors.h"

static Adafruit_SHT4x sht4 = Adafruit_SHT4x();
static const int GSR_PIN = A0;
// The MAX30205 on this board is a clone stuck in extended data format: it
// reports (true temp - 64 C) and ignores the DATA_FORMAT config bit
// (bench-verified 2026-07-04: config reads back 0x00, raw word tracks ambient - 64).
static const float MAX30205_EXT_FORMAT_OFFSET_C = 64.0;
// TODO: -0.2 C is an empirically-estimated placeholder pending calibration
// against a reference thermometer.
static const float SKIN_TEMP_CAL_OFFSET_C = -0.2;

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
#ifdef SSB_DEBUG_SERIAL_BUTTON
        // BENCH DEBUG — remove before ship: still halts, but says why every second.
        while (1) {
            Serial.println("ERROR: SHT45 not responding");
            delay(1000);
        }
#else
        while (1) delay(1);
#endif
    }

    sht4.setPrecision(SHT4X_HIGH_PRECISION);
}


void gsr_calibrate() {
    // BENCH DEBUG — remove before ship: contact-wait skipped in bench builds, so
    // baseline lands at the offline value (~2450). gsr_is_sweating() then never
    // fires at the bench — fine, it gates no FSM transition.
#ifndef SSB_DEBUG_SERIAL_BUTTON
    while (analogRead(GSR_PIN) > 2300) {
        delay(500);
        Serial.print(".");
    }
#endif

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
        body_temp_c = raw_temp_c + MAX30205_EXT_FORMAT_OFFSET_C + SKIN_TEMP_CAL_OFFSET_C;
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