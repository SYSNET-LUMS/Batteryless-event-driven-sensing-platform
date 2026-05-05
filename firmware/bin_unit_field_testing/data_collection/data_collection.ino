#include <SPI.h>
#include <LoRa.h>

// ============ LOGGING CONFIG ============
const unsigned long CONTINUOUS_LOG_INTERVAL = 100;
unsigned long lastContinuousLog = 0;
bool isLogging = false;
unsigned long loggingStopTime = 0;
const unsigned long LOGGING_DELAY_AFTER_CLOSE = 200;
const unsigned long CLOSE_LOCKOUT_MS = 100;
unsigned long lastCloseTime = 0;

// ============ ENCODER CONFIG ============
const long PPR = 1000;
const bool ENABLE_SPEED_CALC = true;
const unsigned long SPEED_CALC_INTERVAL = 100;

// ============ PINS ============
const int limitInternalPin = 27;
const int limitExternalPin = 26;
const int encoderPinA = 32;
const int encoderPinB = 33;
const int voltagePin = 34;
const float R1 = 58000.0;
const float R2 = 9800.0;

#define LORA_SCK  18
#define LORA_MISO 19
#define LORA_MOSI 23
#define LORA_CS    5
#define LORA_RST  14
#define LORA_DIO0  2
#define SF 10
#define BW 125E3
#define CR 8

// ============ STATE ============
enum BinState { CLOSED, OPENING, OPEN, CLOSING };
BinState currentState = CLOSED;
const char* stateNames[] = { "CLOSED", "OPENING", "OPEN", "CLOSING" };

bool systemIdle = true;
unsigned long lastActivityTime = 0;
const unsigned long IDLE_TIMEOUT = 500;

// ============ DATA STRUCTURES ============
struct LoRaPacket {
  uint16_t identifier;
  uint8_t distance;
  int rssi;
  unsigned long timestamp_ms;
};

struct EncoderData {
  long pulse_count = 0;
  int angle_deg = 0;
  float current_speed = 0.0;
  float max_speed = 0.0;
  float avg_speed = 0.0;
  unsigned long last_speed_calc_time = 0;
  int last_speed_calc_angle = 0;
  int speed_sample_count = 0;
  float speed_sum = 0.0;
};

struct CycleData {
  unsigned long opening_number = 0;
  unsigned long open_start_ms = 0;
  unsigned long open_complete_ms = 0;
  unsigned long close_start_ms = 0;
  unsigned long close_complete_ms = 0;
  int max_angle = 0;
  int start_angle = 0;
  long start_pulse_count = 0;
  long end_pulse_count = 0;
  long total_pulses = 0;
  EncoderData encoder;
  LoRaPacket lora_packets[50];
  int lora_count = 0;
  float max_capacitor_voltage = 0.0;
  bool is_half_open = false;
};

const int MAX_CYCLES_BUFFER = 10;
CycleData cycleBuffer[MAX_CYCLES_BUFFER];
int cycleBufferCount = 0;
CycleData currentCycle;

// ============ VOLTAGE MONITOR ============
float currentVoltage = 0.0;

void readVoltage() {
  int raw = analogRead(voltagePin);
  float voltageAtPin = (raw / 4095.0) * 3.3;
  currentVoltage = voltageAtPin * (R1 + R2) / R2;

  if (currentState != CLOSED && currentVoltage > currentCycle.max_capacitor_voltage) {
    currentCycle.max_capacitor_voltage = currentVoltage;
  }
}

// ============ CONTINUOUS LOGGING ============
void logContinuousData() {
  unsigned long now = millis();

  if (isLogging && loggingStopTime > 0 && now >= loggingStopTime) {
    isLogging = false;
    loggingStopTime = 0;
  }

  if (!isLogging) return;

  if (now - lastContinuousLog >= CONTINUOUS_LOG_INTERVAL) {
    lastContinuousLog = now;
    Serial.print("DATA,");
    Serial.print(now);
    Serial.print(",");
    Serial.print(currentVoltage, 2);
    Serial.print(",");
    Serial.print(currentCycle.opening_number);
    Serial.print(",");
    Serial.println(stateNames[currentState]);
  }
}

// ============ TRACKING ============
volatile long rawCounter = 0;
bool lastInternalState = HIGH;
bool lastExternalState = HIGH;
unsigned long lastInternalChange = 0;
unsigned long lastExternalChange = 0;
const unsigned long DEBOUNCE_DELAY = 100;

// ============ INTERRUPTS ============
void IRAM_ATTR encoderISR_A() {
  if (digitalRead(encoderPinB) == LOW) rawCounter++;
  else rawCounter--;
}

void IRAM_ATTR encoderISR_B() {
  if (digitalRead(encoderPinA) == LOW) rawCounter--;
  else rawCounter++;
}

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(2000);

  pinMode(limitInternalPin, INPUT_PULLUP);
  pinMode(limitExternalPin, INPUT_PULLUP);
  lastInternalState = digitalRead(limitInternalPin);
  lastExternalState = digitalRead(limitExternalPin);

  pinMode(encoderPinA, INPUT_PULLUP);
  pinMode(encoderPinB, INPUT_PULLUP);
  attachInterrupt(encoderPinA, encoderISR_A, RISING);
  attachInterrupt(encoderPinB, encoderISR_B, RISING);

  analogReadResolution(12);
  analogSetPinAttenuation(voltagePin, ADC_11db);

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
  LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) { while (1) delay(1000); }
  LoRa.setSpreadingFactor(SF);
  LoRa.setSignalBandwidth(BW);
  LoRa.setCodingRate4(CR);
  LoRa.setPreambleLength(8);
  LoRa.setSyncWord(0x11);
  LoRa.enableCrc();
}

// ============ MAIN LOOP ============
void loop() {
  handleSwitches();
  handleEncoder();
  handleLoRa();
  readVoltage();
  logContinuousData();
  checkIdleAndPrint();
  delay(10);
}

// ============ LORA HANDLER ============
void handleLoRa() {
  int packetSize = LoRa.parsePacket(2);
  if (packetSize != 2) return;

  lastActivityTime = millis();
  systemIdle = false;

  uint8_t buf[2];
  LoRa.readBytes(buf, 2);
  uint16_t packetData = (buf[0] << 8) | buf[1];
  uint16_t identifier = (packetData >> 6) & 0xFFF;
  uint8_t distance = packetData & 0x3F;
  int rssi = LoRa.packetRssi();

  if (currentState == OPENING || currentState == OPEN || currentState == CLOSING) {
    if (currentCycle.lora_count < 50) {
      currentCycle.lora_packets[currentCycle.lora_count++] = { identifier, distance, rssi, millis() };
    }
  } else if (currentState == CLOSED && cycleBufferCount > 0) {
    CycleData& last = cycleBuffer[cycleBufferCount - 1];
    if (last.lora_count < 50) {
      last.lora_packets[last.lora_count++] = { identifier, distance, rssi, millis() };
    }
  }
}

// ============ ENCODER HANDLER ============
void handleEncoder() {
  if (currentState == CLOSED) return;

  long relativePulses = rawCounter - currentCycle.start_pulse_count;
  int currentAngle = (relativePulses * 360L) / PPR;

  if (abs(currentAngle) > abs(currentCycle.max_angle)) currentCycle.max_angle = currentAngle;
  currentCycle.encoder.angle_deg = currentAngle;
  currentCycle.encoder.pulse_count = relativePulses;

  if (ENABLE_SPEED_CALC) {
    unsigned long now = millis();
    if (now - currentCycle.encoder.last_speed_calc_time >= SPEED_CALC_INTERVAL) {
      int angle_delta = currentAngle - currentCycle.encoder.last_speed_calc_angle;
      unsigned long time_delta = now - currentCycle.encoder.last_speed_calc_time;

      if (time_delta > 0) {
        currentCycle.encoder.current_speed = (abs(angle_delta) * 1000.0) / time_delta;
        if (currentCycle.encoder.current_speed > currentCycle.encoder.max_speed)
          currentCycle.encoder.max_speed = currentCycle.encoder.current_speed;
        currentCycle.encoder.speed_sum += currentCycle.encoder.current_speed;
        currentCycle.encoder.speed_sample_count++;
        currentCycle.encoder.avg_speed = currentCycle.encoder.speed_sum / currentCycle.encoder.speed_sample_count;
      }

      currentCycle.encoder.last_speed_calc_time = now;
      currentCycle.encoder.last_speed_calc_angle = currentAngle;
    }
  }
}

// ============ SWITCH HANDLER ============
void handleSwitches() {
  bool internalState = digitalRead(limitInternalPin);
  bool externalState = digitalRead(limitExternalPin);
  unsigned long now = millis();

  if (internalState != lastInternalState && now - lastInternalChange > DEBOUNCE_DELAY) {
    lastInternalChange = now;
    lastInternalState = internalState;
    lastActivityTime = now;
    systemIdle = false;

    if (internalState == LOW) {
      if (millis() - lastCloseTime > CLOSE_LOCKOUT_MS) startNewOpening();
    } else {
      if (currentState == OPENING)      { handleHalfOpen();  lastCloseTime = millis(); }
      else if (currentState == CLOSING) { handleFullClose(); lastCloseTime = millis(); }
    }
  }

  if (externalState != lastExternalState && now - lastExternalChange > DEBOUNCE_DELAY) {
    lastExternalChange = now;
    lastExternalState = externalState;
    lastActivityTime = now;
    systemIdle = false;

    if (externalState == LOW)  { if (currentState == OPENING) handleFullyOpen(); }
    else                       { if (currentState == OPEN)    handleStartClosing(); }
  }
}

// ============ STATE TRANSITIONS ============
void startNewOpening() {
  isLogging = true;
  loggingStopTime = 0;
  currentState = OPENING;
  currentCycle.opening_number++;
  currentCycle.open_start_ms = millis();
  currentCycle.open_complete_ms = currentCycle.close_start_ms = currentCycle.close_complete_ms = 0;
  currentCycle.lora_count = 0;
  currentCycle.max_angle = 0;
  currentCycle.is_half_open = false;
  currentCycle.max_capacitor_voltage = 0.0;
  currentCycle.start_angle = (rawCounter * 360L) / PPR;
  currentCycle.start_pulse_count = rawCounter;
  currentCycle.encoder = { 0, 0, 0.0, 0.0, 0.0, millis(), currentCycle.start_angle, 0, 0.0 };

  Serial.print("MARKER,INTERNAL_RELEASED,");
  Serial.println(currentCycle.opening_number);
}

void handleFullyOpen() {
  currentState = OPEN;
  currentCycle.open_complete_ms = millis();
  Serial.print("MARKER,EXTERNAL_PRESSED,");
  Serial.println(currentCycle.opening_number);
}

void handleStartClosing() {
  currentState = CLOSING;
  currentCycle.close_start_ms = millis();
  currentCycle.end_pulse_count = rawCounter;
  currentCycle.total_pulses = abs(currentCycle.end_pulse_count - currentCycle.start_pulse_count);
  Serial.print("MARKER,EXTERNAL_RELEASED,");
  Serial.println(currentCycle.opening_number);
}

void handleHalfOpen() {
  loggingStopTime = millis() + LOGGING_DELAY_AFTER_CLOSE;
  currentCycle.is_half_open = true;
  currentCycle.open_complete_ms = currentCycle.close_start_ms = currentCycle.close_complete_ms = millis();
  currentCycle.end_pulse_count = rawCounter;
  currentCycle.total_pulses = abs(currentCycle.end_pulse_count - currentCycle.start_pulse_count);
  currentState = CLOSED;
  Serial.print("MARKER,INTERNAL_PRESSED,");
  Serial.println(currentCycle.opening_number);
  bufferCycle();
}

void handleFullClose() {
  loggingStopTime = millis() + LOGGING_DELAY_AFTER_CLOSE;
  currentState = CLOSED;
  currentCycle.close_complete_ms = millis();
  currentCycle.end_pulse_count = rawCounter;
  currentCycle.total_pulses = abs(currentCycle.end_pulse_count - currentCycle.start_pulse_count);
  if (currentCycle.open_complete_ms == 0)  currentCycle.open_complete_ms = currentCycle.close_complete_ms;
  if (currentCycle.close_start_ms == 0)    currentCycle.close_start_ms   = currentCycle.close_complete_ms;
  Serial.print("MARKER,INTERNAL_PRESSED,");
  Serial.println(currentCycle.opening_number);
  bufferCycle();
}

void bufferCycle() {
  if (cycleBufferCount < MAX_CYCLES_BUFFER) cycleBuffer[cycleBufferCount++] = currentCycle;
  else printAllBufferedCycles();
}

// ============ IDLE CHECK ============
void checkIdleAndPrint() {
  if (currentState == CLOSED && !systemIdle && millis() - lastActivityTime > IDLE_TIMEOUT) {
    systemIdle = true;
    if (cycleBufferCount > 0) printAllBufferedCycles();
  }
}

// ============ PRINT BUFFERED CYCLES ============
void printAllBufferedCycles() {
  if (cycleBufferCount == 0) return;

  Serial.println("\n========== CYCLE SUMMARY ==========");

  for (int i = 0; i < cycleBufferCount; i++) {
    CycleData& cycle = cycleBuffer[i];
    float open_duration  = (cycle.open_complete_ms  - cycle.open_start_ms)  / 1000.0;
    float close_duration = (cycle.close_complete_ms - cycle.close_start_ms) / 1000.0;

    float avg_distance = 0.0, avg_rssi = 0.0;
    for (int j = 0; j < cycle.lora_count; j++) {
      avg_distance += cycle.lora_packets[j].distance;
      avg_rssi     += cycle.lora_packets[j].rssi;
    }
    if (cycle.lora_count > 0) { avg_distance /= cycle.lora_count; avg_rssi /= cycle.lora_count; }

    long calculated_pulses = (abs(cycle.max_angle) * PPR) / 360;

    Serial.println("-----------------------------------");
    Serial.print("Opening #: ");   Serial.println(cycle.opening_number);
    Serial.print("Type: ");        Serial.println(cycle.is_half_open ? "HALF" : "FULL");
    Serial.print("Open Time: ");   Serial.print(open_duration, 3);  Serial.println(" s");
    Serial.print("Close Time: ");  Serial.print(close_duration, 3); Serial.println(" s");
    Serial.print("Max Angle: ");   Serial.print(cycle.max_angle);   Serial.println(" °");
    Serial.print("Max Voltage: "); Serial.print(cycle.max_capacitor_voltage, 2); Serial.println(" V");
    Serial.print("Peak Speed: ");  Serial.print(cycle.encoder.max_speed, 2); Serial.println(" °/s");
    Serial.print("Avg Speed: ");   Serial.print(cycle.encoder.avg_speed, 2); Serial.println(" °/s");
    Serial.print("LoRa Packets: ");Serial.println(cycle.lora_count);
    Serial.print("Avg Distance: ");Serial.print(avg_distance, 1); Serial.println(" cm");
    Serial.print("Avg RSSI: ");    Serial.print(avg_rssi, 1);     Serial.println(" dBm");
    Serial.print("Pulses: ");      Serial.println(calculated_pulses);
  }

  Serial.println("===================================\n");
  cycleBufferCount = 0;
}