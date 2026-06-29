#pragma once

#include "sensors.h"
#include "storage.h"

enum class Device_State {
    IDLE,
    RECORDING,
    TRANSFER_READY,
    TRANSFERRING
};

extern Device_State current_state;

extern volatile bool button_a_pressed;
extern volatile bool button_b_pressed;

const int BUTTON_A_PIN = D1;
const int BUTTON_B_PIN = D2;
const int LED_PIN = D3;

void state_machine_init();
void state_machine_update();
void led_update();