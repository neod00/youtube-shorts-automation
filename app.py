import streamlit as st
st.set_page_config(
    page_title="YouTube Shorts 자동화 생성기",
    page_icon="🎬",
    layout="wide"
)

# 그 이후에 나머지 streamlit 관련 코드 작성
import os
import time
import subprocess
import sys
import json
import random
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd
import base64
from PIL import Image
import socket
import re
import importlib.util

# app-git.py 파일 상단에 추가
try:
    import nltk
    
    # 필요한 NLTK 리소스 다운로드
    nltk.download('punkt')
    nltk.download('averaged_perceptron_tagger')
    nltk.download('maxent_ne_chunker')
    nltk.download('words')
    
    # 특수한 punkt_tab 리소스 문제 해결 시도
    try:
        nltk.download('punkt_tab')
    except:
        # punkt_tab이 없는 경우 punkt로 대체
        logger.warning("punkt_tab 리소스를 찾을 수 없습니다. punkt를 대신 사용합니다.")
        
    logger.info("NLTK 리소스 다운로드 완료")
except Exception as e:
    logger.error(f"NLTK 리소스 다운로드 실패: {e}")
    st.error(f"NLTK 리소스 다운로드 실패: {e}")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='streamlit_app.log',
    filemode='a'
)

logger = logging.getLogger('app')

# 모듈 경로 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

# 인터넷 연결 확인 함수 추가
def check_internet_connection():
    """인터넷 연결 상태 확인"""
    try:
        # 8.8.8.8은 Google DNS 서버
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        logger.warning("인터넷 연결 없음: 오프라인 모드로 전환")
        return False
    except:
        logger.warning("인터넷 연결 상태 확인 불가: 오프라인 모드 가정")
        return False

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output_videos")
TTS_DIR = os.path.join(BASE_DIR, "tts_files")
SCRIPT_DIR = os.path.join(BASE_DIR, "scripts")
BG_VIDEO_DIR = os.path.join(BASE_DIR, "background_videos")
BG_MUSIC_DIR = os.path.join(BASE_DIR, "background_music")
THUMBNAIL_DIR = os.path.join(BASE_DIR, "thumbnails")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 디렉토리 생성
for directory in [OUTPUT_DIR, TTS_DIR, SCRIPT_DIR, BG_VIDEO_DIR, BG_MUSIC_DIR, THUMBNAIL_DIR, CACHE_DIR, LOG_DIR]:
    os.makedirs(directory, exist_ok=True)

# 진행 상황 업데이트 함수
def update_progress(message, progress=None):
    """Streamlit 진행 상황 업데이트"""
    if 'progress_bar' in st.session_state and st.session_state.progress_bar is not None:
        if progress is not None:
            st.session_state.progress_bar.progress(progress / 100)
            # 퍼센트 표시 추가
            if 'progress_percent' in st.session_state and st.session_state.progress_percent is not None:
                st.session_state.progress_percent.text(f"{int(progress)}%")
        if message is not None and 'status_text' in st.session_state and st.session_state.status_text is not None:
            st.session_state.status_text.markdown(message)
    else:
        if message is not None:  # message가 None이 아닐 때만 표시
            st.write(message)
    
    # 로깅 (None 메시지는 로깅하지 않음)
    if message is not None:
        logger.info(message)

# 필요한 모듈 가져오기 - 모듈별 개별 임포트 시도
try:
    from video_creator import VideoCreator
    logger.info("VideoCreator 모듈 로드 성공")
except ImportError as e:
    logger.error(f"VideoCreator 모듈 로드 실패: {e}")
    st.error(f"VideoCreator 모듈 로드 실패: {e}")

try:
    from tts_generator import TTSGenerator
    logger.info("TTSGenerator 모듈 로드 성공")
except ImportError as e:
    logger.error(f"TTSGenerator 모듈 로드 실패: {e}")
    st.error(f"TTSGenerator 모듈 로드 실패: {e}")

# YouTubeUploader 모듈 동적 로드 시도
try:
    # 파일 경로 확인
    youtube_uploader_path = os.path.join(script_dir, 'youtube_uploader.py')
    if not os.path.exists(youtube_uploader_path):
        logger.error(f"youtube_uploader.py 파일을 찾을 수 없습니다. 경로: {youtube_uploader_path}")
        st.error(f"youtube_uploader.py 파일을 찾을 수 없습니다.")
        # 대체 클래스 정의
        class YouTubeUploader:
            def __init__(self, *args, **kwargs):
                self.credentials_file = None
                logger.warning("YouTubeUploader 대체 클래스가 사용됩니다. 유튜브 업로드 기능이 제한됩니다.")
                st.warning("YouTubeUploader 모듈을 찾을 수 없어 유튜브 업로드 기능이 제한됩니다.")
    else:
        # 동적 임포트 시도
        spec = importlib.util.spec_from_file_location("youtube_uploader", youtube_uploader_path)
        youtube_uploader_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(youtube_uploader_module)
        YouTubeUploader = youtube_uploader_module.YouTubeUploader
        logger.info("YouTubeUploader 모듈 동적 로드 성공")
except Exception as e:
    logger.error(f"YouTubeUploader 동적 로드 실패: {e}")
    st.error(f"YouTubeUploader 모듈 로드 실패: {e}")
    # 대체 클래스 정의
    class YouTubeUploader:
        def __init__(self, *args, **kwargs):
            self.credentials_file = None
            logger.warning("YouTubeUploader 대체 클래스가 사용됩니다. 유튜브 업로드 기능이 제한됩니다.")
            st.warning("YouTubeUploader 로드 실패로 유튜브 업로드 기능이 제한됩니다.")

try:
    from content_extractor import ContentExtractor
    logger.info("ContentExtractor 모듈 로드 성공")
except ImportError as e:
    logger.error(f"ContentExtractor 모듈 로드 실패: {e}")
    st.error(f"ContentExtractor 모듈 로드 실패: {e}")

try:
    from pexels_downloader import PexelsVideoDownloader
    logger.info("PexelsVideoDownloader 모듈 로드 성공")
except ImportError as e:
    logger.error(f"PexelsVideoDownloader 모듈 로드 실패: {e}")
    st.error(f"PexelsVideoDownloader 모듈 로드 실패: {e}")

try:
    from jamendo_music_provider import JamendoMusicProvider
    logger.info("JamendoMusicProvider 모듈 로드 성공")
except ImportError as e:
    logger.error(f"JamendoMusicProvider 모듈 로드 실패: {e}")
    st.error(f"JamendoMusicProvider 모듈 로드 실패: {e}")

try:
    from thumbnail_generator import ThumbnailGenerator
    logger.info("ThumbnailGenerator 모듈 로드 성공")
except ImportError as e:
    logger.error(f"ThumbnailGenerator 모듈 로드 실패: {e}")
    st.error(f"ThumbnailGenerator 모듈 로드 실패: {e}")

try:
    from config import config, get_api_key
    logger.info("Config 모듈 로드 성공")
except ImportError as e:
    logger.error(f"Config 모듈 로드 실패: {e}")
    st.error(f"Config 모듈 로드 실패: {e}")

# Secrets에서 클라이언트 시크릿 정보 가져오기
client_secret = None
if 'google_api' in st.secrets and 'client_secret' in st.secrets['google_api']:
    # Secrets에서 클라이언트 시크릿 정보를 임시 파일로 저장
    try:
        import tempfile
        client_secret_data = st.secrets['google_api']['client_secret']
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        with open(temp_file.name, 'w') as f:
            json.dump(client_secret_data, f)
        
        client_secret = temp_file.name
        logger.info(f"클라이언트 시크릿을 임시 파일에 저장했습니다: {client_secret}")
        st.success(f"클라이언트 시크릿을 임시 파일에 저장했습니다: {client_secret}")
    except Exception as e:
        logger.error(f"클라이언트 시크릿 저장 실패: {e}")
        st.error(f"클라이언트 시크릿 저장 실패: {e}")

# CSS 스타일 적용
st.markdown("""
<style>
    .main-header {
        font-size: 2.5em;
        color: #FF0000;
        text-align: center;
        margin-bottom: 20px;
    }
    .sub-header {
        font-size: 1.8em;
        color: #0066CC;
        margin-top: 30px;
        margin-bottom: 15px;
    }
    .info-text {
        font-size: 1.1em;
        color: #444;
    }
    .success-box {
        padding: 10px;
        background-color: #e6ffe6;
        border-left: 5px solid #00cc66;
        margin-bottom: 10px;
        color: #005500; /* 어두운 녹색 텍스트 색상 추가 */
        font-weight: 500; /* 텍스트 굵기 추가 */
    }
    .warning-box {
        padding: 10px;
        background-color: #ffffcc;
        border-left: 5px solid #ffcc00;
        margin-bottom: 10px;
        color: #664d00; /* 어두운 갈색 텍스트 색상 추가 */
        font-weight: 500; /* 텍스트 굵기 추가 */
    }
    .error-box {
        padding: 10px;
        background-color: #ffe6e6;
        border-left: 5px solid #cc0000;
        margin-bottom: 10px;
        color: #800000; /* 어두운 빨간색 텍스트 색상 추가 */
        font-weight: 500; /* 텍스트 굵기 추가 */
    }
    .info-box {
        padding: 10px;
        background-color: #e6f2ff;
        border-left: 5px solid #0066cc;
        margin-bottom: 10px;
        color: #003366; /* 어두운 파란색 텍스트 색상 */
        font-weight: 500; /* 텍스트 굵기 추가 */
    }
    .stButton>button {
        width: 100%;
        height: 3em;
        font-size: 1.1em;
        font-weight: bold;
    }
    .settings-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border: 1px solid #dee2e6;
    }
    .settings-title {
        font-size: 1.5em;
        margin-bottom: 15px;
        color: #0066CC;
    }
    /* 진행률 표시 스타일 */
    .progress-container {
        margin-bottom: 10px;
    }
    .progress-text {
        display: flex;
        justify-content: space-between;
        margin-bottom: 5px;
    }
    .progress-message {
        font-weight: 500;
    }
    .progress-percent {
        font-weight: bold;
        color: #0066CC;
    }
</style>
""", unsafe_allow_html=True)

# 헤더
st.markdown('<div class="main-header">YouTube Shorts 자동화 생성기</div>', unsafe_allow_html=True)
st.markdown('<div class="info-text">한 번의 클릭으로 고품질 YouTube Shorts 비디오를 생성하세요!</div>', unsafe_allow_html=True)

# 세션 상태 초기화
if 'generated_video' not in st.session_state:
    st.session_state.generated_video = None
if 'tts_file' not in st.session_state:
    st.session_state.tts_file = None
if 'script_content' not in st.session_state:
    st.session_state.script_content = ""
if 'subtitles' not in st.session_state:
    st.session_state.subtitles = None
if 'video_logs' not in st.session_state:
    st.session_state.video_logs = []
if 'background_video' not in st.session_state:
    st.session_state.background_video = None
if 'settings_tab' not in st.session_state:
    st.session_state.settings_tab = False
if 'openai_api_key' not in st.session_state:
    st.session_state.openai_api_key = ""
if 'google_api_key' not in st.session_state:
    st.session_state.google_api_key = ""
if 'pexels_api_key' not in st.session_state:
    st.session_state.pexels_api_key = ""
if 'jamendo_client_id' not in st.session_state:
    st.session_state.jamendo_client_id = ""
# 오프라인 모드 감지 변수 추가
if 'is_offline_mode' not in st.session_state:
    st.session_state.is_offline_mode = not check_internet_connection()
# API 인스턴스 저장 변수 추가
if 'pexels_downloader' not in st.session_state:
    st.session_state.pexels_downloader = None
if 'jamendo_provider' not in st.session_state:
    st.session_state.jamendo_provider = None

# API 키 설정 파일 경로
API_SETTINGS_FILE = os.path.join(BASE_DIR, "api_settings.json")

# API 설정 저장 함수
def save_api_settings():
    settings = {
        "openai_api_key": st.session_state.openai_api_key,
        "google_api_key": st.session_state.google_api_key,
        "pexels_api_key": st.session_state.pexels_api_key,
        "jamendo_client_id": st.session_state.jamendo_client_id
    }
    
    try:
        with open(API_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"API 설정 저장 오류: {e}")
        return False

# API 설정 로드 함수
def load_api_settings():
    if os.path.exists(API_SETTINGS_FILE):
        try:
            with open(API_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
                # 세션 상태에 설정 저장
                for key, value in settings.items():
                    if key in st.session_state:
                        st.session_state[key] = value
            return True
        except Exception as e:
            logger.error(f"API 설정 로드 오류: {e}")
    return False

# Pexels 다운로더 초기화 함수
def initialize_pexels_downloader():
    """Pexels API 다운로더 초기화"""
    try:
        # 이미 초기화된 경우 재사용
        if st.session_state.pexels_downloader is not None:
            logger.info("기존 Pexels 다운로더 인스턴스 재사용")
            return st.session_state.pexels_downloader
        
        # API 키 가져오기
        api_key = st.session_state.pexels_api_key or get_api_key("PEXELS_API_KEY")
        
        if api_key:
            logger.info(f"Pexels API 키 확인됨: {api_key[:4]}...{api_key[-4:]}")
        else:
            logger.warning("Pexels API 키가 없습니다.")
        
        # 오프라인 모드 감지
        if st.session_state.is_offline_mode:
            logger.info("오프라인 모드: Pexels API 사용 불가")
            return None
            
        # 다운로더 초기화
        if api_key:
            logger.info("Pexels 다운로더 초기화 시작...")
            # 수정: PexelsVideoDownloader 클래스는 output_dir와 cache_dir 매개변수를 지원하지 않음
            # 지원되는 매개변수만 사용 (api_key, progress_callback, offline_mode)
            downloader = PexelsVideoDownloader(
                api_key=api_key,
                progress_callback=update_progress,
                offline_mode=st.session_state.is_offline_mode
            )
            logger.info(f"Pexels 다운로더 초기화 완료")
            
            # API 키 설정 확인
            if hasattr(downloader, 'api_key') and downloader.api_key:
                logger.info(f"✅ Pexels API 키 확인됨: {downloader.api_key[:4]}...{downloader.api_key[-4:]}")
            else:
                logger.warning("⚠️ Pexels API 키가 다운로더에 설정되지 않았습니다!")
            
            # 캐시 디렉토리 확인 (직접 생성하지 않음 - 클래스가 내부적으로 처리)
            logger.info("Pexels 캐시 디렉토리 확인 완료")
            
            # 다운로더 저장 및 반환
            st.session_state.pexels_downloader = downloader
            return downloader
    except Exception as e:
        logger.error(f"Pexels 다운로더 초기화 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return None

# Jamendo 음악 제공자 초기화 함수
def initialize_jamendo_provider():
    """Jamendo API 음악 제공자 초기화"""
    try:
        # 이미 초기화된 경우 재사용
        if st.session_state.jamendo_provider is not None:
            return st.session_state.jamendo_provider
        
        # API 키 가져오기
        client_id = st.session_state.jamendo_client_id or get_api_key("JAMENDO_CLIENT_ID")
        
        # 오프라인 모드 감지
        if st.session_state.is_offline_mode:
            logger.info("오프라인 모드: Jamendo API 사용 불가")
            return None
        
        # Pexels 다운로더 가져오기 (번역 기능을 위해)
        pexels_downloader = st.session_state.pexels_downloader
        if pexels_downloader is None:
            # 필요시 초기화 시도
            pexels_downloader = initialize_pexels_downloader()
            
        # 음악 제공자 초기화
        if client_id:
            try:
                provider = JamendoMusicProvider(
                    client_id=client_id,
                    output_dir=BG_MUSIC_DIR,
                    cache_dir=os.path.join(CACHE_DIR, "jamendo"),
                    progress_callback=update_progress,
                    pexels_downloader=pexels_downloader  # Pexels 다운로더 객체 전달
                )
                st.session_state.jamendo_provider = provider
                logger.info("Jamendo 음악 제공자 초기화 성공")
                return provider
            except Exception as e:
                logger.error(f"Jamendo 제공자 클래스 초기화 오류: {e}")
                import traceback
                traceback.print_exc()
                
                # 안전하게 기본 JamendoMusicProvider 객체 생성 시도
                try:
                    # 기본 파라미터로 시도
                    provider = JamendoMusicProvider(
                        client_id=client_id,
                        output_dir=BG_MUSIC_DIR
                    )
                    st.session_state.jamendo_provider = provider
                    logger.info("기본 Jamendo 음악 제공자로 초기화")
                    return provider
                except:
                    logger.error("모든 Jamendo 초기화 시도 실패")
    except Exception as e:
        logger.error(f"Jamendo 제공자 초기화 오류: {e}")
    
    return None

# 배경 음악을 가져오는 함수
def fetch_background_music(keywords, duration=60):
    """배경 음악 가져오기"""
    try:
        # Jamendo 제공자 초기화
        provider = initialize_jamendo_provider()
        
        if not provider:
            logger.warning("Jamendo 제공자가 초기화되지 않았습니다")
            return None
            
        # 키워드가 문자열이면 콤마로 분리
        if isinstance(keywords, str):
            keywords_str = keywords
        else:
            # 리스트면 콤마로 결합
            keywords_str = ",".join(keywords)
            
        # 검색 시도    
        logger.info(f"배경 음악 검색 중: {keywords_str}")
        
        # search_with_fallback 함수 사용하여 검색
        try:
            # 한국어 키워드 자동 번역이 적용된 search_with_fallback 함수 사용
            music_path = provider.get_music(keywords_str)
            
            if music_path and os.path.exists(music_path):
                logger.info(f"음악 찾음: {os.path.basename(music_path)}")
                return music_path
        except Exception as e:
            logger.error(f"음악 검색 중 오류: {str(e)}")
        
        # 백업 방법: 기본 키워드로 검색
        logger.warning("기본 키워드로 음악 검색 시도")
        for keyword in ["calm", "ambient", "piano", "relaxing"]:
            try:
                music_path = provider.search_music(keyword)
                if music_path and len(music_path) > 0:
                    # 첫 번째 트랙 다운로드
                    track = music_path[0]
                    downloaded = provider.download_track(track)
                    if downloaded:
                        logger.info(f"기본 키워드로 음악 찾음: {os.path.basename(downloaded)}")
                        return downloaded
            except:
                continue
                
        # 로컬 음악 확인
        if os.path.exists(BG_MUSIC_DIR):
            music_files = [f for f in os.listdir(BG_MUSIC_DIR) 
                          if f.lower().endswith(('.mp3', '.wav', '.m4a'))]
            if music_files:
                selected = random.choice(music_files)
                music_path = os.path.join(BG_MUSIC_DIR, selected)
                logger.info(f"로컬 음악 파일 사용: {selected}")
                return music_path
                
        logger.warning("배경 음악을 찾을 수 없습니다")
        return None
    except Exception as e:
        logger.error(f"배경 음악 검색 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# 앱 시작 시 API 설정 로드
load_api_settings()

def estimate_speech_duration(text):
    """
    음절 기반 분석을 통해 텍스트의 예상 발화 시간을 계산
    
    Args:
        text: 분석할 텍스트
        
    Returns:
        예상 발화 시간 (초)
    """
    # 빈 텍스트 처리
    if not text or not text.strip():
        return 0
        
    # 문장 단위로 분리
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    total_duration = 0.0
    
    # 각 문장별로 계산
    for sentence in sentences:
        # 공백 제거 (발화 시간 계산용)
        text_without_space = sentence.replace(" ", "")
        
        # 기본 음절 수 (길이)
        syllable_count = len(text_without_space)
        
        # 문장 부호 처리 (쉼표, 마침표 등) - 휴지
        pause_time = 0
        pause_time += sentence.count(',') * 0.1    # 쉼표
        pause_time += sentence.count('.') * 0.15   # 마침표
        pause_time += sentence.count('!') * 0.15   # 느낌표
        pause_time += sentence.count('?') * 0.15   # 물음표
        pause_time += sentence.count(';') * 0.1    # 세미콜론
        pause_time += sentence.count(':') * 0.1    # 콜론
        
        # 한글 자모 분석 (단순화된 버전)
        complex_char_count = 0
        for char in text_without_space:
            if '가' <= char <= '힣':  # 한글 유니코드 범위
                # 한글 유니코드 분해
                char_code = ord(char) - ord('가')
                
                # 종성 여부 확인 (받침이 있으면 더 복잡)
                final = char_code % 28
                if final > 0:
                    complex_char_count += 0.3
        
        # 숫자와 영어 글자 처리
        numbers = sum(1 for char in text_without_space if char.isdigit())
        english_chars = sum(1 for char in text_without_space if 'a' <= char.lower() <= 'z')
        
        # 기본 발화 속도: 초당 6.5음절
        base_duration = syllable_count / 6.5
        
        # 가중치 적용
        complexity_factor = 1.0 + (complex_char_count / max(1, syllable_count)) * 0.15
        duration = (base_duration * complexity_factor) + pause_time
        duration += (numbers / max(1, syllable_count)) * base_duration * 0.15
        duration += (english_chars / max(1, syllable_count)) * base_duration * 0.1
        
        # 공백 수 반영 (읽기 쉬움)
        spaces = sentence.count(' ')
        if spaces > 0:
            space_factor = min(0.95, 0.98 - (spaces / max(1, len(sentence)) * 0.02))
            duration *= space_factor
        
        # 긴 문장은 발화 속도가 더 빨라짐
        if syllable_count > 10:
            duration *= 0.85
        elif syllable_count > 20:
            duration *= 0.8
        elif syllable_count > 30:
            duration *= 0.75
        
        # 문장별 최소 지속 시간 보장
        sentence_duration = max(0.7, duration)
        total_duration += sentence_duration
    
    return total_duration

# 사이드바
with st.sidebar:
    st.markdown('<div class="sidebar-header">⚙️ 메뉴</div>', unsafe_allow_html=True)
    
    # 설정 페이지로 이동 버튼
    if st.button("API 키 설정", key="open_settings"):
        st.session_state.settings_tab = True
    
    # 영상 길이 설정 슬라이더 추가
    st.markdown("### 영상 길이 설정")
    video_duration = st.slider(
        "최대 영상 길이 (초)",
        min_value=15,
        max_value=180,
        value=60,
        step=15,
        help="생성할 영상의 최대 길이를 설정합니다. YouTube 쇼츠는 최대 3분(180초)까지 지원합니다."
    )
    
    # TTS 엔진 선택
    st.markdown("### TTS 엔진 선택")
    tts_engine = st.selectbox(
        "TTS 엔진",
        ["Google Cloud TTS", "OpenAI TTS", "로컬 TTS"], 
        index=0
    )
    
    # TTS 음성 선택
    tts_voice = None
    if tts_engine == "Google Cloud TTS":
        tts_voice = st.selectbox(
            "TTS 음성",
            ["ko-KR-Neural2-C", "ko-KR-Neural2-A", "ko-KR-Standard-A", "ko-KR-Standard-B", "ko-KR-Standard-C", "ko-KR-Standard-D"],
            index=0
        )
    elif tts_engine == "OpenAI TTS":
        tts_voice = st.selectbox(
            "TTS 음성",
            ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
            index=0
        )
    
    # 배경 음악 설정
    st.markdown("### 배경 음악 설정")
    use_background_music = st.checkbox("배경 음악 사용", value=True)
    
    if use_background_music:
        background_music_volume = st.slider("배경 음악 볼륨", 0.0, 1.0, 0.15, 0.05)
        
        # 배경 음악 소스 선택
        bg_music_source = st.radio(
            "배경 음악 소스",
            ["로컬 음악 파일", "Jamendo API (자동 검색)"],
            index=1  # Jamendo API (자동 검색)을 기본값으로 설정
        )
        
        if bg_music_source == "로컬 음악 파일":
            # 배경 음악 파일 선택
            bg_music_files = []
            for file in os.listdir(BG_MUSIC_DIR):
                if file.endswith(('.mp3', '.wav', '.m4a')):
                    bg_music_files.append(file)
            
            if bg_music_files:
                background_music = st.selectbox(
                    "배경 음악 선택",
                    ["랜덤 선택"] + bg_music_files,
                    index=0
                )
            else:
                st.warning("배경 음악 파일이 없습니다. 배경 음악 파일을 'background_music' 폴더에 추가하세요.")
                background_music = None
        else:
            st.info("Jamendo API를 사용하여 키워드에 맞는 배경 음악을 자동으로 검색합니다.")
    
    # 배경 비디오 설정
    st.markdown("### 배경 비디오 설정")
    bg_video_option = st.radio(
        "배경 비디오 소스",
        ["랜덤 선택", "Pexels에서 검색", "직접 업로드", "그라데이션 배경 생성"],
        index=1  # Pexels에서 검색을 기본값으로 설정
    )
    
    # 그라데이션 배경 옵션 추가
    if bg_video_option == "그라데이션 배경 생성":
        gradient_style = st.selectbox(
            "그라데이션 스타일",
            ["랜덤", "블루", "레드", "그린", "퍼플", "오렌지", "레인보우"],
            index=0
        )
        
        st.info("그라데이션 배경은 인터넷 연결 없이도 생성 가능합니다.")
    
    # 비디오 스타일 설정 추가
    st.markdown("### 비디오 스타일 설정")
    video_style = st.radio(
        "비디오 스타일",
        ["기본 스타일", "삼분할 템플릿 스타일"],
        index=1,  # 삼분할 템플릿 스타일을 기본값으로 설정
        help="삼분할 템플릿 스타일은 상단에 제목, 중앙에 비디오, 하단에 설명을 배치합니다."
    )
    
    if video_style == "삼분할 템플릿 스타일":
        st.info("삼분할 템플릿 스타일이 선택되었습니다. 비디오가 세 영역으로 나뉘어 생성됩니다: 상단(제목), 중앙(비디오), 하단(설명)")
    
    # 업로드 설정
    st.markdown("### 업로드 설정")
    auto_upload = st.checkbox("생성 후 자동 업로드", value=False)
    
    # 자막 설정
    st.markdown("### 자막 설정")
    use_subtitles = st.checkbox("자막 추가", value=True, help="비디오에 자막을 추가합니다.")
    
    if use_subtitles:
        st.markdown("#### 자막 설정")
        
        st.markdown("**자막 동기화 방식 선택**")
        
        # 음절 기반 자막 동기화는 항상 적용됨 (기본 방식)
        st.info("📊 **음절 기반 자막 동기화**: 한국어 음절의 복잡도를 분석하여 발화 시간을 정확하게 예측합니다. 자막은 문장 구조에 따라 자연스럽게 절로 나뉘어 표시됩니다.")
        
        # STT 기반 자막 동기화 옵션 추가
        use_stt_for_subtitles = st.checkbox(
            "고급 자막 동기화 (STT 사용)", 
            value=False, 
            help="음성 인식(STT)을 사용하여 더 정확한 자막 타임스탬프를 생성합니다. 처리 시간이 길어질 수 있습니다. 선택하지 않으면 텍스트 길이 기반 방식으로 자동 동기화됩니다."
        )
        
        if use_stt_for_subtitles:
            st.info("STT 기반 자막 동기화를 활성화했습니다. 자막 생성에 추가 시간이 소요될 수 있으며, Google Cloud 인증이 필요합니다.")
            
            # Google Cloud 인증 관련 안내
            if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                st.warning("Google Cloud Speech API 사용을 위해 서비스 계정 키가 필요합니다. 환경 변수 'GOOGLE_APPLICATION_CREDENTIALS'가 설정되지 않았습니다.")
                
            # 필요한 패키지 확인
            try:
                import google.cloud.speech_v1p1beta1
                from pydub import AudioSegment
            except ImportError:
                st.error("STT 기능을 위해 추가 패키지가 필요합니다. 'pip install google-cloud-speech pydub' 명령으로 설치하세요.")
                use_stt_for_subtitles = False
            else:
                st.info("❓ **고급 자막 동기화(STT 사용)** 옵션을 활성화하면 음성 인식을 통해 더 정확한 자막 타이밍을 계산할 수 있습니다.")
        
        # 추가 자막 옵션들을 사전으로 만들기
        subtitle_options = {}
        
        # 자막 크기 옵션 (슬라이더에서 선택 박스로 변경)
        subtitle_size_options = ["작게", "기본크기(중간)", "크게"]
        subtitle_size = st.radio("자막 크기", subtitle_size_options, index=1, horizontal=True)
        
        # 크기 옵션에 따라 font_size 설정
        BASE_FONT_SIZE = 90  # 이미지에 보이는 자막과 같은 기본 크기
        if subtitle_size == "작게":
            font_size = int(BASE_FONT_SIZE * 0.7)  # 기본 크기의 70%
        elif subtitle_size == "크게":
            font_size = int(BASE_FONT_SIZE * 1.3)  # 기본 크기의 130%
        else:  # 기본크기(중간)
            font_size = BASE_FONT_SIZE
            
        subtitle_options["font_size"] = font_size
        # 디버그 정보는 로깅만 하고 UI에는 표시하지 않음
        logging.info(f"자막 크기가 '{subtitle_size}'({font_size})로 설정되었습니다.")
        
        # 세션 상태에 저장 (전역 변수처럼 사용하기 위함)
        st.session_state.font_size = font_size
        
        # 디버그 로그 추가 - 값이 제대로 설정되었는지 확인
        logging.debug(f"자막 옵션 설정 디버그: subtitle_options['font_size']={subtitle_options.get('font_size')}")
        logging.debug(f"세션 상태에 저장: st.session_state.font_size={st.session_state.font_size}")
        
        # 자막 색상 (리스트에서 선택)
        subtitle_color_options = ["흰색", "노란색", "파란색", "초록색", "빨간색"]
        subtitle_color_values = {"흰색": (255, 255, 255), "노란색": (255, 255, 0), 
                                "파란색": (0, 0, 255), "초록색": (0, 255, 0), 
                                "빨간색": (255, 0, 0)}
        
        subtitle_color = st.selectbox("자막 색상", subtitle_color_options, index=0)
        subtitle_options["text_color"] = subtitle_color_values[subtitle_color]
        
        # 자막 위치 설정 추가
        subtitle_position_options = ["하단", "상단", "중앙 하단"]
        subtitle_position_values = {"하단": "bottom", "상단": "top", "중앙 하단": "center_bottom"}
        
        subtitle_position = st.selectbox("자막 위치", subtitle_position_options, index=0)
        subtitle_options["position"] = subtitle_position_values[subtitle_position]
        
        # 자막 테두리 설정
        subtitle_options["outline_width"] = st.slider("자막 테두리 두께", 0, 10, 2)
        subtitle_options["outline_color"] = (0, 0, 0)  # 기본 검은색 테두리

# 설정 페이지 또는 메인 탭 표시
if st.session_state.settings_tab:
    # 설정 화면 표시
    st.markdown('<div class="sub-header">API 설정</div>', unsafe_allow_html=True)
    
    # API 키 입력 양식
    col1, col2 = st.columns(2)
    
    with col1:
        # OpenAI API 키
        openai_key = st.text_input(
            "OpenAI API 키:",
            value=st.session_state.openai_api_key,
            type="password",
            help="ChatGPT 스크립트 변환에 필요합니다"
        )
        st.session_state.openai_api_key = openai_key
        
        # Google API 키
        google_key = st.text_input(
            "Google Cloud API 키:",
            value=st.session_state.google_api_key,
            type="password",
            help="Google TTS 서비스에 필요합니다"
        )
        st.session_state.google_api_key = google_key
        
        # Pexels API 키
        pexels_key = st.text_input(
            "Pexels API 키:",
            value=st.session_state.pexels_api_key,
            type="password",
            help="배경 비디오 다운로드에 필요합니다"
        )
        st.session_state.pexels_api_key = pexels_key
        
        # Jamendo API 키
        jamendo_key = st.text_input(
            "Jamendo Client ID:",
            value=st.session_state.jamendo_client_id,
            type="password",
            help="배경 음악 다운로드에 필요합니다"
        )
        st.session_state.jamendo_client_id = jamendo_key
        
        # 설정 저장 버튼
        if st.button("API 설정 저장", use_container_width=True):
            if save_api_settings():
                st.success("API 설정이 저장되었습니다.")
            else:
                st.error("API 설정 저장 중 오류가 발생했습니다.")
    
    with col2:
        if st.button("메인 화면으로 돌아가기", use_container_width=True):
            st.session_state.settings_tab = False
            st.rerun()

# 탭 생성 (항상 생성됨)
tab1, tab2, tab3, tab4 = st.tabs(["콘텐츠 생성", "비디오 미리보기", "업로드 설정", "로그 및 기록"])

# 설정 탭이 활성화되었을 때는 메인 탭의 내용을 표시하지 않음
if not st.session_state.settings_tab:
    # 기존 앱 기능 표시
    # ChatGPT를 이용한 콘텐츠 변환 함수
    def convert_content_to_shorts_script(content, api_key=None, max_duration=180):
        """
        ChatGPT를 이용하여 콘텐츠를 YouTube 쇼츠용 스크립트로 변환
        
        Args:
            content: 원본 콘텐츠
            api_key: OpenAI API 키
            max_duration: 최대 영상 길이(초)
            
        Returns:
            변환된 스크립트
        """
        if not api_key:
            return "OpenAI API 키가 설정되지 않았습니다."
        
        try:
            import openai
            
            # OpenAI API 설정
            openai.api_key = api_key
            
            # 최소 길이 요구사항 설정 (최대 길이의 70%)
            min_duration = max(max_duration * 0.7, 30)  # 최소 30초 또는 최대 길이의 70%
            
            # 스크립트 생성 시도 (최대 3번)
            max_attempts = 3
            current_attempt = 0
            final_script = None
            
            while current_attempt < max_attempts:
                current_attempt += 1
                
                # 프롬프트 구성 (이전 시도 결과에 따라 조정)
                length_guidance = f"총 길이는 {max_duration}초 동안 읽을 수 있는 양으로 작성하세요."
                if current_attempt > 1:
                    length_guidance = f"총 길이는 최소 {int(min_duration)}초에서 최대 {max_duration}초 사이로 작성해야 합니다. 이전 스크립트가 너무 짧았으므로, 더 많은 내용을 포함하여 최소 {int(min_duration)}초 이상 되도록 해주세요."
                
                prompt = f"""
                당신은 YouTube 쇼츠용 스크립트 작성 전문가입니다.
                입력된 콘텐츠를 분석하고 YouTube 쇼츠에 최적화된 스크립트로 재작성해주세요.
                
                작성 지침:
                1. 하나의 명확한 핵심 메시지를 정하고 (기획)
                2. 구조를 '3초 훅-핵심 전달-강력한 마무리'으로 나누고 (구성)
                3. 말하듯 짧고 강하게 시청자의 감정을 자극하는 문장으로 작성하세요 (작성)
                4. {length_guidance} (매우 중요)
                5. 첫 문장은 시청자의 관심을 끌 수 있도록 강력하게 시작하세요
                6. 핵심 내용을 충분히 전달하면서도 대화체로 친근하게 작성하세요
                
                금지 사항:
                - 여러 주제 혼합 금지 (오직 하나의 주제에만 집중)
                - 불필요한 배경 설명이나 지나치게 긴 도입부 금지
                - 모호하거나 일반적인 표현 사용 금지
                - 과장된 클릭베이트성 표현 사용 금지
                - 스크립트에 시간 표시나 섹션 레이블을 포함하지 마세요
                - 스크립트 형식 지시사항이나 메타데이터를 포함하지 마세요
                - 대괄호([]) 안에 있는 구조적 설명이나 지시사항을 포함하지 마세요
                - TTS로 발음되어야 하는 순수한 내용만 포함하세요
                - 별표(*), 이모티콘, 특수문자 등 TTS에서 발음되는 불필요한 요소를 포함하지 마세요
                - '좋아요, 구독해 주세요'와 같은 CTA(Call-to-Action) 문구를 넣지 마세요
                
                원본 콘텐츠: {content}
                """
                
                # API 호출
                try:
                    # 최신 OpenAI API 사용
                    try:
                        client = openai.Client(api_key=api_key)
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": "당신은 유능한 YouTube 쇼츠 스크립트 작성자입니다."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=1000,
                            temperature=0.7
                        )
                        script = response.choices[0].message.content.strip()
                    except Exception as e:
                        # 구버전 API 사용 시도
                        response = openai.ChatCompletion.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": "당신은 유능한 YouTube 쇼츠 스크립트 작성자입니다."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=1000,
                            temperature=0.7
                        )
                        script = response.choices[0].message.content.strip()
                    
                    # 생성된 스크립트의 예상 재생 시간 확인
                    estimated_duration = estimate_speech_duration(script)
                    
                    logger.info(f"생성된 스크립트 예상 시간: {estimated_duration:.1f}초 (시도 {current_attempt}/{max_attempts})")
                    
                    # 길이 요구사항 충족 여부 확인
                    if estimated_duration >= min_duration and estimated_duration <= max_duration:
                        # 요구사항 충족
                        final_script = script
                        logger.info(f"적절한 길이의 스크립트 생성 성공! (예상 시간: {estimated_duration:.1f}초)")
                        break
                    elif estimated_duration < min_duration:
                        # 너무 짧음, 다음 시도에서 더 길게 생성하도록 함
                        logger.warning(f"생성된 스크립트가 너무 짧습니다. (예상 시간: {estimated_duration:.1f}초, 최소 요구: {min_duration:.1f}초)")
                        if current_attempt == max_attempts:
                            # 마지막 시도였다면 현재 스크립트 사용
                            final_script = script
                    else:
                        # 너무 길지만 최대 길이 이내이므로 사용
                        final_script = script
                        logger.info(f"스크립트 생성 성공! (예상 시간: {estimated_duration:.1f}초)")
                        break
                        
                except Exception as api_error:
                    # API 호출 오류
                    logger.error(f"OpenAI API 호출 실패 (시도 {current_attempt}/{max_attempts}): {str(api_error)}")
                    if current_attempt == max_attempts:
                        raise Exception(f"모든 시도에서 OpenAI API 호출 실패: {str(api_error)}")
            
            # 최종 스크립트가 생성되지 않았다면 원본 콘텐츠 사용
            if not final_script:
                logger.warning("스크립트 생성에 실패하여 원본 콘텐츠를 사용합니다.")
                return content
                
            return final_script
                
        except ImportError:
            return "OpenAI 라이브러리가 설치되지 않았습니다. 'pip install openai' 명령으로 설치하세요."
        except Exception as e:
            return f"OpenAI API 호출 중 오류가 발생했습니다: {str(e)}"

    # 키워드 자동 추천 함수 추가
    def generate_keywords_from_content(content, api_key=None):
        """
        ChatGPT를 사용하여 콘텐츠에서 키워드를 자동으로 추출
        
        Args:
            content: 원본 콘텐츠
            api_key: OpenAI API 키
            
        Returns:
            키워드 리스트 (최대 10개)
        """
        if not api_key:
            return []
        
        try:
            import openai
            
            # OpenAI API 설정
            openai.api_key = api_key
            
            # 프롬프트 구성
            prompt = """
            다음 콘텐츠를 분석하여 YouTube 비디오에 적합한 키워드를 10개 추출해주세요.
            키워드는 YouTube 검색 최적화에 도움이 되고, 주제와 관련성이 높아야 합니다.
            각 키워드는 한 단어 또는 짧은 구문이어야 하며, 단순히 쉼표로 구분하여 제공해주세요.
            특수문자나 해시태그(#)는 포함하지 마세요.
            
            콘텐츠: {content}
            """
            
            # API 호출
            try:
                # 최신 OpenAI API 사용
                client = openai.Client(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "당신은 콘텐츠 분석 및 키워드 추출 전문가입니다."},
                        {"role": "user", "content": prompt.format(content=content)}
                    ],
                    max_tokens=200,
                    temperature=0.3
                )
                keywords_text = response.choices[0].message.content.strip()
            except Exception as e:
                # 이전 버전 방식 시도
                try:
                    # 구버전 API 사용 시도
                    response = openai.ChatCompletion.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "당신은 콘텐츠 분석 및 키워드 추출 전문가입니다."},
                            {"role": "user", "content": prompt.format(content=content)}
                        ],
                        max_tokens=200,
                        temperature=0.3
                    )
                    keywords_text = response.choices[0].message.content.strip()
                except Exception as fallback_error:
                    # 모든 시도 실패
                    raise Exception(f"OpenAI API 호출 실패: {str(fallback_error)}")
            
            # 쉼표로 구분된 키워드 리스트로 변환
            keywords = [keyword.strip() for keyword in keywords_text.split(',') if keyword.strip()]
            
            # 최대 10개 키워드 반환
            return keywords[:10]
                
        except ImportError:
            return []
        except Exception as e:
            logger.error(f"키워드 추출 중 오류 발생: {str(e)}")
            return []

    # 콘텐츠에서 매력적인 쇼츠 제목 생성 함수
    def generate_catchy_title(content, api_key=None):
        """
        ChatGPT를 사용하여 콘텐츠에서 매력적인 YouTube 쇼츠 제목을 생성
        
        Args:
            content: 원본 콘텐츠
            api_key: OpenAI API 키
            
        Returns:
            매력적인 쇼츠 제목 (영어, 특수문자, 공백 등이 파일명에 적합하게 처리됨)
        """
        if not api_key:
            return f"shorts_{int(time.time())}"
        
        try:
            import openai
            import re
            
            # OpenAI API 설정
            openai.api_key = api_key
            
            # 프롬프트 구성
            prompt = """
            다음 콘텐츠를 분석하여 YouTube 쇼츠에 최적화된 매력적이고 클릭을 유도하는 제목을 만들어주세요.
            
            작성 지침:
            1. 10~20자 내외의 짧고 강력한 제목을 만드세요
            2. 호기심을 자극하고 클릭을 유도하는 표현을 사용하세요
            3. 관심을 끌 수 있는 감정적인 단어나 표현을 포함하세요
            4. 콘텐츠의 핵심 가치나 놀라운 정보를 암시하세요
            5. 쇼츠 특성상 모바일에서 보기 좋은 간결한 제목이어야 합니다
            6. 한국어로만 작성해야 합니다
            7. "제목: " 같은 접두어 없이 제목만 작성해주세요
            
            콘텐츠: {content}
            """
            
            # API 호출
            try:
                # 최신 OpenAI API 사용
                client = openai.Client(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "당신은 YouTube 쇼츠 제목 작성 전문가입니다."},
                        {"role": "user", "content": prompt.format(content=content)}
                    ],
                    max_tokens=50,
                    temperature=0.7
                )
                title = response.choices[0].message.content.strip()
            except Exception as e:
                # 이전 버전 방식 시도
                try:
                    # 구버전 API 사용 시도
                    response = openai.ChatCompletion.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "당신은 YouTube 쇼츠 제목 작성 전문가입니다."},
                            {"role": "user", "content": prompt.format(content=content)}
                        ],
                        max_tokens=50,
                        temperature=0.7
                    )
                    title = response.choices[0].message.content.strip()
                except Exception as fallback_error:
                    # 모든 시도 실패 시 타임스탬프 사용
                    return f"shorts_{int(time.time())}"
            
            # 파일명에 적합하지 않은 문자 제거
            # 특수문자, 공백 등을 언더스코어로 대체
            safe_title = re.sub(r'[^\w\s가-힣ㄱ-ㅎㅏ-ㅣ]', '_', title)
            # 공백을 언더스코어로 대체하고 중복 언더스코어 제거
            safe_title = re.sub(r'_+', '_', safe_title.replace(' ', '_'))
            # 언더스코어로 시작하거나 끝나는 경우 제거
            safe_title = safe_title.strip('_')
            
            # 파일명 길이 제한 (최대 50자)
            if len(safe_title) > 50:
                safe_title = safe_title[:50]
            
            # 안전장치: 제목이 비어있거나 너무 짧은 경우 기본값 사용
            if len(safe_title) < 5:
                return f"shorts_{int(time.time())}"
            
            return safe_title
            
        except ImportError:
            return f"shorts_{int(time.time())}"
        except Exception as e:
            logger.error(f"제목 생성 중 오류 발생: {str(e)}")
            return f"shorts_{int(time.time())}"

    # VideoCreator 인스턴스 생성 함수
    def get_video_creator(_progress_callback=None):
        """VideoCreator 인스턴스 생성"""
        # 기본 경로 설정
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "output_videos")
        temp_dir = os.path.join(base_dir, "temp_videos")
        background_dir = os.path.join(base_dir, "background_videos")
        music_dir = os.path.join(base_dir, "background_music")
        
        # 경로 생성
        for directory in [output_dir, temp_dir, background_dir, music_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # VideoCreator 인스턴스 생성 및 경로 설정
        from video_creator import VideoCreator
        video_creator = VideoCreator(
            output_dir=output_dir,
            temp_dir=temp_dir,
            background_dir=background_dir,
            music_dir=music_dir,
            progress_callback=_progress_callback
        )

        # API 키 설정 (세션 상태에서 가져옴)
        pexels_api_key = st.session_state.get("pexels_api_key", "")
        jamendo_client_id = st.session_state.get("jamendo_client_id", "")
        
        # setup_external_services 호출
        if pexels_api_key or jamendo_client_id:
            video_creator.setup_external_services(
                pexels_api_key=pexels_api_key,
                jamendo_client_id=jamendo_client_id
            )
        
        return video_creator
        
    def get_video_creator_with_ui_components(_progress_callback=None):
        """
        VideoCreator 인스턴스를 생성하고 에러 메시지를 UI에 표시하는 함수
        
        이 함수는 캐시가 적용된 get_video_creator를 호출하고,
        생성된 객체의 에러 메시지를 UI에 표시합니다.
        """
        # 기본 VideoCreator 인스턴스 가져오기
        video_creator = get_video_creator(_progress_callback)
        
        # TTSGenerator 관련 에러 메시지 표시
        if hasattr(video_creator, 'tts_generator') and hasattr(video_creator.tts_generator, 'error_messages'):
            for error_msg in video_creator.tts_generator.error_messages:
                st.error(error_msg)
        
        return video_creator

    # 탭 1: 콘텐츠 생성
    with tab1:
        st.markdown('<div class="sub-header">쇼츠 콘텐츠 생성</div>', unsafe_allow_html=True)
        
        # 입력 유형 선택
        input_type = st.radio(
            "입력 유형을 선택하세요:",
            ["직접 텍스트 입력", "YouTube URL", "뉴스/블로그 URL"]
        )
        
        # 입력 유형에 따른 처리
        if input_type == "직접 텍스트 입력":
            st.markdown("### 스크립트 작성")
            script_content = st.text_area(
                "3분(180초) 이내의 쇼츠 비디오용 스크립트를 작성하세요:",
                height=200,
                value=st.session_state.script_content,
                placeholder="여기에 스크립트를 입력하세요. 최대 3분(180초) 분량으로 작성하세요."
            )
            st.session_state.script_content = script_content
            
            # 직접 생성한 동영상 업로드 기능 추가
            st.markdown("### 또는 직접 생성한 동영상 업로드")
            st.markdown("이미 만든 동영상이 있다면 여기에 업로드하여 바로 YouTube에 게시할 수 있습니다.")
            
            uploaded_video = st.file_uploader("동영상 파일", type=["mp4", "mov", "avi"], key="direct_video_uploader")
            
            if uploaded_video is not None:
                # 임시 파일로 저장
                direct_video_path = os.path.join(OUTPUT_DIR, uploaded_video.name)
                
                with open(direct_video_path, "wb") as f:
                    f.write(uploaded_video.getbuffer())
                
                # 세션 상태에 저장
                st.session_state.generated_video = direct_video_path
                
                # 성공 메시지 표시
                st.markdown(f'<div class="success-box">✅ 동영상 업로드 완료: {uploaded_video.name}</div>', unsafe_allow_html=True)
                st.markdown("이제 '비디오 미리보기' 탭에서 확인하거나 '업로드 설정' 탭에서 YouTube에 업로드할 수 있습니다.")
                
                # 동영상 미리보기
                st.video(direct_video_path)
                
                # 업로드 바로가기 버튼
                if st.button("YouTube 업로드 설정으로 이동", key="direct_upload_btn"):
                    # 자동 탭 전환은 Streamlit에서 직접 지원하지 않지만, 안내 메시지 제공
                    st.info("'업로드 설정' 탭을 클릭하여 YouTube 업로드 정보를 입력하세요.")
            
            if st.button("콘텐츠 분석하기", key="analyze_direct"):
                if st.session_state.script_content.strip():
                    with st.spinner("스크립트를 분석 중입니다..."):
                        # 스크립트 저장
                        script_filename = f"script_{int(time.time())}.txt"
                        script_path = os.path.join(SCRIPT_DIR, script_filename)
                        with open(script_path, 'w', encoding='utf-8') as f:
                            f.write(st.session_state.script_content)
                        
                        # 예상 길이 계산 (정교한 알고리즘 사용)
                        char_count = len(st.session_state.script_content)
                        estimated_duration = estimate_speech_duration(st.session_state.script_content)
                        
                        st.markdown('<div class="success-box">스크립트 분석 완료!</div>', unsafe_allow_html=True)
                        st.markdown(f"### 분석 결과")
                        st.markdown(f"- 글자 수: {char_count}자")
                        st.markdown(f"- 예상 재생 시간: {estimated_duration:.1f}초")
                        
                        if estimated_duration > video_duration:
                            st.markdown(f'<div class="warning-box">⚠️ 콘텐츠가 설정된 최대 길이({video_duration}초)를 초과합니다. 더 짧게 편집하거나 최대 길이를 늘리세요.</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="error-box">⚠️ 스크립트를 입력해주세요!</div>', unsafe_allow_html=True)
        
        elif input_type == "YouTube URL":
            youtube_url = st.text_input("YouTube URL을 입력하세요:", placeholder="https://www.youtube.com/watch?v=...")
            
            if st.button("URL에서 콘텐츠 가져오기", key="fetch_youtube"):
                if youtube_url:
                    with st.spinner("YouTube에서 콘텐츠를 가져오는 중..."):
                        # YouTube 콘텐츠 가져오기
                        content_extractor = ContentExtractor(progress_callback=update_progress)
                        script_content = content_extractor.extract_from_youtube(youtube_url)
                        
                        # script_content가 딕셔너리인 경우 처리
                        if isinstance(script_content, dict):
                            # 오류 메시지 확인
                            script_text = script_content.get('script', '')
                            if script_text and "오류" in script_text:
                                error_message = script_text.replace("오류: ", "")
                                st.markdown(f'<div class="error-box">⚠️ {error_message}</div>', unsafe_allow_html=True)
                                
                                # 오류 발생 시 사용자에게 콘텐츠 직접 입력 옵션 제공
                                st.markdown("트랜스크립트를 가져올 수 없습니다. 아래에 콘텐츠를 직접 입력해주세요.")
                                
                                # 스크립트 직접 입력 영역 추가
                                manual_script = st.text_area(
                                    "스크립트 직접 입력:", 
                                    value="", 
                                    height=200,
                                    key="manual_script_youtube"
                                )
                                
                                if manual_script.strip():
                                    # 직접 입력한 스크립트 저장
                                    st.session_state.original_content = manual_script
                                    st.session_state.script_content = manual_script
                                    
                        if script_content and script_content.startswith("오류:"):
                            error_message = script_content.replace("오류: ", "")
                            st.markdown(f'<div class="error-box">⚠️ {error_message}</div>', unsafe_allow_html=True)
                            
                            # 오류 발생 시 사용자에게 콘텐츠 직접 입력 옵션 제공
                            st.markdown("트랜스크립트를 가져올 수 없습니다. 아래에 콘텐츠를 직접 입력해주세요.")
                            
                            # 스크립트 직접 입력 영역 추가
                            manual_script = st.text_area(
                                "스크립트 직접 입력:", 
                                value="", 
                                height=200,
                                key="manual_script_youtube"
                            )
                            
                            if manual_script.strip():
                                # 직접 입력한 스크립트 저장
                                st.session_state.original_content = manual_script
                                st.session_state.script_content = manual_script
                                
                                # 스크립트 저장
                                script_filename = f"manual_youtube_{int(time.time())}.txt"
                                script_path = os.path.join(SCRIPT_DIR, script_filename)
                                with open(script_path, 'w', encoding='utf-8') as f:
                                    f.write(manual_script)
                                
                                # 글자 수 및 예상 길이 계산
                                char_count = len(manual_script)
                                estimated_duration = estimate_speech_duration(manual_script)
                                
                                st.markdown(f"- 글자 수: {char_count}자")
                                st.markdown(f"- 예상 재생 시간: {estimated_duration:.1f}초")
                        else:
                            # 가져온 원본 콘텐츠를 세션에 저장
                            st.session_state.original_content = script_content
                            st.session_state.script_content = script_content
                            st.markdown('<div class="success-box">YouTube 콘텐츠 가져오기 완료!</div>', unsafe_allow_html=True)
                            
                            # 스크립트 저장
                            script_filename = f"youtube_{int(time.time())}.txt"
                            script_path = os.path.join(SCRIPT_DIR, script_filename)
                            with open(script_path, 'w', encoding='utf-8') as f:
                                # script_content가 None이거나 딕셔너리인 경우 처리
                                if script_content is None:
                                    f.write("YouTube 콘텐츠를 가져올 수 없습니다. 다른 영상을 시도하거나 직접 스크립트를 입력해주세요.")
                                    st.error("YouTube 콘텐츠를 가져올 수 없습니다.")
                                elif isinstance(script_content, dict):
                                    # 딕셔너리에서 'script' 키 추출
                                    actual_script = script_content.get('script', "")
                                    f.write(actual_script)
                                    # 세션 상태 업데이트
                                    st.session_state.original_content = actual_script
                                    st.session_state.script_content = actual_script
                                    script_content = actual_script  # 이후 코드에서 사용하기 위해
                                else:
                                    # 문자열인 경우 그대로 저장
                                    f.write(script_content)
                            
                            # 가져온 콘텐츠 표시
                            st.text_area("가져온 콘텐츠:", value=script_content, height=200, key="youtube_content_display", disabled=True)
                            
                            # 글자 수 및 예상 길이 계산
                            char_count = len(script_content)
                            estimated_duration = estimate_speech_duration(script_content)
                            
                            st.markdown(f"- 글자 수: {char_count}자")
                            st.markdown(f"- 예상 재생 시간: {estimated_duration:.1f}초")
                            
                            if estimated_duration > video_duration:
                                st.markdown(f'<div class="warning-box">⚠️ 콘텐츠가 설정된 최대 길이({video_duration}초)를 초과합니다. 더 짧게 편집하거나 최대 길이를 늘리세요.</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="error-box">⚠️ YouTube URL을 입력해주세요!</div>', unsafe_allow_html=True)
            
            # ChatGPT로 변환 버튼 - URL 입력 구조 외부로 이동
            if 'original_content' in st.session_state and input_type == "YouTube URL":
                if st.button("ChatGPT로 쇼츠용 스크립트 변환", key="convert_youtube"):
                    with st.spinner("ChatGPT를 이용하여 콘텐츠를 쇼츠용 스크립트로 변환 중..."):
                        # OpenAI API 키 가져오기
                        openai_api_key = st.session_state.get("openai_api_key", "") or get_api_key("OPENAI_API_KEY")
                        
                        if not openai_api_key:
                            st.markdown('<div class="error-box">⚠️ OpenAI API 키가 설정되지 않았습니다. 사이드바에서 API 키를 설정하세요.</div>', unsafe_allow_html=True)
                        else:
                            # ChatGPT를 이용하여 콘텐츠 변환
                            converted_script = convert_content_to_shorts_script(
                                st.session_state.original_content,
                                api_key=openai_api_key,
                                max_duration=video_duration
                            )
                            
                            # 변환된 콘텐츠를 세션에 저장
                            st.session_state.script_content = converted_script
                            st.session_state.converted_script = converted_script
                            
                            # 스크립트 저장
                            script_filename = f"youtube_converted_{int(time.time())}.txt"
                            script_path = os.path.join(SCRIPT_DIR, script_filename)
                            with open(script_path, 'w', encoding='utf-8') as f:
                                f.write(converted_script)
                            
                            # 변환이 완료되었음을 표시
                            st.session_state.conversion_complete = True
            
            # 변환이 완료되었으면 결과 표시
            if 'conversion_complete' in st.session_state and st.session_state.conversion_complete and 'converted_script' in st.session_state:
                st.markdown("### 변환된 쇼츠용 스크립트")
                # 수정 가능한 텍스트 영역으로 변환된 스크립트 표시
                edited_script = st.text_area(
                    "쇼츠용 스크립트를 수정하세요:", 
                    value=st.session_state.converted_script, 
                    height=200,
                    key="edited_youtube_script"
                )
                # 수정된 스크립트 저장
                st.session_state.script_content = edited_script
                
                # 글자 수 및 예상 길이 계산
                char_count = len(edited_script)
                estimated_duration = estimate_speech_duration(edited_script)
                
                st.markdown(f"- 글자 수: {char_count}자")
                st.markdown(f"- 예상 재생 시간: {estimated_duration:.1f}초")
                st.markdown('<div class="success-box">✅ 쇼츠용 스크립트로 변환 완료!</div>', unsafe_allow_html=True)
        
        elif input_type == "뉴스/블로그 URL":
            news_url = st.text_input("뉴스 또는 블로그 URL을 입력하세요:", placeholder="https://...")
            
            if st.button("URL에서 콘텐츠 가져오기", key="fetch_news"):
                if news_url:
                    with st.spinner("웹페이지에서 콘텐츠를 가져오는 중..."):
                        # 웹 콘텐츠 가져오기
                        content_extractor = ContentExtractor(progress_callback=update_progress)
                        script_content = content_extractor.extract_from_url(news_url)
                        
                        if "오류" in script_content or "실패" in script_content:
                            st.markdown(f'<div class="error-box">⚠️ {script_content}</div>', unsafe_allow_html=True)
                        else:
                            # 가져온 원본 콘텐츠를 세션에 저장
                            st.session_state.original_content = script_content
                            st.session_state.script_content = script_content
                            st.markdown('<div class="success-box">웹 콘텐츠 가져오기 완료!</div>', unsafe_allow_html=True)
                            
                            # 스크립트 저장
                            script_filename = f"web_{int(time.time())}.txt"
                            script_path = os.path.join(SCRIPT_DIR, script_filename)
                            with open(script_path, 'w', encoding='utf-8') as f:
                                # script_content가 None이거나 딕셔너리인 경우 처리
                                if script_content is None:
                                    f.write("웹 콘텐츠를 가져올 수 없습니다. 다른 URL을 시도하거나 직접 스크립트를 입력해주세요.")
                                    st.error("웹 콘텐츠를 가져올 수 없습니다.")
                                elif isinstance(script_content, dict):
                                    # 딕셔너리에서 'script' 키 추출
                                    actual_script = script_content.get('script', "")
                                    f.write(actual_script)
                                    # 세션 상태 업데이트
                                    st.session_state.original_content = actual_script
                                    st.session_state.script_content = actual_script
                                    script_content = actual_script  # 이후 코드에서 사용하기 위해
                                else:
                                    # 문자열인 경우 그대로 저장
                                    f.write(script_content)
                            
                            # 가져온 콘텐츠 표시
                            st.text_area("가져온 콘텐츠:", value=script_content, height=200, key="news_content_display", disabled=True)
                            
                            # 글자 수 및 예상 길이 계산
                            char_count = len(script_content)
                            estimated_duration = estimate_speech_duration(script_content)
                            
                            st.markdown(f"- 글자 수: {char_count}자")
                            st.markdown(f"- 예상 재생 시간: {estimated_duration:.1f}초")
                            
                            if estimated_duration > video_duration:
                                st.markdown(f'<div class="warning-box">⚠️ 콘텐츠가 설정된 최대 길이({video_duration}초)를 초과합니다. 더 짧게 편집하거나 최대 길이를 늘리세요.</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="error-box">⚠️ URL을 입력해주세요!</div>', unsafe_allow_html=True)
            
            # ChatGPT로 변환 버튼 - URL 입력 구조 외부로 이동
            if 'original_content' in st.session_state and input_type == "뉴스/블로그 URL":
                if st.button("ChatGPT로 쇼츠용 스크립트 변환", key="convert_news"):
                    with st.spinner("ChatGPT를 이용하여 콘텐츠를 쇼츠용 스크립트로 변환 중..."):
                        # OpenAI API 키 가져오기
                        openai_api_key = st.session_state.get("openai_api_key", "") or get_api_key("OPENAI_API_KEY")
                        
                        if not openai_api_key:
                            st.markdown('<div class="error-box">⚠️ OpenAI API 키가 설정되지 않았습니다. 사이드바에서 API 키를 설정하세요.</div>', unsafe_allow_html=True)
                        else:
                            # ChatGPT를 이용하여 콘텐츠 변환
                            converted_script = convert_content_to_shorts_script(
                                st.session_state.original_content,
                                api_key=openai_api_key,
                                max_duration=video_duration
                            )
                            
                            # 변환된 콘텐츠를 세션에 저장
                            st.session_state.script_content = converted_script
                            st.session_state.converted_script = converted_script
                            
                            # 스크립트 저장
                            script_filename = f"news_converted_{int(time.time())}.txt"
                            script_path = os.path.join(SCRIPT_DIR, script_filename)
                            with open(script_path, 'w', encoding='utf-8') as f:
                                f.write(converted_script)
                            
                            # 변환이 완료되었음을 표시
                            st.session_state.conversion_complete = True
            
            # 변환이 완료되었으면 결과 표시
            if 'conversion_complete' in st.session_state and st.session_state.conversion_complete and 'converted_script' in st.session_state and input_type == "뉴스/블로그 URL":
                st.markdown("### 변환된 쇼츠용 스크립트")
                # 수정 가능한 텍스트 영역으로 변환된 스크립트 표시
                edited_script = st.text_area(
                    "쇼츠용 스크립트를 수정하세요:", 
                    value=st.session_state.converted_script, 
                    height=200,
                    key="edited_news_script"
                )
                # 수정된 스크립트 저장
                st.session_state.script_content = edited_script
                
                # 글자 수 및 예상 길이 계산
                char_count = len(edited_script)
                estimated_duration = estimate_speech_duration(edited_script)
                
                st.markdown(f"- 글자 수: {char_count}자")
                st.markdown(f"- 예상 재생 시간: {estimated_duration:.1f}초")
                st.markdown('<div class="success-box">✅ 쇼츠용 스크립트로 변환 완료!</div>', unsafe_allow_html=True)
        
        # 키워드 입력 부분 수정 (모든 입력 유형에 공통)
        if st.session_state.script_content:
            # 키워드 섹션 표시
            st.markdown("### 비디오 키워드")
            st.markdown("키워드는 배경 음악과 비디오 검색에 사용됩니다.")
            
            # 키워드 자동 생성 버튼
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("키워드 자동 추천", key="auto_keywords"):
                    with st.spinner("키워드를 분석 중입니다..."):
                        # OpenAI API 키 가져오기
                        openai_api_key = st.session_state.get("openai_api_key", "") or get_api_key("OPENAI_API_KEY")
                        
                        if not openai_api_key:
                            st.markdown('<div class="warning-box">⚠️ OpenAI API 키가 설정되지 않았습니다. 사이드바에서 API 키를 설정하세요.</div>', unsafe_allow_html=True)
                        else:
                            # 콘텐츠에서 키워드 자동 추출
                            keywords = generate_keywords_from_content(
                                st.session_state.script_content,
                                api_key=openai_api_key
                            )
                            
                            if keywords:
                                # 키워드를 쉼표로 구분된 문자열로 변환하여 세션에 저장
                                st.session_state.suggested_keywords = ", ".join(keywords)
                                st.success(f"{len(keywords)}개의 키워드가 생성되었습니다!")
                            else:
                                st.warning("키워드를 생성할 수 없습니다. 다시 시도하거나 직접 입력하세요.")
                                st.session_state.suggested_keywords = ""
            
            # 키워드 입력 필드
            if 'suggested_keywords' not in st.session_state:
                st.session_state.suggested_keywords = ""
                
            keyword = st.text_area("키워드 (쉼표로 구분):", 
                                 value=st.session_state.suggested_keywords,
                                 placeholder="예: 여행, 음식, 스포츠 등",
                                 help="여러 키워드는 쉼표(,)로 구분하세요. 자동 추천된 키워드를 편집하거나 추가할 수 있습니다.")
            
            # 비디오 생성 버튼 
            if st.button("비디오 생성하기", use_container_width=True):
                if st.session_state.script_content.strip():
                    # 진행 상황 표시 UI 요소 개선
                    progress_container = st.container()
                    with progress_container:
                        st.markdown('<div class="progress-container">', unsafe_allow_html=True)
                        progress_col1, progress_col2 = st.columns([9, 1])
                        
                        with progress_col1:
                            st.session_state.progress_bar = st.progress(0)
                        
                        # 진행 상태 텍스트 컨테이너
                        st.markdown('<div class="progress-text">', unsafe_allow_html=True)
                        progress_message = st.empty()
                        progress_percent = st.empty()
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        st.session_state.status_text = progress_message
                        st.session_state.progress_percent = progress_percent
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    with st.spinner("비디오 생성 중... 몇 분 정도 소요될 수 있습니다"):
                        # 로그 기록 시작
                        log_entry = {
                            "생성 시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "비디오 제목": f"쇼츠_{int(time.time())}",
                            "키워드": keyword,
                            "상태": "생성 중",
                            "URL": ""
                        }
                        
                        # 진행 상황 업데이트 함수 수정
                        def video_progress_callback(message, progress_value=None):
                            """Streamlit 진행 상황 업데이트 개선 버전"""
                            if progress_value is not None:
                                # 진행 상황 업데이트
                                st.session_state.progress_bar.progress(progress_value / 100)
                                # 퍼센트 표시
                                st.session_state.progress_percent.markdown(f'<div class="progress-percent">{int(progress_value)}%</div>', unsafe_allow_html=True)
                            
                            # 메시지 업데이트
                            if message:
                                st.session_state.status_text.markdown(f'<div class="progress-message">{message}</div>', unsafe_allow_html=True)
                            
                            # 로깅
                            logger.info(f"비디오 생성 진행 [{int(progress_value) if progress_value else '?'}%]: {message}")
                        
                        try:
                            # 1. TTS 생성
                            video_progress_callback("TTS 생성 중...", 5)
                            
                            # TTS 생성 엔진 설정
                            tts_engine_id = "google"
                            if tts_engine == "OpenAI TTS":
                                tts_engine_id = "openai"
                            elif tts_engine == "로컬 TTS":
                                tts_engine_id = "local"
                            
                            # API 키 설정
                            api_key = None
                            if tts_engine_id == "google" and st.session_state.google_api_key:
                                api_key = st.session_state.google_api_key
                            elif tts_engine_id == "openai" and st.session_state.openai_api_key:
                                api_key = st.session_state.openai_api_key
                            
                            # TTS 생성기 초기화
                            tts_generator = TTSGenerator(
                                tts_engine=tts_engine_id,
                                api_key=api_key,
                                output_dir=TTS_DIR,
                                progress_callback=video_progress_callback,
                                use_stt_for_subtitles=use_stt_for_subtitles if 'use_stt_for_subtitles' in locals() else False
                            )
                            
                            # 스크립트 길이 확인 및 조절
                            original_script = st.session_state.script_content
                            estimated_duration = estimate_speech_duration(original_script)
                            
                            if estimated_duration > video_duration:
                                video_progress_callback(f"스크립트가 너무 깁니다. 길이 조절 중... (예상 시간: {estimated_duration:.1f}초, 최대 허용: {video_duration}초)", 8)
                                
                                # 스크립트 길이 자동 조절
                                adjusted_script = tts_generator.trim_script_to_duration(original_script, video_duration)
                                
                                # 세션 상태 업데이트
                                if adjusted_script != original_script:
                                    st.session_state.original_script = original_script  # 원본 저장
                                    st.session_state.script_content = adjusted_script  # 조절된 스크립트로 업데이트
                                    
                                    # 조절된 스크립트 길이 재계산
                                    new_estimated_duration = estimate_speech_duration(adjusted_script)
                                    video_progress_callback(f"스크립트 길이 조절 완료. 조절 전: {estimated_duration:.1f}초, 조절 후: {new_estimated_duration:.1f}초", 10)
                            
                            # TTS 생성 및 자막 생성
                            tts_file, subtitles = tts_generator.get_tts_with_timestamps(
                                st.session_state.script_content
                            )
                            
                            if not tts_file or not os.path.exists(tts_file):
                                raise Exception("TTS 파일 생성 실패")
                            
                            st.session_state.tts_file = tts_file
                            st.session_state.subtitles = subtitles
                            
                            video_progress_callback(f"TTS 생성 완료: {os.path.basename(tts_file)}", 25)
                            
                            # 2. 배경 비디오 준비
                            video_progress_callback("배경 비디오 준비 중...", 30)
                            
                            background_video_path = None
                            
                            if bg_video_option == "Pexels에서 검색":
                                try:
                                    # 키워드 처리 (한국어 키워드를 영어로 자동 변환)
                                    search_keyword = keyword
                                    if keyword and any(ord(char) > 127 for char in keyword):  # 한글 등 ASCII 아닌 문자 감지
                                        # OpenAI API를 통한 번역 시도
                                        try:
                                            openai_api_key = st.session_state.get("openai_api_key", "") or get_api_key("OPENAI_API_KEY")
                                            if openai_api_key and not st.session_state.is_offline_mode:
                                                try:
                                                    # 최신 OpenAI API 호출 방식 (v1.0.0+)
                                                    try:
                                                        # 신버전 방식 시도 (v1.0.0+)
                                                        from openai import OpenAI
                                                        client = OpenAI(api_key=openai_api_key)
                                                        response = client.chat.completions.create(
                                                            model="gpt-3.5-turbo",
                                                            messages=[
                                                                {"role": "system", "content": "Translate the following Korean keyword to English"},
                                                                {"role": "user", "content": f"Translate this keyword to English for video search: {keyword}"}
                                                            ],
                                                            max_tokens=50
                                                        )
                                                        english_keyword = response.choices[0].message.content.strip().strip('"\'')
                                                    except ImportError:
                                                        # 구버전 방식 사용 (v0.28.0)
                                                        import openai
                                                        openai.api_key = openai_api_key
                                                        response = openai.ChatCompletion.create(
                                                            model="gpt-3.5-turbo",
                                                            messages=[
                                                                {"role": "system", "content": "Translate the following Korean keyword to English"},
                                                                {"role": "user", "content": f"Translate this keyword to English for video search: {keyword}"}
                                                            ],
                                                            max_tokens=50
                                                        )
                                                        english_keyword = response.choices[0].message.content.strip().strip('"\'')
                                                    
                                                    video_progress_callback(f"번역된 키워드: '{keyword}' → '{english_keyword}'", 35)
                                                    search_keyword = english_keyword
                                                except Exception as e:
                                                    logger.warning(f"OpenAI API 번역 오류 상세: {e}")
                                                    # 변환 실패 시 기본 키워드 사용
                                                    search_keyword = "nature"
                                            else:
                                                # OpenAI API 없으면 기본 키워드 사용
                                                video_progress_callback("API 키 없이 한글 키워드 변환 불가, 기본 영어 키워드 사용", 35)
                                                search_keyword = "nature"
                                        except Exception as e:
                                            logger.warning(f"OpenAI API 번역 오류: {e}")
                                            # 변환 실패 시 기본 키워드 사용
                                            search_keyword = "nature"

                                    # TTS 오디오 파일의 길이 확인
                                    audio_duration = 10  # 기본값
                                    try:
                                        from moviepy.editor import AudioFileClip
                                        with AudioFileClip(st.session_state.tts_file) as audio_clip:
                                            audio_duration = audio_clip.duration
                                            video_progress_callback(f"오디오 파일 길이: {audio_duration:.2f}초", 38)
                                    except Exception as e:
                                        logger.warning(f"오디오 길이 확인 오류: {e}")
                                    
                                    # 여러 키워드로 검색 시도 (최적화: TTS 길이 기반으로 필요한 만큼만 다운로드)
                                    pexels_downloader = initialize_pexels_downloader()
                                    
                                    # 효율성 개선: 한 번에 비디오 모두 가져오기
                                    video_progress_callback(f"'{search_keyword}' 관련 배경 비디오 검색 중...", 40)
                                    
                                    # 비디오 목록 가져오기
                                    videos_info = pexels_downloader.get_multiple_background_videos(
                                        keyword=search_keyword,
                                        required_duration=audio_duration,  # TTS 길이 기반
                                        max_videos=3  # 최대 3개 비디오
                                    )
                                    
                                    if videos_info:
                                        # 다운로드된 비디오 경로 목록
                                        background_video_path = [info.get('path') for info in videos_info]
                                        st.session_state['video_info'] = videos_info  # 세션에 비디오 정보 저장
                                        video_progress_callback(f"{len(videos_info)}개 비디오 준비 완료", 50)
                                    else:
                                        # 비디오를 찾지 못하면 샘플 비디오 사용
                                        video_progress_callback("Pexels에서 비디오를 찾지 못함, 샘플 비디오 사용", 50)
                                        background_video_path = [
                                            os.path.join("SCUstreamlit", "background_videos", "sample_background.mp4")
                                        ]
                                except Exception as e:
                                    logger.error(f"Pexels 비디오 다운로드 오류: {e}")
                                    video_progress_callback(f"Pexels 비디오 다운로드 실패 - 그라데이션 배경으로 대체", 31)
                                    bg_video_option = "그라데이션 배경 생성"
                                    gradient_style = "랜덤"
                            elif bg_video_option == "직접 업로드":
                                # 이미 업로드된 배경 비디오 사용
                                if st.session_state.background_video:
                                    background_video_path = st.session_state.background_video
                                else:
                                    # 폴더에서 비디오 찾기
                                    bg_videos = []
                                    for file in os.listdir(BG_VIDEO_DIR):
                                        if file.lower().endswith(('.mp4', '.mov', '.avi')):
                                            bg_videos.append(os.path.join(BG_VIDEO_DIR, file))
                                    
                                    if bg_videos:
                                        background_video_path = random.choice(bg_videos)
                                        video_progress_callback(f"기존 배경 비디오 선택: {os.path.basename(background_video_path)}", 40)
                                    else:
                                        # 비디오가 없는 경우 그라데이션 배경으로 대체
                                        video_progress_callback(f"사용 가능한 배경 비디오 없음 - 그라데이션 배경으로 대체", 31)
                                        bg_video_option = "그라데이션 배경 생성"
                                        gradient_style = "랜덤"
                            elif bg_video_option == "그라데이션 배경 생성":
                                video_progress_callback(f"{gradient_style} 그라데이션 배경 생성 중...", 35)
                                # 그라데이션 배경 생성 로직
                                try:
                                    from moviepy.editor import ColorClip
                                    import numpy as np
                                    from PIL import Image
                                    
                                    # 비디오 크기 및 지속 시간 설정
                                    video_size = (1080, 1920)  # 쇼츠 크기 (세로형)
                                    duration = max(60, estimated_duration * 1.2)  # 비디오 길이 (초)
                                    
                                    # 그라데이션 색상 설정
                                    colors = {
                                        "블루": [(0, 0, 50), (0, 0, 255)],
                                        "레드": [(50, 0, 0), (255, 0, 0)],
                                        "그린": [(0, 50, 0), (0, 255, 0)],
                                        "퍼플": [(50, 0, 50), (200, 0, 255)],
                                        "오렌지": [(50, 20, 0), (255, 100, 0)],
                                        "레인보우": [(255, 0, 0), (0, 0, 255)]
                                    }
                                    
                                    # 랜덤 또는 선택된 색상
                                    if gradient_style == "랜덤" or gradient_style not in colors:
                                        color_key = random.choice(list(colors.keys()))
                                        color_pair = colors[color_key]
                                    else:
                                        color_pair = colors[gradient_style]
                                    
                                    # 그라데이션 이미지 생성
                                    gradient_img = Image.new('RGB', video_size)
                                    pixels = gradient_img.load()
                                    
                                    c1, c2 = color_pair
                                    for y in range(video_size[1]):
                                        # 수직 그라데이션
                                        r = int(c1[0] + (c2[0] - c1[0]) * y / video_size[1])
                                        g = int(c1[1] + (c2[1] - c1[1]) * y / video_size[1])
                                        b = int(c1[2] + (c2[2] - c1[2]) * y / video_size[1])
                                        
                                        for x in range(video_size[0]):
                                            pixels[x, y] = (r, g, b)
                                    
                                    # 임시 파일로 저장
                                    gradient_img_path = os.path.join(CACHE_DIR, f"gradient_{int(time.time())}.png")
                                    gradient_img.save(gradient_img_path)
                                    
                                    # 이미지를 비디오로 변환
                                    gradient_video_path = os.path.join(CACHE_DIR, f"gradient_{int(time.time())}.mp4")
                                    
                                    # ColorClip을 사용하여 비디오 생성
                                    clip = ColorClip(video_size, color=(0, 0, 0), duration=duration)
                                    
                                    def make_frame(t):
                                        return np.array(Image.open(gradient_img_path))
                                    
                                    clip = clip.set_make_frame(make_frame)
                                    clip.write_videofile(gradient_video_path, fps=30, codec='libx264')
                                    
                                    background_video_path = gradient_video_path
                                    video_progress_callback(f"그라데이션 배경 생성 완료", 40)
                                    
                                except Exception as e:
                                    logger.error(f"그라데이션 배경 생성 오류: {e}")
                                    video_progress_callback(f"그라데이션 배경 생성 실패 - 기본 배경 사용", 35)
                                    
                                    # 폴더에서 비디오 찾기 (대체 옵션)
                                    bg_videos = []
                                    for file in os.listdir(BG_VIDEO_DIR):
                                        if file.lower().endswith(('.mp4', '.mov', '.avi')):
                                            bg_videos.append(os.path.join(BG_VIDEO_DIR, file))
                                    
                                    if bg_videos:
                                        background_video_path = random.choice(bg_videos)
                                        video_progress_callback(f"기본 배경 비디오 선택: {os.path.basename(background_video_path)}", 40)
                            
                            elif bg_video_option == "랜덤 선택":
                                # 폴더에서 랜덤 비디오 선택 또는 Pexels에서 다운로드
                                bg_videos = []
                                for file in os.listdir(BG_VIDEO_DIR):
                                    if file.lower().endswith(('.mp4', '.mov', '.avi')):
                                        bg_videos.append(os.path.join(BG_VIDEO_DIR, file))
                                
                                if bg_videos:
                                    background_video_path = random.choice(bg_videos)
                                    video_progress_callback(f"배경 비디오 선택: {os.path.basename(background_video_path)}", 40)
                                else:
                                    # Pexels API 인스턴스 가져오기
                                    pexels_downloader = initialize_pexels_downloader()
                                    
                                    if pexels_downloader and not st.session_state.is_offline_mode:
                                        # 키워드 또는 기본값으로 검색
                                        search_keyword = keyword or "nature"
                                        background_video_path = pexels_downloader.get_background_video(
                                            search_keyword
                                        )
                                        video_progress_callback(f"Pexels에서 '{search_keyword}' 비디오 다운로드 완료", 40)
                                    else:
                                        # 오프라인 모드 또는 API 초기화 실패 시 그라데이션 배경 생성
                                        video_progress_callback("오프라인 모드 또는 API 초기화 실패 - 그라데이션 배경 생성", 31)
                                        bg_video_option = "그라데이션 배경 생성"
                                        gradient_style = "랜덤"
                                        # 재귀적 호출 방지를 위해 직접 처리
                                        try:
                                            from moviepy.editor import ColorClip
                                            import numpy as np
                                            from PIL import Image
                                            
                                            # 비디오 크기 및 지속 시간 설정
                                            video_size = (1080, 1920)  # 쇼츠 크기 (세로형)
                                            duration = max(60, estimated_duration * 1.2)  # 비디오 길이 (초)
                                            
                                            # 랜덤 색상 선택
                                            colors = [
                                                [(0, 0, 50), (0, 0, 255)],  # 블루
                                                [(50, 0, 0), (255, 0, 0)],  # 레드
                                                [(0, 50, 0), (0, 255, 0)],  # 그린
                                                [(50, 0, 50), (200, 0, 255)],  # 퍼플
                                                [(50, 20, 0), (255, 100, 0)]  # 오렌지
                                            ]
                                            color_pair = random.choice(colors)
                                            
                                            # 그라데이션 이미지 생성
                                            gradient_img = Image.new('RGB', video_size)
                                            pixels = gradient_img.load()
                                            
                                            c1, c2 = color_pair
                                            for y in range(video_size[1]):
                                                # 수직 그라데이션
                                                r = int(c1[0] + (c2[0] - c1[0]) * y / video_size[1])
                                                g = int(c1[1] + (c2[1] - c1[1]) * y / video_size[1])
                                                b = int(c1[2] + (c2[2] - c1[2]) * y / video_size[1])
                                                
                                                for x in range(video_size[0]):
                                                    pixels[x, y] = (r, g, b)
                                            
                                            # 임시 파일로 저장
                                            gradient_img_path = os.path.join(CACHE_DIR, f"gradient_{int(time.time())}.png")
                                            gradient_img.save(gradient_img_path)
                                            
                                            # 이미지를 비디오로 변환
                                            gradient_video_path = os.path.join(CACHE_DIR, f"gradient_{int(time.time())}.mp4")
                                            
                                            # ColorClip을 사용하여 비디오 생성
                                            clip = ColorClip(video_size, color=(0, 0, 0), duration=duration)
                                            
                                            def make_frame(t):
                                                return np.array(Image.open(gradient_img_path))
                                            
                                            clip = clip.set_make_frame(make_frame)
                                            clip.write_videofile(gradient_video_path, fps=30, codec='libx264')
                                            
                                            background_video_path = gradient_video_path
                                            video_progress_callback(f"그라데이션 배경 생성 완료", 40)
                                        except Exception as e:
                                            logger.error(f"그라데이션 배경 생성 오류: {e}")
                                            video_progress_callback(f"배경 비디오 생성 실패", 40)
                                            background_video_path = None
                            
                            # 배경 음악 설정
                            background_music_path = None
                            if use_background_music:
                                video_progress_callback("배경 음악 설정 중...", 45)
                                
                                if bg_music_source == "로컬 음악 파일":
                                    if background_music and background_music != "랜덤 선택":
                                        background_music_path = os.path.join(BG_MUSIC_DIR, background_music)
                                    else:
                                        # 랜덤 배경 음악 선택
                                        bg_music_files = []
                                        for file in os.listdir(BG_MUSIC_DIR):
                                            if file.lower().endswith(('.mp3', '.wav', '.m4a')):
                                                bg_music_files.append(os.path.join(BG_MUSIC_DIR, file))
                                        
                                        if bg_music_files:
                                            background_music_path = random.choice(bg_music_files)
                                            video_progress_callback(f"배경 음악 선택: {os.path.basename(background_music_path)}", 50)
                                else:
                                    # Jamendo API를 사용하여 키워드 기반 배경 음악 가져오기
                                    try:
                                        video_progress_callback("Jamendo API로 배경 음악 검색 중...", 45)
                                        # 인스턴스 초기화
                                        jamendo_provider = initialize_jamendo_provider()
                                        
                                        # 키워드 처리 (한국어 키워드를 영어로 자동 변환)
                                        search_keyword = keyword
                                        if keyword and any(ord(char) > 127 for char in keyword):  # 한글 등 ASCII 아닌 문자 감지
                                            # OpenAI API를 통한 번역 시도
                                            try:
                                                openai_api_key = st.session_state.get("openai_api_key", "") or get_api_key("OPENAI_API_KEY")
                                                if openai_api_key and not st.session_state.is_offline_mode:
                                                    # 최신 버전의 OpenAI 라이브러리에 맞게 클라이언트 초기화
                                                    try:
                                                        # 방법 1: 최신 OpenAI SDK (v1.x)
                                                        if hasattr(openai, 'OpenAI'):
                                                            client = openai.OpenAI(api_key=openai_api_key)
                                                            response = client.chat.completions.create(
                                                                model="gpt-3.5-turbo",
                                                                messages=[
                                                                    {"role": "system", "content": "You are a translator. Translate the given Korean keywords to English. Reply with only the translated words, comma separated."},
                                                                    {"role": "user", "content": keyword}
                                                                ],
                                                                max_tokens=50
                                                            )
                                                            translated = response.choices[0].message.content.strip()
                                                        # 방법 2: 구버전 방식의 API 호출
                                                        else:
                                                            openai.api_key = openai_api_key
                                                            response = openai.ChatCompletion.create(
                                                                model="gpt-3.5-turbo",
                                                                messages=[
                                                                    {"role": "system", "content": "You are a translator. Translate the given Korean keywords to English. Reply with only the translated words, comma separated."},
                                                                    {"role": "user", "content": keyword}
                                                                ],
                                                                max_tokens=50
                                                            )
                                                            translated = response.choices[0].message.content.strip()
                                                        
                                                        if translated:
                                                            video_progress_callback(f"음악 키워드 번역: {keyword} → {translated}", 46)
                                                            search_keyword = translated
                                                    except Exception as translate_error:
                                                        logger.warning(f"음악 키워드 번역 오류 (기본값 'calm' 사용): {translate_error}")
                                                        search_keyword = "calm"
                                            except Exception as e:
                                                logger.warning(f"음악 키워드 번역 오류 (기본값 'calm' 사용): {e}")
                                                search_keyword = "calm"
                                        
                                        # Jamendo API가 초기화되었는지 확인
                                        if jamendo_provider and not st.session_state.is_offline_mode:
                                            # 예상 비디오 길이 계산
                                            estimated_duration = len(st.session_state.script_content) / 3.5 if st.session_state.script_content else 30
                                            
                                            # 키워드 기반 배경 음악 가져오기
                                            background_music_path = jamendo_provider.get_music(
                                                keyword=search_keyword or "calm"
                                            )
                                            
                                            if background_music_path:
                                                video_progress_callback(f"Jamendo 배경 음악 선택: {os.path.basename(background_music_path)}", 50)
                                            else:
                                                video_progress_callback("Jamendo에서 음악을 찾지 못했습니다. 로컬 음악 사용", 46)
                                                # 오류 발생시 로컬 음악으로 대체
                                                raise Exception("Jamendo 음악 다운로드 실패")
                                        else:
                                            # 오프라인 모드 또는 API 초기화 실패
                                            video_progress_callback("오프라인 모드 또는 Jamendo API 초기화 실패 - 로컬 음악 사용", 46)
                                            raise Exception("Jamendo API 사용 불가")
                                    except Exception as e:
                                        logger.warning(f"Jamendo 음악 가져오기 오류: {e}")
                                        video_progress_callback("로컬 음악으로 대체합니다.", 47)
                                        
                                        # 대체: 폴더에서 랜덤 배경 음악 선택
                                        bg_music_files = []
                                        for file in os.listdir(BG_MUSIC_DIR):
                                            if file.lower().endswith(('.mp3', '.wav', '.m4a')):
                                                bg_music_files.append(os.path.join(BG_MUSIC_DIR, file))
                                        
                                        if bg_music_files:
                                            background_music_path = random.choice(bg_music_files)
                                            video_progress_callback(f"로컬 배경 음악 선택: {os.path.basename(background_music_path)}", 50)
                                        else:
                                            video_progress_callback("사용 가능한 배경 음악이 없습니다.", 50)
                            
                            # 3. 비디오 생성
                            video_progress_callback("비디오 생성 중...", 55)
                            
                            # 폰트 설정 추가 - 자막에 대한 추가 옵션 처리
                            subtitle_options = {}
                            if use_subtitles:
                                # 글꼴 크기 설정 (UI에서 사용자가 설정한 값 사용)
                                try:
                                    # 세션 상태에서 폰트 크기 가져오기 (가장 안정적인 방법)
                                    if 'font_size' in st.session_state:
                                        subtitle_options['font_size'] = st.session_state.font_size
                                        logging.info(f"자막 크기를 세션 상태 값 {st.session_state.font_size}로 설정합니다 (비디오 생성 시)")
                                    # 로컬 변수에서도 확인
                                    elif 'font_size' in locals() and font_size:
                                        subtitle_options['font_size'] = font_size
                                        logging.info(f"자막 크기를 로컬 변수 값 {font_size}로 설정합니다 (비디오 생성 시)")
                                    else:
                                        # 기본값 설정
                                        subtitle_options['font_size'] = 70  # 기본값
                                        logging.warning("font_size를 찾을 수 없어 기본값 70을 사용합니다.")
                                except Exception as e:
                                    logging.error(f"자막 크기 설정 중 오류: {e}")
                                    # 오류 발생시 기본값 설정
                                    subtitle_options['font_size'] = 70
                                
                                # 자막 언어 설정
                                if 'subtitle_lang' in locals():
                                    subtitle_options['language'] = subtitle_lang
                                
                                # 자막 위치 설정 (기본값: 하단)
                                if 'subtitle_position' in locals() and subtitle_position:
                                    # locals에서 UI에서 선택한 위치가 있는 경우
                                    subtitle_options['position'] = subtitle_position_values[subtitle_position]
                                else:
                                    # 기본값 설정
                                    subtitle_options['position'] = "bottom"
                                
                                # 폰트 자동 감지 옵션
                                if 'auto_detect_font' in locals() and auto_detect_font:
                                    subtitle_options['auto_detect_font'] = True
                                elif 'subtitle_font' in locals() and subtitle_font:
                                    subtitle_options['font'] = subtitle_font
                            
                            # 디버그 로그 추가 - create_video 호출 직전에 subtitle_options 내용 확인 (더 상세한 로그)
                            if use_subtitles and subtitle_options:
                                logging.info(f"비디오 생성 직전 자막 옵션 확인: font_size={subtitle_options.get('font_size')}, 자막 옵션 전체={subtitle_options}")
                            
                            # 비디오 생성기 초기화
                            video_creator = get_video_creator_with_ui_components(video_progress_callback)
                            
                            # 외부 API 서비스 설정
                            video_creator.setup_external_services(
                                pexels_api_key=st.session_state.get("pexels_api_key", ""),
                                jamendo_client_id=st.session_state.get("jamendo_client_id", "")
                            )
                            
                            # 매력적인 제목으로 출력 파일명 설정
                            output_title = generate_catchy_title(
                                content=st.session_state.script_content,
                                api_key=st.session_state.get("openai_api_key", "")
                            )
                            output_filename = f"{output_title}.mp4"
                            
                            # 비디오 스타일 로깅
                            if 'video_style' in locals():
                                logging.info(f"선택된 비디오 스타일: {video_style}")
                            
                            # 비디오 스타일에 따라 다른 처리
                            if 'video_style' in locals() and video_style == "삼분할 템플릿 스타일":
                                video_progress_callback("삼분할 템플릿 비디오 생성 중...", 60)
                                
                                # 먼저 일반 비디오 생성 (임시 파일)
                                temp_filename = f"temp_{int(time.time())}.mp4"
                                temp_video_path = video_creator.create_video(
                                    script_content=st.session_state.script_content,
                                    audio_path=st.session_state.tts_file,
                                    keyword=keyword,
                                    background_video_path=background_video_path,
                                    output_filename=temp_filename,
                                    subtitles=st.session_state.subtitles if use_subtitles else None,
                                    background_music_path=background_music_path,
                                    background_music_volume=background_music_volume if use_background_music else 0,
                                    subtitle_options=subtitle_options if use_subtitles else None,
                                    max_duration=video_duration
                                )
                                
                                if not temp_video_path or not os.path.exists(temp_video_path):
                                    raise Exception("임시 비디오 생성 실패")
                                
                                video_progress_callback("템플릿 형식 적용 중...", 80)
                                
                                # 스크립트 내용 한 줄 요약 생성
                                if not hasattr(st.session_state, 'script_summary') or not st.session_state.script_summary:
                                    try:
                                        # 스크립트 내용에서 첫 문장이나 중요 부분 추출하여 요약 생성
                                        script_content = st.session_state.script_content
                                        
                                        # 문장 분리
                                        sentences = script_content.split('.')
                                        if sentences and len(sentences) > 0:
                                            # 첫 문장이 의미 있는 길이인 경우 사용
                                            first_sentence = sentences[0].strip()
                                            if len(first_sentence) > 10:
                                                if len(first_sentence) > 70:
                                                    summary = first_sentence[:67] + "..."
                                                else:
                                                    summary = first_sentence
                                                
                                                # 세션 상태에 저장
                                                st.session_state.script_summary = summary
                                            else:
                                                # 첫 문장이 너무 짧으면 앞 부분 사용
                                                summary = script_content[:70].strip()
                                                if len(script_content) > 70:
                                                    summary += "..."
                                                st.session_state.script_summary = summary
                                        else:
                                            # 문장 분리가 어려우면 앞 부분만 사용
                                            summary = script_content[:70].strip()
                                            if len(script_content) > 70:
                                                summary += "..."
                                            st.session_state.script_summary = summary
                                    except Exception as e:
                                        logger.warning(f"스크립트 요약 생성 실패: {e}")
                                        # 실패 시 기본 앞부분 사용
                                        st.session_state.script_summary = st.session_state.script_content[:100] + ("..." if len(st.session_state.script_content) > 100 else "")
                                
                                # 삼분할 템플릿 적용
                                video_path = video_creator.create_template_video(
                                    video_path=temp_video_path,
                                    title=output_title,
                                    subtitle_text=st.session_state.script_content[:100] + ("..." if len(st.session_state.script_content) > 100 else ""),
                                    output_filename=output_filename,
                                    description=st.session_state.script_summary if hasattr(st.session_state, 'script_summary') and st.session_state.script_summary else st.session_state.script_content[:150] + ("..." if len(st.session_state.script_content) > 150 else "")
                                )
                                
                                # 임시 파일 삭제
                                try:
                                    if os.path.exists(temp_video_path):
                                        os.remove(temp_video_path)
                                except Exception as e:
                                    logger.warning(f"임시 파일 삭제 실패: {e}")
                                
                            else:
                                # 기본 비디오 생성
                                video_path = video_creator.create_video(
                                    script_content=st.session_state.script_content,
                                    audio_path=st.session_state.tts_file,
                                    keyword=keyword,
                                    background_video_path=background_video_path,
                                    output_filename=output_filename,
                                    subtitles=st.session_state.subtitles if use_subtitles else None,
                                    background_music_path=background_music_path,
                                    background_music_volume=background_music_volume if use_background_music else 0,
                                    subtitle_options=subtitle_options if use_subtitles else None,
                                    max_duration=video_duration
                                )
                            
                            if not video_path or not os.path.exists(video_path):
                                raise Exception("비디오 생성 실패")
                            
                            st.session_state.generated_video = video_path
                            
                            # 로그 업데이트
                            log_entry["비디오 제목"] = os.path.basename(video_path).replace(".mp4", "")
                            log_entry["상태"] = "생성 완료"
                            
                            video_progress_callback("비디오 생성 완료!", 100)
                            st.markdown(f'<div class="success-box">✅ 비디오 생성 완료! 파일명: {os.path.basename(video_path)}</div>', unsafe_allow_html=True)
                            
                            # 스크립트가 자동으로 조절되었는지 확인하고 알림
                            if hasattr(st.session_state, 'original_script') and st.session_state.original_script != st.session_state.script_content:
                                st.markdown(f'<div class="info-box">ℹ️ 스크립트가 최대 비디오 길이({video_duration}초)에 맞게 자동으로 조절되었습니다.</div>', unsafe_allow_html=True)
                                
                                # 원본 스크립트 보기 옵션
                                if st.checkbox("원본 스크립트 보기"):
                                    st.text_area("원본 스크립트:", value=st.session_state.original_script, height=200, disabled=True)
                                    # 원본과 조절된 스크립트 길이 비교
                                    original_duration = estimate_speech_duration(st.session_state.original_script)
                                    adjusted_duration = estimate_speech_duration(st.session_state.script_content)
                                    st.markdown(f"**원본 스크립트 예상 시간:** {original_duration:.1f}초")
                                    st.markdown(f"**조절된 스크립트 예상 시간:** {adjusted_duration:.1f}초")
                            
                            # 키워드 자동 생성 및 저장
                            try:
                                # 키워드 생성
                                generated_keywords = generate_keywords_from_content(
                                    content=st.session_state.script_content,
                                    api_key=st.session_state.get("openai_api_key", "")
                                )
                                
                                if generated_keywords:
                                    # 세션 상태에 키워드 저장
                                    st.session_state.generated_keywords = generated_keywords
                                    # 쉼표로 구분된 문자열로 변환하여 저장
                                    st.session_state.generated_tags = ", ".join(generated_keywords)
                                    logger.info(f"키워드 자동 생성 완료: {st.session_state.generated_tags}")
                            except Exception as e:
                                logger.warning(f"키워드 자동 생성 실패: {str(e)}")
                            
                            # 자동 업로드 옵션 선택 시
                            if auto_upload:
                                video_progress_callback("YouTube 업로드 준비 중...", 5)
                                st.markdown("자동 업로드 기능이 선택되었습니다. '업로드 설정' 탭으로 이동하여 정보를 입력해주세요.")
                            
                            # 비디오 미리보기 탭으로 전환
                            st.write("'비디오 미리보기' 탭에서 생성된 비디오를 확인할 수 있습니다.")
                            
                        except Exception as e:
                            error_msg = f"비디오 생성 중 오류 발생: {str(e)}"
                            video_progress_callback(error_msg, 100)
                            st.markdown(f'<div class="error-box">❌ {error_msg}</div>', unsafe_allow_html=True)
                            
                            # 로그 업데이트
                            log_entry["상태"] = f"오류 발생: {str(e)}"
                        
                        # 로그 저장
                        st.session_state.video_logs.insert(0, log_entry)
                        
                        # 로그 파일에 저장
                        log_file = os.path.join(LOG_DIR, "video_creation_log.json")
                        try:
                            # 기존 로그 불러오기
                            existing_logs = []
                            if os.path.exists(log_file):
                                with open(log_file, 'r', encoding='utf-8') as f:
                                    existing_logs = json.load(f)
                            
                            # 새 로그 추가
                            existing_logs.insert(0, log_entry)
                            
                            # 로그 파일 저장
                            with open(log_file, 'w', encoding='utf-8') as f:
                                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            logger.error(f"로그 저장 오류: {e}")
                else:
                    st.markdown('<div class="error-box">⚠️ 콘텐츠가 비어 있습니다. 비디오를 생성하려면 콘텐츠가 필요합니다.</div>', unsafe_allow_html=True)

    # 탭 2: 비디오 미리보기
    with tab2:
        st.markdown('<div class="sub-header">비디오 미리보기</div>', unsafe_allow_html=True)
        
        if st.session_state.generated_video and os.path.exists(st.session_state.generated_video):
            # 비디오 파일 경로
            video_path = st.session_state.generated_video
            
            # 비디오 표시
            st.video(video_path)
            
            # 비디오 정보 표시
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # 비디오 파일명
                st.markdown(f"**파일명:** {os.path.basename(video_path)}")
            
            with col2:
                # 비디오 크기
                video_size = os.path.getsize(video_path) / (1024 * 1024)  # MB 단위
                st.markdown(f"**파일 크기:** {video_size:.2f} MB")
                
            with col3:
                # 생성 시간
                created_time = datetime.fromtimestamp(os.path.getctime(video_path))
                st.markdown(f"**생성 시간:** {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 비디오 다운로드 및 편집 버튼
            col1, col2 = st.columns(2)
            
            with col1:
                # 비디오 다운로드 버튼 
                with open(video_path, "rb") as file:
                    video_bytes = file.read()
                
                btn = st.download_button(
                    label="비디오 다운로드",
                    data=video_bytes,
                    file_name=os.path.basename(video_path),
                    mime="video/mp4",
                    key="download_video_btn"
                )
            
            with col2:
                # YouTube 업로드 바로가기 버튼
                if st.button("YouTube 업로드 설정으로 이동"):
                    st.markdown("'업로드 설정' 탭으로 이동하여 업로드 정보를 입력하세요.")
                    # 참고: Streamlit에서는 직접 탭 전환 API가 없어 사용자에게 안내만 제공
            
            # 비디오 상세 정보
            with st.expander("비디오 상세 정보", expanded=False):
                # TTS 파일 정보
                if st.session_state.tts_file and os.path.exists(st.session_state.tts_file):
                    st.markdown(f"**TTS 파일:** {os.path.basename(st.session_state.tts_file)}")
                
                # 자막 정보
                if st.session_state.subtitles:
                    st.markdown(f"**자막 개수:** {len(st.session_state.subtitles)}")
                    
                    # 자막 미리보기
                    st.markdown("**자막 미리보기:**")
                    for i, subtitle in enumerate(st.session_state.subtitles[:5]):  # 앞의 5개만 표시
                        start = subtitle.get('start_time', 0)
                        end = subtitle.get('end_time', 0)
                        text = subtitle.get('text', '')
                        st.markdown(f"{i+1}. [{start:.1f}s - {end:.1f}s] {text}")
                    
                    if len(st.session_state.subtitles) > 5:
                        st.markdown(f"... 외 {len(st.session_state.subtitles) - 5}개")
                
                # 스크립트 내용
                if st.session_state.script_content:
                    st.markdown("**스크립트 내용:**")
                    st.text_area("스크립트", value=st.session_state.script_content, height=150, disabled=True, key="detail_script_content")
        else:
            st.markdown("생성된 비디오가 없습니다. '콘텐츠 생성' 탭에서 먼저 비디오를 생성해주세요.")
            
            # 배경 비디오 업로드 기능
            st.markdown("### 배경 비디오 업로드")
            st.markdown("아래에서 직접 배경 비디오를 업로드할 수 있습니다. 업로드된 비디오는 다음 비디오 생성 시 사용할 수 있습니다.")
            
            uploaded_bg_video = st.file_uploader("배경 비디오 파일", type=["mp4"], label_visibility="visible", key="bg_video_uploader")
            
            if uploaded_bg_video is not None:
                # 업로드 파일 저장
                video_path = os.path.join(BG_VIDEO_DIR, uploaded_bg_video.name)
                with open(video_path, "wb") as f:
                    f.write(uploaded_bg_video.getbuffer())
                
                st.session_state.background_video = video_path
                st.markdown(f'<div class="success-box">✅ 배경 비디오 업로드 완료: {uploaded_bg_video.name}</div>', unsafe_allow_html=True)
                st.markdown("이제 '콘텐츠 생성' 탭에서 배경 비디오 소스를 '직접 업로드'로 선택하여 사용할 수 있습니다.")

    # 탭 3: 업로드 설정
    with tab3:
        st.markdown('<div class="sub-header">YouTube 업로드 설정</div>', unsafe_allow_html=True)
        
        # YouTube API 인증 상태 확인
        youtube_uploader = YouTubeUploader(progress_callback=update_progress)
        is_authenticated = False
        
        if os.path.exists(youtube_uploader.credentials_file):
            st.markdown('<div class="success-box">YouTube API 인증 파일이 있습니다.</div>', unsafe_allow_html=True)
            is_authenticated = True
        else:
            st.markdown('<div class="warning-box">YouTube API 인증이 필요합니다.</div>', unsafe_allow_html=True)
            
            # 인증 안내
            st.markdown("""
            ### YouTube API 인증 방법
            
            1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성하세요.
            2. YouTube Data API v3를 사용 설정하세요.
            3. OAuth 클라이언트 ID를 생성하고 클라이언트 시크릿 JSON 파일을 다운로드하세요.
            4. 다운로드한 파일을 `client_secret.json`으로 이름을 바꾸고 앱 폴더에 저장하세요.
            5. 아래 버튼을 클릭하여 인증 과정을 시작하세요.
            """)
            
            # 인증 버튼
            if st.button("YouTube API 인증 시작"):
                with st.spinner("인증 진행 중..."):
                    try:
                        is_authenticated = youtube_uploader.initialize_api()
                        if is_authenticated:
                            st.markdown('<div class="success-box">YouTube API 인증 성공!</div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div class="error-box">YouTube API 인증 실패. 위 안내에 따라 클라이언트 시크릿 파일을 설정해주세요.</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.markdown(f'<div class="error-box">인증 오류: {str(e)}</div>', unsafe_allow_html=True)
        
        # 업로드 정보 입력
        if st.session_state.generated_video and os.path.exists(st.session_state.generated_video):
            st.markdown("### 비디오 정보 설정")
            
            # 비디오 파일명
            st.markdown(f"**업로드할 비디오:** {os.path.basename(st.session_state.generated_video)}")
            
            # 기본 비디오 제목과 설명
            default_title = ""
            default_description = ""
            
            # 비디오 파일이 있는 경우 자동으로 정보 가져오기
            if st.session_state.generated_video and os.path.exists(st.session_state.generated_video):
                # 비디오 파일 이름에서 제목 추출 (확장자 제외)
                video_filename = os.path.basename(st.session_state.generated_video)
                default_title = os.path.splitext(video_filename)[0]
                
                # 스크립트 내용이 있으면 설명에 추가
                if st.session_state.script_content:
                    # 설명에는 내용 일부와 자동 태그 추가
                    summary = st.session_state.script_content[:200] + "..." if len(st.session_state.script_content) > 200 else st.session_state.script_content
                    default_description = f"{summary}\n\n#Shorts"
            
            # 비디오 제목
            video_title = st.text_input(
                "비디오 제목:",
                value=default_title,
                help="YouTube에 표시될 비디오 제목을 입력하세요."
            )
            
            video_description = st.text_area("비디오 설명:", 
                                           placeholder="비디오에 대한 설명을 입력하세요",
                                           height=150,
                                           value=default_description)
            
            # 태그 입력 - 자동 생성된 키워드가 있으면 사용
            default_tags = ""
            if hasattr(st.session_state, 'generated_tags') and st.session_state.generated_tags:
                default_tags = st.session_state.generated_tags
                
            video_tags = st.text_input("태그 (쉼표로 구분):", 
                                      placeholder="태그1, 태그2, 태그3",
                                      value=default_tags,
                                      help="자동으로 생성된 키워드가 입력되어 있습니다. 필요한 경우 수정하세요.")
            
            # 카테고리 매핑 (YouTube API는 카테고리 ID 사용)
            category_mapping = {
                "영화 및 애니메이션": "1",
                "자동차 및 차량": "2",
                "음악": "10",
                "애완동물 및 동물": "15",
                "스포츠": "17",
                "여행 및 이벤트": "19",
                "게임": "20",
                "인물 및 블로그": "22",
                "코미디": "23",
                "엔터테인먼트": "24",
                "뉴스 및 정치": "25",
                "노하우 및 스타일": "26",
                "교육": "27",
                "과학 및 기술": "28"
            }
            
            # 카테고리 선택
            video_category_name = st.selectbox(
                "카테고리:",
                list(category_mapping.keys()),
                index=6  # 기본값: 인물 및 블로그
            )
            video_category = category_mapping.get(video_category_name, "22")  # 기본값: 인물 및 블로그
            
            # 공개 상태 선택
            privacy_mapping = {
                "공개": "public",
                "비공개": "private",
                "일부공개": "unlisted"
            }
            
            privacy_status_name = st.radio(
                "공개 상태:",
                list(privacy_mapping.keys()),
                index=1  # 기본값: 비공개
            )
            privacy_status = privacy_mapping.get(privacy_status_name, "private")
            
            # Shorts 관련 설정
            is_shorts = st.checkbox("YouTube Shorts로 업로드 (#Shorts 태그 자동 추가)", value=True)
            notify_subscribers = st.checkbox("구독자에게 알림", value=True)
            
            # 썸네일 설정
            st.markdown("### 썸네일 설정")
            
            # 썸네일 생성 옵션
            thumbnail_option = st.radio(
                "썸네일 옵션:",
                ["자동 생성", "직접 업로드"],
                index=0
            )
            
            thumbnail_path = None
            
            if thumbnail_option == "자동 생성":
                if st.button("썸네일 자동 생성", key="generate_thumbnail"):
                    with st.spinner("썸네일 생성 중..."):
                        try:
                            # 키워드 추출 (제목에서 첫 단어만 사용)
                            keyword = video_title.split()[0] if video_title else "Shorts"
                            
                            # 썸네일 생성기 초기화
                            thumbnail_generator = ThumbnailGenerator(
                                output_dir=THUMBNAIL_DIR,
                                progress_callback=update_progress
                            )
                            
                            # 스크립트 내용이 있으면 스타일 분석하여 썸네일 생성
                            if st.session_state.script_content:
                                thumbnail_path = thumbnail_generator.generate_thumbnail(
                                    keyword, st.session_state.script_content
                                )
                            else:
                                # 스크립트가 없으면 기본 썸네일 생성
                                thumbnail_path = thumbnail_generator.create_default_thumbnail(keyword)
                            
                            if thumbnail_path and os.path.exists(thumbnail_path):
                                st.session_state.thumbnail_path = thumbnail_path
                                st.markdown(f'<div class="success-box">✅ 썸네일 생성 완료!</div>', unsafe_allow_html=True)
                                
                                # 썸네일 이미지 표시
                                image = Image.open(thumbnail_path)
                                st.image(image, caption=f"생성된 썸네일: {os.path.basename(thumbnail_path)}")
                            else:
                                st.markdown('<div class="error-box">❌ 썸네일 생성 실패</div>', unsafe_allow_html=True)
                        except Exception as e:
                            st.markdown(f'<div class="error-box">❌ 썸네일 생성 오류: {str(e)}</div>', unsafe_allow_html=True)
                            logger.error(f"썸네일 생성 중 오류 발생: {str(e)}")
                
                # 이전에 생성된 썸네일 표시
                if hasattr(st.session_state, 'thumbnail_path') and os.path.exists(st.session_state.thumbnail_path):
                    image = Image.open(st.session_state.thumbnail_path)
                    st.image(image, caption=f"현재 썸네일: {os.path.basename(st.session_state.thumbnail_path)}")
                    thumbnail_path = st.session_state.thumbnail_path
            
            else:  # 직접 업로드
                uploaded_thumbnail = st.file_uploader("썸네일 이미지 업로드 (JPG, PNG)", type=["jpg", "jpeg", "png"])
                
                if uploaded_thumbnail is not None:
                    # 업로드 파일 저장
                    thumbnail_filename = f"thumbnail_{int(time.time())}.jpg"
                    thumbnail_path = os.path.join(THUMBNAIL_DIR, thumbnail_filename)
                    
                    with open(thumbnail_path, "wb") as f:
                        f.write(uploaded_thumbnail.getbuffer())
                    
                    st.session_state.thumbnail_path = thumbnail_path
                    st.markdown(f'<div class="success-box">✅ 썸네일 업로드 완료: {thumbnail_filename}</div>', unsafe_allow_html=True)
                    
                    # 썸네일 이미지 표시
                    image = Image.open(thumbnail_path)
                    st.image(image, caption=f"업로드된 썸네일: {thumbnail_filename}")
            
            # 업로드 버튼
            if st.button("YouTube에 업로드", key="upload_to_youtube", use_container_width=True):
                if video_title and video_description:
                    with st.spinner("YouTube에 업로드 중..."):
                        # 로그 기록
                        log_entry = {
                            "생성 시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "비디오 제목": video_title,
                            "상태": "업로드 중",
                            "URL": ""
                        }
                        
                        # 진행 상황 표시 UI 요소
                        upload_progress_bar = st.progress(0)
                        upload_status_text = st.empty()
                        
                        # 진행 단계 추적을 위한 세션 상태 초기화 
                        st.session_state.progress_phase = []
                        
                        def upload_progress_callback(message, progress=None):
                            """업로드 진행 상황 콜백"""
                            # session_state 확인 및 초기화
                            if 'progress_phase' not in st.session_state:
                                st.session_state.progress_phase = []
                                
                            # 진행률 막대 업데이트 (있는 경우)
                            if progress is not None:
                                upload_progress_bar.progress(progress / 100)
                            
                            # 메시지 처리 (빈 문자열 체크 전에 None 체크 필요)
                            if message is None:
                                # 메시지 없이 진행률만 있는 경우 처리
                                if progress is not None and st.session_state.progress_phase:
                                    phases_display = " → ".join(st.session_state.progress_phase)
                                    upload_status_text.markdown(f"**진행 상황**: {phases_display} ({progress}%)")
                                return
                                
                            # 빈 메시지는 진행률만 업데이트
                            if message == "":
                                if progress is not None and st.session_state.progress_phase:
                                    phases_display = " → ".join(st.session_state.progress_phase)
                                    upload_status_text.markdown(f"**진행 상황**: {phases_display} ({progress}%)")
                                return
                            
                            # 특수 메시지 처리
                            if message == "__PROGRESS_UPDATE_ONLY__":
                                if progress is not None and st.session_state.progress_phase:
                                    phases_display = " → ".join(st.session_state.progress_phase)
                                    upload_status_text.markdown(f"**진행 상황**: {phases_display} ({progress}%)")
                                return
                            
                            # 단계 키워드 매핑
                            phase_keywords = {
                                "인증 시작": "인증",
                                "인증 정보": "인증",
                                "인증 토큰": "인증",
                                "클라이언트 생성": "초기화", 
                                "인증 상태": "초기화",
                                "인증 성공": "인증완료",
                                "업로드 준비": "준비",
                                "비디오 파일 업로드": "요청",
                                "YouTube에 업로드 중": "업로드"
                            }
                            
                            # 단계 업데이트
                            for keyword, phase in phase_keywords.items():
                                if keyword in message:
                                    if phase not in st.session_state.progress_phase:
                                        st.session_state.progress_phase.append(phase)
                                    break
                                    
                            # 진행 단계 표시
                            if st.session_state.progress_phase:
                                phases_display = " → ".join(st.session_state.progress_phase)
                                if progress is not None:
                                    upload_status_text.markdown(f"**진행 상황**: {phases_display} ({progress}%)")
                                else:
                                    upload_status_text.markdown(f"**진행 상황**: {phases_display}")
                            else:
                                # 단계 정보가 없는 경우 메시지 그대로 표시
                                upload_status_text.markdown(message)
                        
                        try:
                            # YouTube 인증 확인
                            if not is_authenticated:
                                is_authenticated = youtube_uploader.initialize_api()
                                if not is_authenticated:
                                    upload_progress_callback("YouTube API 인증이 필요합니다. 아래 안내에 따라 수동 인증을 진행해주세요.", 0)
                                    
                                    # 사용자에게 인증 안내 제공
                                    st.markdown("""
                                    ## YouTube API 인증이 필요합니다.
                                    
                                    1. 명령 프롬프트/터미널에서:
                                       - 작업 디렉토리로 이동: `cd 경로/SCUstreamlit`
                                       - 다음 명령어 실행: `python youtube_auth_helper.py`
                                    
                                    2. 브라우저가 열리면 Google 계정으로 로그인하고 권한을 허용해주세요.
                                    
                                    3. 인증이 완료되면 자동으로 youtube_credentials.json 파일이 생성됩니다.
                                    
                                    4. 인증 후 이 앱을 새로고침하고 다시 시도해주세요.
                                    """, unsafe_allow_html=True)
                                    
                                    # 로그 업데이트
                                    log_entry["상태"] = "인증 필요"
                                    st.session_state.video_logs.insert(0, log_entry)
                                    
                                    # 인증 안내 후 업로드 중단
                                    raise Exception("YouTube API 인증이 필요합니다. 위 안내에 따라 인증을 진행한 후 다시 시도해주세요.")
                            
                            upload_progress_callback("YouTube에 업로드 준비 중...", 10)
                            
                            # 태그 처리
                            tags_list = [tag.strip() for tag in video_tags.split(',') if tag.strip()]
                            
                            # Shorts 태그 추가
                            if is_shorts and "#Shorts" not in tags_list:
                                tags_list.append("#Shorts")
                            
                            # 업로드 전 썸네일 경로 확인
                            final_thumbnail_path = None
                            try:
                                if hasattr(st.session_state, 'thumbnail_path') and os.path.exists(st.session_state.thumbnail_path):
                                    final_thumbnail_path = st.session_state.thumbnail_path
                            except Exception as e:
                                upload_progress_callback(f"썸네일 경로 확인 중 오류: {str(e)}", 10)
                                logger.error(f"썸네일 경로 확인 오류: {e}")
                            
                            # 비디오 업로드
                            upload_progress_callback("비디오 파일 업로드 중...", 20)
                            try:
                                video_id = youtube_uploader.upload_video(
                                    video_file=st.session_state.generated_video,
                                    title=video_title,
                                    description=video_description,
                                    tags=tags_list,
                                    category=video_category,
                                    privacy_status=privacy_status,
                                    is_shorts=is_shorts,
                                    notify_subscribers=notify_subscribers,
                                    thumbnail=final_thumbnail_path
                                )
                            except Exception as upload_error:
                                # 업로드 중 오류 발생시 처리
                                logger.error(f"업로드 함수 호출 오류: {upload_error}")
                                upload_progress_callback(f"업로드 함수 호출 오류: {str(upload_error)}", 100)
                                st.session_state.progress_phase = ["인증", "초기화", "준비", "오류"]
                                phases_display = " → ".join(st.session_state.progress_phase)
                                upload_status_text.markdown(f"**진행 상황**: {phases_display} (실패)")
                                st.markdown(f'<div class="error-box">❌ 업로드 오류: {str(upload_error)}</div>', unsafe_allow_html=True)
                                log_entry["상태"] = f"업로드 실패: {str(upload_error)}"
                                st.session_state.video_logs.insert(0, log_entry)
                                time.sleep(1)
                                st.session_state.progress_phase = []
                                # return 문 제거하고 video_id를 None으로 설정
                                video_id = None
                            if video_id:
                                video_url = f"https://youtu.be/{video_id}"
                                upload_progress_callback(f"✅ 업로드 완료! 비디오 URL: {video_url}", 100)
                                st.session_state.progress_phase = ["인증", "초기화", "준비", "요청", "업로드", "완료"]
                                phases_display = " → ".join(st.session_state.progress_phase)
                                upload_status_text.markdown(f"**진행 상황**: {phases_display} (100%)")
                                st.markdown(f'<div class="success-box">✅ YouTube 업로드 완료!</div>', unsafe_allow_html=True)
                                st.markdown(f"[비디오 확인하기]({video_url})")
                                
                                # 로그 업데이트
                                log_entry["상태"] = "업로드 완료"
                                log_entry["URL"] = video_url
                                
                                # 진행 단계 초기화 (처리 완료 후)
                                time.sleep(1)
                                st.session_state.progress_phase = []
                            else:
                                # 진행 단계 초기화
                                st.session_state.progress_phase = ["인증", "초기화", "준비", "오류"]
                                phases_display = " → ".join(st.session_state.progress_phase)
                                upload_status_text.markdown(f"**진행 상황**: {phases_display} (실패)")
                                st.session_state.progress_phase = []
                                raise Exception("업로드 중 오류가 발생했습니다. 로그를 확인하세요.")
                        
                        except Exception as e:
                            # 진행 단계 표시 및 초기화
                            if not st.session_state.progress_phase or "오류" not in st.session_state.progress_phase:
                                st.session_state.progress_phase.append("오류")
                            phases_display = " → ".join(st.session_state.progress_phase)
                            upload_status_text.markdown(f"**진행 상황**: {phases_display} (실패)")
                            
                            # 진행 단계 초기화
                            time.sleep(1)
                            st.session_state.progress_phase = []
                            
                            error_msg = f"업로드 오류: {str(e)}"
                            upload_progress_callback(error_msg, 100)
                            st.markdown(f'<div class="error-box">❌ {error_msg}</div>', unsafe_allow_html=True)
                            
                            # 로그 업데이트
                            log_entry["상태"] = f"업로드 실패: {str(e)}"
                        
                        # 로그 저장
                        st.session_state.video_logs.insert(0, log_entry)
                        
                        # 로그 파일에 저장
                        log_file = os.path.join(LOG_DIR, "video_creation_log.json")
                        try:
                            # 기존 로그 불러오기
                            existing_logs = []
                            if os.path.exists(log_file):
                                with open(log_file, 'r', encoding='utf-8') as f:
                                    existing_logs = json.load(f)
                            
                            # 새 로그 추가
                            existing_logs.insert(0, log_entry)
                            
                            # 로그 파일 저장
                            with open(log_file, 'w', encoding='utf-8') as f:
                                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            logger.error(f"로그 저장 오류: {e}")
                else:
                    st.markdown('<div class="error-box">⚠️ 제목과 설명은 필수 항목입니다.</div>', unsafe_allow_html=True)
            else:
                st.markdown("생성된 비디오가 없습니다. '콘텐츠 생성' 탭에서 먼저 비디오를 생성해주세요.")

    # 탭 4: 로그 및 기록
    with tab4:
        st.markdown('<div class="sub-header">로그 및 생성 기록</div>', unsafe_allow_html=True)
        
        # 로그 파일 로드
        log_file = os.path.join(LOG_DIR, "video_creation_log.json")
        log_data = []
        
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            except Exception as e:
                st.error(f"로그 파일 로드 오류: {e}")
        
        # 세션 로그가 있으면 추가
        if st.session_state.video_logs:
            # 중복 제거 (같은 생성 시간 항목)
            session_times = [log.get("생성 시간") for log in st.session_state.video_logs]
            log_data = [log for log in log_data if log.get("생성 시간") not in session_times]
            log_data = st.session_state.video_logs + log_data
        
        if log_data:
            st.markdown("### 최근 생성 기록")
            
            # 데이터프레임 변환
            df = pd.DataFrame(log_data)
            
            # 컬럼 정렬
            columns = ["생성 시간", "비디오 제목", "키워드", "상태", "URL"]
            df = df.reindex(columns=[col for col in columns if col in df.columns])
            
            # URL이 있는 경우 클릭 가능한 링크로 변환
            if "URL" in df.columns:
                df["URL"] = df["URL"].apply(lambda x: f'[보기]({x})' if x and x.startswith('http') else x)
            
            # 데이터프레임 표시
            st.dataframe(df, use_container_width=True)
            
            # 로그 파일 다운로드 버튼
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="CSV 파일로 다운로드",
                data=csv,
                file_name="video_creation_log.csv",
                mime="text/csv",
            )
        else:
            st.markdown("아직 생성된 비디오 기록이 없습니다.")
        
        # 시스템 정보 표시
        st.markdown("### 시스템 정보")
        
        # 시스템 정보 수집
        try:
            import platform
            import psutil
            import moviepy
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**시스템 정보:**")
                st.markdown(f"- 운영체제: {platform.system()} {platform.release()}")
                st.markdown(f"- Python 버전: {platform.python_version()}")
                st.markdown(f"- CPU 코어: {psutil.cpu_count(logical=True)}")
                
                # 메모리 정보
                mem = psutil.virtual_memory()
                mem_gb = mem.total / (1024 ** 3)
                st.markdown(f"- 메모리: {mem_gb:.2f} GB")
                
            with col2:
                st.markdown("**앱 상태:**")
                st.markdown(f"- 오프라인 모드: {'켜짐' if st.session_state.is_offline_mode else '꺼짐'}")
                st.markdown(f"- Moviepy 버전: {moviepy.__version__}")
                
                # Tensorflow 정보
                try:
                    import tensorflow as tf
                    st.markdown(f"- TensorFlow 버전: {tf.__version__}")
                    tf_gpu = tf.config.list_physical_devices('GPU')
                    st.markdown(f"- GPU 가용성: {'지원' if tf_gpu else '미지원'}")
                except ImportError:
                    st.markdown("- TensorFlow: 설치되지 않음")
                
                # 디스크 정보
                disk = psutil.disk_usage('/')
                disk_gb = disk.total / (1024 ** 3)
                disk_free = disk.free / (1024 ** 3)
                st.markdown(f"- 디스크: {disk_free:.2f} GB 여유 / {disk_gb:.2f} GB")
        except ImportError:
            st.info("시스템 정보를 표시하려면 `pip install psutil` 명령으로 라이브러리를 설치하세요.")
            st.markdown("- 운영체제: " + platform.system() + " " + platform.release())
            st.markdown("- Python 버전: " + platform.python_version())
        
        # 시스템 로그 표시
        st.markdown("### 시스템 로그")
        
        # 로그 파일 목록
        log_files = []
        for file in os.listdir(LOG_DIR):
            if file.endswith('.log'):
                log_files.append(file)
        
        # 선택된 로그 파일
        selected_log = "streamlit_app.log"
        if log_files:
            selected_log = st.selectbox("로그 파일 선택", log_files)
        
        # 로그 내용 표시
        log_path = os.path.join(LOG_DIR, selected_log)
        if os.path.exists(log_path):
            try:
                # 마지막 50줄만 표시
                with open(log_path, 'r', encoding='utf-8') as f:
                    log_lines = f.readlines()
                    log_content = "".join(log_lines[-50:])
                
                st.code(log_content, language="")
                
                # 로그 파일 다운로드 버튼
                with open(log_path, "rb") as file:
                    log_bytes = file.read()
                
                st.download_button(
                    label="로그 파일 다운로드",
                    data=log_bytes,
                    file_name=selected_log,
                    mime="text/plain",
                )
            except Exception as e:
                st.error(f"로그 파일 읽기 오류: {e}")
        else:
            st.markdown("로그 파일이 없습니다.")
        
        # 출력 폴더 관리
        st.markdown("### 출력 폴더 관리")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 비디오 파일 개수 및 크기
            video_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(('.mp4', '.mov', '.avi'))]
            total_size = sum(os.path.getsize(os.path.join(OUTPUT_DIR, f)) for f in video_files) / (1024 * 1024)  # MB
            st.metric("비디오 파일", f"{len(video_files)}개", f"{total_size:.2f} MB")
        
        with col2:
            # TTS 파일 개수 및 크기
            tts_files = [f for f in os.listdir(TTS_DIR) if f.endswith(('.mp3', '.wav'))]
            total_tts_size = sum(os.path.getsize(os.path.join(TTS_DIR, f)) for f in tts_files) / (1024 * 1024)  # MB
            st.metric("TTS 파일", f"{len(tts_files)}개", f"{total_tts_size:.2f} MB")
        
        with col3:
            # 배경 비디오 파일 개수 및 크기
            bg_files = [f for f in os.listdir(BG_VIDEO_DIR) if f.endswith(('.mp4', '.mov', '.avi'))]
            total_bg_size = sum(os.path.getsize(os.path.join(BG_VIDEO_DIR, f)) for f in bg_files) / (1024 * 1024)  # MB
            st.metric("배경 비디오", f"{len(bg_files)}개", f"{total_bg_size:.2f} MB")
        
        # 임시 파일 정리 기능
        if st.button("임시 파일 정리"):
            try:
                # 캐시 폴더 정리
                cache_files = [os.path.join(CACHE_DIR, f) for f in os.listdir(CACHE_DIR)]
                removed_files = 0
                for file_path in cache_files:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        removed_files += 1
                
                st.markdown(f'<div class="success-box">✅ 임시 파일 정리 완료: {removed_files}개 파일 삭제됨</div>', unsafe_allow_html=True)
            except Exception as e:
                st.markdown(f'<div class="error-box">❌ 파일 정리 중 오류 발생: {str(e)}</div>', unsafe_allow_html=True)

# 하단 정보
st.markdown("---")
st.markdown("### 🎬 YouTube Shorts 자동화 생성기")
st.markdown("© 2025 YouTube Shorts Creator. 모든 권리 보유.")

# 앱 개발자 정보
with st.expander("앱 정보", expanded=False):
    st.markdown("""
    **YouTube Shorts 자동화 생성기** 는 YouTube Shorts 비디오를 손쉽게 생성할 수 있는 도구입니다.
    
    **기능:**
    - 다양한 소스에서 콘텐츠 추출 (직접 텍스트 입력, YouTube, 웹페이지)
    - 여러 TTS 엔진 지원 (Google Cloud TTS, OpenAI TTS, 로컬 TTS)
    - 자동 자막 생성 및 추가 (한국어 최적화 지원)
    - Pexels API를 통한 배경 비디오 검색 및 다운로드
    - 한국어 키워드 자동 변환 지원
    - 그라데이션 배경 비디오 자동 생성
    - Jamendo API를 통한 배경 음악 검색 및 다운로드
    - 오프라인 모드 지원 (인터넷 연결 없이도 비디오 생성 가능)
    - YouTube API를 통한 비디오 업로드
    
    **새로운 기능:**
    - 시스템 폰트 자동 감지 (한글 자막 최적화)
    - 인터넷 연결 상태 감지 및 오프라인 모드 자동 전환
    - 한국어 키워드 자동 영어 변환 (Pexels, Jamendo 검색용)
    - 그라데이션 배경 비디오 생성 (오프라인 모드에서도 작동)
    - 향상된 에러 처리 및 로깅 시스템
    
    **도움말:** 사용 중 문제가 발생하면 로그 탭에서 로그를 확인하세요.
    """)

# 처음 앱을 로드할 때 안내 메시지 표시
if not st.session_state.get('app_loaded', False):
    st.session_state.app_loaded = True
    
    # 오프라인 모드 감지
    st.session_state.is_offline_mode = not check_internet_connection()
    
    # 시작 시 알림 표시
    if st.session_state.is_offline_mode:
        st.warning("⚠️ 오프라인 모드가 감지되었습니다. 일부 기능이 제한될 수 있습니다.")
        logger.warning("오프라인 모드로 앱 시작")
    
    st.balloons()
    
    # 로그 폴더에 시작 로그 기록
    logger.info("앱 시작됨")
    
    welcome_message = """
    # 🎉 환영합니다!
    
    **YouTube Shorts 자동화 생성기**에 오신 것을 환영합니다!
    
    이 앱을 사용하여 손쉽게 고품질 YouTube Shorts 비디오를 생성할 수 있습니다.
    시작하려면 '콘텐츠 생성' 탭에서 스크립트를 작성하거나 URL을 통해 콘텐츠를 가져오세요.
    
    도움이 필요하시면 언제든지 로그 및 기록 탭에서 도움말을 확인하세요!
    """
    
    # 시작 메시지 표시
    st.markdown(welcome_message) 
    
    # 오프라인 모드일 때 추가 안내
    if st.session_state.is_offline_mode:
        st.info("""
        **오프라인 모드 안내**
        
        현재 인터넷 연결이 감지되지 않아 오프라인 모드로 실행 중입니다.
        다음 기능들은 제한될 수 있습니다:
        
        - Pexels API를 통한 배경 비디오 다운로드
        - Jamendo API를 통한 배경 음악 다운로드
        - OpenAI API를 통한 콘텐츠 변환
        - YouTube 업로드
        
        대체 기능으로 다음을 사용할 수 있습니다:
        
        - 그라데이션 배경 비디오 생성
        - 로컬에 저장된 배경 음악 사용
        - 로컬 TTS 엔진 사용
        
        인터넷 연결이 복구되면 앱을 재시작하세요.
        """)

# 앱 시작 후 인터넷 연결 상태 변경 감지
if 'is_offline_mode' in st.session_state:
    current_connection_status = check_internet_connection()
    # 이전에 오프라인이었다가 온라인이 된 경우
    if st.session_state.is_offline_mode and current_connection_status:
        st.session_state.is_offline_mode = False
        st.success("🌐 인터넷 연결이 감지되었습니다. 모든 기능을 사용할 수 있습니다.")
        logger.info("오프라인 → 온라인 모드로 전환")
    # 이전에 온라인이었다가 오프라인이 된 경우
    elif not st.session_state.is_offline_mode and not current_connection_status:
        st.session_state.is_offline_mode = True
        st.warning("⚠️ 인터넷 연결이 끊겼습니다. 일부 기능이 제한됩니다.")
        logger.warning("온라인 → 오프라인 모드로 전환")
