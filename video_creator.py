"""
비디오 생성 모듈 - Streamlit 버전
기존 video_creator_SCU.py를 기반으로 Streamlit 환경에 맞게 최적화됨
"""

import os
import logging
import time
import random
from pathlib import Path
import sys
import numpy as np
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, TextClip, CompositeAudioClip,
    ColorClip, ImageClip, VideoClip, CompositeVideoClip, 
    concatenate_videoclips
)
import tempfile
import traceback
import json
import requests
import uuid
from tempfile import gettempdir

# 외부 모듈 import 시도 (설치되지 않았을 경우 경고만)
try:
    from google.cloud import speech_v1p1beta1 as speech
except ImportError:
    logging.warning("Google Cloud Speech API 패키지가 설치되지 않았습니다. 음성 인식 기능이 제한됩니다.")

# Pexels 및 Jamendo 관련 모듈은 나중에 동적으로 import

# 환경 설정
class VideoCreator:
    """비디오 생성 클래스 - Streamlit 버전"""
    
    def __init__(self, output_dir="output", temp_dir="temp", background_dir="background", music_dir="music", progress_callback=None):
        """초기화"""
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.background_dir = background_dir
        self.music_dir = music_dir
        self.progress_callback = progress_callback
        
        # 디렉토리 생성
        for directory in [output_dir, temp_dir, background_dir, music_dir]:
            if not os.path.exists(directory):
                self.update_progress(f"디렉토리 생성: {directory}", None)
                os.makedirs(directory, exist_ok=True)
                
        # 폰트 디렉토리 생성
        font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
        os.makedirs(font_dir, exist_ok=True)
        
        # 자체 폰트 확인 및 필요시 다운로드
        self.get_font_path()
        
        # Jamendo 음악 제공자 초기화
        try:
            # 상대 경로 임포트를 위한 시도
            try:
                from jamendo_music_provider import JamendoMusicProvider
            except ImportError:
                # 다른 위치에서 임포트 시도
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                try:
                    from ModuleSet.jamendo_music_provider import JamendoMusicProvider
                except ImportError:
                    # 마지막 시도
                    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
                    from ModuleSet.jamendo_music_provider_v01 import JamendoMusicProvider
            
            self.jamendo_provider = JamendoMusicProvider(
                client_id="a9d56059",  # 기본 클라이언트 ID
                output_dir=self.music_dir
            )
            self.update_progress("✅ Jamendo 음악 제공자 초기화 완료", None)
        except Exception as e:
            self.update_progress(f"⚠️ Jamendo 음악 제공자 초기화 실패: {str(e)}", None)
            self.jamendo_provider = None
        
        # Pexels 비디오 다운로더 초기화
        try:
            # 상대 경로 임포트를 위한 시도
            try:
                from pexels_downloader import PexelsVideoDownloader
            except ImportError:
                # 다른 위치에서 임포트 시도
                try:
                    from ModuleSet.pexels_video_downloader import PexelsVideoDownloader
                except ImportError:
                    # 마지막 시도
                    from ModuleSet.pexels_video_downloader import PexelsVideoDownloader
            
            self.pexels_downloader = PexelsVideoDownloader()
            self.update_progress("✅ Pexels 다운로더 초기화 완료", None)
        except Exception as e:
            self.update_progress(f"⚠️ Pexels 다운로더 초기화 실패: {str(e)}", None)
            self.pexels_downloader = None
        
        # 샘플 배경 비디오 생성 (테스트용)
        self._create_sample_background_if_needed()
        
        # 쇼츠 최대/최소 길이 설정
        self.MAX_DURATION = 180  # 쇼츠 최대 길이 180초(3분)
        self.MIN_DURATION = 15  # 쇼츠 최소 길이 15초
        
        # 기본 배경 음악 경로 설정
        self.bgm_path = None  # 배경 음악 경로
        
        logging.info("Video Creator initialized")

    def _create_sample_background_if_needed(self):
        """테스트를 위한 샘플 배경 비디오 생성"""
        # 배경 디렉토리가 없으면 생성
        os.makedirs(self.background_dir, exist_ok=True)
        
        # 이미 배경 비디오가 있는지 확인
        background_files = [f for f in os.listdir(self.background_dir) 
                           if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        
        if len(background_files) >= 3:
            self.update_progress(f"✅ 충분한 배경 비디오가 있습니다 ({len(background_files)}개)", None)
            return
            
        self.update_progress(f"배경 비디오가 부족합니다 ({len(background_files)}개). 샘플 비디오 생성을 시도합니다.", None)
        
        try:
            # 배경 디렉토리가 비어있으면 다양한 색상 및 패턴의 배경 비디오 생성
            # 기본 색상 목록 (다양한 색조의 파란색과 보라색 등 쇼츠에 적합한 색상)
            background_colors = [
                (25, 25, 112),  # 미드나이트 블루
                (65, 105, 225),  # 로열 블루
                (0, 0, 128),     # 네이비
                (106, 90, 205),  # 슬레이트 블루
                (72, 61, 139),   # 다크 슬레이트 블루
                (123, 104, 238), # 미디엄 슬레이트 블루
                (0, 0, 0),       # 블랙 (기존 컬러)
            ]
            
            # 생성할 비디오 수 결정 (최소 3개)
            num_videos_to_create = max(3 - len(background_files), 0)
            if num_videos_to_create == 0:
                return
                
            # 랜덤하게 색상 선택
            selected_colors = random.sample(background_colors, min(num_videos_to_create, len(background_colors)))
            
            for i, color in enumerate(selected_colors):
                sample_path = os.path.join(self.background_dir, f"sample_background_{int(time.time())}_{i}.mp4")
                
                try:
                    # 더 긴 시간(15초)으로 변경하고, 더 높은 해상도(1080x1920, 쇼츠 형식)로 설정
                    color_clip = ColorClip(size=(1080, 1920), color=color, duration=15)
                    color_clip.write_videofile(
                        sample_path, 
                        fps=24, 
                        codec='libx264', 
                        audio=False,
                        logger=None,
                        verbose=False,
                        ffmpeg_params=[
                            "-preset", "medium",      
                            "-crf", "23",            
                            "-pix_fmt", "yuv420p",   
                            "-b:v", "2000k",         
                            "-profile:v", "high",    
                            "-level", "4.0"          
                        ]
                    )
                    self.update_progress(f"✅ 샘플 배경 비디오 생성 완료: {sample_path}", None)
                    logging.info(f"샘플 배경 비디오 생성 완료: {sample_path}")
                except Exception as e:
                    self.update_progress(f"⚠️ 샘플 배경 비디오 생성 실패: {e}", None)
                    logging.error(f"샘플 배경 비디오 생성 실패: {e}")
            
            # 그라데이션 배경 추가하기
            try:
                # PIL을 사용하여 그라데이션 이미지 생성
                from PIL import Image, ImageDraw
                import numpy as np
                
                width, height = 1080, 1920  # 쇼츠 비디오 크기
                gradient_colors = [
                    [(0, 0, 128), (65, 105, 225)],  # 네이비 → 로열 블루
                    [(25, 25, 112), (123, 104, 238)],  # 미드나이트 블루 → 미디엄 슬레이트 블루
                    [(72, 61, 139), (106, 90, 205)]   # 다크 슬레이트 블루 → 슬레이트 블루
                ]
                
                # 더 다양한 그라데이션 추가 (더 밝고 화려한 색상)
                additional_gradients = [
                    [(0, 0, 128), (135, 206, 250)],  # 네이비 → 하늘색
                    [(75, 0, 130), (238, 130, 238)],  # 인디고 → 바이올렛
                    [(46, 139, 87), (152, 251, 152)], # 씨그린 → 라이트그린
                    [(178, 34, 34), (255, 127, 80)],  # 벽돌색 → 산호색
                ]
                gradient_colors.extend(additional_gradients)
                
                # 랜덤하게 그라데이션 선택
                selected_gradients = random.sample(gradient_colors, min(3, len(gradient_colors)))
                
                for i, (color1, color2) in enumerate(selected_gradients):
                    # 이미지 생성
                    img = Image.new('RGB', (width, height), color=(0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    
                    # 그라데이션 생성
                    for y in range(height):
                        # y 위치에 따른 색상 보간
                        r = int(color1[0] + (color2[0] - color1[0]) * y / height)
                        g = int(color1[1] + (color2[1] - color1[1]) * y / height)
                        b = int(color1[2] + (color2[2] - color1[2]) * y / height)
                        draw.line([(0, y), (width, y)], fill=(r, g, b))
                    
                    # 이미지를 임시 파일로 저장
                    temp_img_path = os.path.join(self.temp_dir, f"gradient_{int(time.time())}_{i}.png")
                    img.save(temp_img_path)
                    
                    # 이미지로부터 비디오 생성
                    gradient_clip = ImageClip(temp_img_path, duration=15)
                    gradient_path = os.path.join(self.background_dir, f"gradient_background_{int(time.time())}_{i}.mp4")
                    
                    gradient_clip.write_videofile(
                        gradient_path, 
                        fps=24, 
                        codec='libx264', 
                        audio=False,
                        logger=None,
                        verbose=False,
                        ffmpeg_params=[
                            "-preset", "medium",      
                            "-crf", "23",            
                            "-pix_fmt", "yuv420p",   
                            "-b:v", "2000k",         
                            "-profile:v", "high",    
                            "-level", "4.0"          
                        ]
                    )
                    
                    # 임시 이미지 파일 삭제
                    try:
                        os.remove(temp_img_path)
                    except:
                        pass
                    
                    self.update_progress(f"✅ 그라데이션 배경 비디오 생성 완료: {gradient_path}", None)
                
            except Exception as e:
                self.update_progress(f"⚠️ 그라데이션 배경 생성 실패: {e}", None)
                logging.error(f"그라데이션 배경 생성 실패: {e}")
                
        except Exception as e:
            self.update_progress(f"⚠️ 샘플 배경 비디오 생성 중 오류 발생: {e}", None)
            logging.error(f"샘플 배경 비디오 생성 중 오류 발생: {e}")

    def update_progress(self, message, progress_value=None):
        """진행 상황 업데이트 (Streamlit 사용 시)"""
        if self.progress_callback:
            # 중요 메시지나 진행률이 있을 때만 실제 메시지 전달
            if progress_value is not None or message.startswith(("✅", "⚠️", "❌")):
                self.progress_callback(message, progress_value)
            else:
                # 일반 디버그 메시지는 로깅만 하고 UI에 표시하지 않음
                logging.info(message)
        else:
            # 콘솔 출력만 사용하고 Streamlit UI 요소는 직접 호출하지 않음
            logging.info(message)

    def _translate_keyword(self, keyword: str) -> str:
        """한글 키워드를 영어로 번역"""
        # 키워드가 비어있거나 None이면 기본값 반환
        if not keyword:
            return "nature"
        
        # 한글-영어 키워드 매핑
        kr_to_en = {
            "경제": "economy", "주식": "stock market", "금융": "finance",
            "관세": "tariff", "관세폭탄": "tariff bomb", "무역": "trade",
            "뉴스": "news", "긍정": "positive", "부정": "negative",
            "위기": "crisis", "성장": "growth", "환경": "environment",
            "기후": "climate", "정치": "politics", "선거": "election",
            "여행": "travel", "자연": "nature", "기술": "technology",
            "과학": "science", "우주": "space", "건강": "health",
            "의학": "medicine", "교육": "education", "역사": "history",
            "문화": "culture", "예술": "art", "음악": "music",
            "영화": "movie", "게임": "game", "스포츠": "sports",
            "음식": "food", "요리": "cooking", "패션": "fashion",
            "뷰티": "beauty", "라이프스타일": "lifestyle",
            "겨울": "winter", "눈": "snow", "바다": "sea", "산": "mountain",
            "꽃": "flower", "동물": "animal", "집": "home", "도시": "city",
            "길": "road", "하늘": "sky", "숲": "forest", "사랑": "love",
            "행복": "happiness", "물": "water", "아이": "child", "공부": "study",
            "운동": "exercise", "친구": "friend", "가족": "family", "휴가": "vacation",
            "이미지": "image", "생성": "generation", "애니메이션": "animation",
            "일본": "japan", "초상권": "portrait rights", "데이터": "data",
            "보호": "protection", "스튜디오": "studio", "지브리": "ghibli",
            "사진": "photo", "변환": "transformation", "이용자": "user", 
            "개인정보": "personal information", "저작권": "copyright",
            "ai": "ai", "인공지능": "artificial intelligence", 
            "미래": "future", "혁신": "innovation", "진보": "progress"
        }
        
        # 콤마로 구분된 키워드 처리
        if ',' in keyword:
            # 콤마로 분리하고 각 키워드 앞뒤 공백 제거
            keyword_list = [k.strip() for k in keyword.split(',')]
            
            # 변환된 키워드를 저장할 리스트
            translated_keywords = []
            
            for kw in keyword_list:
                # 빈 키워드 건너뛰기
                if not kw:
                    continue
                    
                # 한글 키워드 감지
                is_korean = any('\uAC00' <= char <= '\uD7A3' for char in kw)
                
                if is_korean:
                    # 매핑 사전에서 정확히 일치하는 키 찾기
                    if kw in kr_to_en:
                        translated = kr_to_en[kw]
                        translated_keywords.append(translated)
                    else:
                        # 공백 제거 후 매핑 시도
                        kw_no_space = kw.replace(" ", "")
                        if kw_no_space in kr_to_en:
                            translated = kr_to_en[kw_no_space]
                            translated_keywords.append(translated)
                        else:
                            # 부분 일치 시도
                            matched = False
                            for kr, en in kr_to_en.items():
                                if kr in kw:
                                    translated_keywords.append(en)
                                    matched = True
                                    break
                            
                            # 매칭 실패 시 원본 키워드 유지 (영어일 수 있음)
                            if not matched:
                                translated_keywords.append(kw)
                else:
                    # 영어 키워드는 그대로 유지
                    translated_keywords.append(kw)
            
            # 번역된 키워드가 있으면 사용, 없으면 기본 키워드 사용
            if translated_keywords:
                # 최대 2개의 키워드만 사용 (검색 효율성)
                if len(translated_keywords) > 2:
                    translated_keywords = translated_keywords[:2]
                # 공백으로 키워드 결합
                return " ".join(translated_keywords)
            else:
                return "nature"  # 기본값
        
        # 단일 키워드 처리 (기존 로직)
        # 한글 키워드 감지
        is_korean = any('\uAC00' <= char <= '\uD7A3' for char in keyword)
        
        if is_korean:
            # 매핑 사전에서 정확히 일치하는 키 찾기
            if keyword in kr_to_en:
                return kr_to_en[keyword]
            
            # 공백 제거 후 매핑 시도
            keyword_no_space = keyword.replace(" ", "")
            if keyword_no_space in kr_to_en:
                return kr_to_en[keyword_no_space]
            
            # 부분 일치 시도
            for kr, en in kr_to_en.items():
                if kr in keyword:
                    return en
            
            # 매칭 실패 시 기본값 반환
            return "nature"
        
        # 이미 영어 키워드면 그대로 반환
        return keyword

    def find_background_videos(self, keywords, use_pexels=True, log_results=True):
        """비디오 키워드를 기반으로 배경 비디오 파일을 찾습니다.
        
        Args:
            keywords (str or list): 검색할 키워드 또는 키워드 리스트
            use_pexels (bool): 로컬에서 비디오를 찾을 수 없는 경우 Pexels API를 사용할지 여부
            log_results (bool): 검색 결과를 로깅할지 여부
            
        Returns:
            list: 찾은 비디오 파일 경로 리스트
        """
        # 키워드 처리
        if not keywords:
            keywords = ["nature", "landscape", "abstract"]
        elif isinstance(keywords, str):
            # 문자열을 쉼표, 공백, 파이프로 분리하여 리스트로 변환
            keywords = re.split(r'[,\s|]+', keywords)
            # 빈 문자열 제거
            keywords = [k.strip() for k in keywords if k.strip()]
        
        # 찾은 비디오 파일 리스트
        found_videos = []
        
        # 검색 결과 카테고리화
        actual_videos = []
        gradient_videos = []
        sample_videos = []
        
        # 로컬 비디오 디렉토리 목록
        video_dirs = []
        
        # 기본 비디오 디렉토리 추가
        if self.video_dir and os.path.exists(self.video_dir):
            video_dirs.append(self.video_dir)
            
        # 공통 비디오 디렉토리 확인 및 추가
        common_video_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "videos"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "videos"),
        ]
        
        for dir_path in common_video_dirs:
            if os.path.exists(dir_path):
                video_dirs.append(dir_path)
                
        if log_results:
            logging.info(f"검색할 비디오 디렉토리: {video_dirs}")
            logging.info(f"검색 키워드: {keywords}")
        
        # 각 디렉토리에서 비디오 파일 찾기
        for video_dir in video_dirs:
            if not os.path.exists(video_dir):
                continue
                
            for root, _, files in os.walk(video_dir):
                for file in files:
                    # 비디오 파일 확장자 확인
                    if file.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                        file_path = os.path.join(root, file)
                        file_lower = file.lower()
                        
                        # 키워드 매칭 여부 확인
                        if any(keyword.lower() in file_lower for keyword in keywords):
                            # 파일 분류
                            if 'gradient' in file_lower or 'background' in file_lower:
                                gradient_videos.append(file_path)
                            elif 'sample' in file_lower:
                                sample_videos.append(file_path)
                            else:
                                actual_videos.append(file_path)
                            
                            # 모든 발견된 비디오 추가
                            found_videos.append(file_path)
        
        # 검색 결과 정렬 및 반환 - 우선순위 변경: 실제 비디오 > 샘플 비디오 > 그라디언트 비디오 순
        if log_results:
            logging.info(f"발견된 실제 비디오: {len(actual_videos)}")
            logging.info(f"발견된 샘플 비디오: {len(sample_videos)}")
            logging.info(f"발견된 그라디언트 비디오: {len(gradient_videos)}")
        
        # 결과가 없고 Pexels API를 사용할 수 있는 경우
        if not found_videos and use_pexels and self.pexels:
            if log_results:
                logging.info(f"로컬에서 비디오를 찾을 수 없어 Pexels에서 '{keywords[0]}' 비디오 다운로드 시도")
            
            # Pexels에서 첫 번째 키워드로 비디오 검색 및 다운로드
            downloaded_videos = self.pexels.download_videos(keywords[0], limit=1)
            
            if downloaded_videos:
                return downloaded_videos
        
        # 이제 우선순위에 따라 결과 반환
        if actual_videos:
            # 실제 비디오가 있으면 그것만 반환
            if log_results:
                logging.info(f"실제 비디오를 반환합니다: {len(actual_videos)}개")
            return actual_videos
        elif sample_videos:
            # 실제 비디오가 없으면 샘플 비디오 반환
            if log_results:
                logging.info(f"샘플 비디오를 반환합니다: {len(sample_videos)}개")
            return sample_videos
        elif gradient_videos:
            # 샘플 비디오도 없으면 그라디언트 비디오 반환
            if log_results:
                logging.info(f"그라디언트 비디오를 반환합니다: {len(gradient_videos)}개")
            return gradient_videos
        else:
            # 아무것도 없으면 빈 리스트 반환
            if log_results:
                logging.info("비디오를 찾을 수 없습니다.")
            return []

    def download_background_videos(self, keyword: str, required_duration: float = 60.0) -> List[str]:
        """
        Pexels API를 통해 키워드에 맞는 배경 비디오를 다운로드합니다.
        이 메서드는 find_background_videos에서 비디오를 찾지 못했을 때 호출됩니다.
        
        Args:
            keyword (str): 검색할 키워드
            required_duration (float): 필요한 비디오 길이 (초)
            
        Returns:
            List[str]: 다운로드된 비디오 파일 경로 목록
        """
        logging.info(f"Pexels API를 통해 '{keyword}' 관련 비디오 다운로드 시도 (필요 길이: {required_duration}초)")
        
        # Pexels 다운로더가 초기화되었는지 확인
        if not hasattr(self, 'pexels_downloader') or self.pexels_downloader is None:
            logging.warning("Pexels 다운로더가 초기화되지 않았습니다.")
            return []
        
        try:
            # 키워드 전처리
            if ',' in keyword:
                # 여러 키워드 중 첫 번째 키워드만 사용
                main_keyword = keyword.split(',')[0].strip()
                # 영어 키워드로 변환
                translated_keyword = self._translate_keyword(main_keyword)
            else:
                translated_keyword = self._translate_keyword(keyword)
                
            # 키워드가 짧으면 일반적인 카테고리 키워드 추가
            if len(translated_keyword) < 3:
                translated_keyword = f"{translated_keyword}, nature, landscape"
            
            # Pexels API를 통해 비디오 다운로드
            video_info = self.pexels_downloader.get_multiple_background_videos(
                keyword=translated_keyword,
                required_duration=required_duration,
                max_videos=3  # 최대 3개 비디오 다운로드
            )
            
            # 다운로드된 비디오 경로 추출
            downloaded_videos = []
            if video_info:
                for info in video_info:
                    if isinstance(info, dict) and "path" in info and os.path.exists(info["path"]):
                        downloaded_videos.append(info["path"])
                        
            if downloaded_videos:
                logging.info(f"Pexels API에서 '{translated_keyword}' 관련 비디오 {len(downloaded_videos)}개 다운로드 성공")
            else:
                logging.warning(f"Pexels API에서 '{translated_keyword}' 관련 비디오를 찾을 수 없습니다.")
                
            return downloaded_videos
                
        except Exception as e:
            logging.error(f"Pexels API 비디오 다운로드 오류: {str(e)}")
            return []

    def get_multiple_background_videos(self, keyword: str, required_duration: float, max_videos: int = 5) -> List[str]:
        """
        여러 배경 비디오를 찾아 목록 반환 - 개선된 버전
        
        순서:
        1. 로컬에서 키워드 관련 실제 비디오 검색
        2. 실제 비디오가 없으면 Pexels API 호출
        3. Pexels API도 실패하면 로컬의 모든 실제 비디오 사용
        4. 실제 비디오가 없으면 그라디언트/샘플 비디오 사용
        """
        # 1. 먼저 로컬에서 키워드 관련 실제 비디오 검색
        local_videos = self.find_background_videos(keyword)
        
        # 실제 비디오와 그라디언트/샘플 비디오 분리
        actual_videos = [v for v in local_videos if "gradient_background" not in v.lower() and "sample_background" not in v.lower()]
        other_videos = [v for v in local_videos if "gradient_background" in v.lower() or "sample_background" in v.lower()]
        
        # 실제 비디오가 있고 충분한 개수이면 바로 반환
        if actual_videos and len(actual_videos) >= 2:
            self.update_progress(f"로컬에서 '{keyword}' 관련 실제 비디오 {len(actual_videos)}개 발견", None)
            # 최대 max_videos 개수만큼 반환 (중복 제거)
            if len(actual_videos) > max_videos:
                return random.sample(actual_videos, max_videos)
            return actual_videos
        
        # 2. 실제 비디오가 부족하면 Pexels API 호출
        if len(actual_videos) < 2 and hasattr(self, 'pexels_downloader') and self.pexels_downloader:
            self.update_progress(f"로컬 비디오 부족, Pexels에서 '{keyword}' 관련 비디오 검색 중...", None)
            pexels_videos = self.download_background_videos(keyword, required_duration)
            
            if pexels_videos:
                # Pexels에서 다운로드 성공, 기존 실제 비디오와 합쳐서 반환
                combined_videos = actual_videos + pexels_videos
                self.update_progress(f"로컬({len(actual_videos)}개)과 Pexels({len(pexels_videos)}개) 비디오 조합", None)
                
                # 최대 max_videos 개수만큼 반환
                if len(combined_videos) > max_videos:
                    return random.sample(combined_videos, max_videos)
                return combined_videos
        
        # 3. Pexels API 실패시, 로컬의 실제 비디오 전체 검색 (키워드 무관)
        if not actual_videos:
            all_actual_videos = []
            
            if os.path.exists(self.background_dir):
                for file in os.listdir(self.background_dir):
                    if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                        if "gradient_background" not in file.lower() and "sample_background" not in file.lower():
                            all_actual_videos.append(os.path.join(self.background_dir, file))
            
            if all_actual_videos:
                self.update_progress(f"키워드 관련 비디오 없음, 전체 {len(all_actual_videos)}개 실제 비디오 사용", None)
                # 랜덤 샘플링
                if len(all_actual_videos) > max_videos:
                    return random.sample(all_actual_videos, max_videos)
                return all_actual_videos
        
        # 4. 실제 비디오가 없으면 그라디언트/샘플 비디오 사용
        if other_videos:
            self.update_progress(f"실제 비디오 없음, {len(other_videos)}개 그라디언트/샘플 배경 사용", None)
            if len(other_videos) > max_videos:
                return random.sample(other_videos, max_videos)
            return other_videos
        
        # 5. 마지막 수단: 샘플 비디오 생성
        self.update_progress("비디오를 찾을 수 없어 샘플 비디오 생성", None)
        self._create_sample_background_if_needed()
        
        # 생성된 샘플 비디오 찾기
        sample_videos = []
        for file in os.listdir(self.background_dir):
            if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                sample_videos.append(os.path.join(self.background_dir, file))
        
        if sample_videos:
            return random.sample(sample_videos, min(len(sample_videos), max_videos))
        
        # 아무것도 없으면 빈 목록 반환
        return []

    def get_background_music(self, keyword: str, required_duration: float) -> Optional[str]:
        """키워드에 맞는 배경 음악 가져오기 - Jamendo 기반으로 개선"""
        self.update_progress(f"키워드 '{keyword}'에 맞는 배경 음악을 검색합니다...", 5)
        
        try:
            # 1. 키워드 번역 및 확장
            search_keyword = keyword
            
            # 한글 키워드 감지
            is_korean = False
            for char in keyword:
                if '\uAC00' <= char <= '\uD7A3':  # 한글 유니코드 범위
                    is_korean = True
                    break
                    
            if is_korean:
                self.update_progress(f"한글 키워드 감지: '{keyword}'", None)
                # 번역된 키워드 사용
                translated_keyword = self._translate_keyword(keyword)
                if translated_keyword and translated_keyword != keyword:
                    search_keyword = translated_keyword
                    self.update_progress(f"번역된 키워드로 음악 검색: '{keyword}' → '{search_keyword}'", None)
            
            # 원본 키워드에서 밝고 긍정적인 키워드로 변환
            positive_prefix = random.choice(["happy", "cheerful", "upbeat", "light", "positive", "uplifting", "bright"])
            enhanced_keyword = f"{positive_prefix} {search_keyword}"
            self.update_progress(f"검색 키워드 개선: '{search_keyword}' → '{enhanced_keyword}'", None)
            search_keyword = enhanced_keyword
            
            # 명시적으로 검색 키워드 목록을 생성
            keywords = []
            
            # 문맥에 맞는 태그 추가 - 쇼츠용 밝은 잔잔한 음악 태그로 수정
            if "news" in keyword.lower() or "breaking" in keyword.lower():
                keywords = ["light piano news", "positive background news", "upbeat instrumental news"]
            elif "drama" in keyword.lower() or "president" in keyword.lower():
                keywords = ["cheerful piano", "light instrumental background", "positive music"]
            elif "disaster" in keyword.lower() or "emergency" in keyword.lower():
                keywords = ["uplifting peaceful piano", "hopeful ambient music", "positive calm background"]
            else:
                keywords = ["happy piano", "cheerful background music", "uplifting calm instrumental", 
                           "positive light music", "bright cheerful piano"]
                
            # 원본 키워드 변형 추가
            keywords.insert(0, enhanced_keyword)
            
            self.update_progress(f"음악 검색 키워드 목록: {keywords}", None)
            
            # 2. Jamendo 제공자가 있으면 사용
            if hasattr(self, 'jamendo_provider') and self.jamendo_provider:
                for music_keyword in keywords:
                    self.update_progress(f"'{music_keyword}' 키워드로 음악 검색 중...", None)
                    
                    # 자체 메서드를 통해 음악 검색
                    try:
                        results = self.jamendo_provider.search_music(music_keyword, limit=10)
                        
                        if results and len(results) > 0:
                            # 결과 중에서 무작위로 선택
                            selected_track = random.choice(results)
                            track_path = self.jamendo_provider.download_track(selected_track)
                            
                            if track_path and os.path.exists(track_path):
                                self.update_progress(f"✅ '{music_keyword}' 키워드로 음악 다운로드 성공: {track_path}", None)
                                self.bgm_path = track_path
                                return track_path
                    except Exception as e:
                        self.update_progress(f"Jamendo 검색 오류: {str(e)}", None)
                
            # 3. 로컬 음악 파일 검색
            self.update_progress("Jamendo API 실패, 로컬 음악 파일 검색 중...", None)
            
            # 기본 음악 디렉토리에서 검색
            if os.path.exists(self.music_dir):
                # 키워드 기반 검색
                music_files = []
                for file in os.listdir(self.music_dir):
                    if file.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg')):
                        # 키워드가 파일명에 포함되면 추가
                        if any(kw.lower() in file.lower() for kw in [keyword, search_keyword, *keywords]):
                            music_path = os.path.join(self.music_dir, file)
                            music_files.append(music_path)
                
                # 키워드 검색 실패 시 모든 음악 파일 추가
                if not music_files:
                    for file in os.listdir(self.music_dir):
                        if file.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg')):
                            music_path = os.path.join(self.music_dir, file)
                            music_files.append(music_path)
                
                # 음악 파일이 있으면 무작위 선택
                if music_files:
                    selected_music = random.choice(music_files)
                    self.update_progress(f"✅ 로컬 음악 파일 선택: {os.path.basename(selected_music)}", None)
                    self.bgm_path = selected_music
                    return selected_music
            
            # 4. 이전에 설정된 배경 음악 확인
            if hasattr(self, 'bgm_path') and self.bgm_path and os.path.exists(self.bgm_path):
                self.update_progress(f"✅ 이전 배경 음악 사용: {os.path.basename(self.bgm_path)}", None)
                return self.bgm_path
            
            # 5. 외부 음악 서비스 확인 (향후 확장용)
            # ...
            
            # 6. 음악을 찾을 수 없는 경우
            self.update_progress("⚠️ 배경 음악을 찾을 수 없습니다. 무음으로 진행합니다.", None)
            return None
            
        except Exception as e:
            self.update_progress(f"❌ 배경 음악 검색 중 오류 발생: {str(e)}", None)
            
            # 로깅 및 스택 트레이스 출력
            import traceback
            logging.error(f"배경 음악 검색 오류: {str(e)}")
            logging.error(traceback.format_exc())
            
            # 이전에 설정된 배경 음악 사용 (있는 경우)
            if hasattr(self, 'bgm_path') and self.bgm_path and os.path.exists(self.bgm_path):
                self.update_progress(f"⚠️ 오류로 인해 이전 배경 음악 사용: {os.path.basename(self.bgm_path)}", None)
                return self.bgm_path
            
            return None

    def create_video(self, script_content, audio_path, keyword=None, background_video_path=None, 
                  output_filename=None, subtitles=None, background_music_path=None, 
                  background_music_volume=0.15, subtitle_options=None, max_duration=None):
        """
        오디오 파일과 배경 비디오를 결합하여 비디오 생성
        
        Args:
            script_content: 스크립트 내용 (텍스트)
            audio_path: 오디오 파일 경로
            keyword: 키워드
            background_video_path: 배경 비디오 경로
            output_filename: 출력 파일 이름
            subtitles: 자막 데이터 리스트
            background_music_path: 배경 음악 경로
            background_music_volume: 배경 음악 볼륨 (0.0 ~ 1.0)
            subtitle_options: 자막 관련 추가 옵션 (폰트, 크기, 색상 등)
            max_duration: 최대 비디오 길이 (초), None이면 기본값(self.MAX_DURATION) 사용
            
        Returns:
            생성된 비디오 파일 경로
        """
        # 진행 상황 업데이트
        self.update_progress("비디오 생성 시작...", 0)
        
        # 최대 길이 설정
        if max_duration is None:
            max_duration = self.MAX_DURATION
        
        self.update_progress(f"최대 비디오 길이: {max_duration}초", 0)
        
        # 출력 파일명 설정
        if not output_filename:
            timestamp = int(time.time())
            keyword_part = f"_{keyword}" if keyword else ""
            output_filename = f"video{keyword_part}_{timestamp}.mp4"
        
        # 출력 경로 설정
        output_path = os.path.join(self.output_dir, output_filename)
        
        # 스크립트 내용을 임시 파일로 저장
        script_path = os.path.join(self.temp_dir, f"script_{int(time.time())}.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        # 배경 비디오 클립 변수
        bg_clip = None
        video_clips = []
        
        try:
            # 오디오 길이 확인
            audio_clip = AudioFileClip(audio_path)
            audio_duration = audio_clip.duration
            self.update_progress(f"오디오 길이: {audio_duration:.1f}초", 5)
            
            # 배경 비디오 준비
            self.update_progress("배경 비디오 준비 중...", 10)
            bg_clip = None
            
            # 백그라운드 비디오 처리 로직 개선
            if isinstance(background_video_path, list) and background_video_path:
                # 비디오 목록이 전달된 경우
                self.update_progress(f"{len(background_video_path)}개 비디오 준비...", 12)
                video_clips = []
                total_duration = 0
                
                # 각 비디오 로드 및 처리
                for i, video_path in enumerate(background_video_path):
                    try:
                        self.update_progress(f"비디오 {i+1}/{len(background_video_path)} 로드 중...", 12 + (i * 3))
                        clip = VideoFileClip(video_path)
                        current_duration = clip.duration
                        
                        # 이 비디오를 포함했을 때 총 길이가 오디오 길이를 초과하는지 확인
                        if total_duration + current_duration > audio_duration:
                            # 마지막 클립은 필요한 만큼만 자르기
                            needed_duration = audio_duration - total_duration
                            if needed_duration > 0:
                                self.update_progress(f"비디오 길이 조정: {current_duration:.1f}초 → {needed_duration:.1f}초", None)
                                clip = clip.subclip(0, needed_duration)
                                video_clips.append(clip)
                                total_duration += needed_duration
                            else:
                                # 이미 충분한 길이인 경우 현재 비디오 닫기
                                clip.close()
                        else:
                            # 전체 길이가 충분하지 않으면 전체 클립 사용
                            video_clips.append(clip)
                            total_duration += current_duration
                        
                        self.update_progress(f"비디오 추가: {os.path.basename(video_path)}, 누적 길이: {total_duration:.1f}초/{audio_duration:.1f}초", 15)
                        
                        # 충분한 길이에 도달했으면 나머지 비디오는 처리하지 않음
                        if total_duration >= audio_duration:
                            self.update_progress(f"충분한 비디오 길이 확보: {total_duration:.1f}초/{audio_duration:.1f}초", None)
                            break
                            
                    except Exception as e:
                        self.update_progress(f"비디오 {i+1} 로드 오류: {str(e)}", None)
                        continue
                
                # 비디오가 준비되었는지 확인
                if video_clips:
                    # 비디오 클립 연결 (부드러운 전환 효과 추가)
                    self.update_progress(f"{len(video_clips)}개 비디오 연결 중...", 20)
                    
                    # 비디오가 하나만 있는 경우
                    if len(video_clips) == 1:
                        bg_clip = video_clips[0]
                    else:
                        # 여러 비디오를 매끄럽게 연결 (crossfade 효과 사용)
                        try:
                            # 각 클립을 필요한 길이와 해상도로 조정
                            processed_clips = []
                            target_size = None  # 첫 번째 클립의 크기를 기준으로 함
                            
                            for i, clip in enumerate(video_clips):
                                # 첫 번째 클립의 해상도를 기준으로 설정
                                if i == 0:
                                    target_size = (clip.w, clip.h)
                                
                                # 해상도 통일 (첫 번째 클립 기준)
                                if clip.w != target_size[0] or clip.h != target_size[1]:
                                    clip = clip.resize(target_size)
                                
                                processed_clips.append(clip)
                            
                            # 크로스페이드 시간 (초) - 너무 짧은 클립에 대해 보정
                            min_clip_duration = min(clip.duration for clip in processed_clips)
                            crossfade_duration = min(0.7, min_clip_duration / 3)
                            
                            # concatenate_videoclips 함수를 사용하여 비디오 연결
                            try:
                                # 명시적으로 다시 임포트 (스코프 문제 해결)
                                from moviepy.editor import concatenate_videoclips
                                
                                # 최신 버전의 moviepy에서는 method와 transition 파라미터 사용
                                # crossfade_duration 인수는 사용하지 않고 transition 인수로 대체
                                bg_clip = concatenate_videoclips(
                                    processed_clips, 
                                    method="chain"  # 기본 연결 방식으로 변경
                                )
                                
                                self.update_progress(f"비디오 연결 완료, 총 길이: {bg_clip.duration:.1f}초", 25)
                            except Exception as e:
                                # 다른 방식으로 재시도
                                try:
                                    # 단순 연결 방식 시도 (크로스페이드 없이)
                                    self.update_progress("크로스페이드 없이 연결 재시도...", None)
                                    bg_clip = concatenate_videoclips(processed_clips)
                                    self.update_progress(f"단순 연결 성공, 총 길이: {bg_clip.duration:.1f}초", 25)
                                except Exception as e2:
                                    self.update_progress(f"비디오 연결 오류: {str(e)} -> {str(e2)}, 첫 번째 비디오만 사용", None)
                                    # 오류 발생 시 첫 번째 비디오만 사용
                                    bg_clip = video_clips[0]
                                    
                                    # 사용하지 않는 클립 메모리 해제
                                    for i in range(1, len(video_clips)):
                                        try:
                                            video_clips[i].close()
                                        except:
                                            pass
                        except Exception as e:
                            self.update_progress(f"비디오 연결 오류: {str(e)}, 첫 번째 비디오만 사용", None)
                            # 오류 발생 시 첫 번째 비디오만 사용
                            bg_clip = video_clips[0]
                            
                            # 사용하지 않는 클립 메모리 해제
                            for i in range(1, len(video_clips)):
                                try:
                                    video_clips[i].close()
                                except:
                                    pass
                else:
                    # 비디오가 없는 경우 검은색 배경 생성
                    self.update_progress("사용 가능한 비디오가 없습니다, 대체 비디오 생성", 20)
                    bg_clip = self._create_sample_background(audio_duration)
            elif isinstance(background_video_path, str) and os.path.exists(background_video_path):
                # 단일 비디오 파일이 전달된 경우
                try:
                    self.update_progress(f"비디오 파일 로드 중: {os.path.basename(background_video_path)}", 15)
                    bg_clip = VideoFileClip(background_video_path)
                    
                    # 비디오 길이 확인
                    if bg_clip.duration < audio_duration:
                        self.update_progress(f"비디오 길이({bg_clip.duration:.1f}초)가 오디오({audio_duration:.1f}초)보다 짧음, 비디오 반복", 18)
                        # 비디오가 오디오보다 짧으면 반복해서 사용
                        import math
                        repeat_count = math.ceil(audio_duration / bg_clip.duration)
                        repeated_clips = [bg_clip] * repeat_count
                        
                        # 크로스페이드로 자연스럽게 연결
                        from moviepy.editor import concatenate_videoclips
                        bg_clip = concatenate_videoclips(
                            repeated_clips, 
                            method="chain"  # 'crossfadeout' 대신 'chain' 사용
                        )
                    
                    # 필요한 경우 비디오 길이 자르기
                    if bg_clip.duration > audio_duration:
                        self.update_progress(f"비디오 길이 조정: {bg_clip.duration:.1f}초 → {audio_duration:.1f}초", 20)
                        bg_clip = bg_clip.subclip(0, audio_duration)
                except Exception as e:
                    self.update_progress(f"비디오 로드 오류: {str(e)}, 대체 비디오 생성", 15)
                    # 비디오 로드 실패 시 대체 비디오 생성
                    bg_clip = self._create_sample_background(audio_duration)
            else:
                # 비디오 파일이 제공되지 않은 경우 샘플 배경 생성
                self.update_progress("배경 비디오 없음, 대체 비디오 생성", 15)
                bg_clip = self._create_sample_background(audio_duration)

            # 오디오 설정
            self.update_progress("오디오 설정 중...", 40)
            final_clip = bg_clip.set_audio(audio_clip)
            
            # 배경 음악이 있으면 TTS 오디오와 믹싱하여 볼륨 조절
            bgm_added = False
            
            # 1. 직접 전달된 배경 음악 사용
            if background_music_path and os.path.exists(background_music_path):
                self.update_progress(f"✅ 직접 전달된 배경 음악 사용: {os.path.basename(background_music_path)}", 45)
                try:
                    bgm_clip = AudioFileClip(background_music_path)
                    bgm_added = True
                except Exception as e:
                    self.update_progress(f"⚠️ 전달된 배경 음악 로드 실패: {e}", 45)
            
            # 2. 클래스에 설정된 배경 음악 사용
            if not bgm_added and hasattr(self, 'bgm_path') and self.bgm_path and os.path.exists(self.bgm_path):
                self.update_progress(f"✅ 자동 선택된 배경 음악 사용: {os.path.basename(self.bgm_path)}", 45)
                try:
                    bgm_clip = AudioFileClip(self.bgm_path)
                    bgm_added = True
                except Exception as e:
                    self.update_progress(f"⚠️ 자동 선택된 배경 음악 로드 실패: {e}", 45)
            
            # 배경 음악 처리 및 믹싱
            if bgm_added and bgm_clip:
                self.update_progress("배경 음악 처리 중...", 50)
                
                # 배경 음악 볼륨 조절
                if background_music_volume > 0:
                    try:
                        # 배경 음악이 오디오보다 짧으면 반복
                        if bgm_clip.duration < audio_duration:
                            bgm_clip = bgm_clip.loop(duration=audio_duration)
                            self.update_progress(f"배경 음악 루핑으로 길이 조정: {bgm_clip.duration:.1f}초", 55)
                        
                        # 배경 음악이 오디오보다 길면 잘라내기
                        if bgm_clip.duration > audio_duration:
                            bgm_clip = bgm_clip.subclip(0, audio_duration)
                        
                        # 볼륨 조절
                        bgm_clip = bgm_clip.volumex(background_music_volume)
                        
                        # 오디오 믹싱
                        mixed_audio = CompositeAudioClip([audio_clip, bgm_clip])
                        final_clip = final_clip.set_audio(mixed_audio)
                        self.update_progress("✅ 오디오와 배경 음악 믹싱 완료", 60)
                    except Exception as e:
                        self.update_progress(f"⚠️ 오디오 믹싱 실패: {e}", 60)
            
            # 자막 처리
            self.update_progress("자막 처리 중...", 70)
            
            if subtitles:
                # 사용자 제공 자막이 있는 경우 (STT나 외부 자막 파일에서 가져온 경우)
                try:
                    # 비디오 크기 가져오기
                    video_width, video_height = final_clip.size
                    
                    # 자막 옵션 검사 및 로그 출력
                    if subtitle_options and 'font_size' in subtitle_options:
                        self.update_progress(f"자막 옵션 전달 확인: 폰트 크기={subtitle_options['font_size']}", None)
                    else:
                        self.update_progress("자막 옵션이 없거나 폰트 크기가 지정되지 않았습니다. 기본값 사용", None)
                        if not subtitle_options:
                            subtitle_options = {}
                        # 기본값은 create_subtitle_clips 메소드에서 처리되므로 여기서는 빈 객체 생성만
                    
                    # 자막 클립 생성
                    subtitle_clips = self.create_subtitle_clips(
                        subtitles, 
                        video_width, 
                        video_height, 
                        audio_duration,
                        subtitle_options
                    )
                    
                    if subtitle_clips:
                        # 배경 비디오와 자막 클립을 합성
                        self.update_progress(f"{len(subtitle_clips)}개의 자막 클립 합성 중...", 75)
                        clips_to_composite = [final_clip] + subtitle_clips
                        final_clip = CompositeVideoClip(clips_to_composite, size=(video_width, video_height))
                        self.update_progress("✅ 자막 합성 완료", 78)
                    else:
                        self.update_progress("⚠️ 사용 가능한 자막 클립이 없습니다", 75)
                except Exception as e:
                    self.update_progress(f"⚠️ 자막 처리 중 오류 발생: {e}", None)
                    import traceback
                    self.update_progress(traceback.format_exc(), None)

            else:
                # subtitles가 없는 경우, 직접 텍스트에서 자막 생성 (텍스트 길이 비례 방식)
                try:
                    # 비디오 크기 가져오기
                    video_width, video_height = final_clip.size
                    
                    # 스크립트 내용 가져오기
                    script_content = script_content if script_content else ""
                    
                    # 자막 옵션 검사 및 로그 출력
                    if subtitle_options and 'font_size' in subtitle_options:
                        self.update_progress(f"텍스트 기반 자막 옵션 전달 확인: 폰트 크기={subtitle_options['font_size']}", None)
                    else:
                        self.update_progress("텍스트 기반 자막 옵션이 없거나 폰트 크기가 지정되지 않았습니다. 기본값 사용", None)
                        if not subtitle_options:
                            subtitle_options = {}
                        # 기본값은 create_subtitle_clips_from_text 메소드에서 처리되므로 여기서는 빈 객체 생성만
                    
                    # 직접 텍스트에서 자막 생성
                    self.update_progress("스크립트에서 직접 자막 생성 중...", 70)
                    subtitle_clips = self.create_subtitle_clips_from_text(
                        script_content,
                        video_width,
                        video_height,
                        audio_duration,
                        subtitle_options
                    )
                    
                    if subtitle_clips:
                        # 배경 비디오와 자막 클립을 합성
                        self.update_progress(f"{len(subtitle_clips)}개의 텍스트 기반 자막 클립 합성 중...", 75)
                        clips_to_composite = [final_clip] + subtitle_clips
                        final_clip = CompositeVideoClip(clips_to_composite, size=(video_width, video_height))
                        self.update_progress("✅ 텍스트 기반 자막 합성 완료", 78)
                    else:
                        self.update_progress("⚠️ 텍스트 기반 자막 생성 실패", 75)
                except Exception as e:
                    self.update_progress(f"⚠️ 텍스트 기반 자막 생성 중 오류 발생: {e}", 75)
                    import traceback
                    self.update_progress(traceback.format_exc(), None)
            
            # 최종 비디오 저장
            self.update_progress("비디오 파일 생성 시작", 80)
            
            # 진행 상황을 나타내는 콜백 함수
            def render_progress_callback(t):
                try:
                    if isinstance(t, tuple) and len(t) == 2:
                        current_time, total_time = t
                        percentage = int((current_time / total_time) * 100)
                    else:
                        percentage = int(t * 100)
                        current_time = t * audio_duration
                        total_time = audio_duration
                    
                    # 80%~100% 범위에서 진행 상황 표시
                    progress = 80 + (percentage / 100 * 20)
                    self.update_progress(f"비디오 렌더링 중: {percentage}%", progress)
                except Exception as e:
                    pass
                    
            try:
                # VideoFileClip을 사용하여 비디오 생성
                self.update_progress("비디오 파일 생성 중...", 90)
                final_clip.write_videofile(
                    output_path,
                    fps=24,
                    codec='libx264',
                    audio_codec='aac',
                    logger=None,
                    verbose=False,
                    ffmpeg_params=[
                        "-preset", "medium",
                        "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        "-b:v", "4000k",
                        "-profile:v", "high",
                        "-level", "4.0"
                    ]
                )
                self.update_progress("비디오 생성 완료!", 100)
                return output_path
            finally:
                # 모든 클립 자원 해제
                try:
                    if 'final_clip' in locals() and final_clip is not None:
                        final_clip.close()
                except:
                    pass
                
                try:
                    if 'video_clip' in locals() and video_clip is not None:
                        video_clip.close()
                except:
                    pass
                
                try:
                    if 'audio_clip' in locals() and audio_clip is not None:
                        audio_clip.close()
                except:
                    pass
                
                try:
                    if 'bgm_clip' in locals() and bgm_clip is not None:
                        bgm_clip.close()
                except:
                    pass
                
                # GC 강제 호출
                import gc
                gc.collect()
                
        except Exception as e:
            self.update_progress(f"비디오 생성 중 오류 발생: {e}", 100)
            logging.error(f"비디오 생성 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            
            # 오류 발생해도 자원 해제 시도
            try:
                if 'final_clip' in locals() and final_clip is not None:
                    final_clip.close()
                if 'video_clip' in locals() and video_clip is not None:
                    video_clip.close()
                if 'audio_clip' in locals() and audio_clip is not None:
                    audio_clip.close()
                if 'bgm_clip' in locals() and bgm_clip is not None:
                    bgm_clip.close()
            except:
                pass
            
            return None

    def _create_sample_background(self, duration=15):
        """단색 배경 비디오 생성 (지정된 길이)"""
        # 배경 색상 설정 (어두운 파란색 또는 검은색)
        background_colors = [
            (25, 25, 112),   # 미드나이트 블루
            (0, 0, 128),     # 네이비
            (0, 0, 0),       # 블랙
            (72, 61, 139),   # 다크 슬레이트 블루
        ]
        color = random.choice(background_colors)
        
        # 비디오 해상도 설정 (쇼츠 형식: 9:16 비율)
        width, height = 1080, 1920
        
        self.update_progress(f"샘플 배경 생성 중 (길이: {duration:.1f}초)...", None)
        
        try:
            # 단색 배경 클립 생성
            color_clip = ColorClip(size=(width, height), color=color, duration=duration)
            
            # 그라디언트를 추가할지 결정 (50% 확률)
            use_gradient = random.choice([True, False])
            
            if use_gradient:
                # 그라디언트 배경 추가
                try:
                    # PIL을 사용하여 그라디언트 이미지 생성
                    img = Image.new('RGB', (width, height), color=(0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    
                    # 그라디언트 색상 선택
                    color1 = color
                    color2 = tuple(max(0, min(255, c + random.randint(-50, 50))) for c in color)
                    
                    # 그라디언트 생성
                    for y in range(height):
                        # y 위치에 따른 색상 보간
                        r = int(color1[0] + (color2[0] - color1[0]) * y / height)
                        g = int(color1[1] + (color2[1] - color1[1]) * y / height)
                        b = int(color1[2] + (color2[2] - color1[2]) * y / height)
                        draw.line([(0, y), (width, y)], fill=(r, g, b))
                    
                    # 이미지를 임시 파일로 저장
                    temp_img_path = os.path.join(self.temp_dir, f"temp_gradient_{int(time.time())}.png")
                    img.save(temp_img_path)
                    
                    # 이미지로부터 비디오 생성
                    gradient_clip = ImageClip(temp_img_path, duration=duration)
                    
                    # 임시 이미지 파일 삭제
                    try:
                        os.remove(temp_img_path)
                    except:
                        pass
                    
                    self.update_progress("그라디언트 배경 생성 완료", None)
                    return gradient_clip
                    
                except Exception as e:
                    self.update_progress(f"그라디언트 생성 실패: {str(e)}, 단색 배경 사용", None)
                    # 그라디언트 생성 실패 시 단색 배경 사용
                    return color_clip
            else:
                # 단색 배경 사용
                return color_clip
                
        except Exception as e:
            self.update_progress(f"샘플 배경 생성 오류: {str(e)}", None)
            
            # 더 안전한 방법으로 다시 시도
            try:
                self.update_progress("단순 검은색 배경으로 대체", None)
                return ColorClip(size=(width, height), color=(0, 0, 0), duration=duration)
            except:
                raise Exception("배경 비디오 생성 실패")

    def setup_external_services(self, pexels_api_key=None, jamendo_client_id=None):
        """외부 서비스 설정 (Pexels 및 Jamendo API)"""
        try:
            # 1. Pexels 다운로더 설정
            if pexels_api_key:
                self.update_progress(f"Pexels API 키 설정 중...", None)
                
                # Pexels 다운로더 모듈 임포트
                try:
                    from pexels_downloader import PexelsVideoDownloader
                    
                    # 배경 비디오 디렉토리
                    bg_video_dir = self.background_dir
                    
                    # 다운로더 초기화
                    self.pexels_downloader = PexelsVideoDownloader(
                        api_key=pexels_api_key,
                        progress_callback=self.update_progress,
                        offline_mode=False
                    )
                    
                    self.update_progress(f"✅ Pexels 다운로더 초기화 완료", None)
                except ImportError:
                    self.update_progress("⚠️ Pexels 다운로더 모듈을 찾을 수 없습니다.", None)
                except Exception as e:
                    self.update_progress(f"⚠️ Pexels 다운로더 초기화 오류: {str(e)}", None)
            else:
                self.update_progress("⚠️ Pexels API 키가 설정되지 않았습니다. 기본 배경 비디오만 사용됩니다.", None)
                
            # 2. Jamendo 음악 제공자 설정
            if jamendo_client_id:
                self.update_progress(f"Jamendo API 키 설정 중...", None)
                
                # Jamendo 제공자 모듈 임포트
                try:
                    from jamendo_music_provider import JamendoMusicProvider
                    
                    # 배경 음악 디렉토리
                    bg_music_dir = self.music_dir
                    
                    # 제공자 초기화
                    self.jamendo_provider = JamendoMusicProvider(
                        client_id=jamendo_client_id,
                        output_dir=bg_music_dir,
                        cache_dir=os.path.join(self.temp_dir, "jamendo_cache"),
                        progress_callback=self.update_progress,
                        pexels_downloader=self.pexels_downloader if hasattr(self, 'pexels_downloader') else None
                    )
                    
                    self.update_progress(f"✅ Jamendo 음악 제공자 초기화 완료", None)
                except ImportError:
                    self.update_progress("⚠️ Jamendo 제공자 모듈을 찾을 수 없습니다.", None)
                except Exception as e:
                    self.update_progress(f"⚠️ Jamendo 제공자 초기화 오류: {str(e)}", None)
            else:
                self.update_progress("⚠️ Jamendo Client ID가 설정되지 않았습니다. 기본 배경 음악만 사용됩니다.", None)
                
        except Exception as e:
            self.update_progress(f"⚠️ 외부 서비스 설정 중 오류 발생: {e}", None)
            import traceback
            traceback.print_exc()
            
        # 실패한 경우 None으로 설정
        if not hasattr(self, 'pexels_downloader'):
            self.pexels_downloader = None
            
        if not hasattr(self, 'jamendo_provider'):
            self.jamendo_provider = None

    def get_font_path(self, font_name=None, font_size=None):
        """폰트 경로 가져오기 (기본 폰트가 없으면 다운로드)"""
        # 폰트 디렉토리 설정
        font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
        os.makedirs(font_dir, exist_ok=True)
        
        # 기본 폰트 파일명 설정
        base_font_name = "NanumGothic.ttf"
        default_font_path = os.path.join(font_dir, base_font_name)
        
        # 요청된 폰트 이름이 있으면 해당 폰트 찾기
        if font_name:
            requested_font_path = os.path.join(font_dir, font_name)
            if os.path.exists(requested_font_path):
                self.update_progress(f"지정된 폰트 사용: {requested_font_path}", None)
                return requested_font_path
        
        # 기본 폰트가 있는지 확인
        if os.path.exists(default_font_path):
            self.update_progress(f"기본 나눔고딕 폰트 사용: {default_font_path}", None)
            return default_font_path
        
        # 기본 폰트가 없으면 다운로드
        try:
            self.update_progress(f"기본 폰트 파일이 없습니다. 나눔고딕 폰트를 다운로드합니다... 경로: {default_font_path}", None)
            
            # 폰트 URL 설정 (CDN에서 직접 다운로드)
            font_url = "https://cdn.jsdelivr.net/gh/fonts-archive/NanumGothic/NanumGothic.ttf"
            
            # 직접 다운로드
            import requests
            try:
                self.update_progress(f"나눔고딕 폰트 직접 다운로드 시도: {font_url}", None)
                response = requests.get(font_url)
                with open(default_font_path, 'wb') as f:
                    f.write(response.content)
                
                if os.path.exists(default_font_path):
                    self.update_progress(f"✅ 나눔고딕 폰트 직접 다운로드 완료: {default_font_path}", None)
                    return default_font_path
            except Exception as direct_download_error:
                self.update_progress(f"⚠️ 직접 다운로드 실패: {str(direct_download_error)}", None)
                
                # 기존 방식으로 시도 (ZIP 파일 다운로드)
                font_url = "https://github.com/naver/nanumfont/blob/master/downloads/NanumFont_TTF_ALL.zip?raw=true"
                
                # 임시 파일로 다운로드
                import zipfile
                import tempfile
                
                # 임시 디렉토리 생성
                temp_dir = tempfile.mkdtemp()
                zip_path = os.path.join(temp_dir, "nanumfont.zip")
                
                # 폰트 ZIP 파일 다운로드
                response = requests.get(font_url, stream=True)
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # ZIP 파일 압축 해제
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # 나눔고딕 폰트 파일 찾아서 복사
                found = False
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.lower() == base_font_name.lower():
                            import shutil
                            src_path = os.path.join(root, file)
                            shutil.copy2(src_path, default_font_path)
                            found = True
                            break
                    if found:
                        break
                
                # 임시 디렉토리 정리
                import shutil
                shutil.rmtree(temp_dir)
                
                if os.path.exists(default_font_path):
                    self.update_progress(f"✅ 나눔고딕 폰트 ZIP 다운로드 완료: {default_font_path}", None)
                    return default_font_path
                else:
                    # 대체 방법: 직접 GitHub에서 단일 파일 다운로드
                    alt_font_url = "https://raw.githubusercontent.com/naver/nanumfont/master/releases/NanumGothic.ttf"
                    response = requests.get(alt_font_url)
                    with open(default_font_path, 'wb') as f:
                        f.write(response.content)
                    
                    if os.path.exists(default_font_path):
                        self.update_progress(f"✅ 나눔고딕 폰트 대체 다운로드 완료: {default_font_path}", None)
                        return default_font_path
                
        except Exception as e:
            self.update_progress(f"⚠️ 폰트 다운로드 실패: {str(e)}", None)
            
            # 시스템 폰트 찾기 시도
            try:
                # PIL에서 기본 폰트 사용
                from PIL import ImageFont
                default_font = ImageFont.load_default()
                self.update_progress("⚠️ 시스템 기본 폰트 사용", None)
                return None
            except:
                self.update_progress("⚠️ 사용 가능한 폰트가 없습니다", None)
                return None
        
        return default_font_path

    def _wrap_text(self, text, max_chars_per_line=30, font_size=None):
        """긴 텍스트를 자동으로 줄바꿈합니다.
        
        Args:
            text: 줄바꿈할 텍스트
            max_chars_per_line: 한 줄에 들어갈 최대 글자 수 (기본값)
            font_size: 폰트 크기. 이 값이 제공되면 줄당 최대 글자 수가 동적으로 조정됨
        
        Returns:
            줄바꿈된 텍스트
        """
        if not text:
            return ""
            
        # 폰트 크기에 따라 max_chars_per_line 동적 조정
        if font_size:
            # 기준 폰트 크기 (이 크기에서 max_chars_per_line이 30)
            BASE_FONT_SIZE = 70
            
            # 폰트 크기가 클수록 한 줄에 들어갈 수 있는 글자 수 감소
            # 폰트 크기와 글자 수는 반비례 관계 (더 강력한 반비례 관계 적용)
            size_ratio = (BASE_FONT_SIZE / font_size) ** 1.2  # 지수를 1.2로 증가시켜 더 적극적인 줄바꿈
            adjusted_chars = int(max_chars_per_line * size_ratio)
            
            # 최소 및 최대 글자 수 제한 (최소값을 더 작게 조정)
            max_chars_per_line = max(10, min(adjusted_chars, 40))
            
            self.update_progress(f"폰트 크기({font_size}px)에 맞게 줄당 글자 수 조정: {max_chars_per_line}자", None)
        
        # 이미 줄바꿈 되어 있는 경우 그대로 반환
        if '\n' in text and max([len(line) for line in text.split('\n')]) <= max_chars_per_line:
            return text
            
        words = text.split()
        lines = []
        current_line = ""
        
        # 한글 포함 여부 확인 (한글이 있으면 더 짧게 자름)
        has_korean = any('\uAC00' <= char <= '\uD7A3' for char in text)
        if has_korean:
            # 한글 텍스트는 줄당 글자 수를 추가로 줄임 (비율 증가)
            max_chars_per_line = int(max_chars_per_line * 0.8)  # 0.85에서 0.8로 변경
            self.update_progress(f"한글 텍스트 감지, 줄당 글자 수 재조정: {max_chars_per_line}자", None)
        
        for word in words:
            # 개행 문자가 있는 경우 처리
            if '\n' in word:
                subwords = word.split('\n')
                for i, subword in enumerate(subwords):
                    if i == 0:  # 첫 번째 하위 단어
                        if current_line:
                            test_line = current_line + " " + subword if current_line else subword
                            if len(test_line) <= max_chars_per_line:
                                current_line = test_line
                            else:
                                lines.append(current_line)
                                current_line = subword
                        else:
                            current_line = subword
                        
                        if i < len(subwords) - 1:  # 마지막이 아니면 줄 추가
                            lines.append(current_line)
                            current_line = ""
                    else:  # 후속 하위 단어
                        if current_line:
                            test_line = current_line + " " + subword if current_line else subword
                            if len(test_line) <= max_chars_per_line:
                                current_line = test_line
                            else:
                                lines.append(current_line)
                                current_line = subword
                        else:
                            current_line = subword
                continue
                
            # 일반 단어 처리
            test_line = current_line + " " + word if current_line else word
            
            # 현재 줄에 단어 추가 시 최대 길이를 초과하는지 확인
            if len(test_line) <= max_chars_per_line:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        
        # 마지막 줄 추가
        if current_line:
            lines.append(current_line)
            
        # 한글의 경우 더 짧게 잘라줍니다 (가독성 향상)
        refined_lines = []
        for line in lines:
            # 한글 포함 여부 확인
            has_korean = any('\uAC00' <= char <= '\uD7A3' for char in line)
            
            if has_korean and len(line) > max_chars_per_line - 10:
                # 한글 텍스트는 더 짧게 (상대적으로 더 복잡하므로)
                mid_point = len(line) // 2
                
                # 공백을 기준으로 자연스럽게 분할 시도
                split_point = line.rfind(' ', 0, mid_point + 5)
                if split_point == -1:
                    split_point = line.find(' ', mid_point - 5)
                
                if split_point != -1:
                    refined_lines.append(line[:split_point])
                    refined_lines.append(line[split_point+1:])
                else:
                    refined_lines.append(line)
            else:
                refined_lines.append(line)
        
        return '\n'.join(refined_lines)

    def _create_text_image(self, text, size=(640, 200), font_path=None, font_size=None, 
                     text_color=(255, 255, 255), bg_color=None, outline_color=(0, 0, 0), 
                     outline_width=2, align='center'):
        """텍스트 이미지 생성 (PIL 사용)"""
        if not text:
            return None
            
        width, height = size
        
        # 공백이나 줄바꿈을 제외한 텍스트가 있는지 확인
        text = text.strip()
        if not text:
            return None
        
        # 배경 설정: 투명(None)이거나 지정된 색상
        if bg_color is None:
            # RGBA 모드로 투명한 배경 생성
            img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        else:
            # RGB 모드로 지정된 배경색 사용
            img = Image.new('RGB', (width, height), bg_color)
        
        draw = ImageDraw.Draw(img)
        
        # 폰트 설정
        if not font_path:
            font_path = self.get_font_path(font_size=font_size)
        
        # 폰트 크기 설정 - font_size가 None인 경우에만 자동 결정
        current_font_size = font_size
        if not current_font_size:
            # 줄 수에 따라 폰트 크기 자동 조정
            line_count = text.count('\n') + 1
            
            # 한글 텍스트 여부 확인 (한글은 더 큰 폰트 필요)
            has_korean = any('\uAC00' <= char <= '\uD7A3' for char in text)
            
            if line_count <= 1:
                current_font_size = 46 if has_korean else 52
            elif line_count == 2:
                current_font_size = 42 if has_korean else 48
            elif line_count == 3:
                current_font_size = 38 if has_korean else 44
            else:
                current_font_size = 34 if has_korean else 40
            
            # 텍스트가 매우 짧으면 더 큰 폰트 사용
            if len(text) < 15:
                current_font_size += 8
        
        # 디버그 메시지 추가
        self.update_progress(f"텍스트 이미지 생성 중 - 폰트 크기: {current_font_size}, 색상: {text_color}", None)
        
        # 폰트 로드 및 텍스트 크기 검사를 위한 초기 설정
        try:
            if font_path:
                font = ImageFont.truetype(font_path, current_font_size)
            else:
                # 기본 폰트 사용 - PIL 내장 폰트는 한글을 지원하지 않음
                # 시스템 폰트 중 한글 지원 폰트 찾기 시도
                try:
                    # Windows에서 맑은 고딕 폰트 사용 시도
                    windows_font_path = "C:\\Windows\\Fonts\\malgun.ttf"
                    if os.path.exists(windows_font_path):
                        font = ImageFont.truetype(windows_font_path, current_font_size)
                        self.update_progress("맑은 고딕 폰트 사용", None)
                    else:
                        # 다른 시스템 폰트 시도
                        font = ImageFont.load_default()
                        self.update_progress("⚠️ 한글 지원 폰트를 찾을 수 없어 기본 폰트 사용 (한글이 제대로 표시되지 않을 수 있음)", None)
                except:
                    font = ImageFont.load_default()
                    self.update_progress("⚠️ 기본 폰트 사용 (한글이 제대로 표시되지 않을 수 있음)", None)
                
        except Exception as e:
            self.update_progress(f"폰트 로드 실패: {str(e)}, 시스템 폰트 사용 시도", None)
            try:
                # Windows에서 맑은 고딕 폰트 사용 시도
                windows_font_path = "C:\\Windows\\Fonts\\malgun.ttf"
                if os.path.exists(windows_font_path):
                    font = ImageFont.truetype(windows_font_path, current_font_size)
                    self.update_progress("맑은 고딕 폰트 사용", None)
                else:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
        
        # 텍스트 크기 확인 및 폰트 크기 자동 조정 (새로 추가된 코드)
        try:
            lines = text.split('\n')
            max_line_width = 0
            
            # 가장 긴 줄의 너비 측정
            for line in lines:
                if line.strip():
                    try:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        line_width = bbox[2] - bbox[0]
                        max_line_width = max(max_line_width, line_width)
                    except UnicodeEncodeError:
                        # 인코딩 오류 발생 시 대체 텍스트 사용
                        self.update_progress(f"⚠️ 한글 텍스트 처리 오류, 대체 텍스트로 표시됩니다", None)
                        bbox = draw.textbbox((0, 0), "텍스트 표시 오류", font=font)
                        line_width = bbox[2] - bbox[0]
                        max_line_width = max(max_line_width, line_width)
            
            # 텍스트가 너무 넓으면 폰트 크기 자동 조정
            if max_line_width > width - 20:  # 여백 20px 고려
                # 원래 폰트 크기를 저장
                original_font_size = current_font_size
                
                # 줄어든 비율로 폰트 크기 조정
                reduction_ratio = (width - 20) / max_line_width
                current_font_size = int(current_font_size * reduction_ratio * 0.95)  # 5% 추가 안전 마진
                
                # 최소 크기 제한
                current_font_size = max(current_font_size, 22)
                
                self.update_progress(f"텍스트가 너무 넓어 폰트 크기 조정: {original_font_size}px → {current_font_size}px", None)
                
                # 새 폰트 크기로 폰트 다시 로드
                try:
                    if font_path:
                        font = ImageFont.truetype(font_path, current_font_size)
                    elif os.path.exists("C:\\Windows\\Fonts\\malgun.ttf"):
                        font = ImageFont.truetype("C:\\Windows\\Fonts\\malgun.ttf", current_font_size)
                    else:
                        font = ImageFont.load_default()
                except Exception as e:
                    self.update_progress(f"폰트 재로드 실패: {str(e)}", None)
                    if os.path.exists("C:\\Windows\\Fonts\\malgun.ttf"):
                        try:
                            font = ImageFont.truetype("C:\\Windows\\Fonts\\malgun.ttf", current_font_size)
                        except:
                            font = ImageFont.load_default()
                    else:
                        font = ImageFont.load_default()
                    
                # 텍스트 줄바꿈 다시 적용 (필요한 경우)
                if len(lines) <= 2 and max_line_width > width - 20:
                    # 기존 줄바꿈이 충분하지 않은 경우, 더 적극적으로 줄바꿈 재적용
                    wrapped_text = self._wrap_text(text, font_size=current_font_size)
                    if wrapped_text != text:
                        text = wrapped_text
                        lines = text.split('\n')
                        self.update_progress(f"폰트 크기 조정 후 줄바꿈 다시 적용: {len(lines)}줄", None)
            
            # 텍스트 위치 계산 (중앙 정렬)
            line_heights = []
            for line in lines:
                if line.strip():
                    try:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        line_height = bbox[3] - bbox[1]
                        line_heights.append(line_height)
                    except UnicodeEncodeError:
                        # 인코딩 오류 발생 시 기본 높이 사용
                        line_heights.append(current_font_size + 10)
                else:
                    # 빈 줄은 폰트 크기의 절반 높이로 처리
                    line_heights.append(current_font_size // 2)
            
            # 줄 간격
            line_spacing = 8  # 줄 간격 (픽셀)
            total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
            
            # 높이 자동 조정 - 텍스트가 기존 높이를 초과하는 경우
            if total_text_height > height - 40:  # 상하 여백 20px씩 고려
                # 새 이미지 높이 계산 (텍스트 높이 + 상하 여백)
                new_height = total_text_height + 40
                self.update_progress(f"텍스트가 너무 높아 이미지 높이 자동 조정: {height}px → {new_height}px", None)
                
                # 새 크기로 이미지 다시 생성
                if bg_color is None:
                    img = Image.new('RGBA', (width, new_height), (0, 0, 0, 0))
                else:
                    img = Image.new('RGB', (width, new_height), bg_color)
                
                draw = ImageDraw.Draw(img)
                height = new_height
            
            # 텍스트 시작 Y 위치 (세로 중앙 정렬)
            current_y = (height - total_text_height) // 2
            
            # 아웃라인이 있는 텍스트 그리기
            for i, line in enumerate(lines):
                if not line.strip():
                    current_y += line_heights[i]  # 빈 줄 높이 적용
                    continue
                    
                # 가로 위치 계산 (정렬 방식에 따라)
                try:
                    if align == 'center':
                        bbox = draw.textbbox((0, 0), line, font=font)
                        text_width = bbox[2] - bbox[0]
                        x = (width - text_width) // 2
                    elif align == 'left':
                        x = 10  # 왼쪽 여백
                    elif align == 'right':
                        bbox = draw.textbbox((0, 0), line, font=font)
                        text_width = bbox[2] - bbox[0]
                        x = width - text_width - 10  # 오른쪽 여백
                    else:  # 기본값 center
                        bbox = draw.textbbox((0, 0), line, font=font)
                        text_width = bbox[2] - bbox[0]
                        x = (width - text_width) // 2
                except UnicodeEncodeError:
                    # 인코딩 오류 발생 시 중앙 정렬로 강제 설정
                    x = width // 2
                    line = "자막 표시 오류"  # 대체 텍스트
                
                try:
                    # 아웃라인 그리기 (간소화된 방식)
                    if outline_width > 0 and outline_color:
                        # 8방향 아웃라인
                        for offset_x in range(-outline_width, outline_width + 1):
                            for offset_y in range(-outline_width, outline_width + 1):
                                if offset_x == 0 and offset_y == 0:
                                    continue  # 중앙은 건너뛰기
                                draw.text((x + offset_x, current_y + offset_y), line, font=font, fill=outline_color)
                    
                    # 메인 텍스트 그리기 - 반드시 지정된 text_color 사용
                    draw.text((x, current_y), line, font=font, fill=text_color)
                except Exception as e:
                    self.update_progress(f"텍스트 그리기 실패: {str(e)}", None)
                    try:
                        # 대체 텍스트 사용 시도
                        draw.text((x, current_y), "자막 오류", font=font, fill=text_color)
                    except:
                        pass
                
                # 다음 줄 위치 계산
                current_y += line_heights[i] + line_spacing
        except Exception as e:
            self.update_progress(f"텍스트 이미지 생성 실패: {str(e)}", None)
            import traceback
            self.update_progress(traceback.format_exc(), None)
            
            # 오류 발생 시 기본 이미지 반환
            try:
                # 오류 메시지를 표시하는 간단한 이미지 생성
                if bg_color is None:
                    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                else:
                    img = Image.new('RGB', (width, height), bg_color)
                draw = ImageDraw.Draw(img)
                draw.text((width//2, height//2), "자막 오류", font=ImageFont.load_default(), fill=text_color, anchor="mm")
            except:
                # 최후의 수단으로 빈 이미지 반환
                img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        
        # 이미지 반환
        return img

    def create_subtitle_clips(self, subtitles, video_width, video_height, video_duration, subtitle_options=None):
        """자막 클립 리스트 생성
        
        Args:
            subtitles: 자막 데이터 리스트 (start_time, end_time, text 키를 가진 딕셔너리 리스트)
            video_width: 비디오 너비
            video_height: 비디오 높이
            video_duration: 비디오 길이 (초)
            subtitle_options: 자막 옵션 (폰트, 크기, 색상 등)
        
        Returns:
            자막 클립 리스트
        """
        if not subtitles:
            self.update_progress("자막 데이터가 없습니다.", None)
            return []
            
        self.update_progress(f"{len(subtitles)}개의 자막 처리 중...", None)
        subtitle_clips = []
        
        # 자막 옵션 디버그 정보 추가
        self.update_progress(f"전달된 자막 옵션: {subtitle_options}", None)
        
        # 자막 옵션 설정
        if subtitle_options is None:
            subtitle_options = {}
            self.update_progress("자막 옵션이 없거나 폰트 크기가 지정되지 않았습니다. 기본값 사용", None)
            
        # 기본값 설정 - 옵션이 없는 경우에만 기본값 사용
        if "font_size" in subtitle_options:
            font_size = subtitle_options.get("font_size")
            self.update_progress(f"사용자가 지정한 폰트 크기를 사용합니다: {font_size}", None)
        else:
            font_size = 70  # 기본값 유지
            self.update_progress(f"폰트 크기가 지정되지 않아 기본값 사용: {font_size}", None)
            
        text_color = subtitle_options.get("text_color", (255, 255, 255))  # 기본 흰색
        outline_color = subtitle_options.get("outline_color", (0, 0, 0))  # 기본 검은색
        outline_width = subtitle_options.get("outline_width", 2)
        
        # 자막 위치 설정
        position = subtitle_options.get("position", "bottom")  # 기본값: 하단
        self.update_progress(f"자막 위치: {position}", None)
        
        # 디버그 정보: 사용되는 자막 옵션 출력
        self.update_progress(f"자막 옵션 정보 - 폰트 크기: {font_size}, 색상: {text_color}", None)
        
        for i, subtitle in enumerate(subtitles):
            try:
                # 자막 데이터에서 정보 추출
                start_time = subtitle.get("start_time", 0)
                end_time = subtitle.get("end_time", start_time + 2)
                text = subtitle.get("text", "")
                
                # 텍스트가 없으면 건너뛰기
                if not text or text.strip() == "":
                    continue
                
                # 시작/종료 시간 유효성 검사
                if end_time <= start_time or start_time < 0 or end_time > video_duration:
                    self.update_progress(f"⚠️ 유효하지 않은 자막 시간: {start_time}s - {end_time}s, 건너뜁니다", None)
                    continue
                
                # 진행 상황 업데이트
                self.update_progress(f"자막 {i+1}/{len(subtitles)} 처리 중: '{text[:30]}...' ({start_time:.1f}s - {end_time:.1f}s)", None)
                
                # 텍스트 자동 줄바꿈
                wrapped_text = self._wrap_text(text, font_size=font_size)
                
                # 텍스트 이미지 생성
                # 비디오 너비에 맞추되 여백 고려 (한글 텍스트를 위해 넉넉한 높이)
                # 비디오 너비에서 여백을 줄여 더 넓은 영역 사용
                text_width = video_width - 40  # 100에서 40으로 줄임: 양쪽 20px씩만 여백으로 사용
                txt_img = self._create_text_image(
                    wrapped_text, 
                    size=(text_width, 500),  # 텍스트 너비 증가, 높이 유지
                    text_color=text_color,
                    outline_color=outline_color,
                    outline_width=outline_width,
                    font_size=font_size,
                    align='center'
                )
                
                if txt_img is None:
                    self.update_progress(f"⚠️ 자막 이미지 생성 실패: '{text[:30]}...'", None)
                    continue
                
                # 이미지를 MoviePy 클립으로 변환
                duration = end_time - start_time
                self.update_progress(f"자막 이미지 변환 중: 폰트 크기 {font_size} 적용됨", None)
                txt_clip = ImageClip(np.array(txt_img), duration=duration)
                
                # 위치 조정 (화면 중앙이 아닌 하단이나 상단에 배치)
                if position == "top":
                    # 상단 위치 (상단에서 15% 지점)
                    y_position = video_height * 0.15
                    txt_clip = txt_clip.set_position(('center', y_position))
                elif position == "bottom":
                    # 하단 위치 (하단에서 15% 지점)
                    y_position = video_height * 0.85 - txt_img.height
                    txt_clip = txt_clip.set_position(('center', y_position))
                elif position == "center_bottom":
                    # 중앙 하단 위치 (중앙에서 20% 아래)
                    y_position = video_height * 0.7 - txt_img.height / 2
                    txt_clip = txt_clip.set_position(('center', y_position))
                else:
                    # 기본: 화면 중앙 하단 (중앙에서 20% 아래)
                    y_position = video_height * 0.7 - txt_img.height / 2
                    txt_clip = txt_clip.set_position(('center', y_position))
                
                # 부드러운 페이드인/아웃 효과 추가
                fade_duration = min(0.5, duration / 4)  # 페이드 지속 시간은 자막 지속 시간의 1/4, 최대 0.5초
                txt_clip = txt_clip.fadein(fade_duration).fadeout(fade_duration)
                
                # 타이밍 설정
                txt_clip = txt_clip.set_start(start_time).set_end(end_time)
                
                # 자막 클립 추가
                subtitle_clips.append(txt_clip)
                self.update_progress(f"✅ 자막 {i+1} 생성 완료", None)
                
            except Exception as e:
                self.update_progress(f"⚠️ 자막 생성 중 오류: {str(e)}", None)
                import traceback
                self.update_progress(traceback.format_exc(), None)
                # 개별 자막 실패 시에도 계속 진행
                continue
        
        return subtitle_clips

    def create_subtitle_clips_from_text(self, full_text, video_width, video_height, video_duration, subtitle_options=None):
        """텍스트 길이 기반으로 자막 클립 생성 (첨부된 video_creator_v02.py 방식)
        
        Args:
            full_text: 전체 스크립트 텍스트
            video_width: 비디오 너비
            video_height: 비디오 높이
            video_duration: 비디오 길이 (초)
            subtitle_options: 자막 옵션 (폰트, 크기, 색상 등)
            
        Returns:
            자막 클립 리스트
        """
        if not full_text or not full_text.strip():
            self.update_progress("자막 텍스트가 없습니다.", None)
            return []
            
        subtitle_clips = []
        
        # 자막 옵션 설정
        if subtitle_options is None:
            subtitle_options = {}
            
        # 옵션 기본값 설정
        if "font_size" in subtitle_options:
            font_size = subtitle_options.get("font_size")
            self.update_progress(f"텍스트 기반 자막 - 사용자가 지정한 폰트 크기를 사용합니다: {font_size}", None)
        else:
            font_size = 70  # 기본값 유지
            self.update_progress(f"텍스트 기반 자막 - 폰트 크기가 지정되지 않아 기본값 사용: {font_size}", None)
            
        text_color = subtitle_options.get("text_color", (255, 255, 255))  # 기본 흰색
        outline_color = subtitle_options.get("outline_color", (0, 0, 0))  # 기본 검은색
        outline_width = subtitle_options.get("outline_width", 2)
        
        # 자막 위치 설정
        position = subtitle_options.get("position", "bottom")  # 기본값: 하단
        
        # 디버그 정보: 사용되는 자막 옵션 출력
        self.update_progress(f"텍스트 기반 자막 옵션 정보 - 폰트 크기: {font_size}, 색상: {text_color}, 위치: {position}", None)
        
        try:
            # 전체 텍스트를 문장 단위로 분할
            sentences = re.split(r'(?<=[.!?])\s+', full_text)
            
            # 빈 문장 제거
            sentences = [s.strip() for s in sentences if s.strip()]
            
            self.update_progress(f"{len(sentences)}개 문장으로 분할됨", None)
            
            # 비디오 길이에 따라 문장별 지속 시간 계산
            total_chars = sum(len(s) for s in sentences)
            avg_duration = video_duration / total_chars
            
            current_time = 0
            
            for i, sentence in enumerate(sentences):
                # 문장 길이에 비례하여 지속 시간 계산
                char_count = len(sentence)
                duration = char_count * avg_duration
                
                # 최소 지속 시간 보장 (너무 짧은 문장도 최소한 볼 수 있게)
                duration = max(1.5, duration)
                
                # 너무 긴 문장은 제한 (한 문장이 너무 오래 표시되지 않게)
                duration = min(7.0, duration)
                
                start_time = current_time
                end_time = start_time + duration
                
                # 비디오 길이 초과 시 조정
                if end_time > video_duration:
                    end_time = video_duration
                    
                # 진행 상황 업데이트
                self.update_progress(f"자막 {i+1}/{len(sentences)} 처리 중: '{sentence[:30]}...' ({start_time:.1f}s - {end_time:.1f}s)", None)
                
                # 텍스트 자동 줄바꿈
                wrapped_text = self._wrap_text(sentence, font_size=font_size)
                
                # 텍스트 이미지 생성 (너비를 더 넓게 사용)
                text_width = video_width - 40  # 100에서 40으로 줄임: 양쪽 20px씩만 여백으로 사용
                txt_img = self._create_text_image(
                    wrapped_text, 
                    size=(text_width, 500),
                    text_color=text_color,
                    outline_color=outline_color,
                    outline_width=outline_width,
                    font_size=font_size,
                    align='center'
                )
                
                if txt_img is None:
                    self.update_progress(f"⚠️ 자막 이미지 생성 실패: '{sentence[:30]}...'", None)
                    current_time = end_time
                    continue
                
                # 이미지를 MoviePy 클립으로 변환
                txt_clip = ImageClip(np.array(txt_img), duration=duration)
                
                # 위치 조정
                if position == "top":
                    # 상단 위치 (상단에서 15% 지점)
                    y_position = video_height * 0.15
                    txt_clip = txt_clip.set_position(('center', y_position))
                elif position == "bottom":
                    # 하단 위치 (하단에서 15% 지점)
                    y_position = video_height * 0.85 - txt_img.height
                    txt_clip = txt_clip.set_position(('center', y_position))
                elif position == "center_bottom":
                    # 중앙 하단 위치 (중앙에서 20% 아래)
                    y_position = video_height * 0.7 - txt_img.height / 2
                    txt_clip = txt_clip.set_position(('center', y_position))
                else:
                    # 기본: 화면 중앙 하단 (중앙에서 20% 아래)
                    y_position = video_height * 0.7 - txt_img.height / 2
                    txt_clip = txt_clip.set_position(('center', y_position))
                
                # 부드러운 페이드인/아웃 효과 추가
                fade_duration = min(0.3, duration / 4)  # 페이드 지속 시간은 지속 시간의 1/4, 최대 0.3초
                txt_clip = txt_clip.fadein(fade_duration).fadeout(fade_duration)
                
                # 타이밍 설정
                txt_clip = txt_clip.set_start(start_time).set_end(end_time)
                
                # 자막 클립 추가
                subtitle_clips.append(txt_clip)
                
                # 다음 문장 시작 시간 업데이트
                current_time = end_time
            
            self.update_progress(f"✅ 텍스트 기반 자막 {len(subtitle_clips)}개 생성 완료", None)
            
        except Exception as e:
            self.update_progress(f"⚠️ 텍스트 기반 자막 생성 중 오류: {str(e)}", None)
            import traceback
            self.update_progress(traceback.format_exc(), None)
        
        return subtitle_clips

    def create_template_video(self, video_path, title, subtitle_text=None, output_filename=None, description=None):
        """
        첨부된 그림과 같은 템플릿으로 비디오를 생성합니다.
        비디오는 세 영역으로 나뉘어집니다:
        1. 첫 번째 칸: 비디오 제목 (후킹한 제목, 글씨 색깔과 크기 자동 조절)
        2. 두 번째 칸: 생성된 비디오 영상
        3. 세 번째 칸: 비디오 설명 (세 번째 칸에 표시)

        Args:
            video_path (str): 사용할 비디오 파일의 경로
            title (str): 비디오 제목 (첫 번째 칸에 표시)
            subtitle_text (str, optional): 하단 자막에 표시될 텍스트 (선택 사항, 유지를 위한 매개변수)
            output_filename (str, optional): 출력 파일 이름. 기본값은 현재 시간을 기반으로 자동 생성됩니다.
            description (str, optional): 비디오 설명 (세 번째 칸에 표시)

        Returns:
            str: 생성된 비디오 파일의 경로
        """
        self.update_progress("템플릿 비디오 생성 시작...", 0)
        
        # 타임스탬프 생성 - 함수 초기에 항상 정의하여 모든 코드 경로에서 사용 가능하도록 함
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 언더스코어 제거 및 제목 정리 (개선된 버전)
        if title:
            # 확장자 제거 (여러 비디오 포맷 지원)
            for ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                if title.lower().endswith(ext):
                    title = title[:-len(ext)]
            
            # 특수 문자 제거 및 공백으로 변환 - 다운하이픈(_)도 제거
            title = re.sub(r'[_\-\.]', ' ', title)  # 언더스코어, 하이픈, 점을 공백으로 변환
            
            # 불필요한 공백 제거 (연속된 공백을 하나로 줄이고 앞뒤 공백 제거)
            title = ' '.join(title.split())
            
            # 첫 글자 대문자로 변환 (영어인 경우)
            if title and re.match(r'^[a-zA-Z]', title[0]):
                words = title.split()
                title = ' '.join(word.capitalize() if i == 0 or len(word) > 3 else word 
                              for i, word in enumerate(words))
        
        # 설명이 없는 경우 기본값 또는 자막 텍스트 사용
        if not description:
            if subtitle_text:
                description = subtitle_text  # 하위 호환성을 위해 subtitle_text를 기본값으로 사용
            else:
                description = "영상을 시청해 주셔서 감사합니다. 좋아요와 구독 부탁드립니다!"
        
        # description에서 '#Shorts' 태그 제거 (세 번째 칸에는 실제 설명만 표시)
        if description:
            # 해시태그 라인이나 단어 제거
            description = re.sub(r'#\w+', '', description)  # 모든 해시태그 제거
            description = re.sub(r'\n+', '\n', description)  # 여러 개의 연속된 줄바꿈을 하나로
            description = description.strip()  # 앞뒤 공백 제거
            
            # 설명을 한 줄로 요약하기
            try:
                # 만약 설명이 여러 줄이거나 너무 길다면, 일정 길이로 자르고 요약 형태로 만듦
                if '\n' in description or len(description) > 80:
                    # 첫 문장이나 첫 부분을 추출하여 요약으로 사용
                    first_sentence = description.split('.')[0].strip()
                    if len(first_sentence) > 60:
                        summary = first_sentence[:57] + "..."
                    else:
                        summary = first_sentence
                        
                    # "내용 요약" 문구 없이 요약만 사용
                    description = summary
                    
            except Exception as e:
                logging.warning(f"설명 요약 실패: {str(e)}")
                # 실패하면 원래 설명 사용
        
        if not output_filename:
            output_filename = f"template_video_{timestamp}.mp4"
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        # 임시 파일 목록 (나중에 삭제하기 위함)
        temp_files = []
        
        try:
            # 원본 비디오 로드
            video_clip = VideoFileClip(video_path)
            original_duration = video_clip.duration
            
            # 비디오 크기 (1080x1920 - 인스타그램 스토리/쇼츠 형식)
            canvas_width, canvas_height = 1080, 1920
            
            # 세 영역의 높이 계산 (전체 높이의 1/6, 4/6, 1/6)
            title_height = canvas_height // 6
            video_height = (canvas_height * 4) // 6
            subtitle_height = canvas_height // 6
            
            # PIL을 사용하여 이미지로 텍스트 렌더링
            from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
            import tempfile
            
            # 1. 제목 영역 생성 (첫 번째 칸) - 세련된 디자인으로 개선
            self.update_progress("제목 이미지 생성 중...", 10)
            
            # 제목 글자 크기 설정 (더 정교하게 개선) - 제목 길이에 따라 더 작은 크기로 조정
            font_size = 110  # 기본 글자 크기
            if len(title) > 10:
                font_size = 90
            if len(title) > 15:
                font_size = 70
            if len(title) > 20:
                font_size = 55
            if len(title) > 25:
                font_size = 45
            if len(title) > 30:
                font_size = 40
            if len(title) > 35:
                font_size = 35
            if len(title) > 40:
                font_size = 30
            
            # 폰트 파일 찾기 (한글 지원 필요)
            font_path = None
            
            # 시스템 폰트 경로 (OS별로 다름)
            system_font_paths = [
                os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts'),  # Windows
                '/usr/share/fonts',  # Linux
                '/System/Library/Fonts',  # Mac
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts'),  # 커스텀 경로
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts'),  # 상위 폴더
            ]
            
            # 폰트 후보 목록 (굵은 고딕체 폰트 우선)
            font_candidates = [
                'malgunbd.ttf',  # Windows 굵은 맑은 고딕 (한글)
                'NanumGothicBold.ttf',  # 나눔 고딕 볼드 (한글)
                'NanumBarunGothicBold.ttf',  # 나눔 바른 고딕 볼드 (한글)
                'KoPubWorldDotumBold.ttf',  # KoPubWorld 돋움체 볼드 (한글)
                'GodoB.ttf',  # 고도체 볼드 (한글)
                'GmarketSansBold.ttf',  # G마켓 산스체 볼드 (한글)
                'PretendardBold.ttf',  # 프리텐다드 볼드 (한글)
                'BMDOHYEON.ttf',  # 배달의민족 도현체 (한글)
                'ONEMobileBold.ttf',  # 원 모바일 볼드 (한글)
                'ArialBold.ttf',  # Arial 볼드 (영문)
                'segoeui.ttf',  # Segoe UI (영문)
                'arial.ttf',  # Arial (영문)
                'malgun.ttf',  # 맑은 고딕 (한글)
                'SpoqaHanSansNeoBold.ttf',  # 스포카 한 산스 네오 볼드 (한글)
                'NotoSansKR-Bold.otf',  # 노토 산스 KR 볼드 (한글)
                # 추가 세련된 폰트들
                'BlackHanSans-Regular.ttf',  # 블랙 한 산스 (한글 - 두껍고 강렬한 느낌)
                'GmarketSansTTFBold.ttf',  # G마켓 산스 볼드 (한글)
                'SDSamliphopangcheTTFOutline.ttf',  # 삼립호빵체 아웃라인 (한글)
                'YESSVGOTHTBold.ttf',  # 예스 고딕 볼드 (한글)
                'LeferiPoint-BlackA.ttf',  # 레페리 포인트 블랙 (한글)
            ]
            
            try:
                # 모든 경로에서 모든 후보 폰트 시도
                for path in system_font_paths:
                    if os.path.exists(path):
                        for font_file in font_candidates:
                            font_full_path = os.path.join(path, font_file)
                            if os.path.exists(font_full_path):
                                try:
                                    # 폰트 로드 테스트
                                    test_font = ImageFont.truetype(font_full_path, 20)
                                    font_path = font_full_path
                                    self.update_progress(f"폰트 로드 성공: {os.path.basename(font_full_path)}", None)
                                    break
                                except Exception as e:
                                    continue
                    
                    # 폰트를 찾았으면 더 이상 검색 안 함
                    if font_path:
                        break
            except Exception as e:
                logging.error(f"폰트 찾기 오류: {str(e)}")
            
            # 세련된 제목 이미지 생성 (더 화려한 그라데이션 배경으로 개선)
            title_img = Image.new('RGB', (canvas_width, title_height), color=(0, 0, 0))
            draw = ImageDraw.Draw(title_img)
            
            # 세련된 그라데이션 배경 (검정→짙은 주황/빨강 그라데이션)
            for y in range(title_height):
                # 상단에서 하단으로 색상 변화
                progress = y / title_height
                # 검정에서 짙은 주황/빨강 계열로 그라데이션 (첨부 이미지와 유사하게)
                r = int(15 + (60 * progress))
                g = int(5 + (15 * progress))
                b = int(5 + (5 * progress))
                draw.line([(0, y), (canvas_width, y)], fill=(r, g, b))
            
            try:
                # 한글 폰트로 텍스트 그리기 - 고급스러운 스타일 적용
                if font_path:
                    title_font = ImageFont.truetype(font_path, font_size)
                    
                    # 텍스트 길이 확인 및 줄바꿈 처리
                    try:
                        if hasattr(title_font, 'getbbox'):
                            text_width = title_font.getbbox(title)[2]
                        else:
                            text_width = title_font.getlength(title)
                    except:
                        # 폴백: 글자 수에 따른 예상 너비
                        text_width = len(title) * (font_size * 0.6)
                        
                    # 텍스트가 너무 길면 두 줄로 나눔
                    if text_width > canvas_width - 40:  # 좌우 여백 20px씩 고려
                        words = title.split()
                        half_point = len(words) // 2
                        title_line1 = ' '.join(words[:half_point])
                        title_line2 = ' '.join(words[half_point:])
                        
                        # 밝고 강렬한 주황/빨강 텍스트 색상 - 첨부 이미지와 유사하게
                        text_color = (255, 80, 0)  # 밝은 주황/빨강 색상
                        
                        # 줄마다 위치 계산
                        try:
                            if hasattr(title_font, 'getbbox'):
                                line1_width = title_font.getbbox(title_line1)[2]
                                line2_width = title_font.getbbox(title_line2)[2]
                            else:
                                line1_width = title_font.getlength(title_line1)
                                line2_width = title_font.getlength(title_line2)
                        except:
                            line1_width = len(title_line1) * (font_size * 0.6)
                            line2_width = len(title_line2) * (font_size * 0.6)
                            
                        x1_position = (canvas_width - line1_width) // 2
                        x2_position = (canvas_width - line2_width) // 2
                        
                        # 줄간격 조정 - 2줄 텍스트를 위한 공간 계산
                        line_spacing = font_size * 0.3
                        y1_position = (title_height // 2) - int(font_size + line_spacing/2)
                        y2_position = (title_height // 2) + int(line_spacing/2)
                        
                        # 텍스트 그림자 효과 향상
                        shadow_offset = 3
                        
                        # 첫 번째 줄 그림자
                        for offset in range(1, shadow_offset+1):
                            shadow_color = (15-offset*2, 5-offset, 2)
                            draw.text((x1_position + offset, y1_position + offset), 
                                    title_line1, fill=shadow_color, font=title_font)
                        
                        # 첫 번째 줄 메인 텍스트
                        draw.text((x1_position, y1_position), 
                                title_line1, fill=text_color, font=title_font)
                        
                        # 두 번째 줄 그림자
                        for offset in range(1, shadow_offset+1):
                            shadow_color = (15-offset*2, 5-offset, 2)
                            draw.text((x2_position + offset, y2_position + offset), 
                                    title_line2, fill=shadow_color, font=title_font)
                        
                        # 두 번째 줄 메인 텍스트
                        draw.text((x2_position, y2_position), 
                                title_line2, fill=text_color, font=title_font)
                        
                    else:
                        # 한 줄로 충분한 경우 - 기존 방식대로 처리
                        # 밝고 강렬한 주황/빨강 텍스트 색상 (더 밝게) - 첨부 이미지와 유사하게
                        text_color = (255, 80, 0)  # 밝은 주황/빨강 색상
                        
                        # 텍스트 중앙 정렬                            
                        x_position = (canvas_width - text_width) // 2
                        
                        # 텍스트 그림자 효과 향상 - 첨부 이미지와 유사하게
                        shadow_offset = 3
                        
                        # 다중 그림자 효과 (더 깊은 느낌)
                        for offset in range(1, shadow_offset+1):
                            # 그림자 색상 (점점 어두워짐)
                            shadow_color = (15-offset*2, 5-offset, 2)
                            draw.text((x_position + offset, title_height // 2 - font_size // 2 + offset), 
                                    title, fill=shadow_color, font=title_font)
                        
                        # 메인 텍스트 (가장 위에 그려짐)
                        draw.text((x_position, title_height // 2 - font_size // 2), 
                                title, fill=text_color, font=title_font)
                else:
                    # 대체 방법: 간단한 텍스트 그리기
                    draw.text((10, 10), title, fill=(255, 80, 0))
            except Exception as e:
                logging.error(f"텍스트 그리기 오류: {str(e)}")
                # 완전 기본적인 방법
                draw.rectangle([0, 0, canvas_width, title_height], fill=(0, 0, 0))
                draw.text((10, 10), title, fill=(255, 80, 0))
            
            # 임시 파일로 저장
            title_img_path = os.path.join(tempfile.gettempdir(), f"title_{int(time.time())}.png")
            title_img.save(title_img_path)
            temp_files.append(title_img_path)
            
            # ImageClip으로 변환
            title_clip = ImageClip(title_img_path).set_duration(original_duration)
            title_clip = title_clip.set_position((0, 0))
            
            # 2. 비디오 영역 조정 (두 번째 칸)
            self.update_progress("비디오 영역 준비 중...", 20)
            # 원본 비디오 크기를 유지하면서 영역에 맞게 조정
            video_clip_resized = video_clip.resize(height=video_height)
            # 너비가 canvas_width보다 크면 너비에 맞게 조정
            if video_clip_resized.w > canvas_width:
                video_clip_resized = video_clip_resized.resize(width=canvas_width)
            
            # 중앙 정렬
            video_x = (canvas_width - video_clip_resized.w) // 2
            video_clip_resized = video_clip_resized.set_position((video_x, title_height))
            
            # 비디오 영역 배경
            video_bg = ColorClip(
                size=(canvas_width, video_height), 
                color=(0, 0, 0),  # 검은색 배경
                duration=original_duration
            )
            video_bg = video_bg.set_position((0, title_height))
            
            # 3. 자막 영역 생성 (세 번째 칸) - 비디오 설명으로 대체
            self.update_progress("비디오 설명 이미지 생성 중...", 70)
            
            description_font_size = 50  # 기본 글자 크기
            if len(description) > 30:
                description_font_size = 42
            if len(description) > 50:
                description_font_size = 36
            if len(description) > 70:
                description_font_size = 30
                
            # 여러 줄로 나누기 위해 텍스트 줄바꿈 적용
            wrapped_description = self._wrap_text(description, max_chars_per_line=30, font_size=description_font_size)
                
            # 세련된 설명 텍스트 영역 생성 (그라데이션 배경)
            description_img = Image.new('RGB', (canvas_width, subtitle_height), color=(0, 0, 0))
            draw = ImageDraw.Draw(description_img)
                
            # 세련된 그라데이션 배경 (첨부 이미지와 유사하게)
            for y in range(subtitle_height):
                # 상단에서 하단으로 색상 변화
                progress = y / subtitle_height
                # 어두운 배경 그라데이션
                r = int(5 + (15 * (1-progress)))
                g = int(5 + (10 * (1-progress)))
                b = int(15 + (30 * (1-progress)))
                draw.line([(0, y), (canvas_width, y)], fill=(r, g, b))
                
            try:
                if font_path:
                    description_font = ImageFont.truetype(font_path, description_font_size)
                        
                    # 비디오 설명 그리기 (흰색 텍스트, 그림자 효과)
                    description_shadow_color = (0, 0, 0)
                    description_text_color = (255, 255, 255)
                        
                    # 설명 텍스트 위치 계산 (중앙 정렬)
                    description_lines = wrapped_description.split('\n')
                    line_heights = []
                        
                    for line in description_lines:
                        if hasattr(description_font, 'getbbox'):
                            bbox = description_font.getbbox(line)
                            line_height = bbox[3] - bbox[1]
                        else:
                            # 폴백: 글자 크기에 따른 예상 높이
                            line_height = description_font_size * 1.2
                        line_heights.append(line_height)
                        
                    total_description_height = sum(line_heights) + (len(description_lines) - 1) * (description_font_size // 4)
                    current_y = (subtitle_height - total_description_height) // 2
                        
                    # 그림자 효과로 설명 텍스트 그리기
                    for i, line in enumerate(description_lines):
                        # 줄 너비 계산 (중앙 정렬)
                        try:
                            if hasattr(description_font, 'getbbox'):
                                text_width = description_font.getbbox(line)[2]
                            else:
                                text_width = description_font.getlength(line)
                        except:
                            # 폴백: 글자 수에 따른 예상 너비
                            text_width = len(line) * (description_font_size * 0.6)
                                
                        x_position = (canvas_width - text_width) // 2
                            
                        # 그림자 효과
                        for offset_x, offset_y in [(1, 1), (1, -1), (-1, 1), (-1, -1), (2, 0), (-2, 0), (0, 2), (0, -2)]:
                            draw.text((x_position + offset_x, current_y + offset_y), line, font=description_font, fill=description_shadow_color)
                                
                        # 메인 텍스트
                        draw.text((x_position, current_y), line, font=description_font, fill=description_text_color)
                            
                        # 다음 줄로 이동
                        current_y += line_heights[i] + (description_font_size // 4)
            except Exception as e:
                self.update_progress(f"비디오 설명 텍스트 그리기 실패: {str(e)}", None)
                # 에러 발생 시 기본 텍스트 표시
                draw.text((canvas_width//2, subtitle_height//2), "비디오 설명", fill=(255, 255, 255), anchor="mm")
                
            # 설명 이미지 저장
            description_img_path = os.path.join(self.temp_dir, f"description_img_{timestamp}.png")
            description_img.save(description_img_path)
            temp_files.append(description_img_path)
                
            # 설명 비디오 클립 생성
            description_clip = ImageClip(description_img_path).set_duration(original_duration)
                
            # 설명 비디오 클립 위치 설정
            description_clip = description_clip.set_position((0, title_height + video_height))
            
            # 4. 전체 캔버스 배경 생성 (검은색)
            self.update_progress("최종 비디오 조합 중...", 40)
            canvas = ColorClip(
                size=(canvas_width, canvas_height),
                color=(0, 0, 0),
                duration=original_duration
            )
            
            # 5. 모든 클립 합치기
            final_clip = CompositeVideoClip([
                canvas,          # 배경
                video_bg,        # 비디오 영역 배경
                video_clip_resized,  # 비디오
                title_clip,      # 제목
                description_clip    # 비디오 설명
            ])
            
            # 오디오 유지
            if video_clip.audio:
                final_clip = final_clip.set_audio(video_clip.audio)
            
            # 비디오 저장
            self.update_progress("템플릿 비디오 렌더링 중...", 50)
            final_clip.write_videofile(
                output_path,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                threads=2,
                logger=None,
                verbose=False,
                ffmpeg_params=[
                    "-preset", "medium",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-b:v", "2000k",
                    "-profile:v", "high",
                    "-level", "4.0"
                ]
            )
            
            # 임시 클립 닫기
            self.update_progress("리소스 정리 중...", 90)
            video_clip.close()
            final_clip.close()
            
            # 임시 파일 삭제
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logging.warning(f"임시 파일 삭제 실패: {str(e)}")
            
            self.update_progress("템플릿 비디오 생성 완료!", 100)
            return output_path
            
        except Exception as e:
            self.update_progress(f"템플릿 비디오 생성 실패: {str(e)}", None)
            logging.error(f"템플릿 비디오 생성 실패: {str(e)}")
            traceback.print_exc()
            
            # 임시 파일 정리 시도
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
                    
            return None
