// INMP441 over I2S at 16 kHz -> DC removal -> low-pass -> 8 kHz 16-bit (tasks F2, F3).
#pragma once
#include <Arduino.h>

bool audioBegin();                 // false if the I2S driver could not start
void audioRead(int16_t* out);      // blocks ~10 ms, then writes BLOCK_SAMPLES samples at 8 kHz
bool audioSilent();                // true after 1 s of identical samples: no mic power, SD not connected or wrong pins
