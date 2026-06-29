#pragma once

#include <Adafruit_SHT4x.h>
#include <Wire.h>

struct SensorReading {
    float skin_temp_c;
    float humidity_pct;
    float chamber_temp_c;
    int gsr_raw;
};

extern int gsr_baseline;

void sensors_init();
void gsr_calibrate();
SensorReading sensors_read();
bool gsr_is_sweating(int gsr_raw);