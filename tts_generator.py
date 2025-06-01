"""
TTS(Text-to-Speech) 생성 모듈 - Streamlit 버전
기존 tts_generator_SCU.py를 기반으로 Streamlit 환경에 맞게 최적화됨
"""

import os
import sys
import time
import logging
import tempfile
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import streamlit as st

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='tts_generator.log',
    filemode='a'
)
logger = logging.getLogger('tts_generator')

class TTSGenerator:
    """TTS 생성 클래스 - Streamlit 버전"""
    
    def __init__(self, tts_engine="google", api_key=None, output_dir=None, progress_callback=None, use_stt_for_subtitles=False):
        """
        TTSGenerator 초기화
        
        Args:
            tts_engine: TTS 엔진 ("google", "openai", "local" 중 하나)
            api_key: API 키 (필요한 경우)
            output_dir: 출력 디렉토리
            progress_callback: 진행 상황 콜백 함수 (Streamlit 용)
            use_stt_for_subtitles: STT를 사용하여 정확한 자막 타임스탬프 생성 여부
        """
        self.tts_engine = tts_engine.lower()
        self.api_key = api_key
        self.progress_callback = progress_callback
        self.use_stt_for_subtitles = use_stt_for_subtitles
        self.error_messages = []  # 에러 메시지를 저장할 리스트
        self.temp_credentials_file = None  # 임시 인증 파일 경로
        
        # 출력 디렉토리 설정
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_files")
        
        # 출력 디렉토리 생성
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Google Cloud TTS를 위한 설정
        if self.tts_engine == "google":
            try:
                from google.cloud import texttospeech_v1 as texttospeech
                
                # 인증 설정 (Streamlit Cloud 환경 고려)
                credentials_set = self._setup_google_credentials()
                
                if credentials_set:
                    self.client = texttospeech.TextToSpeechClient()
                    logger.info("Google Cloud TTS 클라이언트 초기화 완료")
                else:
                    logger.error("Google Cloud 인증 설정 실패")
                    self.error_messages.append("Google Cloud 인증 설정에 실패했습니다. 환경 변수 또는 Streamlit Secrets 설정을 확인하세요.")
            except ImportError:
                logger.error("Google Cloud TTS 라이브러리가 설치되지 않았습니다.")
                self.error_messages.append("Google Cloud TTS 라이브러리가 설치되지 않았습니다. pip install google-cloud-texttospeech 명령으로 설치하세요.")
        
        # OpenAI TTS를 위한 설정
        elif self.tts_engine == "openai":
            try:
                import openai
                if api_key:
                    openai.api_key = api_key
                logger.info("OpenAI TTS 설정 완료")
            except ImportError:
                logger.error("OpenAI 라이브러리가 설치되지 않았습니다.")
                self.error_messages.append("OpenAI 라이브러리가 설치되지 않았습니다. pip install openai 명령으로 설치하세요.")
        
        # 로컬 TTS를 위한 설정
        elif self.tts_engine == "local":
            try:
                # 기본 라이브러리 사용 (pyttsx3)
                import pyttsx3
                self.engine = pyttsx3.init()
                logger.info("로컬 TTS 엔진 초기화 완료")
            except ImportError:
                logger.error("pyttsx3 라이브러리가 설치되지 않았습니다.")
                self.error_messages.append("pyttsx3 라이브러리가 설치되지 않았습니다. pip install pyttsx3 명령으로 설치하세요.")
        
        else:
            logger.error(f"지원되지 않는 TTS 엔진: {tts_engine}")
            self.error_messages.append(f"지원되지 않는 TTS 엔진: {tts_engine}. 'google', 'openai', 'local' 중 하나를 선택하세요.")

        # Google Cloud Speech API 초기화 (STT 자막 동기화용)
        if self.use_stt_for_subtitles:
            try:
                from google.cloud import speech_v1p1beta1 as speech
                # 인증 설정은 위에서 이미 처리됨
                self.speech_client = speech.SpeechClient()
                logger.info("Google Cloud Speech 클라이언트 초기화 완료")
            except ImportError:
                logger.error("Google Cloud Speech 라이브러리가 설치되지 않았습니다.")
                self.error_messages.append("Google Cloud Speech 라이브러리가 설치되지 않았습니다. pip install google-cloud-speech 명령으로 설치하세요.")
                self.use_stt_for_subtitles = False
    
    def _setup_google_credentials(self):
        """
        Google Cloud 인증 설정
        
        환경 변수 또는 Streamlit Secrets에서 서비스 계정 키를 가져와 설정
        
        Returns:
            bool: 인증 설정 성공 여부
        """
        # 1. 환경 변수 GOOGLE_APPLICATION_CREDENTIALS 확인
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if os.path.exists(cred_path):
                logger.info(f"기존 환경 변수를 통한 인증 사용: {cred_path}")
                return True
            else:
                logger.warning(f"환경 변수에 지정된 인증 파일이 존재하지 않음: {cred_path}")
        
        # 2. Streamlit Secrets에서 서비스 계정 키 가져오기 시도
        try:
            if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
                # Secrets에서 서비스 계정 정보 가져오기
                logger.info("Streamlit Secrets에서 서비스 계정 정보 로드 중...")
                
                # 임시 파일 생성
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                    # 서비스 계정 정보를 임시 파일에 쓰기
                    json.dump(st.secrets['gcp_service_account'], temp_file)
                    temp_file_path = temp_file.name
                
                # 임시 파일 경로를 환경 변수에 설정
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_file_path
                self.temp_credentials_file = temp_file_path  # 나중에 정리하기 위해 저장
                
                logger.info(f"임시 서비스 계정 키 파일 생성 및 환경 변수 설정 완료: {temp_file_path}")
                return True
                
            # 3. api_key 매개변수가 제공된 경우 (JSON 문자열 형태일 수 있음)
            elif self.api_key and (self.api_key.startswith('{') or os.path.exists(self.api_key)):
                try:
                    if os.path.exists(self.api_key):
                        # 파일 경로인 경우 직접 환경 변수에 설정
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.api_key
                        logger.info(f"API 키 파일 경로를 환경 변수에 설정: {self.api_key}")
                        return True
                    else:
                        # JSON 문자열인 경우 임시 파일로 저장
                        service_account_info = json.loads(self.api_key)
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                            json.dump(service_account_info, temp_file)
                            temp_file_path = temp_file.name
                        
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_file_path
                        self.temp_credentials_file = temp_file_path
                        
                        logger.info(f"API 키 JSON에서 임시 서비스 계정 키 파일 생성: {temp_file_path}")
                        return True
                except Exception as e:
                    logger.error(f"API 키 처리 중 오류: {str(e)}")
                    
        except Exception as e:
            logger.error(f"서비스 계정 키 설정 중 오류: {str(e)}")
        
        # 인증 설정 실패
        logger.error("Google Cloud 인증 설정 실패. 환경 변수나 Streamlit Secrets에 서비스 계정 키가 없습니다.")
        self.error_messages.append("Google Cloud 인증 정보를 찾을 수 없습니다. 환경 변수 GOOGLE_APPLICATION_CREDENTIALS 설정 또는 Streamlit Secrets 설정이 필요합니다.")
        return False
    
    def __del__(self):
        """
        객체 소멸 시 임시 파일 정리
        """
        if hasattr(self, 'temp_credentials_file') and self.temp_credentials_file and os.path.exists(self.temp_credentials_file):
            try:
                os.remove(self.temp_credentials_file)
                logger.info(f"임시 인증 파일 삭제 완료: {self.temp_credentials_file}")
            except Exception as e:
                logger.error(f"임시 인증 파일 삭제 중 오류: {str(e)}")
    
    def update_progress(self, message, progress_value=None):
        """진행 상황 업데이트 (Streamlit 사용 시)"""
        if self.progress_callback:
            # 중요 메시지나 진행률이 있을 때만 실제 메시지 전달
            if progress_value is not None or message.startswith(("✅", "⚠️", "❌")):
                self.progress_callback(message, progress_value)
            else:
                # 일반 디버그 메시지는 로깅만
                logger.info(message)
        else:
            print(message)
            
    def generate_tts(self, text, output_filename=None, voice_name=None):
        """
        텍스트에서 TTS 오디오 생성
        
        Args:
            text: TTS로 변환할 텍스트
            output_filename: 출력 파일 이름 (없으면 자동 생성)
            voice_name: 음성 이름 (엔진별로 다름)
            
        Returns:
            생성된 TTS 파일 경로
        """
        if not text.strip():
            logger.error("빈 텍스트는 TTS 생성이 불가능합니다.")
            return None
        
        # 출력 파일명 설정
        if not output_filename:
            timestamp = int(time.time())
            output_filename = f"tts_{timestamp}.mp3"
        
        # 확장자 확인 및 추가
        if not output_filename.lower().endswith(('.mp3', '.wav')):
            output_filename += '.mp3'
        
        # 출력 경로 설정
        output_path = os.path.join(self.output_dir, output_filename)
        
        # TTS 생성 시작 - 선택한 엔진에 따라 분기
        try:
            if self.tts_engine == "google":
                self.update_progress("Google Cloud TTS로 음성 생성 중...", 10)
                return self._generate_google_tts(text, output_path, voice_name)
            
            elif self.tts_engine == "openai":
                self.update_progress("OpenAI TTS로 음성 생성 중...", 10)
                return self._generate_openai_tts(text, output_path, voice_name)
            
            elif self.tts_engine == "local":
                self.update_progress("로컬 TTS 엔진으로 음성 생성 중...", 10)
                return self._generate_local_tts(text, output_path, voice_name)
                
            else:
                logger.error(f"지원되지 않는 TTS 엔진: {self.tts_engine}")
                return None
                
        except Exception as e:
            logger.error(f"TTS 생성 중 오류 발생: {e}")
            return None
    
    def _generate_google_tts(self, text, output_path, voice_name=None):
        """Google Cloud TTS를 사용하여 오디오 생성"""
        try:
            from google.cloud import texttospeech_v1 as texttospeech
            
            # 텍스트 입력 설정
            synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # 음성 설정
            if not voice_name:
                voice_name = 'ko-KR-Neural2-C'  # 기본 한국어 음성
            
            voice = texttospeech.VoiceSelectionParams(
                language_code='ko-KR',
                name=voice_name
            )
            
            # 오디오 설정
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,  # 기본 속도
                pitch=0.0,  # 기본 피치
                volume_gain_db=0.0  # 기본 볼륨
            )
            
            # 진행 상황 업데이트
            self.update_progress("Google Cloud TTS API 호출 중...", 30)
            
            # TTS API 호출
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            
            # 오디오 파일로 저장
            with open(output_path, 'wb') as out:
                out.write(response.audio_content)
                
            self.update_progress("Google Cloud TTS 생성 완료", 90)
            logger.info(f"TTS 오디오 저장 완료: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Google TTS 생성 중 오류: {e}")
            return None
    
    def _generate_openai_tts(self, text, output_path, voice_name=None):
        """OpenAI TTS를 사용하여 오디오 생성"""
        try:
            import openai
            
            # 음성 설정
            if not voice_name:
                voice_name = 'alloy'  # 기본 음성
            
            # 진행 상황 업데이트
            self.update_progress("OpenAI TTS API 호출 중...", 30)
            
            # OpenAI TTS API 호출
            response = openai.audio.speech.create(
                model="tts-1",
                voice=voice_name,
                input=text
            )
            
            # 오디오 파일로 저장
            response.stream_to_file(output_path)
                
            self.update_progress("OpenAI TTS 생성 완료", 90)
            logger.info(f"TTS 오디오 저장 완료: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"OpenAI TTS 생성 중 오류: {e}")
            return None
    
    def _generate_local_tts(self, text, output_path, voice_name=None):
        """로컬 TTS 엔진을 사용하여 오디오 생성"""
        try:
            import pyttsx3
            
            # 음성 선택 (가능한 경우)
            if voice_name:
                voices = self.engine.getProperty('voices')
                for voice in voices:
                    if voice_name in voice.name:
                        self.engine.setProperty('voice', voice.id)
                        break
            
            # 진행 상황 업데이트
            self.update_progress("로컬 TTS 엔진으로 음성 변환 중...", 50)
            
            # 임시 파일로 저장 (WAV 형식)
            temp_wav = output_path.replace('.mp3', '.wav')
            self.engine.save_to_file(text, temp_wav)
            self.engine.runAndWait()
            
            # MP3로 변환 (필요한 경우)
            if output_path.lower().endswith('.mp3'):
                try:
                    from pydub import AudioSegment
                    sound = AudioSegment.from_wav(temp_wav)
                    sound.export(output_path, format="mp3")
                    os.remove(temp_wav)  # 임시 WAV 파일 삭제
                except ImportError:
                    # pydub이 설치되어 있지 않으면 WAV 파일을 그대로 사용
                    output_path = temp_wav
                    logger.warning("pydub 라이브러리가 설치되지 않아 MP3 변환을 건너뜁니다. WAV 파일을 사용합니다.")
            
            self.update_progress("로컬 TTS 생성 완료", 90)
            logger.info(f"TTS 오디오 저장 완료: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"로컬 TTS 생성 중 오류: {e}")
            return None
            
    def _adjust_timestamps_based_on_actual_duration(self, subtitles, tts_file_path):
        """
        실제 오디오 파일 길이를 기준으로 자막 타임스탬프를 비례적으로 조정
        
        Args:
            subtitles: 조정할 자막 리스트
            tts_file_path: 실제 오디오 파일 경로
            
        Returns:
            조정된 자막 리스트
        """
        if not subtitles or len(subtitles) == 0:
            return subtitles
            
        try:
            # 실제 오디오 길이 확인
            from pydub import AudioSegment
            audio = AudioSegment.from_file(tts_file_path)
            actual_duration = len(audio) / 1000.0  # 밀리초 → 초
            
            # 현재 예측된 총 시간 계산 (마지막 자막의 end_time)
            estimated_duration = subtitles[-1]["end_time"]
            
            # 길이가 거의 같으면 조정하지 않음
            if abs(actual_duration - estimated_duration) < 0.5:
                self.update_progress("자막 타임스탬프 조정 불필요 (실제 길이와 유사)", None)
                return subtitles
                
            # 시간 비율 계산 및 조정
            ratio = actual_duration / estimated_duration
            self.update_progress(f"실제 오디오 길이({actual_duration:.2f}초)에 맞게 자막 타임스탬프 조정 (비율: {ratio:.2f})", None)
            
            for subtitle in subtitles:
                subtitle["start_time"] *= ratio
                subtitle["end_time"] *= ratio
            
            return subtitles
            
        except Exception as e:
            self.update_progress(f"⚠️ 자막 타임스탬프 조정 중 오류: {str(e)}", None)
            logger.warning(f"자막 타임스탬프 조정 실패: {str(e)}")
            # 오류 발생 시 원본 자막 반환
            return subtitles
    
    def get_tts_with_timestamps(self, text, voice_name=None):
        """
        텍스트에서 TTS를 생성하고 타임스탬프를 생성하여 자막 데이터 반환
        
        Args:
            text: TTS로 변환할 텍스트
            voice_name: 사용할 음성 이름 (엔진별로 다름)
            
        Returns:
            (tts_file_path, subtitles): TTS 파일 경로와 자막 데이터의 튜플
        """
        # 문장 단위로 분리
        sentences = self._split_into_sentences(text)
        
        # 전체 텍스트에 대한 TTS 생성
        tts_file = self.generate_tts(text, voice_name=voice_name)
        
        if not tts_file or not os.path.exists(tts_file):
            self.update_progress("❌ TTS 파일 생성 실패", None)
            return None, []
        
        # STT 기반 자막 동기화를 사용할 경우 (사용자가 명시적으로 선택한 경우에만)
        if self.use_stt_for_subtitles:
            self.update_progress("STT를 사용하여 정확한 자막 타임스탬프 생성 중...", None)
            try:
                # STT로 정확한 타임스탬프 추출
                subtitles = self._get_stt_based_timestamps(tts_file, text)
                if subtitles and len(subtitles) > 0:
                    self.update_progress(f"✅ STT 기반 자막 생성 완료 ({len(subtitles)}개 자막)", None)
                    # 실제 오디오 길이에 맞게 미세 조정 (STT 결과도 완벽하지 않을 수 있음)
                    subtitles = self._adjust_timestamps_based_on_actual_duration(subtitles, tts_file)
                    return tts_file, subtitles
                else:
                    self.update_progress("⚠️ STT 기반 자막 생성 실패, 추정 기반 방식으로 전환", None)
            except Exception as e:
                self.update_progress(f"⚠️ STT 처리 오류: {str(e)}, 추정 기반 방식으로 전환", None)
                import traceback
                logger.error(f"STT 처리 오류 세부 정보: {traceback.format_exc()}")
        
        # 기본값: 추정 기반 타임스탬프 생성
        self.update_progress("추정 기반 자막 타임스탬프 생성 중...", None)
        subtitles = self._estimate_timestamps(sentences)
        self.update_progress(f"✅ 추정 기반 자막 생성 완료 ({len(subtitles)}개 자막)", None)
        
        # 실제 오디오 길이에 맞게 자막 타임스탬프 조정
        subtitles = self._adjust_timestamps_based_on_actual_duration(subtitles, tts_file)
        
        return tts_file, subtitles
    
    def _split_into_sentences(self, text):
        """텍스트를 문장 단위로 분리"""
        # 기본 구분자로 문장 분리
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # 빈 문장 제거 및 정리
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _estimate_timestamps(self, sentences):
        """
        문장의 길이를 기반으로 대략적인 타임스탬프 생성
        
        Args:
            sentences: 문장 리스트
            
        Returns:
            자막 데이터 리스트
        """
        self.update_progress("음절 기반 자막 타임스탬프 생성 중...", None)
        subtitles = []
        current_time = 0.0
        
        for sentence in sentences:
            # 문장을 절로 분리
            clauses = self._split_into_clauses(sentence)
            
            for clause in clauses:
                # 음절 기반 분석으로 발음 시간 계산
                duration = self._analyze_syllables(clause)
                
                # 자막 데이터 추가
                subtitles.append({
                    "text": clause,
                    "start_time": current_time,
                    "end_time": current_time + duration
                })
                
                # 다음 절 시작 시간 업데이트
                current_time += duration
        
        return subtitles
    
    def _analyze_syllables(self, text):
        """
        한국어 음절 기반 발화 시간 분석
        
        Args:
            text: 분석할 텍스트
            
        Returns:
            예상 발화 시간 (초)
        """
        # 기본 최소 지속 시간 (빈 텍스트 예외 처리)
        if not text or not text.strip():
            return 0.8  # 1.0 → 0.8
        
        # 공백 제거 (발화 시간 계산용)
        text_without_space = text.replace(" ", "")
        
        # 기본 음절 수 (길이)
        syllable_count = len(text_without_space)
        
        # 문장 부호 처리 (쉼표, 마침표 등) - 휴지
        pause_time = 0
        pause_time += text.count(',') * 0.1   # 0.15 → 0.1 (쉼표)
        pause_time += text.count('.') * 0.15  # 0.2 → 0.15 (마침표)
        pause_time += text.count('!') * 0.15  # 0.2 → 0.15 (느낌표)
        pause_time += text.count('?') * 0.15  # 0.2 → 0.15 (물음표)
        pause_time += text.count(';') * 0.1   # 0.15 → 0.1 (세미콜론)
        pause_time += text.count(':') * 0.1   # 0.15 → 0.1 (콜론)
        
        # 한글 자모 분석
        complex_char_count = 0
        total_jamo_count = 0
        
        for char in text_without_space:
            if '가' <= char <= '힣':  # 한글 유니코드 범위
                jamo_complexity, jamo_count = self._analyze_korean_char(char)
                complex_char_count += jamo_complexity
                total_jamo_count += jamo_count
        
        # 숫자 처리 (숫자는 발음이 더 복잡함)
        numbers = sum(1 for char in text_without_space if char.isdigit())
        
        # 영어 글자 처리 (한국어 발음 시)
        english_chars = sum(1 for char in text_without_space if 'a' <= char.lower() <= 'z')
        
        # 기본 발화 속도: 초당 6.5음절 (6.0 → 6.5)
        base_duration = syllable_count / 6.5
        
        # 가중치 적용 (모든 가중치를 더 줄임)
        complexity_factor = 1.0 + (complex_char_count / max(1, syllable_count)) * 0.15  # 0.2 → 0.15
        duration = (base_duration * complexity_factor) + pause_time
        duration += (numbers / max(1, syllable_count)) * base_duration * 0.15  # 0.2 → 0.15
        duration += (english_chars / max(1, syllable_count)) * base_duration * 0.1  # 0.15 → 0.1
        
        # 공백 수 반영 (읽기 쉬움)
        spaces = text.count(' ')
        if spaces > 0:
            space_factor = min(0.95, 0.98 - (spaces / max(1, len(text)) * 0.02))  # 0.03 → 0.02
            duration *= space_factor
        
        # 긴 문장은 발화 속도가 더 빨라짐 (단계적 가속)
        if syllable_count > 10:  # 15 → 10 (더 짧은 문장부터 가속 적용)
            duration *= 0.85
        elif syllable_count > 20:  # 10-20 글자
            duration *= 0.8
        elif syllable_count > 30:  # 20-30 글자
            duration *= 0.75  # 0.8 → 0.75
        
        # 최대 발화 시간 제한 (특히 긴 문장의 경우)
        if duration > 3.0 and syllable_count > 15:
            duration = min(duration, 3.0 + (syllable_count - 15) * 0.1)
        
        # 최소 지속 시간 보장
        return max(0.7, duration)  # 0.8 → 0.7
    
    def _analyze_korean_char(self, char):
        """
        한글 문자 하나를 분석하여 복잡도 계산
        
        Args:
            char: 분석할 한글 문자 하나
            
        Returns:
            (복잡도, 자모 수) 튜플
        """
        # 한글이 아니면 기본값 반환
        if not '가' <= char <= '힣':
            return 0, 1
        
        # 한글 유니코드 분해
        char_code = ord(char) - ord('가')
        
        # 초성, 중성, 종성 분리
        initial = char_code // (21 * 28)
        medial = (char_code % (21 * 28)) // 28
        final = char_code % 28
        
        # 자모 수 계산 (종성이 없으면 2, 있으면 3)
        jamo_count = 3 if final > 0 else 2
        
        # 복잡도 계산
        complexity = 0
        
        # 초성 복잡도 (쌍자음, 된소리 등이 더 복잡)
        complex_initials = [1, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]  # ㄱ,ㄲ,ㄴ,ㄷ,ㄸ 등 복잡한 자음
        if initial in complex_initials:
            complexity += 0.5
        
        # 중성 복잡도 (이중 모음이 더 복잡)
        complex_medials = [2, 3, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]  # ㅑ,ㅒ,ㅕ,ㅖ 등 복잡한 모음
        if medial in complex_medials:
            complexity += 0.3
        
        # 종성 복잡도 (겹받침이 더 복잡)
        if final > 0:
            complex_finals = [3, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # ㄱㅅ,ㄴㅈ,ㄹㄱ 등 복잡한 받침
            if final in complex_finals:
                complexity += 0.7
            else:
                complexity += 0.3  # 일반 받침
        
        return complexity, jamo_count
    
    def _split_into_clauses(self, sentence):
        """
        문장을 절/구 단위로 분리 (한국어 특성 고려)
        
        Args:
            sentence: 분리할 문장
            
        Returns:
            절/구 리스트
        """
        # 아주 짧은 문장은 그대로 반환
        if len(sentence) <= 10:  # 15 → 10
            return [sentence]
            
        # 결과 저장할 리스트
        clauses = []
        
        # 1. 기본 구두점 기준 분리 (쉼표, 세미콜론, 콜론, 따옴표 등)
        primary_delimiters = r'[,;:"\']'
        primary_splits = re.split(f'(?<={primary_delimiters})', sentence)
        
        # 임시 저장 목록
        temp_clauses = []
        
        # 구두점 기준 1차 분리
        for split in primary_splits:
            split = split.strip()
            if not split:
                continue
                
            # 충분히 짧은 경우 그대로 추가
            if len(split) <= 20:  # 30 → 20
                temp_clauses.append(split)
            else:
                # 2. 한국어 조사/어미 기준 2차 분리
                korean_splits = self._split_by_korean_particles(split)
                temp_clauses.extend(korean_splits)
        
        # 3. 길이 기준 최종 조정
        current_clause = ""
        
        for clause in temp_clauses:
            # 현재 절이 비어 있으면 새로 시작
            if not current_clause:
                current_clause = clause
                continue
                
            # 현재 절에 추가했을 때 너무 길면 저장하고 새로 시작
            combined = current_clause + " " + clause if current_clause else clause
            if len(combined) > 25:  # 최대 길이 25자로 제한
                clauses.append(current_clause)
                current_clause = clause
            else:
                # 조합해도 괜찮은 길이면 합침
                current_clause = combined
        
        # 남은 절 추가
        if current_clause:
            clauses.append(current_clause)
            
        # 빈 절 제거 및 원본 반환 보호
        clauses = [c for c in clauses if c.strip()]
        if not clauses:
            return [sentence]
            
        return clauses
        
    def _split_by_korean_particles(self, text):
        """
        한국어 조사와 어미 등의 특성을 활용한 분리
        
        Args:
            text: 분리할 텍스트
            
        Returns:
            분리된 구 리스트
        """
        # 결과 저장할 리스트
        fragments = []
        
        # 기본 어절 분리 (공백 기준)
        words = text.split()
        
        if len(words) <= 3:  # 어절이 3개 이하면 그대로 반환
            return [text]
            
        # 문장을 순회하며 적절한 끊김 위치 찾기
        current_fragment = ""
        word_count = 0
        
        for i, word in enumerate(words):
            # 현재 단어 추가
            if current_fragment:
                current_fragment += " " + word
            else:
                current_fragment = word
                
            word_count += 1
            
            # 조건 확인: 조사나 어미로 끝나는 경우 + 적절한 길이
            should_split = False
            
            # 1. 긴 어절이 3개 이상 모였으면 분리
            if word_count >= 3:
                should_split = True
                
            # 2. 특정 조사 뒤에서 분리 (은/는, 이/가, 을/를, 에, 의, 로/으로 등)
            elif word_count >= 2 and i < len(words) - 1:  # 마지막 단어가 아니면
                # 주요 조사 패턴 (단어 끝에 위치)
                subject_particles = r'(이|가)$'  # 주격 조사
                topic_particles = r'(은|는)$'    # 주제 조사
                object_particles = r'(을|를)$'   # 목적격 조사
                location_particles = r'(에서|에|께|한테|에게)$'  # 위치/방향 조사
                
                # 단어 끝에 주요 조사가 있는지 확인
                if (re.search(subject_particles, word) or 
                    re.search(topic_particles, word) or 
                    re.search(object_particles, word) or 
                    re.search(location_particles, word)):
                    should_split = True
                    
            # 3. 특정 연결 어미로 끝나는 경우 (고, 며, 서, 자, 면 등)
            elif word_count >= 2 and i < len(words) - 1:  # 마지막 단어가 아니면
                # 주요 연결 어미 패턴
                connective_endings = r'(고|며|서|되|자|면|니까|지만)$'
                
                # 단어 끝에 주요 연결 어미가 있는지 확인
                if re.search(connective_endings, word):
                    should_split = True
            
            # 4. 인용 표현 ("라고", "하고" 등)
            elif word_count >= 2 and i < len(words) - 1:
                quote_patterns = r'(라고|하고|하며|하자|하면)$'
                if re.search(quote_patterns, word):
                    should_split = True
            
            # 분리 조건 만족시 현재 프래그먼트 저장 및 초기화
            if should_split:
                fragments.append(current_fragment)
                current_fragment = ""
                word_count = 0
        
        # 남은 부분 추가
        if current_fragment:
            fragments.append(current_fragment)
            
        # 결과가 없으면 원본 반환
        if not fragments:
            return [text]
            
        return fragments
    
    def _get_stt_based_timestamps(self, audio_path, original_text):
        """
        STT를 사용하여 정확한 자막 타임스탬프 생성
        
        Args:
            audio_path: 오디오 파일 경로
            original_text: 원본 텍스트
            
        Returns:
            정확한 타임스탬프가 포함된 자막 데이터 리스트
        """
        try:
            from google.cloud import speech_v1p1beta1 as speech
            
            # 원본 오디오를 STT용으로 준비 (16kHz WAV로 변환)
            self.update_progress("오디오 파일 준비 중...", None)
            
            # 임시 WAV 파일 생성 (필요시)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
            
            # MP3/기타 형식을 WAV로 변환 (STT API 요구사항)
            if not audio_path.lower().endswith('.wav'):
                from pydub import AudioSegment
                audio = AudioSegment.from_file(audio_path)
                audio = audio.set_channels(1)  # 모노로 변환
                audio = audio.set_frame_rate(16000)  # 16kHz로 변환
                audio.export(temp_wav_path, format="wav")
            else:
                # 이미 WAV인 경우 파일 복사
                import shutil
                shutil.copy2(audio_path, temp_wav_path)
            
            self.update_progress("Google Speech API 호출 중...", None)
            
            # 오디오 파일 로드
            with open(temp_wav_path, "rb") as audio_file:
                content = audio_file.read()
            
            # Speech API 설정
            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code="ko-KR",
                enable_word_time_offsets=True,  # 단어별 타임스탬프 활성화
                enable_automatic_punctuation=True,
                model="default"
            )
            
            # STT 요청
            response = self.speech_client.recognize(config=config, audio=audio)
            
            # 사용한 임시 파일 삭제
            try:
                os.remove(temp_wav_path)
            except:
                pass
            
            # 결과 처리
            if not response.results:
                self.update_progress("⚠️ STT 결과가 없습니다.", None)
                return []
            
            # 문장 모으기 및 자막 데이터 생성
            subtitles = []
            current_sentence = {"text": "", "start_time": 0, "end_time": 0}
            
            for result in response.results:
                for i, word_info in enumerate(result.alternatives[0].words):
                    word = word_info.word
                    start_time = word_info.start_time.total_seconds()
                    end_time = word_info.end_time.total_seconds()
                    
                    # 첫 단어인 경우 새로운 문장 시작
                    if i == 0 and not current_sentence["text"]:
                        current_sentence["text"] = word
                        current_sentence["start_time"] = start_time
                        current_sentence["end_time"] = end_time
                    else:
                        # 기존 문장에 단어 추가
                        current_sentence["text"] += " " + word
                        current_sentence["end_time"] = end_time
                    
                    # 문장 끝 감지 (마침표, 물음표, 느낌표 등으로 끝나는 경우)
                    if word.endswith(('.', '?', '!', '。', '？', '！')):
                        subtitles.append(current_sentence.copy())
                        current_sentence = {"text": "", "start_time": 0, "end_time": 0}
            
            # 마지막 문장이 남아있으면 추가
            if current_sentence["text"]:
                subtitles.append(current_sentence)
            
            # 자막이 없으면 빈 리스트 반환
            if not subtitles:
                self.update_progress("⚠️ 유효한 자막을 생성하지 못했습니다.", None)
                return []
            
            # 원본 텍스트와 STT 결과 비교 및 조정
            self._align_stt_with_original(subtitles, original_text)
            
            self.update_progress(f"✅ STT 기반 자막 {len(subtitles)}개 생성 완료", None)
            return subtitles
            
        except Exception as e:
            self.update_progress(f"❌ STT 처리 오류: {str(e)}", None)
            import traceback
            logger.error(f"STT 처리 오류 세부 정보: {traceback.format_exc()}")
            return []
    
    def _align_stt_with_original(self, subtitles, original_text):
        """
        STT 결과와 원본 텍스트를 비교하여 자막 내용을 조정
        
        Args:
            subtitles: STT로 생성된 자막 데이터
            original_text: 원본 텍스트
        """
        try:
            # 원본 텍스트를 문장으로 분리
            original_sentences = self._split_into_sentences(original_text)
            
            # STT 결과 개수와 원본 문장 개수가 크게 다르면 조정 안함
            if abs(len(subtitles) - len(original_sentences)) > len(original_sentences) / 2:
                self.update_progress("⚠️ STT 결과와 원본 문장 수가 크게 차이납니다. 자막 내용은 STT 결과를 유지합니다.", None)
                return
            
            # 자막 수가 더 적은 쪽을 기준으로 처리
            min_count = min(len(subtitles), len(original_sentences))
            
            # 자막 내용을 원본 텍스트로 교체
            for i in range(min_count):
                # 타임스탬프는 유지하면서 텍스트만 교체
                subtitles[i]["text"] = original_sentences[i]
            
        except Exception as e:
            self.update_progress(f"⚠️ 자막 정렬 오류: {str(e)}", None)
            logger.error(f"자막 정렬 오류: {str(e)}") 

    def trim_script_to_duration(self, text, max_duration):
        """
        스크립트를 최대 허용 재생 시간에 맞게 자동으로 줄이는 함수
        
        Args:
            text: 원본 스크립트 텍스트
            max_duration: 최대 허용 재생 시간 (초)
            
        Returns:
            조정된 스크립트 텍스트
        """
        # 이미 충분히 짧으면 그대로 반환
        estimated_duration = self._estimate_total_duration(text)
        if estimated_duration <= max_duration:
            logger.info(f"스크립트 길이가 적절합니다. 예상 재생 시간: {estimated_duration:.1f}초, 최대 허용 시간: {max_duration}초")
            return text
        
        # 넉넉한 마진 설정 (실제 TTS 생성 시 약간의 차이가 있을 수 있음)
        target_duration = max_duration * 0.95  # 5% 마진 적용
        
        logger.info(f"스크립트가 너무 깁니다. 예상 재생 시간: {estimated_duration:.1f}초, 목표 시간: {target_duration:.1f}초")
        
        # 문장 단위로 분리
        sentences = self._split_into_sentences(text)
        
        # 각 문장의 예상 재생 시간 계산
        sentence_durations = []
        for sentence in sentences:
            duration = self._analyze_syllables(sentence)
            sentence_durations.append((sentence, duration))
        
        # 중요도에 따라 문장 정렬 (첫 번째 문장과 마지막 문장이 가장 중요)
        # 중간 문장들은 길이 대비 내용 밀도가 높은 순으로 정렬
        
        # 첫 문장과 마지막 문장은 무조건 포함
        first_sentence = sentence_durations[0] if sentence_durations else None
        last_sentence = sentence_durations[-1] if len(sentence_durations) > 1 else None
        
        # 중간 문장들 (첫 문장과 마지막 문장을 제외)
        middle_sentences = sentence_durations[1:-1] if len(sentence_durations) > 2 else []
        
        # 내용 밀도가 높은 순으로 정렬 (더 짧고 내용이 많은 문장 우선)
        # 길이 대비 내용 밀도 = 단어 수 / 예상 재생 시간
        middle_sentences.sort(
            key=lambda x: len(x[0].split()) / max(x[1], 0.5),
            reverse=True
        )
        
        # 문장 선택하기
        selected_sentences = []
        current_duration = 0
        
        # 첫 문장 항상 포함
        if first_sentence:
            selected_sentences.append(first_sentence[0])
            current_duration += first_sentence[1]
        
        # 마지막 문장도 일단 추가 예약
        last_sentence_duration = last_sentence[1] if last_sentence else 0
        reserved_duration = current_duration + last_sentence_duration
        
        # 중간 문장 추가 (목표 시간을 초과하지 않는 선에서)
        for sentence, duration in middle_sentences:
            if reserved_duration + duration <= target_duration:
                selected_sentences.append(sentence)
                reserved_duration += duration
            else:
                # 목표 시간을 초과하므로 이 문장은 건너뜀
                logger.debug(f"문장 제외: '{sentence[:30]}...' (길이: {duration:.1f}초)")
        
        # 마지막 문장 추가
        if last_sentence and last_sentence[0] not in selected_sentences:
            selected_sentences.append(last_sentence[0])
        
        # 선택된 문장을 원래 순서대로 정렬
        final_sentences = []
        for sentence in sentences:
            if sentence in selected_sentences:
                final_sentences.append(sentence)
        
        # 최종 스크립트 생성
        trimmed_script = " ".join(final_sentences)
        
        # 최종 예상 시간 계산
        final_duration = self._estimate_total_duration(trimmed_script)
        
        logger.info(f"스크립트 조정 완료. 원본: {len(sentences)}문장, 조정 후: {len(final_sentences)}문장")
        logger.info(f"조정된 재생 시간: {final_duration:.1f}초 (목표: {target_duration:.1f}초)")
        
        return trimmed_script
    
    def _estimate_total_duration(self, text):
        """
        전체 텍스트의 예상 재생 시간 계산
        
        Args:
            text: 예상 시간을 계산할 텍스트
            
        Returns:
            예상 재생 시간 (초)
        """
        # 문장 단위로 분리
        sentences = self._split_into_sentences(text)
        
        # 각 문장의 재생 시간 합산
        total_duration = 0
        for sentence in sentences:
            duration = self._analyze_syllables(sentence)
            total_duration += duration
        
        return total_duration

@st.cache_resource
def get_tts_generator(tts_engine="google", api_key=None, output_dir=None, use_stt_for_subtitles=False):
    """
    TTSGenerator 인스턴스를 캐싱하여 반환합니다.
    
    Args:
        tts_engine: TTS 엔진 ("google", "openai", "local" 중 하나)
        api_key: API 키 (필요한 경우)
        output_dir: 출력 디렉토리
        use_stt_for_subtitles: STT를 사용하여 정확한 자막 타임스탬프 생성 여부
        
    Returns:
        TTSGenerator 인스턴스
    """
    return TTSGenerator(
        tts_engine=tts_engine,
        api_key=api_key,
        output_dir=output_dir,
        progress_callback=None,  # 콜백은 UI에서 별도로 처리
        use_stt_for_subtitles=use_stt_for_subtitles
    ) 
