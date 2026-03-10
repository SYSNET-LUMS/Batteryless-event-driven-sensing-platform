#include <SPI.h>
#include <LoRa.h>

// LoRa PHY parameters must match the transmitter exactly.
#define SF 10
#define BW 125E3
#define CR 8

void setup() {
  Serial.begin(115200);
  while (!Serial);

  if (!LoRa.begin(433E6)) {
    Serial.println("LoRa init failed!");
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
  // parsePacket(2) uses implicit header mode expecting a fixed 2-byte payload.
  int packetSize = LoRa.parsePacket(2);
  if (packetSize == 2) {
    uint8_t buf[2];
    LoRa.readBytes(buf, 2);

    uint16_t packetData = buf[0] | (buf[1] << 8);

    // Unpack [15:6] 10-bit ID (1024 nodes max) and [5:0] distance from the 2-byte payload.
    uint16_t identifier = (packetData >> 6) & 0x3FF;
    uint8_t distance6 = packetData & 0x3F;

    float distance_cm = (float)distance6;

    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();

    Serial.print("ID: "); Serial.print(identifier);
    Serial.print(" | Distance: "); Serial.print(distance_cm); Serial.print(" cm");
    Serial.print(" | RSSI: "); Serial.print(rssi); Serial.print(" dBm");
    Serial.print(" | SNR: "); Serial.println(snr);
  }
}