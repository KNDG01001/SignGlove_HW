#include <Arduino_LSM6DS3.h>

// -------------------- 설정 --------------------
const int FLEX_PINS[5] = {A0, A1, A2, A3, A6}; // Nano 33 IoT 기준
const unsigned long DEFAULT_INTERVAL_MS = 250;   // 기본 50Hz
const unsigned long MIN_INTERVAL_MS = 2;        // 500Hz 한계치 가정 (실효는 전송속도에 좌우됨)

// -------------------- 상태 변수 --------------------
unsigned long sampleIntervalMs = DEFAULT_INTERVAL_MS;
unsigned long lastSampleUs = 0;     // micros() 기반 타이밍
bool connected = false;             // USB CDC 연결 상태 추적

// -------------------- 유틸 --------------------
void clearSerialBuffers() {
  // RX 버퍼 비우기
  while (Serial.available()) {
    Serial.read();
  }
  // TX 버퍼는 전송 완료 대기만 수행 (아두이노 1.0 이후 flush 의미)
  Serial.flush();
}

void sendCsvHeader() {
  Serial.println(F("timestamp,pitch,roll,yaw,flex1,flex2,flex3,flex4,flex5"));
}

void handleIncomingCommand() {
  // 한 줄 단위 커맨드 처리 (예: "interval,20\n")
  static char lineBuf[64];
  static size_t idx = 0;

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;

    if (c == '\n') {
      lineBuf[idx] = '\0';
      idx = 0;

      // 파싱
      // 포맷: interval,<ms>
      // 공백 제거 없이 단순 파싱
      if (strncmp(lineBuf, "interval,", 9) == 0) {
        const char* p = lineBuf + 9;
        long val = atol(p);
        if (val <= 0) {
          // 무시
        } else {
          if ((unsigned long)val < MIN_INTERVAL_MS) val = (long)MIN_INTERVAL_MS;
          sampleIntervalMs = (unsigned long)val;
          // 적용 사실을 에코(로그)
          Serial.print(F("# interval(ms) set to "));
          Serial.println(sampleIntervalMs);
        }
      } else if (strcmp(lineBuf, "header") == 0) {
        sendCsvHeader();
      } else if (strcmp(lineBuf, "flush") == 0) {
        clearSerialBuffers();
        Serial.println(F("# flushed"));
      } else {
        // 기타 명령 로깅
        Serial.print(F("# unknown cmd: "));
        Serial.println(lineBuf);
      }
    } else {
      if (idx < sizeof(lineBuf) - 1) {
        lineBuf[idx++] = c;
      } else {
        // 오버플로 시 리셋
        idx = 0;
      }
    }
  }
}

void printCsvRow(unsigned long ts, float pitch, float roll, float yaw, const int flex[5]) {
  // 한 줄 CSV 출력
  Serial.print(ts);
  Serial.print(',');

  Serial.print(pitch, 2);
  Serial.print(',');
  Serial.print(roll, 2);
  Serial.print(',');
  Serial.print(yaw, 2);

  for (int i = 0; i < 5; i++) {
    Serial.print(',');
    Serial.print(flex[i]);
  }
  Serial.println();
}

// -------------------- 표준 스케치 --------------------
void setup() {
  Serial.begin(115200);
  // 시리얼 준비 대기 (상황에 따라 타임아웃 없이 무한대기)
  unsigned long t0 = millis();
  while (!Serial) {
    if (millis() - t0 > 3000) break; // 3초 후 포기 (원하면 삭제)
  }

  // IMU 초기화
  if (!IMU.begin()) {
    // Serial이 연결 안됐더라도 에러 문구는 일단 출력 시도
    Serial.println(F("Failed to initialize IMU."));
    while (1);
  }

  // 연결 상태 초기화
  connected = (bool)Serial;

  // 연결되어 있다면 헤더 송신
  if (connected) {
    clearSerialBuffers();  // 시작 시 버퍼 정리
    sendCsvHeader();
  }

  lastSampleUs = micros();
}

void loop() {
  // 1) 연결 상태 감지 및 전이 처리
  bool nowConn = (bool)Serial;
  if (nowConn && !connected) {
    // 재연결됨 → 버퍼 정리 + 헤더 재전송
    connected = true;
    clearSerialBuffers();
    sendCsvHeader();
  } else if (!nowConn && connected) {
    // 끊김 → 버퍼 정리, 전송 중단
    connected = false;
    clearSerialBuffers();
  }

  // 2) 들어오는 커맨드 처리
  if (connected) {
    handleIncomingCommand();
  }

  // 3) 주기적 샘플링 (연결되었을 때만 송신)
  unsigned long nowUs = micros();
  unsigned long intervalUs = sampleIntervalMs * 1000UL;

  if (connected && (nowUs - lastSampleUs >= intervalUs)) {
    lastSampleUs += intervalUs;  // 누적 방식으로 드리프트 감소

    // IMU 자이로 읽기
    float gx = 0, gy = 0, gz = 0;
    // 가용한지 체크 후 읽기 (가용하지 않으면 이전값 유지 or 0)
    if (IMU.gyroscopeAvailable()) {
      IMU.readGyroscope(gx, gy, gz);
    }

    // 필요에 따라 축 매핑/부호 조정 가능
    float pitch = gy;
    float roll  = gx;
    float yaw   = gz;

    // 플렉스 센서 ADC 읽기
    int flex[5];
    for (int i = 0; i < 5; i++) {
      flex[i] = analogRead(FLEX_PINS[i]); // 0~1023
    }

    // CSV 출력
    unsigned long tsMs = millis();
    printCsvRow(tsMs, pitch, roll, yaw, flex);
  }
}
