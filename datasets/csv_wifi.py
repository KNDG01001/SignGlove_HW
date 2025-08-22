import socket
import csv
from datetime import datetime

HOST = '0.0.0.0'
PORT = 5000

csv_filename = f"imu_wifi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# 로그 출력 함수
def debug_print(msg):
    print(f"[DEBUG] {msg}")

with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['timestamp(ms)', 'ax(g)', 'ay(g)', 'az(g)', 'pitch(°)', 'roll(°)', 'yaw(°)'])

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        print(f"[+] Server listening on port {PORT}...")

        while True:
            conn, addr = server_socket.accept()
            with conn:
                debug_print(f"Connection from {addr}")
                try:
                    buffer = b''
                    while True:
                        chunk = conn.recv(1024)
                        if not chunk:
                            break
                        buffer += chunk
                    data = buffer.decode().strip()

                    debug_print(f"Raw data: {repr(data)}")

                    row = data.split(',')
                    if len(row) == 7:
                        writer.writerow(row)
                        file.flush()
                        print("✔️ Data saved:", row)
                    else:
                        print("❌ Invalid data format (not 7 columns):", row)
                except Exception as e:
                    print("❗ Error handling data:", e)
