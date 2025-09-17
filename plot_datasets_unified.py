from __future__ import annotations

import argparse
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
        timestamps, series = load_series(folder)
        ts_ds, series_ds = downsample(timestamps, series, ds_target)
        target_dir = save_dir / letter
        if index is not None:
            target_dir /= index
        outfile = target_dir / "flex.png"
        plot_flex(ts_ds, series_ds, series, outfile)


if __name__ == "__main__":
    main()
