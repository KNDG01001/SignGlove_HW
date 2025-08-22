# SignGlove_HW 변경 이력

## 📊 이전 vs 현재 방향성 비교

| 항목 | 이전 (Madgwick 기반) | 현재 (보완 필터 기반) | 변경 이유 |
|------|---------------------|---------------------|----------|
| **센서 퓨전** | Madgwick AHRS 알고리즘 | 간단한 보완 필터 (Complementary Filter) | 계산 복잡도 감소, 실시간 성능 향상 |
| **펌웨어** | 복잡한 quaternion 계산 | 직접적인 pitch/roll/yaw 계산 | 메모리 사용량 감소, 디버깅 용이 |
| **데이터 포맷** | 7필드 (madgwick 중심) | 12필드 (가속도 포함) | 가속도 데이터 활용으로 ML 성능 향상 |
| **수집 방식** | WiFi 기반 수집 | UART + 통합 수집기 | 안정성 향상, 실시간 처리 개선 |
| **파일명 규칙** | `imu_madgwick_*.csv` | `imu_flex_*.csv` / `episode_*.h5` | 센서 유형 명확화, 체계적 관리 |
| **주 수집기** | csv_wifi.py | server.py + integration/ | 기능 통합, 사용 편의성 향상 |
| **데이터 저장** | 단순 CSV | CSV + H5 (KLP 호환) | ML 파이프라인 호환성 개선 |
| **클래스 관리** | 수동 레이블링 | 34개 KSL 자동 관리 | 체계적 데이터셋 구축 |
| **진행률 추적** | 없음 | JSON 기반 자동 추적 | 수집 효율성 향상 |
| **실시간 피드백** | 기본 로깅 | 진행률 바, Hz 측정 | 사용자 경험 개선 |

## 🚀 주요 개선사항

### 2025.01.26 - 현재 버전 (v2.0)
- ✅ **보완 필터 도입**: Madgwick → 간단한 complementary filter
- ✅ **가속도 데이터 추가**: 12필드 CSV 지원
- ✅ **통합 수집기**: ROS2 스타일 키보드 인터페이스
- ✅ **H5 형식 지원**: KLP-SignGlove 호환
- ✅ **34개 KSL 클래스**: 체계적 수어 데이터 관리
- ✅ **실시간 Hz 측정**: 아두이노 타임스탬프 기준
- ✅ **진행률 추적**: JSON 기반 자동 관리

### 2025.07.26 - 이전 버전 (v1.0)
- ❌ **Madgwick AHRS**: 복잡한 quaternion 계산
- ❌ **WiFi 중심**: 네트워크 의존성
- ❌ **7필드 CSV**: 제한적 센서 데이터
- ❌ **수동 수집**: 단순한 로깅 방식

## 📝 삭제된 레거시 파일들

### Madgwick 관련 파일 (2025.01.26 정리)
```
❌ imu_madgwick_20250726_213415.csv  # 빈 파일
❌ imu_madgwick_20250726_213531.csv  # 빈 파일  
❌ imu_madgwick_20250726_213930.csv  # 36KB 데이터
❌ imu_madgwick_20250726_214506.csv  # 21KB 데이터
❌ imu_madgwick_20250726_214840.csv  # 2KB 데이터
❌ imu_madgwick_20250726_215851.csv  # 빈 파일
❌ imu_madgwick_20250726_215937.csv  # 2KB 데이터
```

### 변경된 파일명 규칙
- `csv_wifi.py`: `imu_madgwick_*` → `imu_wifi_*`
- 메인 수집: `imu_flex_*` (UART) / `episode_*` (H5)

## 🎯 현재 핵심 파일 구조

```
SignGlove_HW/
├── 🔥 server.py                    # 메인 테스트 수집기 (9필드)
├── 🔥 integration/signglove_unified_collector.py  # 통합 수집기 (12필드)
├── 📱 imu_flex_serial.ino          # 아두이노 펌웨어
├── 📊 csv_uart.py                  # 간단 CSV 수집
├── 📊 csv_wifi.py                  # WiFi 수집 (레거시)
├── 📂 datasets/                    # 체계적 데이터 관리
└── 📚 README.md + EXPERIMENT_DESIGN.md  # 종합 문서
```

## 🔄 업데이트 이력

| 날짜 | 버전 | 주요 변경사항 | 담당자 |
|------|------|--------------|--------|
| 2025.01.26 | v2.0 | Madgwick 제거, 보완 필터 도입, 통합 수집기 | @사용자 |
| 2025.01.26 | v1.9 | server.py 기준 반영, 실험 고려사항 보강 | @AI |
| 2025.01.26 | v1.8 | 가속도 데이터 추가, 12필드 지원 | @AI |
| 2025.07.26 | v1.0 | Madgwick 기반 초기 버전 | @이전팀 |

---

**📝 이 파일은 채팅 진행에 따라 지속적으로 업데이트됩니다.**
