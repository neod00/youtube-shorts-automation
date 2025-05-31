"""
Streamlit 앱 설정 모듈
기존 config_SCU.py를 기반으로 Streamlit 환경에 맞게 최적화됨
"""

import os
import json
import logging
from pathlib import Path
import streamlit as st

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output_videos")
TTS_DIR = os.path.join(BASE_DIR, "tts_files")
SCRIPT_DIR = os.path.join(BASE_DIR, "scripts")
BG_VIDEO_DIR = os.path.join(BASE_DIR, "background_videos")
BG_MUSIC_DIR = os.path.join(BASE_DIR, "background_music")
THUMBNAIL_DIR = os.path.join(BASE_DIR, "thumbnails")
LOG_DIR = os.path.join(BASE_DIR, "logs")
TEMP_DIR = os.path.join(BASE_DIR, "temp_videos")

# 디렉토리 생성
for directory in [OUTPUT_DIR, TTS_DIR, SCRIPT_DIR, BG_VIDEO_DIR, BG_MUSIC_DIR, THUMBNAIL_DIR, LOG_DIR, TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

# TTS 설정
TTS_ENGINE = "google"  # 기본 엔진 (google, openai, local)
TTS_VOICE = "ko-KR-Neural2-C"  # 기본 한국어 음성

# YouTube 설정
YT_DEFAULT_CATEGORY = "22"  # 기본 카테고리 (22 = 사람과 블로그)
YT_DEFAULT_PRIVACY = "private"  # 기본 공개 상태

# API 설정
JAMENDO_CLIENT_ID = "a9d56059"  # 기본 Jamendo API 클라이언트 ID

# 비디오 설정
MAX_SHORTS_DURATION = 60  # 최대 쇼츠 길이 (초)
VIDEO_WIDTH = 1080  # 쇼츠 비디오 너비
VIDEO_HEIGHT = 1920  # 쇼츠 비디오 높이

# 자막 설정
FONT_SIZE = 50  # 기본 자막 폰트 크기
FONT_PATH = None  # 자동 감지

# Windows 기본 폰트 경로 리스트
WINDOWS_FONTS = [
    "C:/Windows/Fonts/malgunbd.ttf",  # 맑은 고딕 볼드체
    "C:/Windows/Fonts/malgun.ttf",    # 맑은 고딕
    "C:/Windows/Fonts/arialbd.ttf",   # Arial Bold
    "C:/Windows/Fonts/arial.ttf"      # Arial
]

# 자동으로 폰트 경로 감지
for font_path in WINDOWS_FONTS:
    if os.path.exists(font_path):
        FONT_PATH = font_path
        break

# API 키 설정 (환경 변수 또는 secrets.toml 파일에서 로드)
def get_api_key(key_name):
    """API 키 가져오기 (Streamlit 환경 기준)"""
    try:
        # Streamlit secrets에서 가져오기 시도
        return st.secrets.get(key_name, None)
    except Exception:
        # 환경 변수에서 가져오기 시도
        return os.environ.get(key_name, None)

# 예시 설정값 로드 함수
def load_config(config_file=None):
    """설정 파일 로드"""
    if not config_file:
        config_file = os.path.join(BASE_DIR, "config.json")
    
    config_data = {
        "TTS_ENGINE": TTS_ENGINE,
        "TTS_VOICE": TTS_VOICE,
        "YT_DEFAULT_CATEGORY": YT_DEFAULT_CATEGORY,
        "YT_DEFAULT_PRIVACY": YT_DEFAULT_PRIVACY,
        "MAX_SHORTS_DURATION": MAX_SHORTS_DURATION,
        "VIDEO_WIDTH": VIDEO_WIDTH,
        "VIDEO_HEIGHT": VIDEO_HEIGHT,
        "FONT_SIZE": FONT_SIZE,
        "FONT_PATH": FONT_PATH,
        "BASE_DIR": BASE_DIR,
        "OUTPUT_DIR": OUTPUT_DIR,
        "TTS_DIR": TTS_DIR,
        "SCRIPT_DIR": SCRIPT_DIR,
        "BG_VIDEO_DIR": BG_VIDEO_DIR,
        "BG_MUSIC_DIR": BG_MUSIC_DIR,
        "THUMBNAIL_DIR": THUMBNAIL_DIR,
        "LOG_DIR": LOG_DIR,
        "JAMENDO_CLIENT_ID": JAMENDO_CLIENT_ID
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                # 로드된 설정으로 기본값 업데이트
                config_data.update(loaded_config)
        except Exception as e:
            logging.warning(f"설정 파일 로드 중 오류 발생: {e}")
    
    return config_data

# 설정 객체 생성
config = load_config()

# Streamlit 앱에서 설정 변경 시 저장하는 함수
def save_config(config_data, config_file=None):
    """설정 저장"""
    if not config_file:
        config_file = os.path.join(BASE_DIR, "config.json")
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"설정 저장 중 오류 발생: {e}")
        return False 