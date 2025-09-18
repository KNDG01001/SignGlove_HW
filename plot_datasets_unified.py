from __future__ import annotations

import argparse
import numpy as np
from pathlib import Path
from flexplot import downsample, iter_group_dirs, load_series, plot_flex


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate flex sensor plots for each datasets/unified subgroup.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("datasets/unified"),
        help="Top-level directory that contains grouped CSV folders (default: datasets/unified).",
    )
    parser.add_argument(
        "--downsample",
        type=int,
        default=1000,
        help="Target number of samples per plot (use 0 to disable downsampling).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for generated PNGs (default: <root>/flexplots).",
    )
    return parser.parse_args()


def process_timestamps(timestamps: np.ndarray) -> np.ndarray:
    """타임스탬프를 정규화하고 유효성을 검사합니다."""
    if len(timestamps) == 0:
        return np.array([])
    
    # 첫 번째 타임스탬프를 0으로 하여 상대적 시간으로 변환
    t_start = timestamps[0]
    normalized = (timestamps - t_start) / 1000.0  # 밀리초를 초로 변환
    
    # 비정상적인 타임스탬프 검출 (예: 큰 점프나 음수 값)
    if np.any(np.diff(normalized) < 0) or np.any(normalized > 60):  # 60초 이상은 비정상으로 간주
        # 인덱스 기반 시간으로 대체
        print("⚠️ 비정상 타임스탬프 감지됨 - 인덱스 기반 시간으로 대체")
        return np.arange(len(timestamps)) * (1.0/33.3)  # 33.3Hz 기준
    
    return normalized

def main() -> None:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Root path {root} does not exist.")

    save_dir = args.output.expanduser().resolve() if args.output else (root / "flexplots")
    save_dir.mkdir(parents=True, exist_ok=True)

    ds_target = None if args.downsample <= 0 else args.downsample

    groups = list(iter_group_dirs(root))
    if not groups:
        raise RuntimeError(f"No CSV files found under {root}.")

    for letter, index, folder in groups:
        label = letter if index is None else f"{letter}/{index}"
        print(f"Plotting {label} from {folder}")
        try:
            timestamps, series = load_series(folder)
            
            # 타임스탬프 정규화 및 처리
            normalized_timestamps = process_timestamps(timestamps)
            
            # 다운샘플링
            ts_ds, series_ds = downsample(normalized_timestamps, series, ds_target)
            
            # 저장 경로 설정 및 플롯 생성
            target_dir = save_dir / letter
            if index is not None:
                target_dir /= index
            outfile = target_dir / "flex.png"
            
            # 플롯 생성
            plot_flex(ts_ds, series_ds, series, outfile)
            
        except Exception as e:
            print(f"⚠️ {label} 처리 중 오류 발생: {e}")
            continue  # 오류가 발생해도 다음 파일 처리 계속


if __name__ == "__main__":
    main()
