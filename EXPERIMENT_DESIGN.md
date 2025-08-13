# SignGlove_HW
센서 기반 수화 통역 장갑 제작기

## 🎯 프로젝트 개요

한국어 수어 인식을 위한 하드웨어 센서 시스템입니다. Arduino Nano 33 IoT와 플렉스 센서를 활용하여 실시간 수어 데이터를 수집하고 ML 학습용 데이터셋을 구축합니다.

## 🔧 하드웨어 구성

- **Arduino Nano 33 IoT** (LSM6DS3 IMU 내장)
- **플렉스 센서 5개** (A0, A1, A2, A3, A6 핀)
- **USB 시리얼 통신** (115200 baud)

## 📊 최신 기능 (2025.08.13 업데이트)

### ✨ 가속도 데이터 지원 추가
- **12필드 CSV 형식**: `timestamp,pitch,roll,yaw,accel_x,accel_y,accel_z,flex1,flex2,flex3,flex4,flex5`
- **IMU 6축 완전 활용**: 자이로스코프 + 가속도계
- **실시간 Hz 측정**: 아두이노 타임스탬프 기반 7정확한 주기 계산

### 🤟 통합 수어 데이터 수집기
- **34개 한국어 수어 클래스** 지원 (자음14 + 모음10 + 숫자10)
- **ROS2 스타일 키보드 인터페이스**
- **H5 형식 저장** (KLP-SignGlove 호환)
- **실시간 진행률 추적** 및 우선순위 기반 수집 가이드

## 🧪 실험 설계 및 데이터 수집 프로토콜

### 실험 프로세스 흐름도

```mermaid
graph TD
    A[실험 준비 단계] --> B[팔 위치 수평 고정]
    B --> C[자이로 센서 0,0,0 초기화]
    C --> D[고정대 제거]
    D --> E[데이터 수집 시작]
    
    E --> F[34개 클래스 순차 측정]
    F --> G[ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ<br/>자음 14개]
    F --> H[ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ<br/>모음 10개]
    F --> I[0123456789<br/>숫자 10개]
    
    G --> J[에피소드별 3-5초 측정]
    H --> J
    I --> J
    
    J --> K[데이터 품질 확인]
    K --> L{품질 OK?}
    L -->|Yes| M[다음 클래스]
    L -->|No| N[재측정]
    N --> J
    M --> O{전체 완료?}
    O -->|No| F
    O -->|Yes| P[실험 종료]
    
    style A fill:#e1f5fe
    style E fill:#c8e6c9
    style P fill:#ffcdd2
```

### 실험 팀 구성 및 시스템 구조

```mermaid
graph LR
    subgraph "실험 환경 구성"
        A[실험자<br/>장갑 착용자] --> B[수평 고정대]
        B --> C[자이로 센서<br/>0,0,0 초기화]
    end
    
    subgraph "실험 팀 구성"
        D[실험보조자<br/>초기자세 고정<br/>센서 초기화]
        E[데이터 수집자<br/>Python 실행<br/>수집 추이 관찰]
        F[실험자<br/>수어 동작 수행]
    end
    
    subgraph "데이터 수집 시스템"
        G[Arduino Nano 33 IoT<br/>IMU + Flex Sensors]
        H[PC - 통합 수집기<br/>integration/signglove_unified_collector.py]
        I[데이터 저장<br/>datasets/unified/]
    end
    
    A --> G
    G --> H
    H --> I
    
    D --> A
    E --> H
    F --> A
    
    style A fill:#ffeb3b
    style D fill:#4caf50
    style E fill:#2196f3
    style G fill:#ff9800
    style H fill:#9c27b0
    style I fill:#607d8b
```

### 실험 설계 핵심 특징

#### 🎯 **3명 팀 구성**
- **실험자**: 정확한 수어 동작 수행 (3-5초 자연스러운 표현)
- **실험보조자**: 팔 고정, 센서 0,0,0 초기화, 고정대 제거
- **데이터 수집자**: 통합 수집기 운영, 실시간 품질 관리

#### 📊 **수집 목표**
- **총 클래스**: 34개 (자음 14 + 모음 10 + 숫자 10)
- **클래스당 에피소드**: 50-100개
- **총 예상 데이터**: 2,460개 에피소드
- **예상 소요 기간**: 3-4주 (15-20 세션)

#### ⚠️ **핵심 유의사항**
- **센서 드리프트**: 10개 에피소드마다 재초기화
- **플렉스 센서 안정성**: 700-900 범위 벗어나면 교체
- **실험자 피로도**: 30분마다 휴식, 최대 2시간 연속
- **환경 통제**: 온도 20-25°C, 습도 40-60%, 무선 간섭 최소화

#### 📋 **상세 프로토콜**
전체 실험 설계 및 유의사항은 [`EXPERIMENT_DESIGN.md`](EXPERIMENT_DESIGN.md)를 참조하세요.

## 🚀 사용법

### 1. 펌웨어 업로드
```bash
# Arduino IDE로 imu_flex_serial.ino 업로드
```

### 2. 데이터 수집 (선택)

**간단한 CSV 수집:**
```bash
python csv_uart.py
```

**통합 수집기 (권장):**
```bash
python integration/signglove_unified_collector.py
```

### 3. 통합 수집기 조작
```
C: 아두이노 연결
N: 새 에피소드 (클래스 선택 1-34)
M: 에피소드 종료
P: 진행 상황
Q: 종료
```

## 📁 파일 구조

```
SignGlove_HW/
├── 📱 imu_flex_serial.ino          # 아두이노 펌웨어 (가속도 지원)
├── 📊 csv_uart.py                  # 간단한 CSV 수집기
├── 📊 csv_wifi.py                  # WiFi 데이터 수집기  
├── 🗂️ datasets/                    # 데이터셋 저장소
│   ├── raw/                       # 원본 CSV
│   ├── processed/                 # 전처리된 데이터
│   ├── unified/                   # H5 에피소드 파일
│   └── ksl_34classes/            # 클래스별 정리
├── 🔧 integration/                 # 통합 시스템
│   ├── README_UNIFIED_COLLECTOR.md
│   └── signglove_unified_collector.py
└── 📋 README.md                   # 이 파일
```

## 🎯 34개 한국어 수어 클래스

| 카테고리 | 클래스 | 목표 |
|---------|--------|------|
| **자음** (14개) | ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ | 80-100개/클래스 |
| **모음** (10개) | ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ | 60-80개/클래스 |
| **숫자** (10개) | 0123456789 | 50개/클래스 |

## 📈 데이터 형식

### CSV 출력 (12필드)
```csv
timestamp(ms),pitch(°),roll(°),yaw(°),accel_x(g),accel_y(g),accel_z(g),flex1,flex2,flex3,flex4,flex5
1234567890,10.5,-5.2,15.8,0.123,-0.045,0.987,512,678,723,834,567
```

### H5 저장 (KLP-SignGlove 호환)
```python
episode_20250813_153000_ㄱ.h5:
├── sensor_data        # [N,8] 메인 센서 (flex5 + orientation3)
├── timestamps         # [N] PC 수신 타임스탬프
├── arduino_timestamps # [N] 아두이노 타임스탬프  
├── sampling_rates     # [N] 실시간 Hz
└── sensors/
    ├── flex           # [N,5] 플렉스 센서
    ├── orientation    # [N,3] 자이로 오일러각
    └── acceleration   # [N,3] 가속도
```

## 🔗 통합 시스템 연동

### KLP-SignGlove 호환
- ✅ 동일한 8채널 센서 데이터 구조
- ✅ 562 FPS 실시간 추론 지원
- ✅ CNN+LSTM+Attention 모델 적용 가능

### SignGlove 메인 프로젝트 연동
- ✅ `SensorData` 모델 완벽 호환
- ✅ FastAPI 서버 직접 연결 가능
- ✅ 실시간 추론 + TTS 통합

## 🧪 기술적 고려사항

### 센서 설계 원칙
- 손의 위치에 무관한 측정 (상대적 움직임 기반)
- Z축 기준 측정으로 안정성 확보
- 개인차 변수 최소화 (팔 길이, 키 등 제외)

### 시스템 요구사항
- 실험 환경별 표준 설정 필요
- 자이로 센서 변수 통제 가능한 환경
- 일관된 데이터 품질 유지

## 📊 성능 특징

- **실시간 Hz 측정**: 아두이노 타임스탬프 기준
- **논블로킹 수집**: 큐 기반 데이터 처리
- **메모리 효율성**: 스트리밍 방식 저장
- **안정성**: 연결 끊김 자동 감지/복구

## 🔮 향후 계획

- [ ] 실시간 모델 학습 파이프라인
- [ ] 웹 기반 수집 인터페이스  
- [ ] 다중 사용자 수집 시스템
- [ ] 자동 데이터 품질 평가
- [ ] 클라우드 저장소 연동

## 📚 관련 문서

- [`integration/README_UNIFIED_COLLECTOR.md`](integration/README_UNIFIED_COLLECTOR.md) - 통합 수집기 상세 가이드
- [`datasets/README.md`](datasets/README.md) - 데이터셋 구조 및 활용법
- [`EXPERIMENT_DESIGN.md`](EXPERIMENT_DESIGN.md) - 실험 설계 및 데이터 수집 프로토콜

---

**🤟 SignGlove Project - Making Sign Language Accessible Through Technology**
