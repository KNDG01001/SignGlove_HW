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
    pitch: float
    roll: float
    yaw: float

    # 플렉스 센서 데이터
    flex1: int
    flex2: int
    flex3: int
    flex4: int
    flex5: int

    # 계산된 Hz
    sampling_hz: float

    # 가속도 데이터
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0


class SignGloveUnifiedCollector:
    """SignGlove 통합 수어 데이터 수집기"""

    def __init__(self):
        print("🤟 SignGlove 통합 수어 데이터 수집기 초기화 중...")

        # 34개 한국어 수어 클래스
        self.ksl_classes = {
            "consonants": ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"],
            "vowels": ["ㅏ", "ㅑ", "ㅓ", "ㅕ", "ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅡ", "ㅣ"],
            "numbers": [str(i) for i in range(10)],
        }

        # 전체 클래스 리스트
        self.all_classes = []
        for category in self.ksl_classes.values():
            self.all_classes.extend(category)

        # 수집 목표
        self.collection_targets = {
            class_name: {"target": 960, "description": f"'{class_name}'"} for class_name in self.all_classes
        }

        # 에피소드 유형
        self.episode_types = {
            "1": "많이 손가락이 펴짐",
            "2": "조금 손가락이 펴짐",
            "3": "기본",
            "4": "조금 손가락이 구부러짐",
            "5": "많이 손가락이 구부러짐",
        }
        self.samples_per_episode = 80
        self.episodes_per_type = 12
        self.total_episodes_target = len(self.episode_types) * self.episodes_per_type
        self.current_episode_type = None

        # 상태 변수
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
        self.collection_stats = defaultdict(lambda: defaultdict(int))
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
        print("📋 조작 방법: C(연결) N(새수집) M(종료) I(자세확인) S(자세저장) T(실시간출력) D(초기화) Q(종료)")
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
            time.sleep(2)

            if not self.test_communication():
                print("❌ 아두이노 통신 테스트 실패")
                return False

            if AUTO_RECAL:
                self.serial_port.write(b"recal\n")
                time.sleep(1.0)
            if AUTO_YAWZERO:
                self.serial_port.write(b"yawzero\n")
                time.sleep(0.2)
            if AUTO_ZERO:
                self.serial_port.write(b"zero\n")
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
        except Exception:
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

                    parts = line.split(',')
                    if len(parts) != 12:
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

                        if not self.data_queue.full():
                            self.data_queue.put(reading)

                        if self.collecting:
                            self.episode_data.append(reading)
                            if len(self.episode_data) % 20 == 0:
                                print(f"📥 진행 중... {len(self.episode_data)}개 수집됨 (샘플링: {sampling_hz:.1f}Hz)")

                            if len(self.episode_data) >= self.samples_per_episode:
                                print(f"📦 '{self.episode_types[self.current_episode_type]}' 유형 {self.episodes_per_type}회 목표 중 1회 완료됨.")
                                self.stop_episode()
                                self.start_episode(self.current_class)

                    except (ValueError, IndexError):
                        continue

                time.sleep(0.001)

            except Exception as e:
                print(f"❌ 데이터 수신 오류: {e}")
                break

    # ------------------- 이하 나머지 메서드는 네가 준 원본과 동일 -------------------
    # show_class_selection, create_progress_bar, start_episode, stop_episode,
    # save_episode_data_csv, save_episode_data, get_class_category,
    # check_initial_posture, set_initial_posture,
    # load_collection_progress, save_collection_progress, reset_all_progress,
    # get_key, handle_key_input, run, main
    # (생략 - 기존 그대로 두면 정상 작동)
