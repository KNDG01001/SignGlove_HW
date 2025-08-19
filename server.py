"""
SignGlove 통합 수어 데이터 수집기 (SignGlove_HW 전용 버전)
한국어 수어 34개 클래스 대응 + 실시간 하드웨어 연동 (개선판)

개선 사항:
- 실시간 출력 정밀도 향상(.3f) + 델타(Δ) 표시
- RAW_ECHO 옵션으로 아두이노 원문 CSV 라인 에코
- 연결 직후 자동 초기화 옵션(AUTO_RECAL / AUTO_YAWZERO / AUTO_ZERO)
- 나머지 저장/진행률/키 입력 로직은 기존 유지
"""

import sys
import time
import serial
import threading
import numpy as np
import h5py
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dataclasses import dataclass, asdict
import json
import queue

# ------------------- 디버그/초기화 옵션 -------------------
RAW_ECHO = False      # True면 아두이노에서 받은 원문 CSV 라인을 그대로 출력
PRINT_DELTAS = True   # True면 각도(P/R/Y)의 직전 샘플 대비 Δ(변화량)도 출력
AUTO_RECAL = False    # 연결 직후 자이로 바이어스 자동 보정(recal 명령)
AUTO_YAWZERO = False  # 연결 직후 yawzero 자동 전송
AUTO_ZERO = False     # 연결 직후 zero 자동 전송(출력 오프셋 0 기준)

# OS별 키보드 입력 모듈 임포트
if sys.platform == 'win32':
    import msvcrt
else:
    import termios
    import tty


@dataclass
class SignGloveSensorReading:
    """SignGlove 센서 읽기 데이터 구조"""
    timestamp_ms: int           # 아두이노 millis() 타임스탬프
    recv_timestamp_ms: int      # PC 수신 타임스탬프

    # IMU 데이터 (오일러 각)
    pitch: float               # Y축 회전 (도)
    roll: float                # X축 회전 (도)
    yaw: float                 # Z축 회전 (도)

    # 플렉스 센서 데이터 (ADC 값)
    flex1: int                 # 엄지 (0-1023)
    flex2: int                 # 검지 (0-1023)
    flex3: int                 # 중지 (0-1023)
    flex4: int                 # 약지 (0-1023)
    flex5: int                 # 소지 (0-1023)

    # 계산된 Hz (실제 측정 주기)
    sampling_hz: float

    # 가속도 데이터 (IMU에서 실제 측정) - 아두이노에서 전송되는 경우 사용
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0


class SignGloveUnifiedCollector:
    """SignGlove 통합 수어 데이터 수집기"""

    def __init__(self):
        print("🤟 SignGlove 통합 수어 데이터 수집기 초기화 중...")

        # 34개 한국어 수어 클래스 정의
        self.ksl_classes = {
            "consonants": ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"],
            "vowels": ["ㅏ", "ㅑ", "ㅓ", "ㅕ", "ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅡ", "ㅣ"],
            "numbers": [str(i) for i in range(10)],
        }

        # 전체 클래스 리스트
        self.all_classes = []
        for category in self.ksl_classes.values():
            self.all_classes.extend(category)

        # 수집 목표/우선순위
        self.collection_targets = {
            "ㄱ": {"target": 100, "priority": 1, "description": "기역 - 기본 자음"},
            "ㄴ": {"target": 100, "priority": 1, "description": "니은 - 기본 자음"},
            "ㄷ": {"target": 100, "priority": 1, "description": "디귿 - 기본 자음"},
            "ㄹ": {"target": 100, "priority": 1, "description": "리을 - 기본 자음"},
            "ㅁ": {"target": 100, "priority": 1, "description": "미음 - 기본 자음"},
            "ㅂ": {"target": 80, "priority": 2, "description": "비읍"},
            "ㅅ": {"target": 80, "priority": 2, "description": "시옷"},
            "ㅇ": {"target": 80, "priority": 2, "description": "이응"},
            "ㅈ": {"target": 80, "priority": 2, "description": "지읒"},
            "ㅊ": {"target": 80, "priority": 2, "description": "치읓"},
            "ㅋ": {"target": 60, "priority": 3, "description": "키읔"},
            "ㅌ": {"target": 60, "priority": 3, "description": "티읕"},
            "ㅍ": {"target": 60, "priority": 3, "description": "피읖"},
            "ㅎ": {"target": 60, "priority": 3, "description": "히읗"},
            "ㅏ": {"target": 80, "priority": 2, "description": "아 - 기본 모음"},
            "ㅓ": {"target": 80, "priority": 2, "description": "어 - 기본 모음"},
            "ㅗ": {"target": 80, "priority": 2, "description": "오 - 기본 모음"},
            "ㅜ": {"target": 80, "priority": 2, "description": "우 - 기본 모음"},
            "ㅡ": {"target": 80, "priority": 2, "description": "으 - 기본 모음"},
            "ㅣ": {"target": 80, "priority": 2, "description": "이 - 기본 모음"},
            "ㅑ": {"target": 60, "priority": 3, "description": "야 - 복합 모음"},
            "ㅕ": {"target": 60, "priority": 3, "description": "여 - 복합 모음"},
            "ㅛ": {"target": 60, "priority": 3, "description": "요 - 복합 모음"},
            "ㅠ": {"target": 60, "priority": 3, "description": "유 - 복합 모음"},
            **{str(i): {"target": 50, "priority": 3, "description": f"숫자 {i}"} for i in range(10)},
        }

        # 상태 변수들
        self.collecting = False
        self.current_class = None
        self.episode_data: List[SignGloveSensorReading] = []
        self.episode_start_time = None
        self.sample_count = 0

        # 시리얼
        self.serial_port: Optional[serial.Serial] = None
        self.serial_thread: Optional[threading.Thread] = None
        self.data_queue: "queue.Queue[SignGloveSensorReading]" = queue.Queue(maxsize=1000)
        self.stop_event = threading.Event()

        # 통계
        self.collection_stats = defaultdict(int)
        self.session_stats = defaultdict(int)

        # 경로/파일
        self.data_dir = Path("datasets/unified")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.progress_file = self.data_dir / "collection_progress.json"

        # 기타
        self.class_selection_mode = False
        self.initial_posture_reference: Optional[SignGloveSensorReading] = None
        self.realtime_print_enabled = False

        self._prev_reading: Optional[SignGloveSensorReading] = None  # 델타 계산용

        self.load_collection_progress()
        print("✅ SignGlove 통합 수집기 준비 완료!")
        self.show_usage_guide()

    # ------------------- UI/도움말 -------------------
    def show_usage_guide(self):
        print("\n" + "=" * 60)
        print("🤟 SignGlove 통합 수어 데이터 수집기")
        print("=" * 60)
        print("📋 조작 방법:")
        print("   C: 시리얼 포트 연결/재연결")
        print("   N: 새 에피소드 시작 (클래스 선택)")
        print("   M: 현재 에피소드 종료")
        print("   I: 현재 자세가 초기 자세와 일치하는지 확인")
        print("   S: 현재 자세를 초기 자세 기준으로 설정")
        print("   T: 실시간 센서 값 출력 토글")
        print("   P: 진행 상황 확인 (※ 필요시 확장 가능)")
        print("   R: 진행률 재계산 (H5 파일 스캔) (※ 필요시 구현)")
        print("   D: 모든 데이터 및 진행률 초기화 (주의!)")
        print("   Q: 프로그램 종료")
        print("")
        print("🎯 34개 한국어 수어 클래스:")
        print("   자음 14개: ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ")
        print("   모음 10개: ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ")
        print("   숫자 10개: 0123456789")
        print("")
        print("💡 먼저 'C' 키로 아두이노 연결 후 'N' 키로 수집 시작!")
        print("=" * 60)

    # ------------------- 연결/통신 -------------------
    def connect_arduino(self, port: str = None, baudrate: int = 115200) -> bool:
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()

            if port is None:
                port = self.find_arduino_port()
                if not port:
                    print("❌ 아두이노 포트를 찾을 수 없습니다.")
                    return False

            print(f"🔌 {port}에 연결 중... (보드레이트: {baudrate})")
            self.serial_port = serial.Serial(port, baudrate, timeout=1)
            time.sleep(2)  # 아두이노 리셋 대기

            # 헤더 체크
            if not self.test_communication():
                print("❌ 아두이노 통신 테스트 실패")
                return False

            # (옵션) 연결 직후 자동 초기화 루틴
            if AUTO_RECAL:
                self.serial_port.write(b"recal\n")
                print("↪️  sent: recal")
                time.sleep(1.0)
            if AUTO_YAWZERO:
                self.serial_port.write(b"yawzero\n")
                print("↪️  sent: yawzero")
                time.sleep(0.2)
            if AUTO_ZERO:
                self.serial_port.write(b"zero\n")
                print("↪️  sent: zero")
                time.sleep(0.2)

            print(f"✅ 아두이노 연결 성공: {port}")
            self.start_data_reception()
            return True

        except Exception as e:
            print(f"❌ 아두이노 연결 실패: {e}")
            return False

    def find_arduino_port(self) -> Optional[str]:
        import serial.tools.list_ports
        arduino_patterns = ['usbmodem', 'usbserial', 'ttyUSB', 'ttyACM', 'COM']
        ports = serial.tools.list_ports.comports()
        for port in ports:
            port_name = port.device.lower()
            if any(p.lower() in port_name for p in arduino_patterns):
                print(f"🔍 아두이노 포트 발견: {port.device} ({port.description})")
                return port.device

        # macOS 보조 탐색
        import platform
        if platform.system() == "Darwin":
            for i in range(1, 10):
                p = f"/dev/cu.usbmodem{i}"
                if Path(p).exists():
                    return p
        return None

    def test_communication(self) -> bool:
        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            self.serial_port.write(b"header\n")
            time.sleep(0.5)
            for _ in range(3):
                if self.serial_port.in_waiting > 0:
                    response = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if 'timestamp' in response.lower() and 'flex' in response.lower():
                        print(f"📋 헤더 확인: {response}")
                        return True
                time.sleep(0.3)
            return False
        except Exception as e:
            print(f"⚠️ 통신 테스트 오류: {e}")
            return False

    def start_data_reception(self):
        if self.serial_thread and self.serial_thread.is_alive():
            self.stop_event.set()
            self.serial_thread.join(timeout=2)
        self.stop_event.clear()
        self.serial_thread = threading.Thread(target=self._data_reception_worker, daemon=True)
        self.serial_thread.start()
        print("📡 데이터 수신 스레드 시작됨")

    def _data_reception_worker(self):
        last_arduino_ms = None
        self._prev_reading = None

        while not self.stop_event.is_set():
            try:
                if not self.serial_port or not self.serial_port.is_open:
                    break

                if self.serial_port.in_waiting > 0:
                    raw = self.serial_port.readline()
                    try:
                        line = raw.decode('utf-8', errors='ignore').strip()
                    except Exception:
                        continue

                    if not line or line.startswith('#'):
                        continue

                    if RAW_ECHO:
                        print("RAW:", line)

                    # CSV: timestamp,pitch,roll,yaw,accel_x,accel_y,accel_z,flex1..5  (총 12개)
                    parts = line.split(',')
                    if len(parts) != 12:
                        # 포맷이 다르면 무시 (필요시 len==9 등 변형도 허용하도록 확장 가능)
                        continue

                    try:
                        recv_time_ms = int(time.time() * 1000)
                        arduino_ts = int(float(parts[0]))

                        sampling_hz = 0.0
                        if last_arduino_ms is not None:
                            dt_ms = max(1, arduino_ts - last_arduino_ms)
                            sampling_hz = 1000.0 / dt_ms
                        last_arduino_ms = arduino_ts

                        reading = SignGloveSensorReading(
                            timestamp_ms=arduino_ts,
                            recv_timestamp_ms=recv_time_ms,
                            pitch=float(parts[1]),
                            roll=float(parts[2]),
                            yaw=float(parts[3]),
                            accel_x=float(parts[4]),
                            accel_y=float(parts[5]),
                            accel_z=float(parts[6]),
                            flex1=int(parts[7]),
                            flex2=int(parts[8]),
                            flex3=int(parts[9]),
                            flex4=int(parts[10]),
                            flex5=int(parts[11]),
                            sampling_hz=sampling_hz
                        )

                        # 실시간 출력
                        if self.realtime_print_enabled:
                            if PRINT_DELTAS and self._prev_reading is not None:
                                dP = reading.pitch - self._prev_reading.pitch
                                dR = reading.roll  - self._prev_reading.roll
                                dY = reading.yaw   - self._prev_reading.yaw
                                print(
                                    f"📊 {reading.timestamp_ms}ms | "
                                    f"P:{reading.pitch:.3f} ({dP:+.3f})  "
                                    f"R:{reading.roll:.3f} ({dR:+.3f})  "
                                    f"Y:{reading.yaw:.3f} ({dY:+.3f}) | "
                                    f"AX:{reading.accel_x:.3f}, AY:{reading.accel_y:.3f}, AZ:{reading.accel_z:.3f} | "
                                    f"{sampling_hz:.1f}Hz"
                                )
                            else:
                                print(
                                    f"📊 {reading.timestamp_ms}ms | "
                                    f"P:{reading.pitch:.3f}, R:{reading.roll:.3f}, Y:{reading.yaw:.3f} | "
                                    f"AX:{reading.accel_x:.3f}, AY:{reading.accel_y:.3f}, AZ:{reading.accel_z:.3f} | "
                                    f"{sampling_hz:.1f}Hz"
                                )

                        self._prev_reading = reading

                        # 큐로 전달
                        if not self.data_queue.full():
                            self.data_queue.put(reading)

                        # 에피소드 수집 중이면 적재
                        if self.collecting:
                            self.episode_data.append(reading)
                            if len(self.episode_data) % 20 == 0:
                                print(f"📊 수집 중... {len(self.episode_data)}개 샘플 (현재: {sampling_hz:.1f}Hz)")
                            if len(self.episode_data) >= 300:
                                print(f"✅ {self.current_class} 클래스 300개 샘플 수집 완료. 에피소드를 종료하고 재시작합니다.")
                                self.stop_episode()
                                self.start_episode(self.current_class)

                    except (ValueError, IndexError) as e:
                        print(f"⚠️ 데이터 파싱 오류: {line} → {e}")

                time.sleep(0.001)

            except Exception as e:
                print(f"❌ 데이터 수신 오류: {e}")
                break

    # ------------------- UI: 클래스 선택/진행 표시 -------------------
    def show_class_selection(self):
        self.class_selection_mode = True
        print("\n🎯 한국어 수어 클래스 선택")
        print("=" * 80)

        priority_groups = defaultdict(list)
        for class_name in self.all_classes:
            if class_name in self.collection_targets:
                priority_groups[self.collection_targets[class_name]["priority"]].append(class_name)

        current_idx = 1
        self.class_map = {}

        for priority in sorted(priority_groups.keys()):
            if priority == 1:
                print("🔥 우선순위 1 (기본 자음 - 먼저 수집 권장)")
            elif priority == 2:
                print("⭐ 우선순위 2 (기본 모음 + 확장 자음)")
            else:
                print("📝 우선순위 3 (복합 모음 + 숫자)")

            for class_name in priority_groups[priority]:
                target_info = self.collection_targets[class_name]
                current = self.collection_stats[class_name]
                target = target_info["target"]
                remaining = max(0, target - current)
                progress = min(100, (current / target * 100)) if target > 0 else 0
                status_emoji = "✅" if current >= target else "⏳"
                progress_bar = self.create_progress_bar(current, target)
                print(f"{status_emoji} {current_idx:2d}: {class_name} - {target_info['description']}")
                print(f"     {progress_bar} ({current}/{target}) {progress:.1f}% - {remaining}개 남음")
                self.class_map[str(current_idx)] = class_name
                current_idx += 1
            print("")

        total_current = sum(self.collection_stats.values())
        total_target = sum(info["target"] for info in self.collection_targets.values())
        overall_progress = (total_current / total_target * 100) if total_target > 0 else 0
        print("📊 전체 진행률:")
        overall_bar = self.create_progress_bar(total_current, total_target, width=30)
        print(f"   {overall_bar} ({total_current}/{total_target}) {overall_progress:.1f}%")
        print("")
        

    def create_progress_bar(self, current: int, target: int, width: int = 15) -> str:
        if target == 0:
            return "█" * width
        percentage = min(current / target, 1.0)
        filled = int(width * percentage)
        return "█" * filled + "░" * (width - filled)

    # ------------------- 에피소드 수집/저장 -------------------
    def start_episode(self, class_name: str):
        if self.collecting:
            self.stop_episode()

        if not self.serial_port or not self.serial_port.is_open:
            print("❌ 아두이노가 연결되지 않았습니다. 'C' 키로 연결하세요.")
            return

        self.current_class = class_name
        self.episode_data = []
        self.collecting = True
        self.episode_start_time = time.time()
        self.sample_count = 0

        # 수신 큐 비우기
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                break

        target_info = self.collection_targets.get(class_name, {"description": "사용자 정의"})
        current = self.collection_stats[class_name]
        target = self.collection_targets.get(class_name, {}).get("target", 100)
        remaining = max(0, target - current)

        print(f"\n🎬 에피소드 시작: '{class_name}' ({target_info['description']})")
        print(f"📊 현재 진행률: {current}/{target} ({remaining}개 남음)")
        print("💡 충분한 데이터 수집 후 'M' 키로 종료하세요!")
        print("⏱️ 권장 수집 시간: 3-5초 (자연스러운 수어 동작)")

    def stop_episode(self):
        if not self.collecting:
            print("⚠️ 수집 중이 아닙니다.")
            return

        self.collecting = False

        if not self.episode_data:
            print("⚠️ 수집된 데이터가 없습니다.")
            return

        duration = time.time() - self.episode_start_time
        h5_save_path = self.save_episode_data()
        csv_save_path = self.save_episode_data_csv()

        self.collection_stats[self.current_class] += 1
        self.session_stats[self.current_class] += 1
        self.save_collection_progress()

        target_info = self.collection_targets.get(self.current_class, {})
        current = self.collection_stats[self.current_class]
        target = target_info.get("target", 100)
        remaining = max(0, target - current)
        progress = min(100, (current / target * 100)) if target > 0 else 0

        print(f"\n✅ 에피소드 완료: '{self.current_class}'")
        print(f"⏱️ 수집 시간: {duration:.1f}초")
        print(f"📊 데이터 샘플: {len(self.episode_data)}개")
        if h5_save_path:
            print(f"💾 H5 저장 경로: {h5_save_path}")
        if csv_save_path:
            print(f"💾 CSV 저장 경로: {csv_save_path}")
        print(f"📈 진행률: {current}/{target} ({progress:.1f}%) - {remaining}개 남음")
        if current >= target:
            print(f"🎉 '{self.current_class}' 클래스 목표 달성!")

    def save_episode_data_csv(self) -> Optional[Path]:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"episode_{timestamp}_{self.current_class}.csv"
        save_path = self.data_dir / filename
        try:
            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not self.episode_data:
                    return None
                header = list(asdict(self.episode_data[0]).keys())
                writer.writerow(header)
                for reading in self.episode_data:
                    writer.writerow(asdict(reading).values())
            return save_path
        except Exception as e:
            print(f"❌ CSV 저장 실패: {e}")
            return None

    def save_episode_data(self) -> Path:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"episode_{timestamp}_{self.current_class}.h5"
        save_path = self.data_dir / filename

        timestamps = []
        arduino_timestamps = []
        sampling_rates = []
        flex_data = []
        orientation_data = []
        accel_data = []

        for reading in self.episode_data:
            timestamps.append(reading.recv_timestamp_ms)
            arduino_timestamps.append(reading.timestamp_ms)
            sampling_rates.append(reading.sampling_hz)
            flex_data.append([reading.flex1, reading.flex2, reading.flex3, reading.flex4, reading.flex5])
            orientation_data.append([reading.pitch, reading.roll, reading.yaw])
            accel_data.append([reading.accel_x, reading.accel_y, reading.accel_z])

        timestamps = np.array(timestamps, dtype=np.int64)
        arduino_timestamps = np.array(arduino_timestamps, dtype=np.int64)
        sampling_rates = np.array(sampling_rates, dtype=np.float32)
        flex_data = np.array(flex_data, dtype=np.float32)
        orientation_data = np.array(orientation_data, dtype=np.float32)
        accel_data = np.array(accel_data, dtype=np.float32)

        with h5py.File(save_path, 'w') as f:
            f.attrs['class_name'] = self.current_class
            f.attrs['class_category'] = self.get_class_category(self.current_class)
            f.attrs['episode_duration'] = time.time() - self.episode_start_time
            f.attrs['num_samples'] = len(self.episode_data)
            f.attrs['avg_sampling_rate'] = float(np.mean(sampling_rates)) if len(sampling_rates) else 0.0
            f.attrs['device_id'] = "SIGNGLOVE_UNIFIED_001"
            f.attrs['collection_date'] = datetime.now().isoformat()

            f.create_dataset('timestamps', data=timestamps, compression='gzip')
            f.create_dataset('arduino_timestamps', data=arduino_timestamps, compression='gzip')
            f.create_dataset('sampling_rates', data=sampling_rates, compression='gzip')

            sensor_data = np.concatenate([flex_data, orientation_data], axis=1)  # (N, 8)
            f.create_dataset('sensor_data', data=sensor_data, compression='gzip')

            sensor_group = f.create_group('sensors')
            sensor_group.create_dataset('flex', data=flex_data, compression='gzip')
            sensor_group.create_dataset('orientation', data=orientation_data, compression='gzip')
            sensor_group.create_dataset('acceleration', data=accel_data, compression='gzip')

            f.attrs['label'] = self.current_class
            f.attrs['label_idx'] = self.all_classes.index(self.current_class)

        return save_path

    # ------------------- 자세 기준/검증 -------------------
    def get_class_category(self, class_name: str) -> str:
        if class_name in self.ksl_classes["consonants"]:
            return "consonant"
        elif class_name in self.ksl_classes["vowels"]:
            return "vowel"
        elif class_name in self.ksl_classes["numbers"]:
            return "number"
        return "unknown"

    def check_initial_posture(self, reading: Optional[SignGloveSensorReading] = None) -> bool:
        if self.initial_posture_reference is None:
            print("⚠️ 초기 자세 기준이 설정되지 않았습니다. 'S' 키를 눌러 현재 자세를 기준으로 설정하세요.")
            return False

        if reading is None:
            try:
                reading = self.data_queue.get_nowait()
            except queue.Empty:
                print("⚠️ 센서 데이터가 없습니다. 아두이노 연결을 확인하거나 데이터 수신을 기다리세요.")
                return False

        POSTURE_TOLERANCE_IMU = 5.0
        POSTURE_TOLERANCE_FLEX = 20

        is_initial_posture = True
        feedback = []

        if abs(reading.pitch - self.initial_posture_reference.pitch) > POSTURE_TOLERANCE_IMU:
            is_initial_posture = False
            feedback.append(f"  - 손목 Pitch가 기준과 다릅니다 (현재: {reading.pitch:.1f}, 기준: {self.initial_posture_reference.pitch:.1f})")
        if abs(reading.roll - self.initial_posture_reference.roll) > POSTURE_TOLERANCE_IMU:
            is_initial_posture = False
            feedback.append(f"  - 손목 Roll이 기준과 다릅니다 (현재: {reading.roll:.1f}, 기준: {self.initial_posture_reference.roll:.1f})")

        for i in range(1, 6):
            flex_key = f'flex{i}'
            cur = getattr(reading, flex_key)
            ref = getattr(self.initial_posture_reference, flex_key)
            if abs(cur - ref) > POSTURE_TOLERANCE_FLEX:
                is_initial_posture = False
                feedback.append(f"  - {i}번 손가락 Flex가 기준과 다릅니다 (현재: {cur}, 기준: {ref})")

        if is_initial_posture:
            print("✅ 현재 자세가 초기 자세 기준과 일치합니다.")
            return True
        else:
            print("❌ 현재 자세가 초기 자세 기준과 일치하지 않습니다. 아래를 참고하여 자세를 교정하세요:")
            for msg in feedback:
                print(msg)
            return False

    def set_initial_posture(self):
        try:
            reading = self.data_queue.get_nowait()
            self.initial_posture_reference = reading
            print("✅ 현재 자세가 초기 자세 기준으로 설정되었습니다.")
            print(f"   기준값: Pitch:{reading.pitch:.1f}, Roll:{reading.roll:.1f}, Yaw:{reading.yaw:.1f} | "
                  f"Flex:{reading.flex1},{reading.flex2},{reading.flex3},{reading.flex4},{reading.flex5}")
        except queue.Empty:
            print("⚠️ 센서 데이터가 없습니다. 아두이노 연결을 확인하거나 데이터 수신을 기다리세요.")

    # ------------------- 진행상황 저장/로드/리셋 -------------------
    def load_collection_progress(self):
        try:
            if self.progress_file.exists():
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.collection_stats = defaultdict(int, data.get('collection_stats', {}))
                print("📊 수집 진행상황 로드 완료")
            else:
                self.collection_stats = defaultdict(int)
                print("📊 새로운 수집 진행상황 시작")
        except Exception as e:
            print(f"⚠️ 진행상황 로드 실패: {e}")
            self.collection_stats = defaultdict(int)

    def save_collection_progress(self):
        try:
            data = {
                "last_updated": datetime.now().isoformat(),
                "collection_stats": dict(self.collection_stats),
                "session_stats": dict(self.session_stats),
                "total_episodes": sum(self.collection_stats.values())
            }
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 진행상황 저장 실패: {e}")

    def reset_all_progress(self):
        print("\n" + "=" * 60)
        print("⚠️ 경고: 모든 수집 데이터(H5, CSV)와 진행 상황(JSON)이 삭제됩니다.")
        print("이 작업은 되돌릴 수 없습니다. 정말로 초기화하시겠습니까? (y/n)")
        print("=" * 60)
        try:
            confirm_key = self.get_key()
            if confirm_key == 'y':
                print("\n🔄 진행 상황 초기화 중...")
                deleted_files_count = 0
                for file_path in self.data_dir.glob('*.h5'):
                    file_path.unlink()
                    deleted_files_count += 1
                for file_path in self.data_dir.glob('*.csv'):
                    file_path.unlink()
                    deleted_files_count += 1
                if deleted_files_count > 0:
                    print(f"🗑️ {deleted_files_count}개의 데이터 파일(H5, CSV)을 삭제했습니다.")
                else:
                    print("🗑️ 삭제할 데이터 파일이 없습니다.")
                self.collection_stats = defaultdict(int)
                self.session_stats = defaultdict(int)
                self.save_collection_progress()
                print("📊 collection_progress.json 파일이 초기화되었습니다.")
                print("✅ 모든 진행 상황이 성공적으로 초기화되었습니다.")
            else:
                print("🚫 초기화 작업이 취소되었습니다.")
        except Exception as e:
            print(f"❌ 초기화 중 오류 발생: {e}")

    # ------------------- 키 입력 -------------------
    def get_key(self) -> str:
        if sys.platform == 'win32':
            if msvcrt.kbhit():
                try:
                    return msvcrt.getch().decode('utf-8').lower()
                except UnicodeDecodeError:
                    return ''
            return ""
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                import select
                if select.select([sys.stdin], [], [], 0.01)[0]:
                    ch = sys.stdin.read(1)
                    return ch.lower()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ""

    def handle_key_input(self, key: str):
        if self.class_selection_mode:
            self.class_selection_mode = False  # Exit selection mode automatically
            if key.isdigit() and key in self.class_map:
                selected_class = self.class_map[key]
                self.start_episode(selected_class)
            else:
                if key:  # If user entered something other than empty string
                    print(f"⚠️ 잘못된 선택: {key}")
                print("🚫 클래스 선택이 취소되었습니다.")
            return

        if key == '\x03' or key == 'q':
            if self.collecting:
                self.stop_episode()
            print("\n👋 SignGlove 수집기를 종료합니다.")
            sys.exit(0)

        elif key == 'c':
            print("🔌 아두이노 연결 중...")
            if self.connect_arduino():
                print("✅ 연결 완료! 'N' 키로 수집을 시작하세요.")
            else:
                print("❌ 연결 실패. 아두이노와 케이블을 확인하세요.")

        elif key == 'n':
            if self.collecting:
                self.stop_episode()
            self.show_class_selection()

        elif key == 'm':
            if self.collecting:
                self.stop_episode()
            else:
                print("⚠️ 현재 수집 중이 아닙니다.")

        elif key == 'i':
            print("🧘 현재 자세가 초기 자세 기준과 일치하는지 확인 중...")
            self.check_initial_posture()

        elif key == 's':
            print("✨ 현재 자세를 초기 자세 기준으로 설정합니다...")
            self.set_initial_posture()

        elif key == 't':
            self.realtime_print_enabled = not self.realtime_print_enabled
            if self.realtime_print_enabled:
                print("✅ 실시간 센서 값 출력이 활성화되었습니다.")
            else:
                print("❌ 실시간 센서 값 출력이 비활성화되었습니다.")

        elif key == 'd':
            self.reset_all_progress()

        else:
            if not self.class_selection_mode:
                print(f"⚠️ 알 수 없는 키: {key.upper()}")
                print("💡 도움말: C(연결), N(새수집), M(종료), Q(종료)")

    # ------------------- 메인 루프 -------------------
    def run(self):
        print("\n⏳ 키보드 입력 대기 중... (도움말은 위 참조)")
        try:
            while True:
                if self.class_selection_mode:
                    # In class selection mode, we wait for user to type a number and press Enter.
                    choice = input("\n✨ 1-34번 중 원하는 클래스를 선택하고 Enter를 누르세요 (취소: Enter): ")
                    self.handle_key_input(choice)
                else:
                    # In normal mode, we use non-blocking get_key for single char commands.
                    key = self.get_key()
                    if key:
                        self.handle_key_input(key)
                time.sleep(0.01)
        except KeyboardInterrupt:
            if self.collecting:
                self.stop_episode()
            print("\n👋 프로그램을 종료합니다.")
        finally:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()


def main():
    try:
        collector = SignGloveUnifiedCollector()
        collector.run()
    except Exception as e:
        print(f"❌ 프로그램 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
