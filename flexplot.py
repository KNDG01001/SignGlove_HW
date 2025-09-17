from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib.pyplot as plt
import numpy as np


FLEX_COLS = [f"flex{i}" for i in range(1, 6)]


def iter_csv_rows(root: Path) -> Iterable[Dict[str, str]]:
    """Yield rows from every CSV under root (depth-first, sorted)."""
    encodings = ("utf-8-sig", "cp949", "utf-8")
    for csv_path in sorted(root.rglob("*.csv")):
        last_error: UnicodeDecodeError | None = None
        for idx, encoding in enumerate(encodings):
            try:
                with csv_path.open("r", encoding=encoding, newline="") as fp:
                    if idx > 0:
                        print(f"Decoding {csv_path} with fallback encoding '{encoding}'")
                    reader = csv.DictReader(fp)
                    for row in reader:
                        yield row
                break
            except UnicodeDecodeError as exc:
                last_error = exc
        else:
            msg = f"Could not decode {csv_path} with supported encodings {encodings}."
            raise RuntimeError(msg) from last_error


def load_series(root: Path) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Load timestamps and flex columns into numpy arrays."""
    timestamps: List[float] = []
    flex_data: Dict[str, List[float]] = {col: [] for col in FLEX_COLS}

    for row in iter_csv_rows(root):
        ts_raw = row.get("timestamp_ms")
        if ts_raw:
            try:
                timestamps.append(float(ts_raw))
            except ValueError:
                timestamps.append(float(len(timestamps)))
        else:
            timestamps.append(float(len(timestamps)))

        for col in FLEX_COLS:
            val = row.get(col, "")
            if val.strip():
                try:
                    flex_data[col].append(float(val))
                except ValueError:
                    flex_data[col].append(np.nan)
            else:
                flex_data[col].append(np.nan)

    if not timestamps:
        raise RuntimeError(f"No CSV data found under {root}")

    timestamps_arr = np.asarray(timestamps, dtype=float)
    series = {col: np.asarray(vals, dtype=float) for col, vals in flex_data.items()}
    return timestamps_arr, series


def downsample(
    timestamps: np.ndarray,
    series: Dict[str, np.ndarray],
    target: int | None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Optional downsampling by simple index selection."""
    if target is None or len(timestamps) <= target:
        return timestamps, series

    idx = np.linspace(0, len(timestamps) - 1, target, dtype=int)
    ts_ds = timestamps[idx]
    series_ds = {col: values[idx] for col, values in series.items()}
    return ts_ds, series_ds


def iter_group_dirs(root: Path) -> Iterable[Tuple[str, str | None, Path]]:
    """Yield (letter, index, path) triples for grouped plotting."""
    for primary in sorted(p for p in root.iterdir() if p.is_dir()):
        secondaries = [p for p in sorted(primary.iterdir()) if p.is_dir()]
        if not secondaries:
            if any(primary.rglob("*.csv")):
                yield primary.name, None, primary
            continue
        for secondary in secondaries:
            if any(secondary.rglob("*.csv")):
                yield primary.name, secondary.name, secondary


def plot_flex(
    timestamps: np.ndarray,
    series: Dict[str, np.ndarray],
    full_series: Dict[str, np.ndarray],
    outfile: Path | None,
) -> None:
    """Create time-series and boxplot figure."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)

    for col in FLEX_COLS:
        axes[0].plot(timestamps, series[col], linewidth=0.8, label=col)
    axes[0].set_title("Flex Sensor Time Series")
    axes[0].set_xlabel("timestamp_ms (raw order if missing)")
    axes[0].set_ylabel("value")
    axes[0].legend(loc="upper right")

    clean = [full_series[col][~np.isnan(full_series[col])] for col in FLEX_COLS]
    axes[1].boxplot(clean, tick_labels=FLEX_COLS, vert=False)
    axes[1].set_title("Flex Sensor Distribution")
    axes[1].set_xlabel("value")

    if outfile:
        outfile.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(outfile, dpi=140)
        print(f"Saved plot to {outfile}")
    else:
        plt.show()

    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize flex sensor CSV data.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Root folder containing flex CSV files (default: current dir).",
    )
    parser.add_argument(
        "--downsample",
        type=int,
        default=2000,
        help="Target number of samples for plotting (use 0 to disable).",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="File path to save a single PNG instead of showing an interactive window.",
    )
    parser.add_argument(
        "--grouped",
        action="store_true",
        help="Create one plot per <letter>/<index> folder instead of aggregating everything.",
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=None,
        help="Directory for grouped PNG outputs (defaults to <root>/flexplots when --grouped).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Root path {root} does not exist.")

    ds_target = None if args.downsample <= 0 else args.downsample

    if args.grouped:
        if args.save is not None:
            print("Ignoring --save because --grouped is enabled; use --save-dir instead.")
        save_dir = (args.save_dir.expanduser().resolve() if args.save_dir
                    else (root / "flexplots"))
        groups = list(iter_group_dirs(root))
        if not groups:
            raise RuntimeError(f"No grouped CSV folders found under {root}.")
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
    else:
        timestamps, series = load_series(root)
        ts_ds, series_ds = downsample(timestamps, series, ds_target)
        plot_flex(ts_ds, series_ds, series, args.save)


if __name__ == "__main__":
    main()