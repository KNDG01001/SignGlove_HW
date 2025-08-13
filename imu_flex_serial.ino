#include <Arduino_LSM6DS3.h>

// ==================== 설정 ====================
const int FLEX_PINS[5] = {A0, A1, A2, A3, A6};  // Nano 33 IoT
const unsigned long DEFAULT_INTERVAL_MS = 20;    // 기본 50Hz
const unsigned long MIN_INTERVAL_MS     = 2;     // 하한(보레이트/부하에 따라 실효 낮아질 수 있음)

// 보완 필터 계수(가속도 vs 자이로): 0.98 권장
float kAlpha = 0.98f;

// 축/부호 보정이 필요하면 여기서 조정(+1/-1)
const float GAIN_GX = +1.0f;  // roll 축
const float GAIN_GY = +1.0f;  // pitch 축
const float GAIN_GZ = +1.0f;  // yaw 축

// ==================== 상태 변수 ====================
unsigned long sampleIntervalMs = DEFAULT_INTERVAL_MS;
unsigned long lastSampleUs = 0;
bool connected = false;

// 자이로 바이어스(오프셋)
float bias_x = 0.0f, bias_y = 0.0f, bias_z = 0.0f;

// 각도(°) 상태(보완필터 결과)
float pitch_deg = 0.0f, roll_deg = 0.0f, yaw_deg = 0.0f;

// ==================== 유틸 ====================
void clearSerialBuffers() {
  while (Serial.available()) Serial.read();  // RX 버퍼 비움
  Serial.flush();                            // TX 전송 완료 대기
}

void sendCsvHeader() {
  Serial.println(F("timestamp,pitch,roll,yaw,accel_x,accel_y,accel_z,flex1,flex2,flex3,flex4,flex5"));
}

void printCsvRow(unsigned long ts, float pitch, float roll, float yaw,
                 float ax, float ay, float az, const int flex[5]) {
  Serial.print(ts);           Serial.print(',');
  Serial.print(pitch, 2);     Serial.print(',');
  Serial.print(roll, 2);      Serial.print(',');
  Serial.print(yaw, 2);       Serial.print(',');
  Serial.print(ax, 3);        Serial.print(',');
  Serial.print(ay, 3);        Serial.print(',');
  Serial.print(az, 3);
  for (int i = 0; i < 5; i++) { Serial.print(','); Serial.print(flex[i]); }
  Serial.println();
}

// 자이로 바이어스 추정(시작 시 정지 상태에서 1초 정도)
void calibrateGyroBias(unsigned samples = 200, unsigned delay_ms = 5) {
  bias_x = bias_y = bias_z = 0.0f;
  unsigned cnt = 0;
  for (unsigned i = 0; i < samples; i++) {
    float gx, gy, gz;
    if (IMU.gyroscopeAvailable() && IMU.readGyroscope(gx, gy, gz)) {
      bias_x += gx; bias_y += gy; bias_z += gz; cnt++;
    }
    delay(delay_ms);
  }
  if (cnt > 0) { bias_x /= cnt; bias_y /= cnt; bias_z /= cnt; }
}

// 가속도 기반 틸트각 계산(°)
inline void accelToAngles(float ax, float ay, float az,
                          float &pitch_acc_deg, float &roll_acc_deg) {
  // pitch_acc = atan2(-ax, sqrt(ay^2 + az^2))
  pitch_acc_deg = atan2f(-ax, sqrtf(ay*ay + az*az)) * 180.0f / PI;
  // roll_acc  = atan2( ay, az)
  roll_acc_deg  = atan2f( ay, az) * 180.0f / PI;
}

// 명령 처리: interval,<ms> / header / flush / recal / alpha,<0~1>
void handleIncomingCommand() {
  static char lineBuf[64];
  static size_t idx = 0;

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[idx] = '\0'; idx = 0;

      if (strncmp(lineBuf, "interval,", 9) == 0) {
        long val = atol(lineBuf + 9);
        if (val > 0) {
          if ((unsigned long)val < MIN_INTERVAL_MS) val = (long)MIN_INTERVAL_MS;
          sampleIntervalMs = (unsigned long)val;
          Serial.print(F("# interval(ms) set to ")); Serial.println(sampleIntervalMs);
        }
      } else if (strcmp(lineBuf, "header") == 0) {
        sendCsvHeader();
      } else if (strcmp(lineBuf, "flush") == 0) {
        clearSerialBuffers(); Serial.println(F("# flushed"));
      } else if (strncmp(lineBuf, "alpha,", 6) == 0) {
        float a = atof(lineBuf + 6);
        if (a >= 0.0f && a <= 1.0f) {
          kAlpha = a;
          Serial.print(F("# alpha set to ")); Serial.println(kAlpha, 3);
        } else {
          Serial.println(F("# alpha must be 0..1"));
        }
      } else if (strcmp(lineBuf, "recal") == 0) {
        Serial.println(F("# recalibrating gyro bias... keep still"));
        calibrateGyroBias();
        Serial.println(F("# recal done"));
      } else {
        Serial.print(F("# unknown cmd: ")); Serial.println(lineBuf);
      }
    } else {
      if (idx < sizeof(lineBuf) - 1) lineBuf[idx++] = c;
      else idx = 0; // overflow 시 리셋
    }
  }
}

// ==================== 표준 스케치 ====================
void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial) { if (millis() - t0 > 3000) break; } // 최대 3초 대기

  if (!IMU.begin()) {
    Serial.println(F("Failed to initialize IMU."));
    while (1);
  }

  // 시작 시 자이로 바이어스 보정(정지 자세)
  calibrateGyroBias();

  connected = (bool)Serial;
  if (connected) { clearSerialBuffers(); sendCsvHeader(); }

  lastSampleUs = micros();
}

void loop() {
  // 1) 연결 상태 전이 처리
  bool nowConn = (bool)Serial;
  if (nowConn && !connected) {
    connected = true;
    clearSerialBuffers();
    sendCsvHeader();
  } else if (!nowConn && connected) {
    connected = false;
    clearSerialBuffers();
  }

  // 2) 명령 처리
  if (connected) handleIncomingCommand();

  // 3) 주기 샘플링 & 보완필터 업데이트
  unsigned long nowUs = micros();
  unsigned long intervalUs = sampleIntervalMs * 1000UL;

  if (connected && (nowUs - lastSampleUs >= intervalUs)) {
    // 드리프트 최소화를 위해 누적 보정
    lastSampleUs += intervalUs;
    float dt = intervalUs * 1e-6f;
    if (dt <= 0.0f) dt = 1e-3f;

    // 센서 읽기
    float gx=0, gy=0, gz=0, ax=0, ay=0, az=0;
    if (IMU.gyroscopeAvailable())    IMU.readGyroscope(gx, gy, gz);
    if (IMU.accelerationAvailable()) IMU.readAcceleration(ax, ay, az);

    // 축/부호 보정
    gx *= GAIN_GX; gy *= GAIN_GY; gz *= GAIN_GZ;

    // 가속도 기반 틸트각
    float pitch_acc_deg, roll_acc_deg;
    accelToAngles(ax, ay, az, pitch_acc_deg, roll_acc_deg);

    // 보완 필터(°): 자이로 적분 + 가속도 혼합
    pitch_deg = kAlpha * (pitch_deg + (gy - bias_y) * dt) + (1.0f - kAlpha) * pitch_acc_deg;
    roll_deg  = kAlpha * (roll_deg  + (gx - bias_x) * dt) + (1.0f - kAlpha) * roll_acc_deg;
    yaw_deg  += (gz - bias_z) * dt; // 절대 yaw 아님(자력계 없음 → 상대값/드리프트 존재)

    // 플렉스
    int flex[5];
    for (int i = 0; i < 5; i++) flex[i] = analogRead(FLEX_PINS[i]);

    // CSV 출력
    unsigned long tsMs = millis();
    printCsvRow(tsMs, pitch_deg, roll_deg, yaw_deg, ax, ay, az, flex);
  }
}
