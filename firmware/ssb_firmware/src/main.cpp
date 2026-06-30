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
    state_machine_update(); // does all the heavy lifitng
    led_update(); // off / solid / 500ms blink per state
    delay(10);
}