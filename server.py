"""
SignGlove 통합 수어 데이터 수집기 (SignGlove_HW 전용 버전)
한국어 수어 34개 클래스 대응 + 실시간 하드웨어 연동

원본: ../scripts/signglove_unified_collector.py
최적화: SignGlove_HW 저장소 독립 실행을 위한 간소화 버전
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
    
    # IMU 데이터 (자이로스코프 - 오일러 각도)
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
    
    # 가속도 데이터 (IMU에서 실제 측정) - 아두이노에서 전송되지 않을 경우 기본값 설정
    accel_x: float = 0.0         # X축 가속도 (g)
    accel_y: float = 0.0         # Y축 가속도 (g)
    accel_z: float = 0.0         # Z축 가속도 (g)


class SignGloveUnifiedCollector:
    """SignGlove 통합 수어 데이터 수집기"""
    
    def __init__(self):
        print("🤟 SignGlove 통합 수어 데이터 수집기 초기화 중...")
        
        # 34개 한국어 수어 클래스 정의
        self.ksl_classes = {
            # 자음 14개
            "consonants": ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"],
            # 모음 10개  
            "vowels": ["ㅏ", "ㅑ", "ㅓ", "ㅕ", "ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅡ", "ㅣ"],
            # 숫자 10개
            "numbers": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
        }
        
        # 전체 클래스 리스트 (총 34개)
        self.all_classes = []
        for category in self.ksl_classes.values():
            self.all_classes.extend(category)
            
        # 진행률 목표 설정
        self.collection_targets = {
            # 기본 자음 우선순위 높음
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
            
            # 기본 모음
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
            
            # 숫자 (중간 우선순위)
            **{str(i): {"target": 50, "priority": 3, "description": f"숫자 {i}"} for i in range(10)}
        }
        
        # 수집 상태 변수
        self.collecting = False
        self.current_class = None
        self.episode_data = []
        self.episode_start_time = None
        self.sample_count = 0
        
        # 시리얼 통신
        self.serial_port = None
        self.serial_thread = None
        self.data_queue = queue.Queue()
        self.stop_event = threading.Event()
        
        # 통계 추적
        self.collection_stats = defaultdict(int)
        self.session_stats = defaultdict(int)
        
        # 데이터 저장 경로
        self.data_dir = Path("datasets/unified")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 진행상황 파일
        self.progress_file = self.data_dir / "collection_progress.json"
        
        # 클래스 선택 모드
        self.class_selection_mode = False
        
        self.load_collection_progress()
        print("✅ SignGlove 통합 수집기 준비 완료!")
        self.show_usage_guide()
        
    def show_usage_guide(self):
        """사용법 가이드 표시"""
        print("\n" + "=" * 60)
        print("🤟 SignGlove 통합 수어 데이터 수집기")
        print("=" * 60)
        print("📋 조작 방법:")
        print("   C: 시리얼 포트 연결/재연결")
        print("   N: 새 에피소드 시작 (클래스 선택)")
        print("   M: 현재 에피소드 종료")
        print("   I: 초기 자세 확인")
        print("   P: 진행 상황 확인")
        print("   R: 진행률 재계산 (H5 파일 스캔)")
        print("   Q: 프로그램 종료")
        print("")
        print("🎯 34개 한국어 수어 클래스:")
        print("   자음 14개: ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ")
        print("   모음 10개: ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ")
        print("   숫자 10개: 0123456789")
        print("")
        print("💡 먼저 'C' 키로 아두이노 연결 후 'N' 키로 수집 시작!")
        print("=" * 60)
        
    def connect_arduino(self, port: str = None, baudrate: int = 115200) -> bool:
        """아두이노 시리얼 연결"""
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
            time.sleep(2)  # 아두이노 초기화 대기
            
            # 연결 테스트
            if self.test_communication():
                print(f"✅ 아두이노 연결 성공: {port}")
                self.start_data_reception()
                return True
            else:
                print("❌ 아두이노 통신 테스트 실패")
                return False
                
        except Exception as e:
            print(f"❌ 아두이노 연결 실패: {e}")
            return False
            
    def find_arduino_port(self) -> Optional[str]:
        """아두이노 포트 자동 검색"""
        import serial.tools.list_ports
        
        # 일반적인 아두이노 포트 패턴
        arduino_patterns = [
            'usbmodem', 'usbserial', 'ttyUSB', 'ttyACM', 'COM'
        ]
        
        ports = serial.tools.list_ports.comports()
        for port in ports:
            port_name = port.device.lower()
            if any(pattern.lower() in port_name for pattern in arduino_patterns):
                print(f"🔍 아두이노 포트 발견: {port.device} ({port.description})")
                return port.device
                
        # macOS 특수 케이스
        import platform
        if platform.system() == "Darwin":
            potential_ports = [f"/dev/cu.usbmodem{i}" for i in range(1, 10)]
            for port in potential_ports:
                if Path(port).exists():
                    return port
                    
        return None
        
    def test_communication(self) -> bool:
        """아두이노 통신 테스트"""
        try:
            # 버퍼 클리어
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            
            # 헤더 요청
            self.serial_port.write(b"header\n")
            time.sleep(0.5)
            
            # 응답 확인 (3회 시도)
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
        """데이터 수신 스레드 시작"""
        if self.serial_thread and self.serial_thread.is_alive():
            self.stop_event.set()
            self.serial_thread.join(timeout=2)
            
        self.stop_event.clear()
        self.serial_thread = threading.Thread(target=self._data_reception_worker, daemon=True)
        self.serial_thread.start()
        print("📡 데이터 수신 스레드 시작됨")
        
    def _data_reception_worker(self):
        """데이터 수신 워커 스레드"""
        last_arduino_ms = None
        
        while not self.stop_event.is_set():
            try:
                if not self.serial_port or not self.serial_port.is_open:
                    break
                    
                if self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    
                    if not line or line.startswith('#'):
                        continue
                        
                    # CSV 형식 파싱: timestamp,pitch,roll,yaw,accel_x,accel_y,accel_z,flex1,flex2,flex3,flex4,flex5
                    parts = line.split(',')
                    if len(parts) == 9:
                        try:
                            recv_time_ms = int(time.time() * 1000)
                            arduino_ts = int(float(parts[0]))
                            
                            # Hz 계산 (아두이노 타임스탬프 기준)
                            sampling_hz = 0.0
                            if last_arduino_ms is not None:
                                dt_ms = max(1, arduino_ts - last_arduino_ms)
                                sampling_hz = 1000.0 / dt_ms
                            last_arduino_ms = arduino_ts
                            
                            # 센서 데이터 생성 (가속도 데이터는 아두이노에서 전송되지 않으므로 기본값 사용)
                            reading = SignGloveSensorReading(
                                timestamp_ms=arduino_ts, # 추가
                                recv_timestamp_ms=recv_time_ms,
                                pitch=float(parts[1]),
                                roll=float(parts[2]),
                                yaw=float(parts[3]),
                                flex1=int(parts[4]),
                                flex2=int(parts[5]),
                                flex3=int(parts[6]),
                                flex4=int(parts[7]),
                                flex5=int(parts[8]),
                                sampling_hz=sampling_hz # 추가
                                # accel_x, accel_y, accel_z는 dataclass의 기본값 사용
                            )
                            
                            # 큐에 추가
                            if not self.data_queue.full():
                                self.data_queue.put(reading)
                                
                            # 수집 중이면 에피소드 데이터에 추가
                            if self.collecting:
                                self.episode_data.append(reading)
                                if len(self.episode_data) % 20 == 0:  # 20샘플마다 로그
                                    print(f"📊 수집 중... {len(self.episode_data)}개 샘플 (현재: {sampling_hz:.1f}Hz)")
                                    
                        except (ValueError, IndexError) as e:
                            print(f"⚠️ 데이터 파싱 오류: {line} → {e}")
                            
                time.sleep(0.001)  # 1ms 대기
                
            except Exception as e:
                print(f"❌ 데이터 수신 오류: {e}")
                break

    def show_class_selection(self):
        """34개 클래스 선택 메뉴 표시"""
        self.class_selection_mode = True
        
        print("\n" + "🎯 한국어 수어 클래스 선택")
        print("=" * 80)
        
        # 우선순위별로 정렬하여 표시
        priority_groups = defaultdict(list)
        for class_name in self.all_classes:
            if class_name in self.collection_targets:
                priority = self.collection_targets[class_name]["priority"]
                priority_groups[priority].append(class_name)
        
        current_idx = 1
        self.class_map = {}  # 숫자 → 클래스명 매핑
        
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
            
        # 전체 진행률 요약
        total_current = sum(self.collection_stats.values())
        total_target = sum(info["target"] for info in self.collection_targets.values())
        overall_progress = (total_current / total_target * 100) if total_target > 0 else 0
        
        print("📊 전체 진행률:")
        overall_bar = self.create_progress_bar(total_current, total_target, width=30)
        print(f"   {overall_bar} ({total_current}/{total_target}) {overall_progress:.1f}%")
        print("")
        print("✨ 1-34번 중 원하는 클래스를 선택하세요!")
        print("🚫 취소하려면 다른 키를 누르세요.")
        
    def create_progress_bar(self, current: int, target: int, width: int = 15) -> str:
        """진행률 바 생성"""
        if target == 0:
            return "█" * width
        percentage = min(current / target, 1.0)
        filled = int(width * percentage)
        bar = "█" * filled + "░" * (width - filled)
        return bar

    def start_episode(self, class_name: str):
        """에피소드 시작"""
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
        
        # 데이터 수신 큐 클리어
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
        """에피소드 종료"""
        if not self.collecting:
            print("⚠️ 수집 중이 아닙니다.")
            return
            
        self.collecting = False
        
        if not self.episode_data:
            print("⚠️ 수집된 데이터가 없습니다.")
            return
            
        # 에피소드 저장
        duration = time.time() - self.episode_start_time
        h5_save_path = self.save_episode_data()
        csv_save_path = self.save_episode_data_csv()
        
        # 통계 업데이트
        self.collection_stats[self.current_class] += 1
        self.session_stats[self.current_class] += 1
        self.save_collection_progress()
        
        # 결과 출력
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
        """에피소드 데이터를 CSV 파일로 저장"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"episode_{timestamp}_{self.current_class}.csv"
        save_path = self.data_dir / filename

        try:
            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # CSV 헤더 작성
                if not self.episode_data:
                    return None
                
                header = list(asdict(self.episode_data[0]).keys())
                writer.writerow(header)

                # 데이터 작성
                for reading in self.episode_data:
                    writer.writerow(asdict(reading).values())
            
            return save_path
        except Exception as e:
            print(f"❌ CSV 저장 실패: {e}")
            return None
            
    def save_episode_data(self) -> Path:
        """에피소드 데이터를 H5 파일로 저장"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"episode_{timestamp}_{self.current_class}.h5"
        save_path = self.data_dir / filename
        
        # 데이터 변환
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
            
        # numpy 배열로 변환
        timestamps = np.array(timestamps, dtype=np.int64)
        arduino_timestamps = np.array(arduino_timestamps, dtype=np.int64)
        sampling_rates = np.array(sampling_rates, dtype=np.float32)
        flex_data = np.array(flex_data, dtype=np.float32)
        orientation_data = np.array(orientation_data, dtype=np.float32)
        accel_data = np.array(accel_data, dtype=np.float32)
        
        # H5 파일 저장 (KLP-SignGlove 호환 형식)
        with h5py.File(save_path, 'w') as f:
            # 메타데이터
            f.attrs['class_name'] = self.current_class
            f.attrs['class_category'] = self.get_class_category(self.current_class)
            f.attrs['episode_duration'] = time.time() - self.episode_start_time
            f.attrs['num_samples'] = len(self.episode_data)
            f.attrs['avg_sampling_rate'] = np.mean(sampling_rates)
            f.attrs['device_id'] = "SIGNGLOVE_UNIFIED_001"
            f.attrs['collection_date'] = datetime.now().isoformat()
            
            # 센서 데이터 (KLP-SignGlove 형식 준수)
            f.create_dataset('timestamps', data=timestamps, compression='gzip')
            f.create_dataset('arduino_timestamps', data=arduino_timestamps, compression='gzip')
            f.create_dataset('sampling_rates', data=sampling_rates, compression='gzip')
            
            # 메인 센서 데이터 (8채널: flex5개 + orientation3개)
            sensor_data = np.concatenate([flex_data, orientation_data], axis=1)
            f.create_dataset('sensor_data', data=sensor_data, compression='gzip')
            
            # 개별 데이터 그룹
            sensor_group = f.create_group('sensors')
            sensor_group.create_dataset('flex', data=flex_data, compression='gzip')
            sensor_group.create_dataset('orientation', data=orientation_data, compression='gzip')
            sensor_group.create_dataset('acceleration', data=accel_data, compression='gzip')
            
            # 라벨 정보
            f.attrs['label'] = self.current_class
            f.attrs['label_idx'] = self.all_classes.index(self.current_class)
            
        return save_path
        
    def get_class_category(self, class_name: str) -> str:
        """클래스 카테고리 반환"""
        if class_name in self.ksl_classes["consonants"]:
            return "consonant"
        elif class_name in self.ksl_classes["vowels"]:
            return "vowel"  
        elif class_name in self.ksl_classes["numbers"]:
            return "number"
        else:
            return "unknown"

    def check_initial_posture(self, reading: Optional[SignGloveSensorReading] = None) -> bool:
        """초기 자세 확인"""
        if reading is None:
            try:
                # 큐에서 최신 데이터 가져오기 (블로킹 없이)
                reading = self.data_queue.get_nowait()
            except queue.Empty:
                print("⚠️ 센서 데이터가 없습니다. 아두이노 연결을 확인하세요.")
                return False

        # 초기 자세 임계값 정의 (실험을 통해 조정 필요)
        initial_posture_thresholds = {
            'pitch': (-15, 15),
            'roll': (-15, 15),
            'yaw': (-15, 15),
            'flex1': (0, 150),
            'flex2': (0, 150),
            'flex3': (0, 150),
            'flex4': (0, 150),
            'flex5': (0, 150),
        }

        is_initial_posture = True
        feedback = []

        # Pitch 확인
        if not (initial_posture_thresholds['pitch'][0] <= reading.pitch <= initial_posture_thresholds['pitch'][1]):
            is_initial_posture = False
            feedback.append(f"  - 손목을 수평으로 유지하세요 (Pitch: {reading.pitch:.1f})")
        
        # Roll 확인
        if not (initial_posture_thresholds['roll'][0] <= reading.roll <= initial_posture_thresholds['roll'][1]):
            is_initial_posture = False
            feedback.append(f"  - 손바닥이 아래를 향하게 하세요 (Roll: {reading.roll:.1f})")

        # Flex 센서 확인
        for i in range(1, 6):
            flex_key = f'flex{i}'
            flex_val = getattr(reading, flex_key)
            if not (initial_posture_thresholds[flex_key][0] <= flex_val <= initial_posture_thresholds[flex_key][1]):
                is_initial_posture = False
                feedback.append(f"  - {i}번 손가락을 펴세요 ({flex_key}: {flex_val})")

        if is_initial_posture:
            print("✅ 초기 자세가 올바릅니다.")
            return True
        else:
            print("❌ 초기 자세가 올바르지 않습니다. 아래를 참고하여 자세를 교정하세요:")
            for msg in feedback:
                print(msg)
            return False

    def load_collection_progress(self):
        """수집 진행상황 로드"""
        try:
            if self.progress_file.exists():
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.collection_stats = defaultdict(int, data.get('collection_stats', {}))
                print(f"📊 수집 진행상황 로드 완료")
            else:
                self.collection_stats = defaultdict(int)
                print("📊 새로운 수집 진행상황 시작")
        except Exception as e:
            print(f"⚠️ 진행상황 로드 실패: {e}")
            self.collection_stats = defaultdict(int)
            
    def save_collection_progress(self):
        """수집 진행상황 저장"""
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

    def get_key(self) -> str:
        """키보드 입력 읽기 (Windows/Unix 호환)"""
        if sys.platform == 'win32':
            try:
                # Windows에서는 msvcrt.getch() 사용
                return msvcrt.getch().decode('utf-8').lower()
            except UnicodeDecodeError:
                # 화살표 키와 같은 특수 키는 여러 바이트를 반환하므로 예외 처리
                return '' # 빈 문자열 반환 또는 다른 방식으로 처리
        else:
            # Unix 계열에서는 기존 termios/tty 사용
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch.lower()
        
    def handle_key_input(self, key: str):
        """키 입력 처리"""
        if key == '\x03' or key == 'q':  # Ctrl+C 또는 Q
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
                
        elif key.isdigit() and self.class_selection_mode:
            # 클래스 선택 모드에서 숫자 입력
            if key in self.class_map:
                selected_class = self.class_map[key]
                self.class_selection_mode = False
                self.start_episode(selected_class)
            else:
                print(f"⚠️ 잘못된 선택: {key}")
                
        elif self.class_selection_mode:
            # 클래스 선택 모드 취소
            self.class_selection_mode = False
            print("🚫 클래스 선택이 취소되었습니다.")
            
        else:
            if not self.class_selection_mode:
                print(f"⚠️ 알 수 없는 키: {key.upper()}")
                print("💡 도움말: C(연결), N(새수집), M(종료), Q(종료)")
                
    def run(self):
        """메인 루프 실행"""
        print("\n⏳ 키보드 입력 대기 중... (도움말은 위 참조)")
        
        try:
            while True:
                key = self.get_key()
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
    """메인 함수"""
    try:
        collector = SignGloveUnifiedCollector()
        collector.run()
    except Exception as e:
        print(f"❌ 프로그램 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()