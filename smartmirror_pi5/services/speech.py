import logging
import io
import wave
import threading
import queue

logger = logging.getLogger(__name__)

# 전역 설정
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
RECORD_SECONDS = 5  # 기본 녹음 시간

# 음성 인식 엔진 타입
ENGINE_GOOGLE = "google"
ENGINE_VOSK = "vosk"

_vosk_model = None
_vosk_model_lock = threading.Lock()


def _get_vosk_model():
    """Vosk 모델 싱글톤 로드 (오프라인용)"""
    global _vosk_model
    if _vosk_model is None:
        with _vosk_model_lock:
            if _vosk_model is None:
                try:
                    from vosk import Model
                    import os
                    # 한국어 모델 경로 (사용자가 다운로드 필요)
                    model_path = os.getenv("VOSK_MODEL_PATH", "vosk-model-small-ko")
                    if os.path.exists(model_path):
                        _vosk_model = Model(model_path)
                        logger.info(f"[Vosk] Model loaded from {model_path}")
                    else:
                        logger.warning(f"[Vosk] Model not found at {model_path}")
                except ImportError:
                    logger.warning("[Vosk] vosk library not installed")
                except Exception as e:
                    logger.error(f"[Vosk] Failed to load model: {e}")
    return _vosk_model


def listen_and_recognize(engine: str = ENGINE_GOOGLE, timeout: float = 5.0, language: str = "ko-KR") -> dict:
    """
    마이크에서 음성을 녹음하고 텍스트로 변환합니다.
    
    Args:
        engine: 사용할 엔진 ("google" 또는 "vosk")
        timeout: 최대 대기 시간 (초)
        language: 언어 코드 (Google용)
    
    Returns:
        {
            "ok": True/False,
            "text": str (인식된 텍스트),
            "error": str (실패 시)
        }
    """
    try:
        import speech_recognition as sr
    except ImportError:
        return {"ok": False, "error": "SpeechRecognition library not installed. Run: pip install SpeechRecognition"}
    
    recognizer = sr.Recognizer()
    
    try:
        with sr.Microphone(sample_rate=SAMPLE_RATE) as source:
            logger.info("[Speech] Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            
            logger.info("[Speech] Listening...")
            try:
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=RECORD_SECONDS)
            except sr.WaitTimeoutError:
                return {"ok": False, "error": "No speech detected (timeout)"}
            
            logger.info("[Speech] Processing audio...")
            
            if engine == ENGINE_GOOGLE:
                return _recognize_google(recognizer, audio, language)
            elif engine == ENGINE_VOSK:
                return _recognize_vosk(audio)
            else:
                return {"ok": False, "error": f"Unknown engine: {engine}"}
                
    except OSError as e:
        logger.error(f"[Speech] Microphone error: {e}")
        return {"ok": False, "error": f"Microphone not available: {e}"}
    except Exception as e:
        logger.error(f"[Speech] Error: {e}")
        return {"ok": False, "error": str(e)}


def _recognize_google(recognizer, audio, language: str) -> dict:
    """Google Web Speech API로 인식"""
    try:
        import speech_recognition as sr
        text = recognizer.recognize_google(audio, language=language)
        logger.info(f"[Speech] Recognized (Google): {text}")
        return {"ok": True, "text": text, "engine": "google"}
    except sr.UnknownValueError:
        return {"ok": False, "error": "Could not understand audio"}
    except sr.RequestError as e:
        return {"ok": False, "error": f"Google API error: {e}"}


def _recognize_vosk(audio) -> dict:
    """Vosk 오프라인 엔진으로 인식"""
    model = _get_vosk_model()
    if model is None:
        return {"ok": False, "error": "Vosk model not available"}
    
    try:
        from vosk import KaldiRecognizer
        import json
        
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        
        # AudioData -> raw bytes
        raw_data = audio.get_raw_data(convert_rate=SAMPLE_RATE, convert_width=2)
        
        if rec.AcceptWaveform(raw_data):
            result = json.loads(rec.Result())
            text = result.get("text", "")
        else:
            result = json.loads(rec.PartialResult())
            text = result.get("partial", "")
        
        if text:
            logger.info(f"[Speech] Recognized (Vosk): {text}")
            return {"ok": True, "text": text, "engine": "vosk"}
        else:
            return {"ok": False, "error": "No speech recognized"}
            
    except Exception as e:
        logger.error(f"[Vosk] Recognition error: {e}")
        return {"ok": False, "error": str(e)}


def test_microphone() -> dict:
    """
    마이크 테스트 - 마이크가 사용 가능한지 확인
    
    Returns:
        {"ok": True/False, "devices": [...], "error": str}
    """
    try:
        import speech_recognition as sr
        
        mic_list = sr.Microphone.list_microphone_names()
        
        if not mic_list:
            return {"ok": False, "error": "No microphones found", "devices": []}
        
        return {
            "ok": True,
            "devices": mic_list,
            "default_index": 0
        }
        
    except ImportError:
        return {"ok": False, "error": "SpeechRecognition library not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
