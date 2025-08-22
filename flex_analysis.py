
import csv
import sys

# 분석할 파일 경로 리스트
file_paths = [
    r'C:\Users\Sunbi\desktop\uib\datasets\unified\ㄱ\1\episode_20250819_190541_ㄱ_1.csv',
    r'C:\Users\Sunbi\desktop\uib\datasets\unified\ㄱ\2\episode_20250819_190457_ㄱ_2.csv',
    r'C:\Users\Sunbi\desktop\uib\datasets\unified\ㄱ\3\episode_20250819_190411_ㄱ_3.csv',
    r'C:\Users\Sunbi\desktop\uib\datasets\unified\ㄱ\4\episode_20250819_190625_ㄱ_4.csv',
    r'C:\Users\Sunbi\desktop\uib\datasets\unified\ㄱ\5\episode_20250819_190709_ㄱ_5.csv'
]

results = []
# CSV에서 flex1~flex5에 해당하는 열 인덱스 (0부터 시작)
flex_column_indices = [5, 6, 7, 8, 9]

for i, file_path in enumerate(file_paths, 1):
    sums = [0.0] * len(flex_column_indices)
    counts = [0] * len(flex_column_indices)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader) # 헤더 건너뛰기
            
            for row in reader:
                for j, col_idx in enumerate(flex_column_indices):
                    try:
                        sums[j] += float(row[col_idx])
                        counts[j] += 1
                    except (ValueError, IndexError):
                        # 숫자가 아니거나, 열 개수가 맞지 않는 행은 건너뜁니다.
                        continue
        
        means = [s / c if c > 0 else 0 for s, c in zip(sums, counts)]
        results.append({
            "variation": i,
            "means": means
        })
    except FileNotFoundError:
        print(f"오류: 파일을 찾을 수 없습니다 - {file_path}", file=sys.stderr)
        continue
    except Exception as e:
        print(f"파일 처리 중 오류 발생 {file_path}: {e}", file=sys.stderr)
        continue

# 결과 출력
print("### 'ㄱ' 동작의 5가지 변형에 대한 Flex 센서 평균값 비교")
print("| Variation (1:폄 ~ 5:구부림) | flex1 | flex2 | flex3 | flex4 | flex5 |")
print("|---|---|---|---|---|---|")
for res in results:
    row = f"| {res['variation']} | "
    row += ' | '.join([f'{mean:.2f}' for mean in res['means']])
    row += " |"
    print(row)
