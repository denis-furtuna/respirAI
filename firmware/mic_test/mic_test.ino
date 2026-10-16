// respirAI microphone test (task F2): the INMP441 on its own, with no Bluetooth and no app.
// Flash this sketch, open the Serial Monitor at 115200 and read what it says. When the mic is right, flash
// firmware/respirai again. Same pins and I2S setup as the firmware (respirai/config.h, respirai/audio.cpp).
//
// At start it checks the wiring and names the likely fault. Then, every 0.5 s, one line: the level, a meter, the
// peak, and how loud that peak would be in the app at the firmware's MIC_GAIN. Tap the chest piece: the line jumps.
// Type p + Enter for the Serial Plotter view (level, peak and background as curves), r + Enter to check again.
//
// Hear it on the computer: close the Serial Monitor and run  python firmware/mic_test/listen.py  It sends a + Enter,
// and the sketch streams the audio over the USB cable exactly as the phone would get it (8 kHz, 16-bit, the
// firmware's filter and MIC_GAIN) until it gets x + Enter. Each frame: "RA", uint16 sequence, 80 int16 samples (LE).
#include <ESP_I2S.h>

// ---------- as firmware/respirai/config.h ----------
constexpr int PIN_MIC_SCK = 7;    // D8
constexpr int PIN_MIC_WS  = 8;    // D9
constexpr int PIN_MIC_SD  = 9;    // D10
constexpr uint32_t CAPTURE_RATE = 16000;
constexpr float MIC_GAIN = 4.0f;  // only to show what the app would get; change it in config.h, not here

// ---------- the test ----------
constexpr int WINDOW = CAPTURE_RATE / 10;   // 100 ms per reading
constexpr int REPORT_EVERY = 5;             // readings per report line: 0.5 s
constexpr int HISTORY = 50;                 // readings kept for the background: 5 s
constexpr float FULL = 8388608.0f;          // 2^23, full scale of a 24-bit sample
constexpr int32_t CLIP = 8380000;           // a sample this loud counts as clipped
constexpr float FLOOR_DB = -90.0f;          // left end of the meter; the INMP441's own noise is about -87 dBFS
constexpr int BAR = 30;                     // meter width in characters: 3 dB each
constexpr float TAP_DB = 20.0f;             // a peak this far above the background is a tap or a sound
constexpr float LOUD_DB = -20.0f;           // a background this loud in a quiet room is a fault, not sound

constexpr int BLOCK_SAMPLES = 80;           // 10 ms at 8 kHz per audio frame, as one Bluetooth packet

static I2SClass i2s;
static bool i2sOn = false;
static bool plotter = false;
static bool streaming = false;              // audio frames to listen.py instead of text
static int32_t raw[WINDOW];
static float history[HISTORY];
static int historyCount = 0, historyHead = 0;

struct Reading {
  float rmsDb = FLOOR_DB, peakDb = FLOOR_DB, dcPercent = 0, appPercent = 0;
  bool flat = true;        // every sample the same: no sound at all
  int32_t value = 0;       // that value, when flat
  uint32_t clipped = 0;
};

// A slot listened to for 1 s (defined up here: Arduino declares the functions that use it above them).
struct Listen {
  bool ok = false, live = false, zero = true;
  int32_t value = 0;
  float rmsDb = FLOOR_DB, dcPercent = 0;
};

static float dbfs(double amplitude) { return 20.0f * log10f(fmaxf((float)amplitude, 1.0f) / FULL); }

static bool startMic(i2s_std_slot_mask_t slot) {
  if (i2sOn) i2s.end();
  i2s.setPins(PIN_MIC_SCK, PIN_MIC_WS, -1, PIN_MIC_SD);
  // As the firmware: 24-bit samples in 32-bit slots, one slot. L/R tied to GND = the left slot.
  i2sOn = i2s.begin(I2S_MODE_STD, CAPTURE_RATE, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO, slot);
  return i2sOn;
}

// 100 ms of samples -> level, peak and DC offset in dBFS of the 24-bit full scale.
static bool readWindow(Reading& r) {
  if (!i2sOn) return false;
  size_t got = 0;
  const uint32_t start = millis();
  while (got < sizeof(raw)) {
    got += i2s.readBytes(reinterpret_cast<char*>(raw) + got, sizeof(raw) - got);
    if (millis() - start > 1000) return false;   // the I2S clock isn't running
  }
  double sum = 0;
  int32_t lo = INT32_MAX, hi = INT32_MIN;
  for (int i = 0; i < WINDOW; i++) {
    const int32_t v = raw[i] >> 8;   // the 24-bit sample, sign kept
    sum += v;
    lo = min(lo, v);
    hi = max(hi, v);
    if (v >= CLIP || v <= -CLIP) r.clipped++;
  }
  const double mean = sum / WINDOW;
  double squares = 0, peak = 0;
  for (int i = 0; i < WINDOW; i++) {
    const double d = (raw[i] >> 8) - mean;
    squares += d * d;
    peak = fmax(peak, fabs(d));
  }
  r.rmsDb = dbfs(sqrt(squares / WINDOW));
  r.peakDb = dbfs(peak);
  r.dcPercent = 100.0f * (float)mean / FULL;
  r.flat = lo == hi;
  r.value = lo;
  r.appPercent = fminf(100.0f, 100.0f * (float)peak / 256.0f * MIC_GAIN / 32767.0f);   // as audio.cpp: 24 -> 16 bit, x MIC_GAIN
  return true;
}

// ---------- the audio stream: the same processing as respirai/audio.cpp ----------
constexpr int TAPS = 31;     // windowed-sinc low-pass at 3.5 kHz, so keeping every second sample doesn't alias
static float taps[TAPS], fir[TAPS];
static int firHead = 0;
static float dcIn = 0, dcOut = 0;
static uint16_t seq = 0;

static void filterBegin() {
  const float fc = 3500.0f / CAPTURE_RATE;
  float sum = 0;
  for (int n = 0; n < TAPS; n++) {
    const float m = n - (TAPS - 1) / 2.0f;
    const float sinc = m == 0 ? 2 * fc : sinf(2 * PI * fc * m) / (PI * m);
    taps[n] = sinc * (0.54f - 0.46f * cosf(2 * PI * n / (TAPS - 1)));
    sum += taps[n];
  }
  for (float& t : taps) t /= sum;   // unity gain at DC
}

static void streamStart() {
  memset(fir, 0, sizeof(fir));
  firHead = 0;
  dcIn = dcOut = 0;
  seq = 0;
  streaming = true;
}

// 10 ms of the mic -> DC removal -> low-pass -> 8 kHz -> MIC_GAIN -> one frame on the USB serial.
static void streamFrame() {
  static int32_t block[BLOCK_SAMPLES * 2];
  static uint8_t frame[4 + 2 * BLOCK_SAMPLES];
  size_t got = 0;
  const uint32_t start = millis();
  while (got < sizeof(block)) {
    got += i2s.readBytes(reinterpret_cast<char*>(block) + got, sizeof(block) - got);
    if (millis() - start > 1000) { streaming = false; return; }   // the I2S clock isn't running
  }
  frame[0] = 'R';
  frame[1] = 'A';
  frame[2] = seq & 0xff;
  frame[3] = seq >> 8;
  seq++;
  for (int i = 0, k = 0; i < BLOCK_SAMPLES * 2; i++) {
    const float x = (block[i] >> 8) / 256.0f;   // 24-bit -> 16-bit scale
    const float y = x - dcIn + 0.995f * dcOut;
    dcIn = x;
    dcOut = y;
    fir[firHead] = y;
    firHead = (firHead + 1) % TAPS;
    if (i & 1) {   // keep every second sample
      float acc = 0;
      for (int t = 0; t < TAPS; t++) acc += taps[t] * fir[(firHead + t) % TAPS];
      const int16_t s = (int16_t)constrain(acc * MIC_GAIN, -32768.0f, 32767.0f);
      frame[4 + 2 * k] = s & 0xff;
      frame[5 + 2 * k] = (uint16_t)s >> 8;
      k++;
    }
  }
  Serial.write(frame, sizeof(frame));
}

// One slot for 1 s, after the mic's start-up time: does it carry sound, only zeros, or one stuck value?

static Listen listen(i2s_std_slot_mask_t slot) {
  Listen s;
  if (!startMic(slot)) return s;
  for (int i = 0; i < 4; i++) {   // the INMP441 starts after 2^18 clock cycles: about 0.25 s at this rate
    Reading skip;
    if (!readWindow(skip)) return s;
  }
  bool allFlat = true;
  for (int i = 0; i < 10; i++) {
    Reading r;
    if (!readWindow(r)) return s;
    allFlat = allFlat && r.flat;
    if (!r.flat || r.value != 0) s.zero = false;
    s.value = r.value;
    s.rmsDb = fmaxf(s.rmsDb, r.rmsDb);
    s.dcPercent += r.dcPercent / 10;
  }
  s.ok = true;
  s.live = !allFlat;
  return s;
}

static void help() {
  Serial.println("Commands (type the letter, then Enter):");
  Serial.println("  p  switch between this report and the Serial Plotter view");
  Serial.println("  r  check the wiring again");
  Serial.println("  a  stream the audio to listen.py (binary: close the Serial Monitor first), x to stop");
  Serial.println("  h  this help");
}

static void checkWiring() {
  Serial.println();
  Serial.println("Checking the microphone. Keep quiet for 2 seconds...");
  historyCount = historyHead = 0;
  const Listen left = listen(I2S_STD_SLOT_LEFT);
  if (!left.ok) {
    Serial.println("PROBLEM: the I2S driver did not start, or its clock is not running. That is not the wiring:");
    Serial.println("  check Tools -> Board is XIAO_ESP32S3 and the esp32 core is 3.x.");
    return;
  }
  if (left.live) {
    Serial.printf("OK: the microphone answers on the left slot, as the firmware expects. Background %.0f dBFS, DC offset %+.2f %%.\n",
                  left.rmsDb, left.dcPercent);
    if (left.rmsDb > LOUD_DB) {
      Serial.println("CHECK: that background is very loud. In a quiet room it is a fault, not sound: SCK and WS may be swapped,");
      Serial.println("  or SD has a loose contact.");
    }
  } else {
    const Listen right = listen(I2S_STD_SLOT_RIGHT);
    if (right.ok && right.live) {
      Serial.println("PROBLEM: the microphone answers on the RIGHT slot, but the firmware listens on the left.");
      Serial.println("  Unplug USB and tie L/R to GND. If it already is, change I2S_STD_SLOT_LEFT to I2S_STD_SLOT_RIGHT");
      Serial.println("  in firmware/respirai/audio.cpp and tell the team.");
    } else if (left.zero) {
      Serial.println("PROBLEM: only zeros on SD: the microphone sends nothing.");
      Serial.println("  Unplug USB, then check: VDD on 3V3 (never 5V), GND on GND, SD on D10, SCK on D8, WS on D9, L/R on GND.");
    } else {
      Serial.printf("PROBLEM: SD is stuck at one value (%ld): no sound, just a fixed level.\n", (long)left.value);
      Serial.println("  Unplug USB, then check that SD on D10 isn't touching 3V3 or GND, and that VDD has 3V3.");
    }
    startMic(I2S_STD_SLOT_LEFT);   // keep listening where the firmware does
  }
  Serial.println("Now tap the chest piece or the table: the level should jump. Type h + Enter for the commands.");
  Serial.println();
}

static void handleInput() {
  while (Serial.available()) {
    const int c = tolower(Serial.read());
    if (streaming) {   // while streaming, only x is a command: anything else would end up in the audio
      if (c == 'x') {
        streaming = false;
        Serial.println("\nAudio stream stopped. Report view.");
      }
      continue;
    }
    if (c == 'a') {
      streamStart();
    } else if (c == 'p') {
      plotter = !plotter;
      if (!plotter) Serial.println("\nReport view. Type p + Enter for the plotter.");
    } else if (c == 'r') {
      checkWiring();
    } else if (c == 'h' || c == '?') {
      help();
    }
  }
}

// The background: the quietest reading of the last 5 s, so taps and breaths don't count.
static float background(float rmsDb) {
  history[historyHead] = rmsDb;
  historyHead = (historyHead + 1) % HISTORY;
  historyCount = min(historyCount + 1, HISTORY);
  float quietest = 0;
  for (int i = 0; i < historyCount; i++) quietest = fminf(quietest, history[i]);
  return quietest;
}

static void printLine(const Reading& r, float bg) {
  static int lines = 0;
  if (lines++ % 20 == 0) Serial.println("  level   meter (-90 to 0 dBFS)              peak   in the app");
  char meter[BAR + 1];
  const int filled = constrain((int)lroundf((r.rmsDb - FLOOR_DB) / -FLOOR_DB * BAR), 0, BAR);
  for (int i = 0; i < BAR; i++) meter[i] = i < filled ? '#' : '.';
  meter[BAR] = 0;
  Serial.printf("%5.0f dBFS [%s] %5.0f dBFS  %3.0f %%", r.rmsDb, meter, r.peakDb, r.appPercent);
  if (r.flat) Serial.print("  SILENT: no sound at all (type r to check the wiring)");
  else if (r.clipped) Serial.print("  CLIPPING: too loud for the microphone");
  else if (r.appPercent >= 100) Serial.print("  would clip in the app: lower MIC_GAIN");
  else if (r.peakDb - bg > TAP_DB) Serial.print("  <- sound");
  if (lines % 10 == 0) Serial.printf("  (background %.0f dBFS)", bg);
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  const uint32_t start = millis();
  while (!Serial && millis() - start < 3000) delay(10);   // USB CDC: give the Serial Monitor a moment to attach
  Serial.println();
  Serial.println("respirAI microphone test: INMP441 on SCK D8, WS D9, SD D10, L/R on GND. No Bluetooth.");
  filterBegin();
  checkWiring();
}

void loop() {
  static Reading summary;   // the loudest of the readings since the last line
  static int count = 0;
  handleInput();
  if (streaming) {
    // listen.py closed the port without saying x: stop after 2 s without a host (the USB link can report a
    // missing host for a few ms on a healthy connection, so one reading isn't enough).
    static uint32_t hostLostAt = 0;
    if (Serial) hostLostAt = 0;
    else if (!hostLostAt) hostLostAt = millis();
    else if (millis() - hostLostAt > 2000) { streaming = false; hostLostAt = 0; return; }
    streamFrame();
    return;
  }
  Reading r;
  if (!readWindow(r)) {
    Serial.println("PROBLEM: no data from I2S. Type r + Enter to check again.");
    delay(1000);
    return;
  }
  const float bg = background(r.rmsDb);
  if (plotter) {   // Arduino IDE 2 Serial Plotter: name:value pairs; top and bottom keep the scale still
    Serial.printf("level:%.1f peak:%.1f background:%.1f top:0 bottom:%.0f\n", r.rmsDb, r.peakDb, bg, FLOOR_DB);
    return;
  }
  if (count == 0) summary = r;
  else {
    summary.rmsDb = fmaxf(summary.rmsDb, r.rmsDb);
    summary.peakDb = fmaxf(summary.peakDb, r.peakDb);
    summary.appPercent = fmaxf(summary.appPercent, r.appPercent);
    summary.clipped += r.clipped;
    summary.flat = summary.flat && r.flat;
  }
  if (++count < REPORT_EVERY) return;
  count = 0;
  printLine(summary, bg);
}
