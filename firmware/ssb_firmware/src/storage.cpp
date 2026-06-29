#include "storage.h"

static File session_file;




bool storage_init() {
    if (!LittleFS.begin(true)) {
        Serial.println("ERROR: LittleFS mount failed");
        return false;
    }
    return true;
}


bool storage_open_session() {
    session_file = LittleFS.open("/session.csv", "w");
    if (!session_file) {
        Serial.println("ERROR: Failed to open session file for writing");
        return false;
    }
    session_file.println("timestamp_ms, skin_temp_c, humidity_pct, chamber_temp_c, gsr_raw");
    return true;
}


bool storage_write_row(unsigned long timestamp_ms, SensorReading reading) {
    if (!session_file) {
        Serial.println("ERROR: Session file is not open");
        return false;
    }
    session_file.printf("%lu,%.2f,%.2f,%.2f,%d\n", 
        timestamp_ms,
        reading.skin_temp_c,
        reading.humidity_pct,
        reading.chamber_temp_c,
        reading.gsr_raw);
    return true;
}


void storage_flush() {
    if (session_file) {
        session_file.flush();
    }
}


void storage_close_session() {
    if (session_file) {
        session_file.close();
    }
}


bool storage_session_exists() {
    if (!LittleFS.exists("/session.csv")) {
        return false;
    }
    
    File check_file = LittleFS.open("/session.csv", "r");
    if (!check_file) {
        return false;
    }

    size_t file_size = check_file.size();
    check_file.close();

    return file_size > 0;
}