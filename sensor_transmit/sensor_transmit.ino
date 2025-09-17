#include <Arduino_LSM6DS3.h>
#include <math.h>
#include <string.h>
#include <ctype.h>
#include <ArduinoJson.h>   // 반드시 ArduinoJson 라이브러리 설치 (v6 이상)

// ==================== 설정 ====================
const int FLEX_PINS[5] = {A0, A1, A2, A3, A7};  // Nano 33 IoT
const unsigned long DEFAULT_INTERVAL_MS = 20;    // 기본 50Hz
const unsigned long MIN_INTERVAL_MS     = 2;     // 하한(보레이트/부하에 따라 실효 낮음)

float kAlpha = 0.98f;  // 보완 필터 계수

// 기준: 오른손 손등, USB가 소지(새끼손가락) 쪽
const float GAIN_GX = +1.0f;  // roll
const float GAIN_GY = +1.0f;  // pitch
const float GAIN_GZ = +1.0f;  // yaw

int ROLL_AXIS  = 0;  // X
int PITCH_AXIS = 1;  // Y

// 가속도 LPF
float ax_f = 0.0f, ay_f = 0.0f, az_f = 1.0f;
const float ACC_LPF_ALPHA = 0.20f;

// ==================== 상태 변수 ====================
unsigned long sampleIntervalMs = DEFAULT_INTERVAL_MS;
unsigned long lastTickUs = 0;

float bias_x = 0.0f, bias_y = 0.0f, bias_z = 0.0f;
float pitch_deg = 0.0f, roll_deg = 0.0f, yaw_deg = 0.0f;

float last_gx=0, last_gy=0, last_gz=0, last_ax=0, last_ay=0, last_az=1.0f;

// ==================== 유틸 ====================
inline float wrap180(float a) {
  while (a > 180.0f) a -= 360.0f;
  while (a < -180.0f) a += 360.0f;
  return a;
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

// JSON 출력 함수
void printJsonRow(unsigned long ts, float pitch, float roll, float yaw,
                  const int flex[5]) {
  StaticJsonDocument<256> doc;

  doc["timestamp"] = ts / 1000.0;  // ms → s 단위
  doc["yaw"]   = yaw;
  doc["pitch"] = pitch;
  doc["roll"]  = roll;

  doc["flex1"] = flex[0];
  doc["flex2"] = flex[1];
  doc["flex3"] = flex[2];
  doc["flex4"] = flex[3];
  doc["flex5"] = flex[4];

  serializeJson(doc, Serial);
  Serial.println();  // 줄바꿈
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

  // 시작시 가속도 기반 초기화
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
  yaw_deg   = 0.0f;

  lastTickUs = micros();
}

void loop() {
  unsigned long nowUs = micros();
  unsigned long dueUs = (unsigned long)(sampleIntervalMs * 1000UL);
  if ((nowUs - lastTickUs) < dueUs) return;

  float dt = (nowUs - lastTickUs) * 1e-6f;
  lastTickUs = nowUs;

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
      ax_f = (1.0f-ACC_LPF_ALPHA)*ax_f + ACC_LPF_ALPHA*tx;
      ay_f = (1.0f-ACC_LPF_ALPHA)*ay_f + ACC_LPF_ALPHA*ty;
      az_f = (1.0f-ACC_LPF_ALPHA)*az_f + ACC_LPF_ALPHA*tz;
      ax = ax_f; ay = ay_f; az = az_f;
      a_ok = true;
    }
  }

  if (g_ok) { last_gx = gx; last_gy = gy; last_gz = gz; }
  if (a_ok) { last_ax = ax; last_ay = ay; last_az = az; }

  float pitch_acc_deg, roll_acc_deg;
  accelToAngles(ax, ay, az, pitch_acc_deg, roll_acc_deg);

  float g_roll  = pickAxis(ROLL_AXIS,  gx, gy, gz);
  float g_pitch = pickAxis(PITCH_AXIS, gx, gy, gz);
  float b_roll  = pickAxis(ROLL_AXIS,  bias_x, bias_y, bias_z);
  float b_pitch = pickAxis(PITCH_AXIS, bias_x, bias_y, bias_z);

  roll_deg  = kAlpha * (roll_deg  + (g_roll  - b_roll ) * dt) + (1.0f - kAlpha) * roll_acc_deg;
  pitch_deg = kAlpha * (pitch_deg + (g_pitch - b_pitch) * dt) + (1.0f - kAlpha) * pitch_acc_deg;
  roll_deg  = wrap180(roll_deg);
  pitch_deg = wrap180(pitch_deg);

  yaw_deg  += (gz - bias_z) * dt;
  yaw_deg   = wrap180(yaw_deg);

  int flex[5];
  for (int i = 0; i < 5; i++) flex[i] = analogRead(FLEX_PINS[i]);

  unsigned long tsMs = millis();
  printJsonRow(tsMs, pitch_deg, roll_deg, yaw_deg, flex);
}
