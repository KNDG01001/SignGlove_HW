#include <Arduino_LSM6DS3.h>

// ==================== 설정 ====================
const int FLEX_PINS[5] = {A0, A1, A2, A3, A6};  // Nano 33 IoT
const unsigned long DEFAULT_INTERVAL_MS = 20;    // 기본 50Hz
const unsigned long MIN_INTERVAL_MS     = 2;     // 하한(보레이트/부하에 따라 실효 낮을 수 있음)

// 보완 필터 계수(가속도 vs 자이로)
float kAlpha = 0.98f;

// 자이로 축 게인(부호만 간단히 조정)
const float GAIN_GX = +1.0f;
const float GAIN_GY = +1.0f;
const float GAIN_GZ = +1.0f;

// ===== 축 매핑(0:X, 1:Y, 2:Z) =====
// 손등 장착에서 굴곡/신전이 보통 Y축으로 크게 나오는 경우가 많음 → roll=Y, pitch=X 가정
int ROLL_AXIS  = 1;  // 1=Y
int PITCH_AXIS = 0;  // 0=X

// ==================== 상태 변수 ====================
unsigned long sampleIntervalMs = DEFAULT_INTERVAL_MS;
unsigned long lastTickUs = 0;
bool connected = false;

// 자이로 바이어스(오프셋)
float bias_x = 0.0f, bias_y = 0.0f, bias_z = 0.0f;

// 각도(°) 상태(보완필터 결과)
float pitch_deg = 0.0f, roll_deg = 0.0f, yaw_deg = 0.0f;

// 마지막 유효 원시 샘플(읽기 실패 시 재사용)
float last_gx=0, last_gy=0, last_gz=0, last_ax=0, last_ay=0, last_az=1.0f;

// ==================== 유틸 ====================
void clearSerialBuffers() {
  while (Serial.available()) Serial.read();
  Serial.flush();
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

inline void accelToAngles(float ax, float ay, float az,
                          float &pitch_acc_deg, float &roll_acc_deg) {
  pitch_acc_deg = atan2f(-ax, sqrtf(ay*ay + az*az)) * 180.0f / PI;
  roll_acc_deg  = atan2f( ay, az) * 180.0f / PI;
}

float pickAxis(int axis, float x, float y, float z) {
  if (axis == 0) return x;
  if (axis == 1) return y;
  return z;
}

// 명령: interval,<ms> / header / flush / recal / alpha,<0~1> / axis,<roll:x|y|z>,<pitch:x|y|z>
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
      } else if (strncmp(lineBuf, "axis,", 5) == 0) {
        // 예: axis,roll:y,pitch:x
        char r='y', p='x';
        // 단순 파서
        char *s = lineBuf + 5;
        // 기본값
        int newROLL = ROLL_AXIS, newPITCH = PITCH_AXIS;
        char *rp = strstr(s, "roll:");
        char *pp = strstr(s, "pitch:");
        if (rp && *(rp+5)) {
          r = (char)tolower(*(rp+5));
          if (r=='x') newROLL=0; else if (r=='y') newROLL=1; else if (r=='z') newROLL=2;
        }
        if (pp && *(pp+6)) {
          p = (char)tolower(*(pp+6));
          if (p=='x') newPITCH=0; else if (p=='y') newPITCH=1; else if (p=='z') newPITCH=2;
        }
        ROLL_AXIS = newROLL; PITCH_AXIS = newPITCH;
        Serial.print(F("# axis set: roll="));
        Serial.print(ROLL_AXIS==0?"x":(ROLL_AXIS==1?"y":"z"));
        Serial.print(F(", pitch="));
        Serial.println(PITCH_AXIS==0?"x":(PITCH_AXIS==1?"y":"z"));
      } else {
        Serial.print(F("# unknown cmd: ")); Serial.println(lineBuf);
      }
    } else {
      if (idx < sizeof(lineBuf) - 1) lineBuf[idx++] = c;
      else idx = 0;
    }
  }
}

// ==================== 표준 스케치 ====================
void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial) { if (millis() - t0 > 3000) break; }

  if (!IMU.begin()) {
    Serial.println(F("Failed to initialize IMU."));
    while (1);
  }
  calibrateGyroBias();

  connected = (bool)Serial;
  if (connected) { clearSerialBuffers(); sendCsvHeader(); }

  lastTickUs = micros();
}

void loop() {
  // 1) 연결 상태 전이
  bool nowConn = (bool)Serial;
  if (nowConn && !connected) { connected = true; clearSerialBuffers(); sendCsvHeader(); }
  else if (!nowConn && connected) { connected = false; clearSerialBuffers(); }

  // 2) 명령 처리
  if (connected) handleIncomingCommand();

  // 3) 주기 샘플링 & 필터
  unsigned long nowUs = micros();
  unsigned long dueUs = (unsigned long)(sampleIntervalMs * 1000UL);
  if (!connected || (nowUs - lastTickUs) < dueUs) return;

  float dt = (nowUs - lastTickUs) * 1e-6f; // 실제 경과시간
  lastTickUs = nowUs;

  // 센서 읽기(읽기 실패 시 마지막 유효값 재사용)
  float gx=last_gx, gy=last_gy, gz=last_gz, ax=last_ax, ay=last_ay, az=last_az;

  bool g_ok=false, a_ok=false;
  if (IMU.gyroscopeAvailable()) {
    float tx, ty, tz;
    if (IMU.readGyroscope(tx, ty, tz)) {
      gx = tx; gy = ty; gz = tz; g_ok = true;
    }
  }
  if (IMU.accelerationAvailable()) {
    float tx, ty, tz;
    if (IMU.readAcceleration(tx, ty, tz)) {
      ax = tx; ay = ty; az = tz; a_ok = true;
    }
  }
  if (g_ok) { last_gx = gx; last_gy = gy; last_gz = gz; }
  if (a_ok) { last_ax = ax; last_ay = ay; last_az = az; }

  // 축/부호 보정
  gx *= GAIN_GX; gy *= GAIN_GY; gz *= GAIN_GZ;

  // 가속도 기반 틸트각
  float pitch_acc_deg, roll_acc_deg;
  accelToAngles(ax, ay, az, pitch_acc_deg, roll_acc_deg);

  // 선택 축: roll/pitch에 사용할 자이로 성분 & 바이어스
  float g_roll  = pickAxis(ROLL_AXIS,  gx, gy, gz);
  float g_pitch = pickAxis(PITCH_AXIS, gx, gy, gz);
  float b_roll  = pickAxis(ROLL_AXIS,  bias_x, bias_y, bias_z);
  float b_pitch = pickAxis(PITCH_AXIS, bias_x, bias_y, bias_z);

  // 보완 필터 업데이트
  roll_deg  = kAlpha * (roll_deg  + (g_roll  - b_roll ) * dt) + (1.0f - kAlpha) * roll_acc_deg;
  pitch_deg = kAlpha * (pitch_deg + (g_pitch - b_pitch) * dt) + (1.0f - kAlpha) * pitch_acc_deg;
  yaw_deg  += (gz - bias_z) * dt; // 절대 yaw 아님(자력계 없음)

  // 플렉스
  int flex[5];
  for (int i = 0; i < 5; i++) flex[i] = analogRead(FLEX_PINS[i]);

  // CSV 출력
  unsigned long tsMs = millis();
  printCsvRow(tsMs, pitch_deg, roll_deg, yaw_deg, ax, ay, az, flex);
}
