// 8x8 LED matrix: breathing guide and simple states (tasks F9, F10).
#pragma once
#include <Arduino.h>

enum LedMode { LED_WAITING, LED_IDLE, LED_GUIDE, LED_DONE };

void ledsBegin();
void ledsSet(LedMode mode);   // LED_GUIDE restarts the breathing cycle at "breathe in"
void ledsUpdate();            // call often; draws at ~40 frames/s
