#include <Arduino.h>
#include "sensors.h"
#include "storage.h"
#include "transfer.h"
#include "state_machine.h"

// Smart Sweat Band main entry point
// sensors.* - I2C sensors and GSR
// storage.* - LittleFS /session.csv(timestamp, skin temp, humidity, chamber temp, GSR)
// transfer.* - USB serial CSV handoff
// state_machine.* - IDLE -> RECORDING -> TRANSFER_READY, Button A(D1), LED(D3)

void setup() {
    Serial.begin(115200);
    analogReadResolution(12); // esp32 ADC is 12-bit

#ifdef SSB_DEBUG_SERIAL_BUTTON
    // BENCH DEBUG — remove before ship: wait for the USB CDC monitor so
    // init-phase errors (e.g. SHT45 failure) are visible.
    while (!Serial) delay(10);
#endif

    sensors_init(); // blocks until sensors are ready
    state_machine_init();

    // device is stuck in TRANSFER_READY state and can't record 
    // until the host confirms and the file is deleted
    if (storage_init() && storage_session_exists()) {
        transfer_reset();
        current_state = Device_State::TRANSFER_READY;
    }
}


void loop() {
#ifdef SSB_DEBUG_SERIAL_BUTTON
    // BENCH DEBUG — remove before ship: 's' over serial simulates Button A by
    // setting the same volatile flag the ISR sets. Must not touch Serial in
    // TRANSFER_READY — transfer_update() owns 'R'/'C' there.
    if (current_state != Device_State::TRANSFER_READY) {
        while (Serial.available() > 0) {
            if ((char)Serial.read() == 's') button_a_pressed = true;
        }
    }
    static Device_State dbg_last_state = Device_State::IDLE;
    if (current_state != dbg_last_state) {
        static const char* dbg_names[] = {"IDLE", "RECORDING", "TRANSFER_READY"};
        Serial.printf("STATE %s -> %s\n",
                      dbg_names[(int)dbg_last_state], dbg_names[(int)current_state]);
        dbg_last_state = current_state;
    }
#endif

    state_machine_update(); // does all the heavy lifitng
    led_update(); // off / solid / 500ms blink per state
    delay(10);
}