"""
Wrapper server that extends the integration collector with:
- Blocking delete confirmation + recursive dataset deletion
- Session progress PNG saving (V)
- Current episode snapshot PNG saving (v)

Run: python server.py
"""

from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime
import time
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
except Exception:
    plt = None  # type: ignore

import numpy as np

from integration.signglove_unified_collector import (
    SignGloveUnifiedCollector as BaseCollector,
)


class Collector(BaseCollector):
    def reset_all_progress(self) -> None:
        print("\n" + "=" * 60)
        print("⚠️ 경고: 모든 수집 데이터(H5, CSV)와 진행 상황(JSON)이 삭제됩니다.")
        print("이 작업은 되돌릴 수 없습니다. 정말로 초기화하시겠습니까? (y/n)")
        print("=" * 60)
        try:
            resp = input("정말로 초기화하시겠습니까? (y/n): ").strip().lower()
            if resp != 'y':
                print("🚫 초기화 작업이 취소되었습니다.")
                return

            print("\n진행 상태 초기화 중..")
            deleted_files_count = 0
            delete_errors = 0
            for pattern in ('*.h5', '*.csv'):
                for file_path in self.data_dir.rglob(pattern):
                    try:
                        file_path.unlink()
                        deleted_files_count += 1
                    except Exception as e:
                        delete_errors += 1
                        print(f"삭제 실패: {file_path} -> {e}")

            removed_dirs = 0
            for p in sorted(self.data_dir.rglob('*'), key=lambda x: len(x.as_posix()), reverse=True):
                if p.is_dir():
                    try:
                        next(p.iterdir())
                    except StopIteration:
                        try:
                            p.rmdir()
                            removed_dirs += 1
                        except Exception:
                            pass

            if deleted_files_count > 0:
                print(f"삭제된 파일: {deleted_files_count}개 (에러 {delete_errors}개)")
            else:
                print("삭제할 H5/CSV 파일이 없습니다.")
            if removed_dirs > 0:
                print(f"정리된 빈 폴더: {removed_dirs}개")

            # Reset counters and progress file
            self.collection_stats = defaultdict(int)
            self.session_stats = defaultdict(int)
            # progress file path exists in integration collector
            try:
                # Overwrite with empty progress
                from json import dump
                data = {
                    "last_updated": datetime.now().isoformat(),
                    "collection_stats": dict(self.collection_stats),
                    "session_stats": dict(self.session_stats),
                    "total_episodes": 0,
                }
                self.progress_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            print("✅ collection_progress.json 파일이 초기화되었습니다.")
            print("✅ 모든 진행 상황이 성공적으로 초기화되었습니다.")
        except Exception as e:
            print(f"❌ 초기화 오류 발생: {e}")

    def save_progress_png(self, out_dir: Optional[Path] = None, session_view: bool = True) -> Optional[Path]:
        if plt is None:
            return None
        try:
            # Build class list and targets
            per_class_current = {}
            per_class_target = {}
            for class_name in self.all_classes:
                cur = int(self.session_stats.get(class_name, 0)) if session_view else int(self.collection_stats.get(class_name, 0))
                target_info = self.collection_targets.get(class_name, {}) if isinstance(self.collection_targets, dict) else {}
                target = int(target_info.get('target', 25))
                per_class_current[class_name] = cur
                per_class_target[class_name] = target

            total_current = sum(per_class_current.values())
            total_target = sum(per_class_target.values()) if per_class_target else 0
            overall_pct = (total_current / total_target * 100.0) if total_target > 0 else 0.0

            # Output path
            if out_dir is None:
                out_dir = Path('viz') / 'progress'
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            scope = 'session' if session_view else 'overall'
            out_path = out_dir / f'collection_progress_{scope}_{ts}.png'

            # Group categories
            categories = [
                ('Consonants', self.ksl_classes.get('consonants', [])),
                ('Vowels', self.ksl_classes.get('vowels', [])),
                ('Numbers', self.ksl_classes.get('numbers', [])),
            ]

            rows = len(categories)
            total_items = sum(len(items) for _, items in categories)
            height = max(6, int(np.ceil(total_items * 0.35)) + 2)
            fig, axs = plt.subplots(rows, 1, figsize=(14, height), constrained_layout=True)
            if rows == 1:
                axs = [axs]

            for ax, (title, items) in zip(axs, categories):
                if not items:
                    ax.axis('off')
                    continue
                cur_vals = [per_class_current.get(name, 0) for name in items]
                tgt_vals = [per_class_target.get(name, 0) for name in items]
                y_pos = np.arange(len(items))
                order = np.argsort([c / t if t else 0 for c, t in zip(cur_vals, tgt_vals)])[::-1]
                items = [items[i] for i in order]
                cur_vals = [cur_vals[i] for i in order]
                tgt_vals = [tgt_vals[i] for i in order]
                y_pos = np.arange(len(items))

                ax.barh(y_pos, tgt_vals, color='#e8e8e8', edgecolor='#cccccc', label='target')
                colors = ['#2e86de' if c < t else '#27ae60' for c, t in zip(cur_vals, tgt_vals)]
                ax.barh(y_pos, cur_vals, color=colors, edgecolor='#1f2d3d', label='current')
                ax.set_yticks(y_pos)
                ax.set_yticklabels(items, fontsize=9)
                ax.invert_yaxis()
                ax.set_xlabel('episodes collected')
                ax.set_title(f'{title}', loc='left', fontsize=12, fontweight='bold')
                for y, c, t in zip(y_pos, cur_vals, tgt_vals):
                    pct = (c / t * 100.0) if t > 0 else 0.0
                    ax.text(max(c, t) + 0.2, y, f'{c}/{t} ({pct:.0f}%)', va='center', fontsize=8)
                ax.set_xlim(0, max(1, max(tgt_vals) + 1))
                ax.grid(axis='x', linestyle='--', alpha=0.3)

            title_scope = 'Session' if session_view else 'Overall'
            fig.suptitle(
                f'SignGlove Collection Progress  |  {title_scope}: {total_current}/{total_target} ({overall_pct:.1f}%)',
                fontsize=14,
                fontweight='bold'
            )
            fig.savefig(out_path, dpi=150)
            plt.close(fig)
            return out_path
        except Exception as e:
            try:
                plt.close('all')  # type: ignore
            except Exception:
                pass
            print(f"진행 상황 PNG 생성 오류: {e}")
            return None

    def save_current_episode_png(self, out_dir: Optional[Path] = None, window_seconds: Optional[int] = 10) -> Optional[Path]:
        if plt is None:
            return None
        if not getattr(self, 'episode_data', None):
            return None
        try:
            times_ms = [r.recv_timestamp_ms for r in self.episode_data]
            t_last = max(times_ms)
            t_min = t_last - int(window_seconds * 1000) if window_seconds is not None else min(times_ms)
            sel = [i for i, t in enumerate(times_ms) if t >= t_min]
            if not sel:
                sel = list(range(len(self.episode_data)))

            ts = np.array([self.episode_data[i].recv_timestamp_ms for i in sel], dtype=np.int64)
            t0 = ts[0]
            tt = (ts - t0) / 1000.0
            pitch = np.array([self.episode_data[i].pitch for i in sel], dtype=np.float32)
            roll  = np.array([self.episode_data[i].roll  for i in sel], dtype=np.float32)
            yaw   = np.array([self.episode_data[i].yaw   for i in sel], dtype=np.float32)
            flex = np.array([[self.episode_data[i].flex1, self.episode_data[i].flex2, self.episode_data[i].flex3, self.episode_data[i].flex4, self.episode_data[i].flex5] for i in sel], dtype=np.float32)

            if out_dir is None:
                out_dir = Path('viz') / 'snapshots'
            out_dir.mkdir(parents=True, exist_ok=True)
            ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            cls = self.current_class or 'unknown'
            ety = self.current_episode_type or 'na'
            out_path = out_dir / f'episode_snapshot_{cls}_{ety}_{ts_str}.png'

            fig, axs = plt.subplots(2, 1, figsize=(14, 8), constrained_layout=True)
            axs[0].plot(tt, pitch, label='pitch'); axs[0].plot(tt, roll, label='roll'); axs[0].plot(tt, yaw, label='yaw')
            axs[0].set_title('Orientation (deg)'); axs[0].set_xlabel('time (s)'); axs[0].set_ylabel('deg'); axs[0].grid(True, linestyle='--', alpha=0.3); axs[0].legend(loc='upper right')
            for i in range(5): axs[1].plot(tt, flex[:, i], label=f'flex{i+1}')
            axs[1].set_title('Flex (ADC)'); axs[1].set_xlabel('time (s)'); axs[1].set_ylabel('value'); axs[1].grid(True, linestyle='--', alpha=0.3); axs[1].legend(loc='upper right', ncol=3)
            fig.suptitle(f'Episode Snapshot | class: {cls}, type: {ety} | samples: {len(tt)}', fontsize=14, fontweight='bold')
            fig.savefig(out_path, dpi=150); plt.close(fig); return out_path
        except Exception as e:
            try:
                plt.close('all')  # type: ignore
            except Exception:
                pass
            print(f"스냅샷 PNG 저장 오류: {e}")
            return None

    def handle_key_input(self, key: str):  # type: ignore[override]
        # Extend with v/V/d
        if key == 'v':
            out_path = self.save_current_episode_png()
            if out_path is not None:
                print(f"\n✅ 현재 수집 데이터 스냅샷 PNG 저장: {out_path}")
            else:
                print("⚠️ 스냅샷 PNG 저장 실패: 수집 중 데이터가 없거나 matplotlib 미설치")
            return
        elif key == 'V':
            out_path = self.save_progress_png(session_view=True)
            if out_path is not None:
                print(f"\n✅ 세션 진행도 PNG 저장: {out_path}")
            else:
                print("⚠️ 진행도 PNG 저장 실패: matplotlib 미설치 또는 예외 발생")
            return
        elif key == 'd':
            self.reset_all_progress()
            return
        else:
            return super().handle_key_input(key)


def main():
    try:
        collector = Collector()
        collector.run()
    except Exception as e:
        print(f"프로그램 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

