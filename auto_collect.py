"""자동 수집 실행 스크립트"""
import time
from ser import SignGloveUnifiedCollector

def main():
    collector = SignGloveUnifiedCollector()

    # 아두이노 연결
    print("\n🔌 아두이노 자동 연결 시도...")
    if not collector.connect_arduino():
        print("❌ 아두이노 연결 실패")
        return

    # 수집할 클래스 목록 표시
    print("\n📋 수집 가능한 클래스:")
    for i, class_name in enumerate(collector.all_classes, 1):
        print(f"{i:2d}. {class_name}")

    try:
        # 수집할 클래스 선택
        while True:
            choice = input("\n✨ 수집할 클래스 번호 입력 (1-34, 0=전체): ")
            if not choice.isdigit():
                print("❌ 숫자를 입력해주세요.")
                continue
            
            choice = int(choice)
            if choice < 0 or choice > 34:
                print("❌ 1-34 사이의 숫자를 입력해주세요.")
                continue
            break

        if choice == 0:
            # 전체 클래스 자동 수집
            classes_to_collect = collector.all_classes
            print("\n🤖 전체 클래스 자동 수집 시작...")
        else:
            # 선택한 클래스만 수집
            classes_to_collect = [collector.all_classes[choice-1]]
            print(f"\n🤖 '{classes_to_collect[0]}' 클래스 자동 수집 시작...")

        # 각 클래스에 대해 자동 수집 실행
        for class_name in classes_to_collect:
            print(f"\n🎯 '{class_name}' 클래스 수집 시작...")
            
            # 현재까지의 진행상황 표시
            current = sum(collector.collection_stats[class_name].values())
            target = len(collector.episode_types) * collector.episodes_per_type
            remaining = max(0, target - current)
            
            if remaining == 0:
                print(f"✅ '{class_name}' 클래스는 이미 수집이 완료되었습니다.")
                continue

            print(f"⏳ 남은 수집 횟수: {remaining}회")
            
            # 자동 수집 시작
            collector.start_auto_collection(class_name)
            
            # 수집이 완료될 때까지 대기
            while collector.auto_collecting:
                time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 자동 수집이 중단되었습니다.")
    finally:
        if collector.collecting:
            collector.stop_episode()
        if collector.serial_port and collector.serial_port.is_open:
            collector.serial_port.close()
        print("\n👋 프로그램을 종료합니다.")

if __name__ == '__main__':
    main()