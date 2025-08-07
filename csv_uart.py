import serial
import csv
from datetime import datetime

csv_filename = f"test.csv"


# ---------- 시리얼 포트 설정 ----------
SERIAL_PORT = 'COM6'  # 또는 'COM3' (윈도우일 경우)
BAUD_RATE = 115200

# ---------- CSV 파일 설정 ----------
csv_filename = f"imu_flex_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# ---------- 로그 출력 함수 ----------
def debug_print(msg):
    print(f"[DEBUG] {msg}")

# ---------- 시리얼 통신 초기화 ----------
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"[+] Connected to {SERIAL_PORT} at {BAUD_RATE} baud")
except Exception as e:
    print(f"[!] Failed to open serial port: {e}")
    exit(1)

# ---------- CSV 파일 열기 ----------
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['timestamp(ms)', 'pitch(°)', 'roll(°)', 'yaw(°)', 'flex1', 'flex2', 'flex3', 'flex4', 'flex5'])

    try:
        while True:
            line = ser.readline().decode('utf-8').strip()
            if not line:
                continue

            debug_print(f"Received: {line}")
            row = line.split(',')

            if len(row) == 9:
                writer.writerow(row)
                file.flush()
                print("✔️ Data saved:", row)
            else:
                print("❌ Invalid format (expected 9 values):", row)

    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
    except Exception as e:
        print("❗ Error during UART read:", e)
    finally:
        ser.close()
