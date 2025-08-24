# 상보필터 (Complementary Filter)

## 📌 왜 상보필터인가?
상보필터는 두 개의 서로 **보완적인 센서 데이터**를 합쳐서 안정적인 추정값을 만드는 기법

### 자이로 (Gyroscope)
- 각속도를 적분해서 roll, pitch 추정  
- **장점**: 빠른 움직임 추적에 강함  
- **단점**: 시간이 지날수록 drift(누적 오차) 발생  

### 가속도계 (Accelerometer)
- 중력 벡터로부터 roll, pitch 직접 계산  
- **장점**: 장기적으로 안정적  
- **단점**: 순간 가속/진동에 약하고 노이즈 많음  

---

## 📌 코드 속 수식

```cpp
roll_deg  = kAlpha * (roll_deg  + (g_roll  - b_roll ) * dt)
          + (1.0f - kAlpha) * roll_acc_deg;

pitch_deg = kAlpha * (pitch_deg + (g_pitch - b_pitch) * dt)
          + (1.0f - kAlpha) * pitch_acc_deg;
```

roll_deg + (g_roll - b_roll) * dt → 자이로 적분 (고역통과 성분)

roll_acc_deg → 가속도 기반 계산 (저역통과 성분)

kAlpha (예: 0.98) → 자이로 신호 98%, 가속도 신호 2% 반영

➡️ 즉, 고역 통과 필터(자이로) + 저역 통과 필터(가속도) = 상보필터 구조

##📌 정리

본 코드 = 상보필터 구현

장점: 계산량이 적어 Arduino Nano 33 IoT 같은 소형 MCU에서 실시간 동작 가능

단점: Yaw는 자력계가 없어서 drift 보정 불가
