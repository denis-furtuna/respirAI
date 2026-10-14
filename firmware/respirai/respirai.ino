// respirAI firmware for the Seeed XIAO ESP32-S3: mic -> 8 kHz audio -> Bluetooth, plus the LED breathing guide.
// Implements contract 1 in docs/ARCHITECTURE.md (tasks F2-F5, F8, F-LED1-F-LED5). Build notes: firmware/README.md.
#include <NimBLEDevice.h>
#include "config.h"
#include "audio.h"
#include "leds.h"

static NimBLECharacteristic* audioChr;
static NimBLECharacteristic* statusChr;

static volatile bool audioOk = false;
static volatile bool connected = false;
static volatile bool subscribed = false;
static volatile bool streaming = false;
static volatile bool statusRequested = false;
static volatile uint16_t packetSamples = MAX_PACKET_SAMPLES;  // fixed for a connection, set at subscribe time
static volatile uint16_t packetsSinceStatus = 0;
static uint16_t seq = 0;

// ---------- Bluetooth callbacks ----------
class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* server, NimBLEConnInfo& info) override {
    connected = true;
    server->updateConnParams(info.getConnHandle(), 12, 24, 0, 400);  // 15-30 ms interval: room for 100 packets/s
    ledsSet(LED_IDLE);
    Serial.println("Connected");
  }

  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    connected = false;
    subscribed = false;
    streaming = false;
    ledsSet(LED_WAITING);
    Serial.printf("Disconnected (reason %d), advertising again\n", reason);
    NimBLEDevice::startAdvertising();
  }

  void onMTUChange(uint16_t mtu, NimBLEConnInfo&) override {
    Serial.printf("MTU negotiated: %u\n", mtu);
  }
};

class AudioCallbacks : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic*, NimBLEConnInfo& info, uint16_t subValue) override {
    subscribed = subValue & 1;
    if (!subscribed) return;
    // A notification carries MTU - 3 bytes; 2 go to the sequence number. Keep the sample count even.
    const uint16_t mtu = info.getMTU();
    packetSamples = min<int>(MAX_PACKET_SAMPLES, ((mtu - 5) / 2) & ~1);
    Serial.printf("Audio subscribed: MTU %u -> %u samples per packet (%u bytes)\n", mtu, packetSamples, 2 + 2 * packetSamples);
  }
};

class ControlCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* chr, NimBLEConnInfo&) override {
    const NimBLEAttValue value = chr->getValue();
    if (value.length() == 0) return;
    const uint8_t* v = value.data();
    switch (v[0]) {
      case CMD_START:  streaming = true;  break;
      case CMD_STOP:   streaming = false; break;
      case CMD_GUIDE:  ledsSet(LED_GUIDE); break;   // an optional v[1] (chest point 0-6) is ignored: the phone shows the place
      case CMD_DONE:   ledsSet(LED_DONE);  break;
      case CMD_IDLE:   ledsSet(LED_IDLE);  break;
      case CMD_STATUS: statusRequested = true; break;
      default: Serial.printf("Unknown command 0x%02x\n", v[0]);
    }
  }
};

// ---------- audio task: runs on its own core so Bluetooth and LEDs never make it miss samples ----------
static void audioTask(void*) {
  int16_t block[BLOCK_SAMPLES];
  int16_t pending[2 * MAX_PACKET_SAMPLES];
  int pendingCount = 0;
  uint8_t packet[2 + 2 * MAX_PACKET_SAMPLES];
  if (!audioOk) vTaskDelete(nullptr);   // no mic: nothing to stream; the status reports STATE_ERROR

  for (;;) {
    audioRead(block);   // blocks for 10 ms of audio
    if (!(connected && subscribed && streaming)) {
      pendingCount = 0;
      continue;
    }
    memcpy(pending + pendingCount, block, sizeof(block));
    pendingCount += BLOCK_SAMPLES;
    const int n = packetSamples;
    while (pendingCount >= n) {
      packet[0] = seq & 0xff;
      packet[1] = seq >> 8;
      memcpy(packet + 2, pending, 2 * n);   // the ESP32 is little-endian, as the contract wants
      audioChr->notify(packet, 2 + 2 * n);  // if Bluetooth is busy the packet is lost; the app fills the gap
      seq++;                                // counts every packet made, so lost ones show up as a gap
      packetsSinceStatus = packetsSinceStatus + 1;
      pendingCount -= n;
      memmove(pending, pending + n, 2 * pendingCount);
    }
  }
}

// ---------- status ----------
static uint8_t batteryPercent() {
  if (PIN_BATTERY < 0) return 255;   // not wired: "unknown"
  const float volts = analogReadMilliVolts(PIN_BATTERY) * 2 / 1000.0f;   // 1:2 divider
  return constrain((volts - 3.3f) / (4.2f - 3.3f) * 100, 0, 100);
}

static void sendStatus() {
  const uint16_t packets = packetsSinceStatus;
  packetsSinceStatus = 0;
  uint8_t status[4] = {
    batteryPercent(),
    !audioOk ? STATE_ERROR : streaming ? STATE_STREAMING : STATE_IDLE,
    (uint8_t)(packets & 0xff), (uint8_t)(packets >> 8),
  };
  ledsStatus(status[1] == STATE_ERROR, status[0]);
  statusChr->setValue(status, sizeof(status));
  if (connected) statusChr->notify();
  Serial.printf("Status: battery %u, state %u, %u packets in the last %lu ms\n", status[0], status[1], packets, STATUS_EVERY_MS);
}

// ---------- setup / loop ----------
void setup() {
  Serial.begin(115200);
  ledsBegin();
  audioOk = audioBegin();
  if (!audioOk) Serial.println("ERROR: I2S microphone did not start. Check the wiring (docs/PLAN.md §3).");
  ledsStatus(!audioOk, batteryPercent());

  NimBLEDevice::init(DEVICE_NAME);
  NimBLEDevice::setMTU(MAX_PACKET_SAMPLES * 2 + 2 + 3);   // ask for room for a full packet
  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  NimBLEService* service = server->createService(SERVICE_UUID);
  audioChr = service->createCharacteristic(AUDIO_UUID, NIMBLE_PROPERTY::NOTIFY);
  audioChr->setCallbacks(new AudioCallbacks());
  NimBLECharacteristic* controlChr = service->createCharacteristic(CONTROL_UUID, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  controlChr->setCallbacks(new ControlCallbacks());
  statusChr = service->createCharacteristic(STATUS_UUID, NIMBLE_PROPERTY::NOTIFY | NIMBLE_PROPERTY::READ);

  NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
  advertising->setName(DEVICE_NAME);
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->enableScanResponse(true);
  advertising->start();
  Serial.println("Advertising as " DEVICE_NAME);

  xTaskCreatePinnedToCore(audioTask, "audio", 8192, nullptr, 5, nullptr, 1);
}

void loop() {
  static uint32_t lastStatus = 0;
  ledsUpdate();
  if (statusRequested || millis() - lastStatus >= STATUS_EVERY_MS) {
    statusRequested = false;
    lastStatus = millis();
    sendStatus();
  }
  delay(5);
}
