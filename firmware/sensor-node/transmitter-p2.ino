#include <SPI.h>
#include <LoRa.h>

const uint16_t identifier = 12;

#define TRIG_PIN 4
#define ECHO_PIN 3
#define TIMEOUT 30000

// LoRa PHY parameters must match the receiver exactly.
#define SF 10
#define BW 125E3
#define CR 8
#define TX_POWER 20

void setup() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  if (!LoRa.begin(433E6)) {
    while (1);
  }

  LoRa.setSpreadingFactor(SF);
  LoRa.setSignalBandwidth(BW);
  LoRa.setCodingRate4(CR);
  LoRa.setPreambleLength(8);
  LoRa.setSyncWord(0x11);
  LoRa.enableCrc();
}

void loop() {
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  uint32_t duration_us = pulseIn(ECHO_PIN, HIGH, TIMEOUT);
  // Single-step ultrasonic scale: microseconds of round-trip echo -> centimeters.
  float distance_cm = duration_us * 0.008575f;

  // Saturate to 6 bits so the value always fits in 0..63 before packing.
  uint8_t distance6 = (distance_cm > 63) ? 63 : (uint8_t)distance_cm;

  // Packet layout: [15:6] 10-bit ID (1024 nodes max), [5:0] 6-bit distance.
  uint16_t packetData = ((identifier & 0x3FF) << 6) | (distance6 & 0x3F);

  // beginPacket(1) enables implicit header mode on TX for fixed 2-byte payloads.
  LoRa.beginPacket(1);
  LoRa.write((uint8_t*)&packetData, 2);
  LoRa.endPacket();
}