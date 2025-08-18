#include <Arduino_LSM6DS3.h>
#include <math.h>
#include <string.h>
#include <ctype.h>

// ==================== 설정 ====================
const int FLEX_PINS[5] = {A0, A1, A2, A3, A7};  // Nano 33 IoT
const unsigned long DEFAULT_INTERVAL_MS = 20;    // 기본 50Hz
const unsigned long MIN_INTERVAL_MS     = 2;     // 하한(보레이트/부하에 따라 실효 낮을 수 있음)

// 보완 필터 계수(가속도 vs 자이로)
float kAlpha = 0.98f;

// 자이로 축 게인(부호만 간단히 조정)
// 기준: 오른손 손등, USB가 소지(새끼손가락) 쪽 → roll = X, pitch = Y
// 손가락을 쥐면 roll +, 손목을 위로 젖히면 pitch +
const float GAIN_GX = +1.0f;  // roll
const float GAIN_GY = +1.0f;  // pitch
const float GAIN_GZ = +1.0f;  // yaw

// ===== 축 매핑(0:X, 1:Y, 2:Z) =====
// USB가 소지 쪽 → 손가락 굴곡/신전(roll)은 X, 손목 위/아래(pitch)는 Y가 주로 변함
int ROLL_AXIS  = 0;  // X
int PITCH_AXIS = 1;  // Y

// 가속도 LPF
float ax_f = 0.0f, ay_f = 0.0f, az_f = 1.0f;
const float ACC_LPF_ALPHA = 0.20f;  // 0.1~0.3 권장

// ==================== 상태 변수 ====================
unsigned long sampleIntervalMs = DEFAULT_INTERVAL_MS;
unsigned long lastTickUs = 0;
bool connected = false;

// 자이로 바이어스(오프셋)
float bias_x = 0.0f, bias_y = 0.0f, bias_z = 0.0f;

// 각도(°) 상태(보완필터 결과) — CSV는 (pitch, roll, yaw) 순서 출력
float pitch_deg = 0.0f, roll_deg = 0.0f, yaw_deg = 0.0f;

// 마지막 유효 원시 샘플(읽기 실패 시 재사용)
float last_gx=0, last_gy=0, last_gz=0, last_ax=0, last_ay=0, last_az=1.0f;

// ==================== 유틸 ====================
inline float wrap180(float a) {
  while (a > 180.0f) a -= 360.0f;
  while (a < -180.0f) a += 360.0f;
  return a;
}

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
  // 틸트(가속도) 기반 각도
  // 장착 가정: 손등 위, USB가 소지 쪽
  pitch_acc_deg = atan2f(-ax, sqrtf(ay*ay + az*az)) * 180.0f / PI;
  roll_acc_deg  = atan2f( ay, az) * 180.0f / PI;
}

float pickAxis(int axis, float x, float y, float z) {
  if (axis == 0) return x;
  if (axis == 1) return y;
  return z;
}

// 명령: interval,<ms> / header / flush / recal / alpha,<0~1> / axis,roll:x|y|z,pitch:x|y|z / yawzero
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
        // 예: axis,roll:x,pitch:y
        int newROLL = ROLL_AXIS, newPITCH = PITCH_AXIS;
        char *s = lineBuf + 5;
        char *rp = strstr(s, "roll:");
        char *pp = strstr(s, "pitch:");
        if (rp && *(rp+5)) {
          char r = (char)tolower(*(rp+5));
          if (r=='x') newROLL=0; else if (r=='y') newROLL=1; else if (r=='z') newROLL=2;
        }
        if (pp && *(pp+6)) {
          char p = (char)tolower(*(pp+6));
          if (p=='x') newPITCH=0; else if (p=='y') newPITCH=1; else if (p=='z') newPITCH=2;
        }
        ROLL_AXIS = newROLL; PITCH_AXIS = newPITCH;
        Serial.print(F("# axis set: roll="));
        Serial.print(ROLL_AXIS==0?"x":(ROLL_AXIS==1?"y":"z"));
        Serial.print(F(", pitch="));
        Serial.println(PITCH_AXIS==0?"x":(PITCH_AXIS==1?"y":"z"));
      } else if (strcmp(lineBuf, "yawzero") == 0) {
        yaw_deg = 0.0f;
        Serial.println(F("# yaw reset to 0"));
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

  // 자이로 바이어스 보정 (정지 상태로)
  calibrateGyroBias();

  // === 시작시 가속도 기반 초기화 (약 120ms 평균) ===
  float sax=0, say=0, saz=0; int n=0;
  unsigned long t_start = millis();
  while (millis() - t_start < 120) {
    float tx, ty, tz;
    if (IMU.accelerationAvailable() && IMU.readAcceleration(tx, ty, tz)) {
      sax += tx; say += ty; saz += tz; n++;
    }
    delay(2);
  }
  if (n>0) { sax/=n; say/=n; saz/=n; }
  ax_f = sax; ay_f = say; az_f = saz;

  float pitch0, roll0;
  accelToAngles(ax_f, ay_f, az_f, pitch0, roll0);
  pitch_deg = pitch0;
  roll_deg  = roll0;
  yaw_deg   = 0.0f;   // 절대 yaw 아님 → 0으로 시작

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

  float dt = (nowUs - lastTickUs) * 1e-6f; // 실제 경과시간(s)
  lastTickUs = nowUs;

  // 센서 읽기(읽기 실패 시 마지막 유효값 재사용)
  float gx=last_gx, gy=last_gy, gz=last_gz;
  float ax=last_ax, ay=last_ay, az=last_az;

  bool g_ok=false, a_ok=false;

  if (IMU.gyroscopeAvailable()) {
    float tx, ty, tz;
    if (IMU.readGyroscope(tx, ty, tz)) {
      gx = tx * GAIN_GX;
      gy = ty * GAIN_GY;
      gz = tz * GAIN_GZ;
      g_ok = true;
    }
  }

  if (IMU.accelerationAvailable()) {
    float tx, ty, tz;
    if (IMU.readAcceleration(tx, ty, tz)) {
      // 가속도 LPF
      ax_f = (1.0f-ACC_LPF_ALPHA)*ax_f + ACC_LPF_ALPHA*tx;
      ay_f = (1.0f-ACC_LPF_ALPHA)*ay_f + ACC_LPF_ALPHA*ty;
      az_f = (1.0f-ACC_LPF_ALPHA)*az_f + ACC_LPF_ALPHA*tz;

      ax = ax_f; ay = ay_f; az = az_f;
      a_ok = true;
    }
  }

  if (g_ok) { last_gx = gx; last_gy = gy; last_gz = gz; }
  if (a_ok) { last_ax = ax; last_ay = ay; last_az = az; }

  // 가속도 기반 틸트각
  float pitch_acc_deg, roll_acc_deg;
  accelToAngles(ax, ay, az, pitch_acc_deg, roll_acc_deg);

  // 자이로 축/바이어스 선택
  float g_roll  = pickAxis(ROLL_AXIS,  gx, gy, gz);
  float g_pitch = pickAxis(PITCH_AXIS, gx, gy, gz);
  float b_roll  = pickAxis(ROLL_AXIS,  bias_x, bias_y, bias_z);
  float b_pitch = pickAxis(PITCH_AXIS, bias_x, bias_y, bias_z);

  // 보완 필터 업데이트 + 래핑
  roll_deg  = kAlpha * (roll_deg  + (g_roll  - b_roll ) * dt) + (1.0f - kAlpha) * roll_acc_deg;
  pitch_deg = kAlpha * (pitch_deg + (g_pitch - b_pitch) * dt) + (1.0f - kAlpha) * pitch_acc_deg;
  roll_deg  = wrap180(roll_deg);
  pitch_deg = wrap180(pitch_deg);

  // Yaw는 절대각 아님(자력계 없음) → 적분 + 래핑
  yaw_deg  += (gz - bias_z) * dt;
  yaw_deg   = wrap180(yaw_deg);

  // (선택) 정지 감지 시 yaw 드리프트 억제 — 필요 시 주석 해제
  // float g_norm = fabsf(gx - bias_x) + fabsf(gy - bias_y) + fabsf(gz - bias_z);
  // if (g_norm < 1.5f) { yaw_deg = 0.0f; }

  // 플렉스
  int flex[5];
  for (int i = 0; i < 5; i++) flex[i] = analogRead(FLEX_PINS[i]);

  // CSV 출력 (pitch, roll, yaw, accel_x,y,z, flex1..5)
  unsigned long tsMs = millis();
  printCsvRow(tsMs, pitch_deg, roll_deg, yaw_deg, ax, ay, az, flex);
}
