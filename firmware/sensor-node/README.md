# Protocol and Application Layer Packet Convention

## Payload Layout

`packetData` is a 16-bit unsigned integer, transmitted little-endian (low byte first).

![Packet Layout Diagram](packet-layout.svg)

- `ID` — bits `[15:6]`: 10-bit node identifier (`0..1023`)
- `D`  — bits `[5:0]`:  distance in cm, saturated to `0..63`

## Pack / Unpack

Transmitter:
```c
uint8_t distance6 = (distance_cm > 63) ? 63 : (uint8_t)distance_cm; // saturate to 6 bits
uint16_t packetData = ((identifier & 0x3FF) << 6) | (distance6 & 0x3F);
```

Receiver:
```c
uint16_t identifier = (packetData >> 6) & 0x3FF;
uint8_t  distance6  = packetData & 0x3F;
```

## Identifier Capacity

10-bit identifier field → **1024 unique nodes** per base-station domain (`0..1023`).

## Overlapping Base Stations

Deployments that share RF coverage but must not interoperate should use distinct sync words. Change `LoRa.setSyncWord()` in both transmitter and receiver to an agreed per-deployment value.
