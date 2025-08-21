import csv
import sys
import glob
from collections import defaultdict
import os

def analyze_all_files():
    """Analyzes all CSV files in the unified directory to find the average flex sensor values for each gesture and variation."""
    base_path = r'C:\Users\Sunbi\desktop\uib\datasets\unified'
    all_files = glob.glob(os.path.join(base_path, '**', '*.csv'), recursive=True)

    data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0])))
    flex_columns = ['flex1', 'flex2', 'flex3', 'flex4', 'flex5']
    flex_column_indices = [5, 6, 7, 8, 9]

    for file_path in all_files:
        try:
            parts = os.path.normpath(file_path).split(os.sep)
            gesture = parts[-3]
            variation = int(parts[-2])

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)

                for row in reader:
                    for i, col_idx in enumerate(flex_column_indices):
                        try:
                            value = float(row[col_idx])
                            flex_name = flex_columns[i]
                            data[gesture][variation][flex_name][0] += value
                            data[gesture][variation][flex_name][1] += 1
                        except (ValueError, IndexError):
                            continue
        except (IndexError, ValueError):
            continue

    # 한글 가나다 순서대로 정렬하기 위한 리스트
    korean_order = [
        'ㄱ', 'ㄴ', 'ㄷ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅅ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
        'ㅏ', 'ㅑ', 'ㅓ', 'ㅕ', 'ㅗ', 'ㅛ', 'ㅜ', 'ㅠ', 'ㅡ', 'ㅣ'
    ]
    # 발견된 제스처만 정렬
    sorted_gestures = sorted(data.keys(), key=lambda x: korean_order.index(x) if x in korean_order else len(korean_order))

    for gesture in sorted_gestures:
        print(f"\n### Gesture: '{gesture}'")
        print("| Variation (1:폄 ~ 5:구부림) | flex1 | flex2 | flex3 | flex4 | flex5 |")
        print("|---|---|---|---|---|---|")
        for variation in sorted(data[gesture].keys()):
            row = f"| {variation} |"
            for flex_name in flex_columns:
                total_sum, count = data[gesture][variation][flex_name]
                mean = total_sum / count if count > 0 else 0
                row += f" {mean:.2f} |"
            print(row)

if __name__ == '__main__':
    analyze_all_files()
