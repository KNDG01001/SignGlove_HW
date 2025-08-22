import h5py
import os

# H5 파일이 있는 디렉토리 경로 (server.py의 data_dir과 동일)
data_dir = "datasets/unified"

# 예시 H5 파일 이름 (실제 파일 이름으로 변경해야 합니다)
# 이전에 수집된 파일 중 하나를 선택하세요.
h5_file_name = "episode_20250813_164439_ㄱ.h5" # 예시 파일명, 실제 파일명으로 변경하세요.

h5_file_path = os.path.join(data_dir, h5_file_name)

if os.path.exists(h5_file_path):
    try:
        with h5py.File(h5_file_path, 'r') as f:
            print(f"--- H5 파일: {h5_file_name} 내용 ---")
            print("데이터셋 및 그룹 목록:")
            for key in f.keys():
                item = f[key]
                if isinstance(item, h5py.Dataset):
                    print(f"  - {key} (Dataset, Shape: {item.shape}, Dtype: {item.dtype})")
                elif isinstance(item, h5py.Group):
                    print(f"  - {key} (Group)")
                    # Optionally, you can iterate through the group's contents
                    for sub_key in item.keys():
                        sub_item = item[sub_key]
                        if isinstance(sub_item, h5py.Dataset):
                            print(f"    - {sub_key} (Dataset, Shape: {sub_item.shape}, Dtype: {sub_item.dtype})")
                        elif isinstance(sub_item, h5py.Group):
                            print(f"    - {sub_key} (Group)")

            print("\n속성 (Attributes) 목록:")
            for attr_name, attr_value in f.attrs.items():
                print(f"  - {attr_name}: {attr_value}")

            # 특정 데이터셋의 내용 확인 예시
            if 'sensor_data' in f:
                print("\n--- 'sensor_data' 데이터셋의 첫 5개 샘플 ---")
                print(f['sensor_data'][:5])
            
            if 'sensors/flex' in f:
                print("\n--- 'sensors/flex' 데이터셋의 첫 5개 샘플 ---")
                print(f['sensors/flex'][:5])

    except Exception as e:
        print(f"H5 파일을 여는 중 오류 발생: {e}")
else:
    print(f"파일을 찾을 수 없습니다: {h5_file_path}")
