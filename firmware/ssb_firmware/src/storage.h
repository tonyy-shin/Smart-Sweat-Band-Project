#pragma once

#include <LittleFS.h>
#include "sensors.h"

bool storage_init();
bool storage_open_session();
bool storage_write_row(unsigned long timestamp_ms, SensorReading reading);
void storage_flush();
void storage_close_session();
bool storage_session_exists();