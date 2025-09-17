import os
import csv
import glob
from typing import List, Dict, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_csv_files(root: str) -> List[str]:
    files = glob.glob(os.path.join(root, "**", "*", "*.csv"), recursive=True)
    if not files:
        files = glob.glob(os.path.join(root, "**", "*.csv"), recursive=True)
    return sorted(files)


def detect_anomalies(rows: List[Dict[str, str]]):
    idx_hz_bad = []
    idx_ts_back = []
    idx_flex_extreme = {k: [] for k in ["flex1","flex2","flex3","flex4","flex5"]}

    prev_ts = None
    for i, r in enumerate(rows):
        try:
            hz = float(r.get("sampling_hz", "nan"))
            if hz < 10 or hz > 100:
                idx_hz_bad.append(i)
        except Exception:
            pass
        try:
            ts = float(r.get("timestamp_ms", "nan"))
            if prev_ts is not None and ts < prev_ts:
                idx_ts_back.append(i)
            prev_ts = ts
        except Exception:
            prev_ts = None
        for k in idx_flex_extreme.keys():
            try:
                v = float(r.get(k, "nan"))
                if v == 0 or v >= 1023:
                    idx_flex_extreme[k].append(i)
            except Exception:
                pass
    return idx_hz_bad, idx_ts_back, idx_flex_extreme


def load_csv(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def safe_name(path: str) -> str:
    # Use basename to avoid deep unicode paths in viz dir
    base = os.path.basename(path)
    # Replace characters that sometimes confuse filesystems
    return base.replace(os.sep, "_")


def plot_episode(path: str, out_dir: str):
    rows = load_csv(path)
    if not rows:
        return None
    idx_hz_bad, idx_ts_back, idx_flex_extreme = detect_anomalies(rows)

    x = list(range(len(rows)))
    def colf(c):
        vals = []
        for r in rows:
            try:
                vals.append(float(r[c]))
            except Exception:
                vals.append(float('nan'))
        return vals

    ax = colf('accel_x'); ay = colf('accel_y'); az = colf('accel_z')
    f1 = colf('flex1'); f2 = colf('flex2'); f3 = colf('flex3'); f4 = colf('flex4'); f5 = colf('flex5')
    hz = colf('sampling_hz')

    fig, axs = plt.subplots(3, 1, figsize=(12, 7), sharex=True)

    # Accelerometer
    axs[0].plot(x, ax, label='accel_x', lw=1)
    axs[0].plot(x, ay, label='accel_y', lw=1)
    axs[0].plot(x, az, label='accel_z', lw=1)
    if idx_ts_back:
        for i in idx_ts_back:
            axs[0].axvline(i, color='red', alpha=0.3, linestyle='--', lw=1)
    axs[0].set_ylabel('accel (g)')
    axs[0].legend(loc='upper right', fontsize=8)

    # Flex
    axs[1].plot(x, f1, label='flex1', lw=1)
    axs[1].plot(x, f2, label='flex2', lw=1)
    axs[1].plot(x, f3, label='flex3', lw=1)
    axs[1].plot(x, f4, label='flex4', lw=1)
    axs[1].plot(x, f5, label='flex5', lw=1)
    # highlight extremes
    for k, color in zip(['flex1','flex2','flex3','flex4','flex5'], ['C0','C1','C2','C3','C4']):
        idxs = idx_flex_extreme[k]
        if idxs:
            vals = [colf(k)[i] for i in idxs]
            axs[1].scatter(idxs, vals, c='red', s=12, marker='x', label=f'{k} extreme' if k=='flex1' else None)
    axs[1].set_ylabel('flex (adc)')
    axs[1].legend(loc='upper right', fontsize=8)

    # Sampling Hz
    axs[2].plot(x, hz, label='sampling_hz', lw=1)
    if idx_hz_bad:
        axs[2].scatter(idx_hz_bad, [hz[i] for i in idx_hz_bad], c='red', s=12, marker='o', label='hz anomaly')
    axs[2].axhline(10, color='grey', linestyle='--', lw=0.8, alpha=0.6)
    axs[2].axhline(100, color='grey', linestyle='--', lw=0.8, alpha=0.6)
    axs[2].set_ylabel('Hz')
    axs[2].set_xlabel('sample index')
    axs[2].legend(loc='upper right', fontsize=8)

    # Title with filename and anomaly summary
    anomalies = []
    if idx_hz_bad: anomalies.append(f'hz:{len(idx_hz_bad)}')
    if idx_ts_back: anomalies.append(f'ts_back:{len(idx_ts_back)}')
    total_flex_ext = sum(len(v) for v in idx_flex_extreme.values())
    if total_flex_ext: anomalies.append(f'flex_ext:{total_flex_ext}')
    subtitle = ' | '.join(anomalies) if anomalies else 'no anomalies'
    fig.suptitle(f'{os.path.basename(path)}  [{subtitle}]', fontsize=11)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])

    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, safe_name(path) + '.png')
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def main():
    root = os.path.join('datasets', 'unified')
    out_root = os.path.join('viz', 'datasets_unified')
    files = find_csv_files(root)
    if not files:
        print('No CSV files found under', root)
        return

    # Identify anomaly files first
    anomaly_files = []
    for f in files:
        try:
            rows = load_csv(f)
            idx_hz_bad, idx_ts_back, idx_flex_extreme = detect_anomalies(rows)
            if idx_hz_bad or idx_ts_back or any(idx_flex_extreme.values()):
                anomaly_files.append(f)
        except Exception:
            continue

    # Prefer visualizing anomalies first; fall back to all if none
    targets = anomaly_files if anomaly_files else files
    print(f'Visualizing {len(targets)} files (anomalies first). Output -> {out_root}')

    count = 0
    for f in targets:
        rel = os.path.relpath(os.path.dirname(f), root)
        out_dir = os.path.join(out_root, rel)
        try:
            out = plot_episode(f, out_dir)
            if out:
                count += 1
        except Exception as e:
            # Skip files that fail to parse/plot
            continue
    print('Saved figures:', count)


if __name__ == '__main__':
    main()

