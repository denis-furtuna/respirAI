// Four LEDs behind the printed lung panel: trachea, both lobes, and the "AI" of the wordmark (tasks F-LED1 to F-LED5).
#pragma once
#include <Arduino.h>

enum LedMode { LED_WAITING, LED_IDLE, LED_GUIDE, LED_DONE };

void ledsBegin();
void ledsSet(LedMode mode);                    // safe from the Bluetooth task; LED_GUIDE always restarts at "breathe in"
void ledsStatus(bool error, uint8_t battery);  // for the "AI" status patterns; battery 255 = unknown
void ledsUpdate();                             // call often from loop(); updates at 50 frames/s
