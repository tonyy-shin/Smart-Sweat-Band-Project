#include "state_machine.h"
#include "ble_transfer.h"

Device_State current_state = Device_State::IDLE;

volatile bool button_a_pressed = false;
volatile bool button_b_pressed = false;

static volatile unsigned long last_press_a_ms = 0;
static volatile unsigned long last_press_b_ms = 0;

static bool error_pattern_active = false;





static void IRAM_ATTR on_button_a_pressed() {
    unsigned long now = millis();
    if (now - last_press_a_ms >= 200) {
        button_a_pressed = true;
        last_press_a_ms = now;
    }
}


static void IRAM_ATTR on_button_b_pressed() {
    unsigned long now = millis();
    if (now - last_press_b_ms >= 200) {
        button_b_pressed = true;
        last_press_b_ms = now;
    }
}


void state_machine_init() {
    pinMode(BUTTON_A_PIN, INPUT_PULLUP);
    pinMode(BUTTON_B_PIN, INPUT_PULLUP);
    pinMode(LED_PIN, OUTPUT);

    attachInterrupt(digitalPinToInterrupt(BUTTON_A_PIN), on_button_a_pressed, FALLING);
    attachInterrupt(digitalPinToInterrupt(BUTTON_B_PIN), on_button_b_pressed, FALLING);

    current_state = Device_State::IDLE;
    button_a_pressed = false;
    button_b_pressed = false;
}


void state_machine_update() {
    static unsigned long last_sample_ms = 0;
    static unsigned long last_flush_ms = 0;
    static unsigned long transfer_start_ms = 0;

    switch (current_state) {
        case Device_State:: IDLE:
            if (button_a_pressed) {
                button_a_pressed = false;

                storage_init();
                storage_open_session();
                
                gsr_calibrate();

                last_sample_ms = millis();
                last_flush_ms = millis();
                current_state = Device_State::RECORDING;
            }
            break;

        case Device_State::RECORDING:
            if (button_a_pressed) {
                button_a_pressed = false;
                storage_close_session();
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
            if (button_b_pressed) {
                button_b_pressed = false;
                if (storage_session_exists()) {
                    ble_start_advertising();
                    transfer_start_ms = millis();
                    current_state = Device_State::TRANSFERRING;
                }
                else {
                    error_pattern_active = true;
                    current_state = Device_State::IDLE;
                }
            }
            break;
        
        case Device_State::TRANSFERRING:
        if (ble_ack_received()) {
            storage_delete_session();
            ble_stop();
            current_state = Device_State::IDLE;
        }
        else if (millis() - transfer_start_ms >= 30000) {
            ble_stop();
            current_state = Device_State::TRANSFER_READY;
        }
        break;   
    }
}


void led_update() {
    static unsigned long led_timer_ms = 0;
    static bool led_on = false;

    static unsigned long error_timer_ms = 0;
    static bool error_led_on = false;
    static int error_blink_count = 0;

    if (error_pattern_active) {
        if (millis() - error_timer_ms >= 100) {
            error_timer_ms = millis();
            error_led_on = !error_led_on;
            digitalWrite(LED_PIN, error_led_on ? HIGH : LOW);

            if (!error_led_on) {
                error_blink_count++;
            }

            if (error_blink_count >= 3) {
                digitalWrite(LED_PIN, LOW);
                error_blink_count = 0;
                error_led_on = false;
                error_pattern_active = false;
            }
        }
        return;
    }
    
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
        
        case Device_State::TRANSFERRING:
            if (millis() - led_timer_ms >= 100) {
                led_timer_ms = millis();
                led_on = !led_on;
                digitalWrite(LED_PIN, led_on ? HIGH : LOW);
            }
            break;
        }
}