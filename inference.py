import numpy as np
import tensorflow as tf
from sklearn.preprocessing import StandardScaler
import joblib
import json
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import deque
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SensorData:
    """센서 데이터를 담는 데이터 클래스"""
    yaw: float
    pitch: float
    roll: float
    flex1: float
    flex2: float
    flex3: float
    flex4: float
    flex5: float
    timestamp: float = None
    
    def to_array(self) -> np.ndarray:
        """센서 데이터를 numpy 배열로 변환"""
        return np.array([self.yaw, self.pitch, self.roll, 
                        self.flex1, self.flex2, self.flex3, 
                        self.flex4, self.flex5])
    
    def to_dict(self) -> Dict:
        """센서 데이터를 딕셔너리로 변환"""
        return {
            'yaw': self.yaw,
            'pitch': self.pitch, 
            'roll': self.roll,
            'flex1': self.flex1,
            'flex2': self.flex2,
            'flex3': self.flex3,
            'flex4': self.flex4,
            'flex5': self.flex5,
            'timestamp': self.timestamp or time.time()
        }

class SignGloveInference:
    """수화 장갑 추론 모델 클래스"""
    
    def __init__(self, model_path: str, scaler_path: str = None, 
                 config_path: str = None, window_size: int = 30):
        """
        Args:
            model_path: 훈련된 모델 파일 경로
            scaler_path: 데이터 정규화용 scaler 파일 경로
            config_path: 설정 파일 경로
            window_size: 시계열 데이터 윈도우 크기
        """
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.config_path = config_path
        self.window_size = window_size
        
        # 모델과 관련 컴포넌트 로드
        self.model = None
        self.scaler = None
        self.config = None
        self.class_names = []
        
        # 데이터 버퍼 (시계열 데이터용)
        self.data_buffer = deque(maxlen=window_size)
        
        # 추론 결과 필터링을 위한 변수들
        self.prediction_history = deque(maxlen=5)
        self.confidence_threshold = 0.7
        self.stability_threshold = 3  # 연속으로 같은 예측이 나와야 하는 횟수
        
        self._load_model_components()
    
    def _load_model_components(self):
        """모델, 스케일러, 설정 파일 로드"""
        try:
            # 모델 로드
            logger.info(f"모델 로드 중: {self.model_path}")
            self.model = tf.keras.models.load_model(self.model_path)
            logger.info("모델 로드 완료")
            
            # 스케일러 로드 (있는 경우)
            if self.scaler_path:
                logger.info(f"스케일러 로드 중: {self.scaler_path}")
                self.scaler = joblib.load(self.scaler_path)
                logger.info("스케일러 로드 완료")
            
            # 설정 파일 로드 (있는 경우)
            if self.config_path:
                logger.info(f"설정 파일 로드 중: {self.config_path}")
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                
                # 클래스 이름 설정
                if 'class_names' in self.config:
                    self.class_names = self.config['class_names']
                    logger.info(f"클래스 수: {len(self.class_names)}")
                
                # 임계값 설정 업데이트
                if 'confidence_threshold' in self.config:
                    self.confidence_threshold = self.config['confidence_threshold']
                if 'stability_threshold' in self.config:
                    self.stability_threshold = self.config['stability_threshold']
            
            logger.info("모든 컴포넌트 로드 완료")
            
        except Exception as e:
            logger.error(f"모델 컴포넌트 로드 실패: {e}")
            raise
    
    def preprocess_data(self, sensor_data: SensorData) -> np.ndarray:
        """센서 데이터 전처리"""
        # 센서 데이터를 배열로 변환
        data_array = sensor_data.to_array().reshape(1, -1)
        
        # 스케일러가 있으면 정규화 적용
        if self.scaler is not None:
            data_array = self.scaler.transform(data_array)
        
        return data_array
    
    def predict_single(self, sensor_data: SensorData) -> Dict:
        """단일 센서 데이터로 예측 수행"""
        try:
            # 데이터 전처리
            processed_data = self.preprocess_data(sensor_data)
            
            # 모델 예측
            predictions = self.model.predict(processed_data, verbose=0)
            
            # 결과 처리
            prediction_probs = predictions[0]
            predicted_class_idx = np.argmax(prediction_probs)
            confidence = float(prediction_probs[predicted_class_idx])
            
            # 클래스 이름 매핑
            predicted_class = (self.class_names[predicted_class_idx] 
                             if self.class_names else str(predicted_class_idx))
            
            result = {
                'predicted_class': predicted_class,
                'predicted_class_idx': int(predicted_class_idx),
                'confidence': confidence,
                'all_probabilities': prediction_probs.tolist(),
                'timestamp': time.time(),
                'sensor_data': sensor_data.to_dict()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"예측 실패: {e}")
            return {
                'error': str(e),
                'timestamp': time.time(),
                'sensor_data': sensor_data.to_dict()
            }
    
    def predict_sequence(self, sensor_data: SensorData) -> Optional[Dict]:
        """시계열 데이터로 예측 수행 (윈도우 기반)"""
        # 데이터 버퍼에 추가
        self.data_buffer.append(sensor_data.to_array())
        
        # 윈도우가 충분히 채워지지 않은 경우
        if len(self.data_buffer) < self.window_size:
            return None
        
        try:
            # 시계열 데이터 준비
            sequence_data = np.array(list(self.data_buffer))
            
            # 스케일러 적용 (있는 경우)
            if self.scaler is not None:
                sequence_data = self.scaler.transform(sequence_data)
            
            # 모델 입력 형태로 변환 [1, window_size, features]
            sequence_data = sequence_data.reshape(1, self.window_size, -1)
            
            # 모델 예측
            predictions = self.model.predict(sequence_data, verbose=0)
            
            # 결과 처리
            prediction_probs = predictions[0]
            predicted_class_idx = np.argmax(prediction_probs)
            confidence = float(prediction_probs[predicted_class_idx])
            
            # 클래스 이름 매핑
            predicted_class = (self.class_names[predicted_class_idx] 
                             if self.class_names else str(predicted_class_idx))
            
            result = {
                'predicted_class': predicted_class,
                'predicted_class_idx': int(predicted_class_idx),
                'confidence': confidence,
                'all_probabilities': prediction_probs.tolist(),
                'timestamp': time.time(),
                'sensor_data': sensor_data.to_dict(),
                'sequence_length': len(self.data_buffer)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"시계열 예측 실패: {e}")
            return {
                'error': str(e),
                'timestamp': time.time(),
                'sensor_data': sensor_data.to_dict()
            }
    
    def predict_with_filtering(self, sensor_data: SensorData) -> Optional[Dict]:
        """필터링이 적용된 예측 (노이즈 제거 및 안정성 향상)"""
        # 기본 예측 수행
        if len(self.data_buffer) >= self.window_size:
            prediction = self.predict_sequence(sensor_data)
        else:
            prediction = self.predict_single(sensor_data)
        
        if prediction is None or 'error' in prediction:
            return prediction
        
        # 신뢰도 임계값 체크
        if prediction['confidence'] < self.confidence_threshold:
            prediction['filtered_result'] = 'low_confidence'
            return prediction
        
        # 예측 히스토리에 추가
        self.prediction_history.append({
            'class': prediction['predicted_class'],
            'confidence': prediction['confidence']
        })
        
        # 안정성 체크 (최근 N개의 예측이 같은지 확인)
        if len(self.prediction_history) >= self.stability_threshold:
            recent_predictions = list(self.prediction_history)[-self.stability_threshold:]
            recent_classes = [p['class'] for p in recent_predictions]
            
            # 모두 같은 클래스인지 확인
            if len(set(recent_classes)) == 1:
                prediction['filtered_result'] = 'stable'
                prediction['stable_class'] = recent_classes[0]
                avg_confidence = np.mean([p['confidence'] for p in recent_predictions])
                prediction['stable_confidence'] = float(avg_confidence)
            else:
                prediction['filtered_result'] = 'unstable'
        else:
            prediction['filtered_result'] = 'insufficient_history'
        
        return prediction
    
    def reset_buffer(self):
        """데이터 버퍼와 히스토리 초기화"""
        self.data_buffer.clear()
        self.prediction_history.clear()
        logger.info("버퍼 초기화 완료")
    
    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        info = {
            'model_path': self.model_path,
            'window_size': self.window_size,
            'confidence_threshold': self.confidence_threshold,
            'stability_threshold': self.stability_threshold,
            'buffer_length': len(self.data_buffer),
            'history_length': len(self.prediction_history)
        }
        
        if self.model:
            info['model_input_shape'] = str(self.model.input_shape)
            info['model_output_shape'] = str(self.model.output_shape)
        
        if self.class_names:
            info['num_classes'] = len(self.class_names)
            info['class_names'] = self.class_names
        
        if self.config:
            info['config'] = self.config
        
        return info

# 사용 예시
def main():
    """메인 실행 함수 - 사용 예시"""
    
    # 추론 모델 초기화
    try:
        inference = SignGloveInference(
            model_path='path/to/your/trained_model.h5',
            scaler_path='path/to/your/scaler.pkl',  # 선택사항
            config_path='path/to/your/config.json', # 선택사항
            window_size=30
        )
        
        print("모델 정보:")
        print(json.dumps(inference.get_model_info(), indent=2, ensure_ascii=False))
        
    except Exception as e:
        logger.error(f"모델 초기화 실패: {e}")
        return
    
    # 시뮬레이션 데이터로 테스트
    logger.info("시뮬레이션 데이터로 추론 테스트 시작")
    
    for i in range(50):
        # 랜덤 센서 데이터 생성 (실제로는 센서에서 받아온 데이터)
        sensor_data = SensorData(
            yaw=np.random.uniform(-180, 180),
            pitch=np.random.uniform(-90, 90),
            roll=np.random.uniform(-180, 180),
            flex1=np.random.uniform(0, 1023),
            flex2=np.random.uniform(0, 1023),
            flex3=np.random.uniform(0, 1023),
            flex4=np.random.uniform(0, 1023),
            flex5=np.random.uniform(0, 1023),
            timestamp=time.time()
        )
        
        # 필터링이 적용된 예측 수행
        result = inference.predict_with_filtering(sensor_data)
        
        if result and 'error' not in result:
            logger.info(f"Step {i+1}: {result['predicted_class']} "
                       f"(confidence: {result['confidence']:.3f}, "
                       f"filter: {result['filtered_result']})")
        
        time.sleep(0.1)  # 100ms 간격

if __name__ == "__main__":
    main()