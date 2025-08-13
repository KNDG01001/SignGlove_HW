#include <Arduino_LSM6DS3.h>

// 플렉스 센서 연결 핀 (A0 ~ A4)
const int FLEX_PINS[5] = {A0, A1, A2, A3, A6};

// 샘플링 간격 설정 (50Hz = 20ms)
const int SAMPLE_INTERVAL = 250;
unsigned long lastSampleTime = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial);

  // IMU 초기화
  if (!IMU.begin()) {
    Serial.println("Failed to initialize IMU.");
    while (1);  // 초기화 실패 시 멈춤
  }

  // CSV 헤더 출력
  Serial.println("timestamp,pitch,roll,yaw,flex1,flex2,flex3,flex4,flex5");
}

void loop() {
  unsigned long now = millis();

  if (now - lastSampleTime >= SAMPLE_INTERVAL) {
    lastSampleTime = now;

    // ----------- IMU 자이로스코프 값 읽기 -----------
    float gx = 0, gy = 0, gz = 0;
    if (!IMU.readGyroscope(gx, gy, gz)) {
      Serial.println("Failed to read gyroscope data.");
    }

    float pitch = gy;  // 회전 방향은 필요에 따라 바꿀 수 있음
    float roll  = gx;
    float yaw   = gz;

    // ----------- 플렉스 센서 값 읽기 -----------
    int flex[5];
    for (int i = 0; i < 5; i++) {
      flex[i] = analogRead(FLEX_PINS[i]);  // 0~1023 범위
    }

    // ----------- Serial로 CSV 형식 출력 -----------
    Serial.print(now);
    Serial.print(",");
    Serial.print(pitch, 2);
    Serial.print(",");
    Serial.print(roll, 2);
    Serial.print(",");
    Serial.print(yaw, 2);
    for (int i = 0; i < 5; i++) {
      Serial.print(",");
      Serial.print(flex[i]);
    }
    Serial.println();
  }
}
