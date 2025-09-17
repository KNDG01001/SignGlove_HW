import os
import csv
import glob
from typing import List, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = os.path.join('datasets', 'unified')
OUT_DIR = os.path.join('viz', 'datasets_unified')


def find_csv_files(root: str) -> List[str]:
    files = glob.glob(os.path.join(root, "**", "*", "*.csv"), recursive=True)
    if not files:
        files = glob.glob(os.path.join(root, "**", "*.csv"), recursive=True)
    return sorted(files)


def load_csv(path: str) -> List[Dict[str, str]]:
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def detect_flex_anomalies(rows: List[Dict[str, str]], spike_thresh: float = 80.0):
    idx_extreme = {k: [] for k in ["flex1","flex2","flex3","flex4","flex5"]}
    idx_spike = {k: [] for k in ["flex1","flex2","flex3","flex4","flex5"]}

    prev = None
    for i, r in enumerate(rows):
        cur = {}
        for k in idx_extreme.keys():
            try:
                v = float(r.get(k, 'nan'))
                cur[k] = v
                if v == 0 or v >= 1023:
                    idx_extreme[k].append(i)
            except Exception:
                cur[k] = None
        if prev is not None:
            for k in idx_spike.keys():
                if prev.get(k) is not None and cur.get(k) is not None:
                    if abs(cur[k] - prev[k]) >= spike_thresh:
                        idx_spike[k].append(i)
        prev = cur
    return idx_extreme, idx_spike


def safe_name(path: str) -> str:
    return os.path.basename(path)


def plot_flex_only(path: str, out_dir: str, spike_thresh: float = 80.0):
    rows = load_csv(path)
    if not rows:
        return None

    x = list(range(len(rows)))
    def colf(c):
        vals = []
        for r in rows:
            try:
                vals.append(float(r[c]))
            except Exception:
                vals.append(float('nan'))
        return vals

    f1 = colf('flex1'); f2 = colf('flex2'); f3 = colf('flex3'); f4 = colf('flex4'); f5 = colf('flex5')
    idx_extreme, idx_spike = detect_flex_anomalies(rows, spike_thresh=spike_thresh)

    fig, ax = plt.subplots(1, 1, figsize=(12, 4))
    ax.plot(x, f1, label='flex1', lw=1)
    ax.plot(x, f2, label='flex2', lw=1)
    ax.plot(x, f3, label='flex3', lw=1)
    ax.plot(x, f4, label='flex4', lw=1)
    ax.plot(x, f5, label='flex5', lw=1)

    # Highlight extremes (0 or >=1023)
    for k, color in zip(['flex1','flex2','flex3','flex4','flex5'], ['C0','C1','C2','C3','C4']):
        idxs = idx_extreme[k]
        if idxs:
            vals = [colf(k)[i] for i in idxs]
            ax.scatter(idxs, vals, c='red', s=18, marker='x', label='extreme' if k=='flex1' else None)

    # Highlight spikes (|Δ| >= spike_thresh)
    for k in ['flex1','flex2','flex3','flex4','flex5']:
        idxs = idx_spike[k]
        if idxs:
            vals = [colf(k)[i] for i in idxs]
            ax.scatter(idxs, vals, c='orange', s=12, marker='o', alpha=0.7, label='spike' if k=='flex1' else None)

    ax.set_ylabel('flex (adc)')
    ax.set_xlabel('sample index')
    ax.legend(loc='upper right', fontsize=8)

    # Title
    n_ext = sum(len(v) for v in idx_extreme.values())
    n_spk = sum(len(v) for v in idx_spike.values())
    subtitle = f'flex_ext:{n_ext} | spikes(>={int(spike_thresh)}):{n_spk}' if (n_ext or n_spk) else 'no flex anomalies'
    fig.suptitle(f'{os.path.basename(path)}  [{subtitle}]', fontsize=11)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, safe_name(path) + '.png')
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def main():
    files = find_csv_files(ROOT)
    if not files:
        print('No CSV files found under', ROOT)
        return

    # Pick only files with flex anomalies
    targets = []
    for f in files:
        try:
            rows = load_csv(f)
            idx_extreme, idx_spike = detect_flex_anomalies(rows)
            if any(idx_extreme.values()) or any(idx_spike.values()):
                targets.append(f)
        except Exception:
            continue

    print(f'Visualizing flex anomalies for {len(targets)} files. Output -> {OUT_DIR}')
    saved = 0
    for f in targets:
        rel = os.path.relpath(os.path.dirname(f), ROOT)
        out_dir = os.path.join(OUT_DIR, rel)
        try:
            if plot_flex_only(f, out_dir):
                saved += 1
        except Exception:
            continue
    print('Saved figures:', saved)


if __name__ == '__main__':
    main()

