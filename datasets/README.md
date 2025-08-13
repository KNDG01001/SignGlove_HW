# SignGlove 데이터셋 저장소

## 📂 폴더 구조

```
datasets/
├── raw/                    # 원본 CSV 파일
│   ├── imu_flex_YYYYMMDD_HHMMSS.csv
│   └── (아두이노에서 직접 수집된 데이터)
│
├── processed/              # 전처리된 데이터
│   ├── normalized/         # 정규화된 데이터
│   ├── filtered/          # 필터링된 데이터
│   └── augmented/         # 데이터 증강된 데이터
│
├── unified/               # 통합 H5 데이터셋
│   ├── episode_YYYYMMDD_HHMMSS_클래스명.h5
│   ├── collection_progress.json
│   └── (통합 수집기로 생성된 에피소드 파일들)
│
└── ksl_34classes/         # 클래스별 정리된 데이터
    ├── consonants/        # 자음 데이터 (14개)
    │   ├── ㄱ/
    │   ├── ㄴ/
    │   └── ...
    ├── vowels/           # 모음 데이터 (10개)
    │   ├── ㅏ/
    │   ├── ㅑ/
    │   └── ...
    └── numbers/          # 숫자 데이터 (10개)
        ├── 0/
        ├── 1/
        └── ...
```

## 📊 데이터 형식

### 원본 CSV (raw/)
아두이노에서 직접 수집된 12필드 데이터:
```csv
timestamp(ms),pitch(°),roll(°),yaw(°),accel_x(g),accel_y(g),accel_z(g),flex1,flex2,flex3,flex4,flex5
1234567890,10.5,-5.2,15.8,0.123,-0.045,0.987,512,678,723,834,567
```

### 통합 H5 (unified/)
통합 수집기로 생성된 구조화된 데이터:
```python
episode_20250126_153000_ㄱ.h5:
├── timestamps          # PC 수신 타임스탬프 [N] (int64)
├── arduino_timestamps  # 아두이노 타임스탬프 [N] (int64)
├── sampling_rates     # 실시간 Hz [N] (float32)
├── sensor_data        # 메인 센서 데이터 [N,8] (float32)
└── sensors/
    ├── flex           # 플렉스 센서 [N,5] (float32)
    ├── orientation    # 자이로 오일러각 [N,3] (float32)
    └── acceleration   # 가속도 [N,3] (float32)

메타데이터:
- class_name: "ㄱ"
- class_category: "consonant"
- episode_duration: 3.2 (초)
- num_samples: 128
- avg_sampling_rate: 40.0 (Hz)
- device_id: "SIGNGLOVE_UNIFIED_001"
- collection_date: "2025-01-26T15:30:00"
- label: "ㄱ"
- label_idx: 0 (0-33)
```

## 🎯 수집 목표

### 34개 한국어 수어 클래스
| 카테고리 | 클래스 수 | 목표 에피소드/클래스 | 총 목표 |
|---------|-----------|---------------------|---------|
| 자음 (우선순위 1-2) | 14개 | 80-100개 | 1,260개 |
| 모음 (우선순위 2-3) | 10개 | 60-80개 | 700개 |
| 숫자 (우선순위 3) | 10개 | 50개 | 500개 |
| **총계** | **34개** | **평균 72개** | **2,460개** |

### 수집 우선순위
1. **우선순위 1** (기본 자음): ㄱ ㄴ ㄷ ㄹ ㅁ - 100개씩
2. **우선순위 2** (확장 자음 + 기본 모음): ㅂㅅㅇㅈㅊ + ㅏㅓㅗㅜㅡㅣ - 80개씩
3. **우선순위 3** (복합 모음 + 숫자): ㅋㅌㅍㅎ + ㅑㅕㅛㅠ + 0-9 - 50-60개씩

## 🚀 사용법

### 1. 데이터 수집
```bash
# 통합 수집기 실행
python integration/signglove_unified_collector.py

# 또는 간단한 CSV 수집
python csv_uart.py
```

### 2. 데이터 처리
```python
import h5py
import numpy as np

# H5 파일 읽기
with h5py.File('datasets/unified/episode_20250126_153000_ㄱ.h5', 'r') as f:
    class_name = f.attrs['class_name']  # "ㄱ"
    sensor_data = f['sensor_data'][:]   # [N, 8] 센서 데이터
    flex_data = f['sensors/flex'][:]    # [N, 5] 플렉스 센서
    accel_data = f['sensors/acceleration'][:]  # [N, 3] 가속도
    
    print(f"클래스: {class_name}")
    print(f"샘플 수: {sensor_data.shape[0]}")
    print(f"센서 데이터 형태: {sensor_data.shape}")
```

### 3. 데이터셋 분할
```python
from sklearn.model_selection import train_test_split

# 클래스별 파일 로드 후 학습/검증/테스트 분할
X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.3, stratify=y)
X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, stratify=y_temp)
```

## 📈 데이터 품질 관리

### 자동 검증 항목
- ✅ **샘플링 레이트**: 20-100Hz 범위 유지
- ✅ **에피소드 길이**: 2-10초 권장
- ✅ **센서 범위**: 플렉스(0-1023), 자이로(-180~180°), 가속도(-2~2g)
- ✅ **결측값**: 없음 (NaN 체크)
- ✅ **중복 제거**: 동일 타임스탬프 제거

### 품질 점검 스크립트
```python
# 데이터셋 품질 검사
import glob
import h5py

def check_dataset_quality():
    h5_files = glob.glob('datasets/unified/*.h5')
    
    for file_path in h5_files:
        with h5py.File(file_path, 'r') as f:
            samples = f.attrs['num_samples']
            duration = f.attrs['episode_duration']
            avg_hz = f.attrs['avg_sampling_rate']
            
            # 품질 기준 체크
            if samples < 50:
                print(f"⚠️ {file_path}: 샘플 부족 ({samples})")
            if duration < 2.0 or duration > 10.0:
                print(f"⚠️ {file_path}: 부적절한 길이 ({duration:.1f}초)")
            if avg_hz < 20 or avg_hz > 100:
                print(f"⚠️ {file_path}: 비정상 주파수 ({avg_hz:.1f}Hz)")
```

## 🔄 데이터 파이프라인

### 수집 → 전처리 → 학습 플로우
```
1. 원본 수집 (csv_uart.py / 통합 수집기)
   ↓
2. H5 변환 (통합 수집기 자동)
   ↓
3. 품질 검증 (자동/수동)
   ↓
4. 전처리 (정규화, 필터링, 증강)
   ↓
5. 클래스별 정리 (ksl_34classes/)
   ↓
6. 학습용 데이터셋 생성
   ↓
7. 모델 학습 및 평가
```

## 📝 메타데이터 스키마

각 H5 파일의 표준 메타데이터:
```python
required_attrs = {
    'class_name': str,           # KSL 클래스명 (예: "ㄱ")
    'class_category': str,       # 카테고리 ("consonant", "vowel", "number")
    'episode_duration': float,   # 수집 시간 (초)
    'num_samples': int,         # 샘플 수
    'avg_sampling_rate': float, # 평균 Hz
    'device_id': str,           # 장치 ID
    'collection_date': str,     # ISO 8601 형식 날짜
    'label': str,               # 동일한 클래스명
    'label_idx': int           # 클래스 인덱스 (0-33)
}
```

## 🎓 머신러닝 활용

### 추천 모델
1. **CNN+LSTM+Attention** (KLP-SignGlove 방식)
2. **Transformer** (시계열 처리)
3. **XGBoost/RandomForest** (전통적 ML)

### 데이터 전처리
```python
from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler

# 정규화 옵션
scaler = MinMaxScaler()  # 0-1 범위
# scaler = StandardScaler()  # 평균0, 표준편차1
# scaler = RobustScaler()   # 아웃라이어 강건

normalized_data = scaler.fit_transform(sensor_data)
```

---

**🤟 SignGlove Project - 기술로 수어를 더 접근하기 쉽게**
