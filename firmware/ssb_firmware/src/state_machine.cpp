#include "state_machine.h"
#include "transfer.h"

Device_State current_state = Device_State::IDLE;

volatile bool button_a_pressed = false;

static volatile unsigned long last_press_a_ms = 0;





static void IRAM_ATTR on_button_a_pressed() {
    unsigned long now = millis();
    if (now - last_press_a_ms >= 200) {
        button_a_pressed = true;
        last_press_a_ms = now;
    }
}


void state_machine_init() {
    pinMode(BUTTON_A_PIN, INPUT_PULLUP);
    pinMode(LED_PIN, OUTPUT);

    attachInterrupt(digitalPinToInterrupt(BUTTON_A_PIN), on_button_a_pressed, FALLING);

    current_state = Device_State::IDLE;
    button_a_pressed = false;
}


void state_machine_update() {
    static unsigned long last_sample_ms = 0;
    static unsigned long last_flush_ms = 0;

    switch (current_state) {
        case Device_State:: IDLE:
            if (button_a_pressed) {
                button_a_pressed = false;

                storage_init();
                gsr_calibrate();
                storage_open_session(gsr_baseline);
                storage_flush();

                last_sample_ms = millis();
                last_flush_ms = millis();
                current_state = Device_State::RECORDING;
            }
            break;

        case Device_State::RECORDING:
            if (button_a_pressed) {
                button_a_pressed = false;
                storage_close_session();
                transfer_reset();
                current_state = Device_State::TRANSFER_READY;
                break;
            }

            if (millis() - last_sample_ms >= 1000) {
                SensorReading reading = sensors_read();
                storage_write_row(millis(), reading);
                last_sample_ms = millis();
            }

            if (millis() - last_flush_ms >= 60000) {
                storage_flush();
                last_flush_ms = millis();
            }
            break;

        case Device_State::TRANSFER_READY:
            if (transfer_update()) {
                current_state = Device_State::IDLE;
            }
            break; 
    }
}


void led_update() {
    static unsigned long led_timer_ms = 0;
    static bool led_on = false;

    switch (current_state) {
        case Device_State::IDLE:
            digitalWrite(LED_PIN, LOW);
            break;

        case Device_State::RECORDING:
            digitalWrite(LED_PIN, HIGH);
            break;
        
        case Device_State::TRANSFER_READY:
            if (millis() - led_timer_ms >= 500) {
                led_timer_ms = millis();
                led_on = !led_on;
                digitalWrite(LED_PIN, led_on ? HIGH : LOW);
            }
            break;
        }
}