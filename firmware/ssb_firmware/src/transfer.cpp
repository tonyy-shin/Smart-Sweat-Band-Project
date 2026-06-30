#include <Arduino.h>
#include <LittleFS.h>
#include "transfer.h"
#include "storage.h"

static const unsigned long CONFIRM_TIMEOUT_MS = 10000;

enum class Transfer_State {
    AWAIT_REQUEST,
    AWAIT_CONFIRM
};

static unsigned long confirm_start_ms = 0;

static Transfer_State sub_state = Transfer_State::AWAIT_REQUEST;




void transfer_reset() {
    sub_state = Transfer_State::AWAIT_REQUEST;
}


bool transfer_update() {
    switch (sub_state) {
        case Transfer_State::AWAIT_REQUEST: {
            if (Serial.available() <= 0) {
                return false;
            }

            char cmd = (char)Serial.read();
            if (cmd != 'R') {
                return false;
            }

            File f = LittleFS.open("/session.csv", "r");
            if (!f) {
                Serial.println("ERROR: no session");
                return false;
            }

            while (f.available()) {
                String line = f.readStringUntil('\n');
                Serial.println(line);
            }

            f.close();
            Serial.println("END");

            confirm_start_ms = millis();
            sub_state = Transfer_State::AWAIT_CONFIRM;
            return false;
        }

        case Transfer_State::AWAIT_CONFIRM: {
            if (Serial.available() > 0) {
            char cmd = (char)Serial.read();
            if (cmd == 'C') {
                storage_delete_session();
                sub_state = Transfer_State::AWAIT_REQUEST;
                return true;
            }
        }
        
            if (millis() - confirm_start_ms >= CONFIRM_TIMEOUT_MS) {
                sub_state = Transfer_State::AWAIT_REQUEST;
            }
        return false;
        }
    }
    return false;
}